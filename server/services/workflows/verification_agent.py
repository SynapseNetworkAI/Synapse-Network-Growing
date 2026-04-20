from __future__ import annotations

import json
import queue
import threading
from datetime import date, datetime
from typing import Any

from server.services.workflows.planner_provider import PlannerRequest, generate_planner_text


_VERIFICATION_PLAN_SYSTEM_PROMPT = """You are a verification planning agent in an agent-first delivery harness.
Read the requirement intent, acceptance contract, execution plan, execution evidence, changed files, activity, and raw output.
Return strict JSON only with this schema:
{
  "verification_plan": {
    "mode": "command_checks|evidence_review|none_required",
    "summary": "short explanation of how this run should be verified",
    "markdown": "Markdown verification plan for humans and agents",
    "required_commands": [
      {
        "required": true,
        "cwd": "absolute or project-relative working directory",
        "command": "non-mutating test/build/lint command",
        "timeout_sec": 300,
        "purpose": "why this command is required"
      }
    ],
    "checks": ["human-readable check or review step"],
    "evidence_to_inspect": ["changed files, screenshots, logs, raw output, or artifacts to inspect"],
    "expected_artifacts": ["artifact names or paths expected after verification"],
    "evidence_expectations": ["what evidence matters most"],
    "non_mutating_rules": ["verification must not modify source files"],
    "verdict_rubric": ["passed/failed/inconclusive rule"],
    "why_no_verification": "required only when mode is none_required"
  }
}

Rules:
- Design the final verification plan after implementation evidence exists.
- Use required_commands only for concrete, non-mutating checks the harness should execute as authoritative evidence.
- Prefer targeted tests, builds, lint, or automation over broad repo-wide sweeps.
- Do not mark execution-agent self-reported commands as authoritative unless the harness can replay them.
- Verification is non-mutating; fixes must happen in the same Execution Agent session as a self-repair turn.
- Use evidence_review for docs/config/governance changes where command execution is not the strongest proof.
- Use none_required only when no meaningful extra verification is possible and explain why.
- Keep output concise and machine-readable.
"""

_VERIFICATION_SYSTEM_PROMPT = """You are a verification verdict agent in an agent-first delivery harness.
Read the requirement intent, acceptance contract, execution plan, verification plan, harness command evidence, changed files, activity, and raw output.
Return strict JSON only with this schema:
{
  "verification_plan": {
    "mode": "command_checks|evidence_review|none_required",
    "summary": "short explanation of how this run should be verified",
    "markdown": "Markdown verification plan used for this verdict",
    "required_commands": [
      {"required": true, "cwd": "working directory", "command": "command", "timeout_sec": 300, "purpose": "why"}
    ],
    "checks": ["command or review step"],
    "evidence_to_inspect": ["evidence item"],
    "expected_artifacts": ["artifact item"],
    "evidence_expectations": ["what evidence matters most"],
    "non_mutating_rules": ["rule"],
    "verdict_rubric": ["rubric item"],
    "why_no_verification": "required only when mode is none_required"
  },
  "status": "passed|failed|needs_revision|inconclusive",
  "summary": "short verdict summary",
  "checks_run": ["short check summary"],
  "evidence_used": ["short evidence summary"],
  "reasoning": "brief explanation of why this verdict is correct",
  "suggested_next_action": "release_ready|continue_execution|route_to_human|revise_requirement",
  "resolution_recommendation": "continue_execution|retry_execution|create_followup_requirement|revise_requirement|route_to_human",
  "resolution_confidence": 0.0,
  "resolution_reason": "brief explanation of the recommended resolution path",
  "repair_guidance": "concrete guidance for the execution agent when status is failed or needs_revision",
  "failed_checks": ["failed check labels or commands"],
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
- Reuse the supplied verification_plan unless harness evidence proves it was insufficient.
- Treat harness command evidence as authoritative over execution-agent self-reported commands.
- Prefer command_checks only when the harness actually executed concrete commands or obvious automated checks.
- Use evidence_review for docs/config/governance changes where evidence is the right proof.
- Use none_required only when no extra verification is needed and explain why.
- Treat raw execution output, implementation summaries, command transcripts, and changed-file summaries as valid delivery evidence when they are specific and internally consistent.
- Do not require a separate artifact when the execution output already states what changed and which targeted checks passed, unless there is contradictory evidence.
- Do not ask for human manual review.
- Prefer continue_execution when the work still belongs to the current requirement.
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


def _normalize_required_command(item: Any, *, default_cwd: str | None = None) -> dict[str, Any] | None:
    if isinstance(item, str):
        command = item.strip()
        if not command:
            return None
        return {
            "required": True,
            "cwd": default_cwd,
            "command": command,
            "timeout_sec": 300,
            "purpose": "Replay command as authoritative harness evidence.",
        }
    if not isinstance(item, dict):
        return None
    command = str(item.get("command") or "").strip()
    if not command:
        return None
    timeout_raw = item.get("timeout_sec")
    try:
        timeout_sec = int(timeout_raw)
    except (TypeError, ValueError):
        timeout_sec = 300
    timeout_sec = max(1, min(timeout_sec, 3600))
    cwd = str(item.get("cwd") or default_cwd or "").strip() or None
    return {
        "required": bool(item.get("required", True)),
        "cwd": cwd,
        "command": command,
        "timeout_sec": timeout_sec,
        "purpose": str(item.get("purpose") or "Run authoritative verification command.").strip(),
    }


def _verification_plan_markdown(plan: dict[str, Any]) -> str:
    existing = str(plan.get("markdown") or "").strip()
    if existing:
        return existing
    lines: list[str] = ["# Verification Plan", ""]
    summary = str(plan.get("summary") or "").strip()
    if summary:
        lines.extend(["## Summary", "", summary, ""])
    commands = [item for item in plan.get("required_commands") or [] if isinstance(item, dict)]
    if commands:
        lines.extend(["## Required Commands", ""])
        for item in commands:
            command = str(item.get("command") or "").strip()
            cwd = str(item.get("cwd") or "").strip() or "."
            purpose = str(item.get("purpose") or "").strip()
            timeout = item.get("timeout_sec") or 300
            lines.append(f"- required: {str(bool(item.get('required', True))).lower()}")
            lines.append(f"  cwd: `{cwd}`")
            lines.append(f"  command: `{command}`")
            lines.append(f"  timeout_sec: {timeout}")
            if purpose:
                lines.append(f"  purpose: {purpose}")
        lines.append("")
    sections = [
        ("Required Checks", plan.get("checks") or []),
        ("Evidence To Inspect", plan.get("evidence_to_inspect") or []),
        ("Expected Artifacts", plan.get("expected_artifacts") or []),
        ("Non-Mutating Rules", plan.get("non_mutating_rules") or []),
        ("Verdict Rubric", plan.get("verdict_rubric") or []),
    ]
    for title, values in sections:
        rows = [str(item).strip() for item in values if str(item).strip()]
        if rows:
            lines.extend([f"## {title}", "", *[f"- {item}" for item in rows], ""])
    why_no_verification = str(plan.get("why_no_verification") or "").strip()
    if why_no_verification:
        lines.extend(["## Why No Verification", "", why_no_verification, ""])
    return "\n".join(lines).strip()


def _normalize_verification_plan(plan: Any, *, fallback: dict[str, Any] | None = None, default_cwd: str | None = None) -> dict[str, Any]:
    source = plan if isinstance(plan, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    raw_commands = source.get("required_commands")
    if raw_commands is None:
        raw_commands = source.get("commands")
    required_commands = [
        command
        for command in (_normalize_required_command(item, default_cwd=default_cwd) for item in raw_commands or [])
        if command is not None
    ]
    mode = str(source.get("mode") or fallback.get("mode") or "").strip()
    if mode not in {"command_checks", "evidence_review", "none_required"}:
        mode = "command_checks" if required_commands else "evidence_review"
    normalized = {
        "mode": mode,
        "summary": str(source.get("summary") or fallback.get("summary") or "").strip(),
        "markdown": str(source.get("markdown") or "").strip(),
        "required_commands": required_commands,
        "checks": [str(item).strip() for item in source.get("checks") or fallback.get("checks") or [] if str(item).strip()],
        "evidence_to_inspect": [str(item).strip() for item in source.get("evidence_to_inspect") or fallback.get("evidence_to_inspect") or [] if str(item).strip()],
        "expected_artifacts": [str(item).strip() for item in source.get("expected_artifacts") or fallback.get("expected_artifacts") or [] if str(item).strip()],
        "evidence_expectations": [str(item).strip() for item in source.get("evidence_expectations") or fallback.get("evidence_expectations") or [] if str(item).strip()],
        "non_mutating_rules": [str(item).strip() for item in source.get("non_mutating_rules") or fallback.get("non_mutating_rules") or [] if str(item).strip()],
        "verdict_rubric": [str(item).strip() for item in source.get("verdict_rubric") or fallback.get("verdict_rubric") or [] if str(item).strip()],
        "why_no_verification": str(source.get("why_no_verification") or fallback.get("why_no_verification") or "").strip() or None,
    }
    if not normalized["checks"] and required_commands:
        normalized["checks"] = [str(item["command"]) for item in required_commands]
    if not normalized["summary"]:
        normalized["summary"] = (
            "Replay required commands as authoritative harness evidence."
            if required_commands
            else "Review changed files, raw execution output, and summarized implementation evidence."
        )
    if not normalized["evidence_expectations"]:
        normalized["evidence_expectations"] = [
            "Harness command evidence and changed files should satisfy the acceptance contract."
        ]
    if not normalized["non_mutating_rules"]:
        normalized["non_mutating_rules"] = [
            "Verification commands must not intentionally modify source files; fixes happen in the same Execution Agent session as a self-repair turn."
        ]
    if not normalized["verdict_rubric"]:
        normalized["verdict_rubric"] = [
            "passed only when acceptance is satisfied by harness evidence",
            "failed when required command evidence fails or scope is violated",
            "inconclusive when evidence is too thin or risky",
        ]
    normalized["markdown"] = _verification_plan_markdown(normalized)
    return normalized


def _deterministic_verification_plan(payload: dict[str, Any]) -> dict[str, Any]:
    raw_output = str(payload.get("raw_task_output") or "").strip()
    changed_files = payload.get("changed_files") or []
    commands = [str(item).strip() for item in payload.get("commands_run") or [] if str(item).strip()]
    requirement = payload.get("requirement") or {}
    default_cwd = str(requirement.get("target_project_path") or "").strip() or None
    acceptance_contract = payload.get("acceptance_contract") or {}
    contract_checks = acceptance_contract.get("verification_checks") or []
    expectations = [
        str(item.get("label") or "").strip()
        for item in contract_checks
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    required_commands = [
        _normalize_required_command(
            {
                "command": command,
                "cwd": default_cwd,
                "timeout_sec": 300,
                "purpose": "Replay execution-agent reported command through the harness as authoritative evidence.",
            },
            default_cwd=default_cwd,
        )
        for command in commands
    ]
    required_commands = [item for item in required_commands if item is not None]
    if required_commands:
        plan = {
            "mode": "command_checks",
            "summary": "Replay concrete commands reported by the execution agent through the harness.",
            "required_commands": required_commands,
            "checks": [str(item["command"]) for item in required_commands],
            "evidence_to_inspect": ["Harness command logs", "Changed files", "Raw execution output"],
            "expected_artifacts": ["verification_evidence.md", "command log files"],
            "evidence_expectations": expectations,
        }
    elif changed_files or raw_output:
        plan = {
            "mode": "evidence_review",
            "summary": "Verify the outcome by reviewing changed files, raw execution output, and summarized implementation evidence.",
            "required_commands": [],
            "checks": [],
            "evidence_to_inspect": ["Changed files", "Raw execution output"],
            "expected_artifacts": ["verification_evidence.md"],
            "evidence_expectations": expectations
            or ["Changed files should align with the requirement and raw output should describe the delivered outcome."],
        }
    else:
        plan = {
            "mode": "none_required",
            "summary": "No meaningful automated verification signal is available yet.",
            "required_commands": [],
            "checks": [],
            "evidence_to_inspect": [],
            "expected_artifacts": [],
            "evidence_expectations": expectations,
            "why_no_verification": "Execution did not produce enough concrete code or runtime evidence to design a stronger verification path.",
        }
    return _normalize_verification_plan(plan, default_cwd=default_cwd)


def _provider_verification_plan(payload: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    prompt = json.dumps(_json_ready(payload), ensure_ascii=False, indent=2)
    try:
        response = generate_planner_text(PlannerRequest(
            prompt=prompt,
            system_prompt=_VERIFICATION_PLAN_SYSTEM_PROMPT,
        ))
        result = json.loads(str(response.text or "").strip())
        if not isinstance(result, dict):
            raise ValueError("verification plan result must be an object")
        requirement = payload.get("requirement") or {}
        default_cwd = str(requirement.get("target_project_path") or "").strip() or None
        return _normalize_verification_plan(result.get("verification_plan"), fallback=baseline, default_cwd=default_cwd)
    except Exception:
        return baseline


def generate_verification_plan(payload: dict[str, Any], *, skip_provider: bool = False) -> dict[str, Any]:
    baseline = _deterministic_verification_plan(payload)
    if skip_provider:
        return baseline
    result_queue: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)

    def _runner() -> None:
        result_queue.put(_provider_verification_plan(payload, baseline))

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    try:
        return result_queue.get(timeout=_VERIFICATION_PROVIDER_WALL_TIMEOUT_SECONDS)
    except queue.Empty:
        return baseline


def _deterministic_verification_result(payload: dict[str, Any]) -> dict[str, Any]:
    checks = payload.get("check_results") or []
    raw_output = str(payload.get("raw_task_output") or "").strip()
    changed_files = payload.get("changed_files") or []
    acceptance_contract = payload.get("acceptance_contract") or {}
    contract_checks = acceptance_contract.get("verification_checks") or []
    verification_plan = _normalize_verification_plan(
        payload.get("verification_plan") or {},
        fallback=_deterministic_verification_plan(payload),
        default_cwd=str((payload.get("requirement") or {}).get("target_project_path") or "").strip() or None,
    )
    failed_checks = [item for item in checks if str(item.get("status") or "") == "failed"]
    passed_checks = [item for item in checks if str(item.get("status") or "") == "passed"]
    explicit_commands = [str(item.get("command") or "").strip() for item in checks if str(item.get("command") or "").strip()]
    evidence_expectations = [
        str(item.get("label") or "").strip()
        for item in contract_checks
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    if evidence_expectations and not verification_plan.get("evidence_expectations"):
        verification_plan["evidence_expectations"] = evidence_expectations
        verification_plan["markdown"] = _verification_plan_markdown(verification_plan)
    if failed_checks:
        status = "failed"
        next_action = "continue_execution"
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
        "resolution_recommendation": "continue_execution" if status in {"failed", "needs_revision"} else "revise_requirement" if status == "inconclusive" else None,
        "resolution_confidence": 0.7 if status in {"failed", "needs_revision"} else 0.58 if status == "inconclusive" else 0.8,
        "resolution_reason": summary,
        "repair_guidance": "Continue in the same execution session. Fix only the gap shown by failed checks and rerun targeted evidence commands." if status in {"failed", "needs_revision"} else "",
        "failed_checks": [str(item.get("label") or item.get("command") or "failed check").strip() for item in failed_checks],
        "followup_requirement_payload": {},
        "verification_agent_id": "verification_agent",
        "verification_agent_label": "Verification Agent",
    }


def _inconclusive_verification_result(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    baseline = _deterministic_verification_result(payload)
    return {
        **baseline,
        "status": "inconclusive",
        "summary": reason,
        "reasoning": reason,
        "suggested_next_action": "route_to_human",
        "resolution_recommendation": "route_to_human",
        "resolution_confidence": 0.5,
        "resolution_reason": reason,
        "repair_guidance": "",
        "failed_checks": [],
    }


def _provider_verification_result(payload: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
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
        requirement = payload.get("requirement") or {}
        default_cwd = str(requirement.get("target_project_path") or "").strip() or None
        normalized_plan = _normalize_verification_plan(
            plan,
            fallback=payload.get("verification_plan") or baseline.get("verification_plan") or {},
            default_cwd=default_cwd,
        )
        normalized = {
            "verification_plan": normalized_plan,
            "status": str(result.get("status") or "inconclusive").strip() or "inconclusive",
            "summary": str(result.get("summary") or "").strip(),
            "checks_run": [str(item).strip() for item in result.get("checks_run") or [] if str(item).strip()],
            "evidence_used": [str(item).strip() for item in result.get("evidence_used") or [] if str(item).strip()],
            "reasoning": str(result.get("reasoning") or "").strip(),
            "suggested_next_action": str(result.get("suggested_next_action") or "revise_requirement").strip() or "revise_requirement",
            "resolution_recommendation": str(result.get("resolution_recommendation") or "").strip() or None,
            "resolution_confidence": float(result.get("resolution_confidence")) if result.get("resolution_confidence") is not None else None,
            "resolution_reason": str(result.get("resolution_reason") or "").strip() or None,
            "repair_guidance": str(result.get("repair_guidance") or "").strip(),
            "failed_checks": [str(item).strip() for item in result.get("failed_checks") or [] if str(item).strip()],
            "followup_requirement_payload": result.get("followup_requirement_payload") if isinstance(result.get("followup_requirement_payload"), dict) else {},
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        }
        if normalized["status"] not in {"passed", "failed", "needs_revision", "inconclusive"}:
            normalized["status"] = "inconclusive"
        if normalized["suggested_next_action"] not in {"release_ready", "continue_execution", "retry_execution", "route_to_human", "revise_requirement"}:
            normalized["suggested_next_action"] = "revise_requirement"
        if normalized["suggested_next_action"] == "retry_execution":
            normalized["suggested_next_action"] = "continue_execution"
        if normalized["resolution_recommendation"] not in {
            "continue_execution",
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
            normalized["verification_plan"] = dict(baseline["verification_plan"])
        normalized["verification_plan"] = _normalize_verification_plan(
            normalized["verification_plan"],
            fallback=baseline["verification_plan"],
            default_cwd=default_cwd,
        )
        if not normalized["summary"]:
            normalized["summary"] = baseline["summary"]
        if not normalized["reasoning"]:
            normalized["reasoning"] = normalized["summary"]
        if not normalized["resolution_recommendation"]:
            fallback_recommendation = baseline.get("resolution_recommendation")
            normalized["resolution_recommendation"] = (
                str(fallback_recommendation).strip() if fallback_recommendation is not None else None
            )
        if normalized["resolution_confidence"] is None:
            normalized["resolution_confidence"] = float(baseline["resolution_confidence"])
        if not normalized["resolution_reason"]:
            normalized["resolution_reason"] = str(baseline["resolution_reason"])
        if not normalized["repair_guidance"]:
            normalized["repair_guidance"] = str(baseline.get("repair_guidance") or "")
        if not normalized["failed_checks"]:
            normalized["failed_checks"] = list(baseline.get("failed_checks") or [])
        return normalized
    except Exception:
        return _inconclusive_verification_result(payload, "Verification agent output was invalid; route to human review.")


def verify_with_agent(payload: dict[str, Any], *, skip_provider: bool = False) -> dict[str, Any]:
    baseline = _deterministic_verification_result(payload)
    if skip_provider:
        return baseline
    result_queue: "queue.Queue[dict[str, Any]]" = queue.Queue(maxsize=1)

    def _runner() -> None:
        result_queue.put(_provider_verification_result(payload, baseline))

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    try:
        return result_queue.get(timeout=_VERIFICATION_PROVIDER_WALL_TIMEOUT_SECONDS)
    except queue.Empty:
        return _inconclusive_verification_result(payload, "Verification agent timed out; route to human review.")
