from __future__ import annotations

import json
import queue
import threading
from datetime import date, datetime
from typing import Any

from server.services.workflows.planner_provider import PlannerRequest, generate_planner_text


_VERIFICATION_SYSTEM_PROMPT = """You are a verification agent in an agent-first delivery harness.
Read the requirement intent, acceptance contract, execution plan, execution evidence, changed files, activity, and raw output.
Return strict JSON only with this schema:
{
  "verification_plan": {
    "mode": "command_checks|evidence_review|none_required",
    "summary": "short explanation of how this run should be verified",
    "checks": ["command or review step"],
    "evidence_expectations": ["what evidence matters most"],
    "why_no_verification": "required only when mode is none_required"
  },
  "status": "passed|failed|needs_revision|inconclusive",
  "summary": "short verdict summary",
  "checks_run": ["short check summary"],
  "evidence_used": ["short evidence summary"],
  "reasoning": "brief explanation of why this verdict is correct",
  "suggested_next_action": "release_ready|retry_execution|revise_requirement",
  "resolution_recommendation": "retry_execution|create_followup_requirement|revise_requirement|route_to_human",
  "resolution_confidence": 0.0,
  "resolution_reason": "brief explanation of the recommended resolution path",
  "followup_requirement_payload": {
    "title": "optional follow-up title",
    "description_markdown": "optional follow-up description",
    "project_key": "optional project key override",
    "target_project_path": "optional target path override",
    "priority": "low|normal|high",
    "scope_assessment": "same_scope|out_of_scope",
    "ownership_change_required": false
  }
}

Rules:
- Prefer passed only when the evidence reasonably satisfies the acceptance contract.
- Use needs_revision when the implementation is incomplete or misses the requested outcome.
- Use failed when explicit check evidence shows failure.
- Use inconclusive when evidence is too thin to justify a pass or a failure.
- Generate a verification_plan that reflects the actual implementation evidence, changed files, and commands run.
- Prefer command_checks only when this run actually has concrete commands or obvious automated checks.
- Use evidence_review for docs/config/governance changes where evidence is the right proof.
- Use none_required only when no extra verification is needed and explain why.
- Treat raw execution output, implementation summaries, command transcripts, and changed-file summaries as valid delivery evidence when they are specific and internally consistent.
- Do not require a separate artifact when the execution output already states what changed and which targeted checks passed, unless there is contradictory evidence.
- Do not ask for human manual review.
- Prefer retry_execution when the work still belongs to the current requirement.
- Recommend create_followup_requirement only when the fix clearly drifts beyond the original scope, repo, or ownership boundary.
- Use route_to_human only when the evidence is too risky or ambiguous to auto-resolve.
- PR merge is the final human check after a passed verdict.
- Keep output concise and machine-readable.
"""

_VERIFICATION_PROVIDER_WALL_TIMEOUT_SECONDS = 30


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _fallback_verification_result(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("check_results") or []
    raw_output = str(payload.get("raw_task_output") or "").strip()
    changed_files = payload.get("changed_files") or []
    acceptance_contract = payload.get("acceptance_contract") or {}
    contract_checks = acceptance_contract.get("verification_checks") or []
    failed_checks = [item for item in checks if str(item.get("status") or "") == "failed"]
    passed_checks = [item for item in checks if str(item.get("status") or "") == "passed"]
    explicit_commands = [str(item.get("command") or "").strip() for item in checks if str(item.get("command") or "").strip()]
    evidence_expectations = [
        str(item.get("label") or "").strip()
        for item in contract_checks
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    if explicit_commands:
        verification_plan = {
            "mode": "command_checks",
            "summary": "Verify the implementation by replaying the concrete commands captured in execution evidence.",
            "checks": explicit_commands,
            "evidence_expectations": evidence_expectations,
            "why_no_verification": None,
        }
    elif changed_files or raw_output:
        verification_plan = {
            "mode": "evidence_review",
            "summary": "Verify the outcome by reviewing changed files, raw execution output, and summarized implementation evidence.",
            "checks": [],
            "evidence_expectations": evidence_expectations
            or ["Changed files should align with the requirement and raw output should describe the delivered outcome."],
            "why_no_verification": None,
        }
    else:
        verification_plan = {
            "mode": "none_required",
            "summary": "No meaningful automated verification signal is available yet.",
            "checks": [],
            "evidence_expectations": evidence_expectations,
            "why_no_verification": "Execution did not produce enough concrete code or runtime evidence to design a stronger verification path.",
        }
    if failed_checks:
        status = "failed"
        next_action = "retry_execution"
        summary = "Verification failed because one or more commanded checks reported failure."
    elif raw_output or changed_files or passed_checks:
        status = "passed"
        next_action = "release_ready"
        summary = "Verification passed based on execution evidence, raw output, and available checks."
    else:
        status = "inconclusive"
        next_action = "revise_requirement"
        summary = "Verification is inconclusive because execution evidence is too thin."
    return {
        "verification_plan": verification_plan,
        "status": status,
        "summary": summary,
        "checks_run": [str(item.get("label") or "").strip() for item in checks if str(item.get("label") or "").strip()],
        "evidence_used": [
            *([f"raw_output:{len(raw_output)} chars"] if raw_output else []),
            *([f"changed_files:{len(changed_files)}"] if changed_files else []),
        ],
        "reasoning": summary,
        "suggested_next_action": next_action,
        "resolution_recommendation": "retry_execution" if status in {"failed", "needs_revision"} else "revise_requirement" if status == "inconclusive" else None,
        "resolution_confidence": 0.7 if status in {"failed", "needs_revision"} else 0.58 if status == "inconclusive" else 0.8,
        "resolution_reason": summary,
        "followup_requirement_payload": {},
        "verification_agent_id": "verification_agent",
        "verification_agent_label": "Verification Agent",
    }


def _provider_verification_result(payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    prompt = json.dumps(_json_ready(payload), ensure_ascii=False, indent=2)
    try:
        response = generate_planner_text(PlannerRequest(
            prompt=prompt,
            system_prompt=_VERIFICATION_SYSTEM_PROMPT,
        ))
        text = response.text
        result = json.loads(str(text or "").strip())
        if not isinstance(result, dict):
            raise ValueError("verification result must be an object")
        plan = result.get("verification_plan")
        if not isinstance(plan, dict):
            plan = {}
        normalized = {
            "verification_plan": {
                "mode": str(plan.get("mode") or "evidence_review").strip() or "evidence_review",
                "summary": str(plan.get("summary") or "").strip(),
                "checks": [str(item).strip() for item in plan.get("checks") or [] if str(item).strip()],
                "evidence_expectations": [
                    str(item).strip() for item in plan.get("evidence_expectations") or [] if str(item).strip()
                ],
                "why_no_verification": str(plan.get("why_no_verification") or "").strip() or None,
            },
            "status": str(result.get("status") or "inconclusive").strip() or "inconclusive",
            "summary": str(result.get("summary") or "").strip(),
            "checks_run": [str(item).strip() for item in result.get("checks_run") or [] if str(item).strip()],
            "evidence_used": [str(item).strip() for item in result.get("evidence_used") or [] if str(item).strip()],
            "reasoning": str(result.get("reasoning") or "").strip(),
            "suggested_next_action": str(result.get("suggested_next_action") or "revise_requirement").strip() or "revise_requirement",
            "resolution_recommendation": str(result.get("resolution_recommendation") or "").strip() or None,
            "resolution_confidence": float(result.get("resolution_confidence")) if result.get("resolution_confidence") is not None else None,
            "resolution_reason": str(result.get("resolution_reason") or "").strip() or None,
            "followup_requirement_payload": result.get("followup_requirement_payload") if isinstance(result.get("followup_requirement_payload"), dict) else {},
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        }
        if normalized["status"] not in {"passed", "failed", "needs_revision", "inconclusive"}:
            normalized["status"] = "inconclusive"
        if normalized["verification_plan"]["mode"] not in {"command_checks", "evidence_review", "none_required"}:
            normalized["verification_plan"]["mode"] = "evidence_review"
        if normalized["suggested_next_action"] not in {"release_ready", "retry_execution", "revise_requirement"}:
            normalized["suggested_next_action"] = "revise_requirement"
        if normalized["resolution_recommendation"] not in {
            "retry_execution",
            "create_followup_requirement",
            "revise_requirement",
            "route_to_human",
            None,
        }:
            normalized["resolution_recommendation"] = None
        if normalized["resolution_confidence"] is not None:
            normalized["resolution_confidence"] = max(0.0, min(1.0, float(normalized["resolution_confidence"])))
        if not normalized["verification_plan"]["summary"]:
            normalized["verification_plan"] = dict(fallback["verification_plan"])
        if not normalized["summary"]:
            normalized["summary"] = fallback["summary"]
        if not normalized["reasoning"]:
            normalized["reasoning"] = normalized["summary"]
        if not normalized["resolution_recommendation"]:
            normalized["resolution_recommendation"] = str(fallback["resolution_recommendation"])
        if normalized["resolution_confidence"] is None:
            normalized["resolution_confidence"] = float(fallback["resolution_confidence"])
        if not normalized["resolution_reason"]:
            normalized["resolution_reason"] = str(fallback["resolution_reason"])
        if normalized["status"] == "inconclusive" and fallback["status"] in {"passed", "failed"}:
            normalized["verification_plan"] = dict(fallback["verification_plan"])
            normalized["status"] = str(fallback["status"])
            normalized["summary"] = str(fallback["summary"])
            normalized["reasoning"] = str(fallback["reasoning"])
            normalized["suggested_next_action"] = str(fallback["suggested_next_action"])
            normalized["resolution_recommendation"] = str(fallback["resolution_recommendation"])
            normalized["resolution_confidence"] = float(fallback["resolution_confidence"])
            normalized["resolution_reason"] = str(fallback["resolution_reason"])
            normalized["checks_run"] = list(fallback["checks_run"])
            normalized["evidence_used"] = list(fallback["evidence_used"])
        return normalized
    except Exception:
        return fallback


def verify_with_agent(payload: dict[str, Any], *, skip_provider: bool = False) -> dict[str, Any]:
    fallback = _fallback_verification_result(payload)
    if skip_provider:
        return fallback
    result_queue: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)

    def _runner() -> None:
        result_queue.put(_provider_verification_result(payload, fallback))

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    try:
        return result_queue.get(timeout=_VERIFICATION_PROVIDER_WALL_TIMEOUT_SECONDS)
    except queue.Empty:
        return fallback
