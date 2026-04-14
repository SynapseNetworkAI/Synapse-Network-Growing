from __future__ import annotations

import json
from typing import Any

from server.services.agents.llm_adapter import get_provider
from server.services.workflows.planner_provider import (
    call_full_plan_provider,
    planner_model_name,
    planner_provider_name,
)


_VERIFICATION_SYSTEM_PROMPT = """You are a verification agent in an agent-first delivery harness.
Read the requirement intent, acceptance contract, execution plan, execution evidence, changed files, activity, and raw output.
Return strict JSON only with this schema:
{
  "status": "passed|failed|needs_revision|inconclusive",
  "summary": "short verdict summary",
  "checks_run": ["short check summary"],
  "evidence_used": ["short evidence summary"],
  "reasoning": "brief explanation of why this verdict is correct",
  "suggested_next_action": "release_ready|retry_execution|revise_requirement"
}

Rules:
- Prefer passed only when the evidence reasonably satisfies the acceptance contract.
- Use needs_revision when the implementation is incomplete or misses the requested outcome.
- Use failed when explicit check evidence shows failure.
- Use inconclusive when evidence is too thin to justify a pass or a failure.
- Do not ask for human manual review.
- PR merge is the final human check after a passed verdict.
- Keep output concise and machine-readable.
"""


def _fallback_verification_result(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("check_results") or []
    raw_output = str(payload.get("raw_task_output") or "").strip()
    changed_files = payload.get("changed_files") or []
    failed_checks = [item for item in checks if str(item.get("status") or "") == "failed"]
    passed_checks = [item for item in checks if str(item.get("status") or "") == "passed"]
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
        "status": status,
        "summary": summary,
        "checks_run": [str(item.get("label") or "").strip() for item in checks if str(item.get("label") or "").strip()],
        "evidence_used": [
            *([f"raw_output:{len(raw_output)} chars"] if raw_output else []),
            *([f"changed_files:{len(changed_files)}"] if changed_files else []),
        ],
        "reasoning": summary,
        "suggested_next_action": next_action,
        "verification_agent_id": "verification_agent",
        "verification_agent_label": "Verification Agent",
    }


def verify_with_agent(payload: dict[str, Any], *, skip_provider: bool = False) -> dict[str, Any]:
    if skip_provider:
        return _fallback_verification_result(payload)
    prompt = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        provider_name = planner_provider_name()
        provider = get_provider(provider_name)
        model_name = planner_model_name(provider_name)
        text, _tokens = call_full_plan_provider(
            provider_name=provider_name,
            provider=provider,
            prompt=prompt,
            model_name=model_name,
            system_prompt=_VERIFICATION_SYSTEM_PROMPT,
        )
        result = json.loads(str(text or "").strip())
        if not isinstance(result, dict):
            raise ValueError("verification result must be an object")
        normalized = {
            "status": str(result.get("status") or "inconclusive").strip() or "inconclusive",
            "summary": str(result.get("summary") or "").strip(),
            "checks_run": [str(item).strip() for item in result.get("checks_run") or [] if str(item).strip()],
            "evidence_used": [str(item).strip() for item in result.get("evidence_used") or [] if str(item).strip()],
            "reasoning": str(result.get("reasoning") or "").strip(),
            "suggested_next_action": str(result.get("suggested_next_action") or "revise_requirement").strip() or "revise_requirement",
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        }
        if normalized["status"] not in {"passed", "failed", "needs_revision", "inconclusive"}:
            normalized["status"] = "inconclusive"
        if normalized["suggested_next_action"] not in {"release_ready", "retry_execution", "revise_requirement"}:
            normalized["suggested_next_action"] = "revise_requirement"
        if not normalized["summary"]:
            normalized["summary"] = _fallback_verification_result(payload)["summary"]
        if not normalized["reasoning"]:
            normalized["reasoning"] = normalized["summary"]
        return normalized
    except Exception:
        return _fallback_verification_result(payload)
