from __future__ import annotations

"""Planner Agent bridge for Goal Markdown PRD -> evidence-bound candidates."""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from server import config
from server.database import PlanningGoalRow
from server.services.workflows.declarative import built_in_workflow_specs
from server.services.workflows.planner_provider import PlannerRequest, generate_planner_text


MAX_REPAIR_ATTEMPTS = 2


class PlannerAgentError(ValueError):
    """Raised when the Planner Agent cannot produce a safe candidate payload."""

    def __init__(
        self,
        message: str,
        *,
        raw_output: str = "",
        metadata: dict[str, Any] | None = None,
        partial_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.metadata = metadata or {}
        self.partial_payload = partial_payload or {}


class PlannerAgentRepairableError(PlannerAgentError):
    """Formatting or required-field error that can be retried with feedback."""


@dataclass
class PlannerAgentCandidate:
    title: str
    description_markdown: str
    workflow_key: str
    priority: str
    risk_level: str
    confidence: float
    rationale: str
    acceptance_contract: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


def synthesize_candidate_for_goal(
    *,
    manifest_payload: Mapping[str, Any],
    goal: PlanningGoalRow,
    project_key: str,
    default_workflow_key: str,
    acceptance_contract: dict[str, Any] | None = None,
) -> PlannerAgentCandidate:
    """Return a candidate proposal for one goal.

    If the goal already has a governed acceptance contract (for example GoalB
    dogfood), we avoid a model call and simply wrap it in the Planner Agent
    envelope. Otherwise, the configured planner backend must synthesize a
    strict JSON candidate from the Goal Markdown PRD.
    """

    workflow_keys = set(built_in_workflow_specs().keys())
    if acceptance_contract is not None:
        workflow_key = _ensure_workflow_key(str(goal.workflow_key or default_workflow_key), workflow_keys)
        title = str(goal.title or goal.goal_key or "Advance goal").strip()
        intent = str(goal.intent_markdown or title).strip()
        return PlannerAgentCandidate(
            title=f"Advance goal: {title[:72]}",
            description_markdown=_description_from_goal(goal, intent),
            workflow_key=workflow_key,
            priority=str(goal.priority or "normal"),
            risk_level=str(goal.risk_level or "normal"),
            confidence=0.72,
            rationale="Planner Agent reused the goal's governed acceptance contract.",
            acceptance_contract=acceptance_contract,
            metadata={
                "generated_by": "planner_agent_v1",
                "planner_agent_mode": "prevalidated_goal_contract",
                "planner_repair_attempts": 0,
            },
        )

    prompt = _planner_prompt(
        manifest_payload=manifest_payload,
        goal=goal,
        project_key=project_key,
        default_workflow_key=default_workflow_key,
        workflow_keys=workflow_keys,
    )
    system_prompt = _planner_system_prompt(workflow_keys)
    metadata: dict[str, Any] = {
        "generated_by": "planner_agent_v1",
        "planner_repair_attempts": 0,
        "planner_validation_errors": [],
    }
    raw_output = ""
    last_error = ""
    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        request_prompt = prompt if attempt == 0 else _repair_prompt(raw_output=raw_output, error=last_error)
        try:
            response = generate_planner_text(
                PlannerRequest(
                    prompt=request_prompt,
                    system_prompt=system_prompt,
                    cwd=config.PROJECT_ROOT,
                    output_path=config.PROJECT_ROOT / "runtime" / "plans" / f"goal-{int(goal.id)}-planner-agent.json",
                    metadata=metadata,
                )
            )
            raw_output = str(response.text or "")
            metadata["planner_agent_backend"] = response.backend
            metadata["planner_agent_model"] = response.model
            parsed = _parse_json_payload(raw_output)
            candidate = _normalize_candidate(parsed, goal=goal, workflow_keys=workflow_keys)
            candidate.metadata = {
                **metadata,
                **candidate.metadata,
                "planner_raw_output_excerpt": raw_output[:1000],
                "planner_repair_attempts": attempt,
            }
            return candidate
        except PlannerAgentRepairableError as exc:
            last_error = str(exc)
            metadata["planner_repair_attempts"] = attempt + 1
            metadata.setdefault("planner_validation_errors", []).append(last_error)
            if attempt >= MAX_REPAIR_ATTEMPTS:
                raise PlannerAgentError(
                    f"Planner Agent could not produce valid candidate JSON after {MAX_REPAIR_ATTEMPTS} repair attempts: {last_error}",
                    raw_output=raw_output or exc.raw_output,
                    metadata=metadata,
                    partial_payload=exc.partial_payload,
                ) from exc
        except PlannerAgentError as exc:
            exc.metadata.update(metadata)
            raise
        except Exception as exc:
            last_error = str(exc)
            metadata.setdefault("planner_validation_errors", []).append(last_error)
            if attempt >= MAX_REPAIR_ATTEMPTS:
                raise PlannerAgentError(
                    f"Planner Agent provider failed after {MAX_REPAIR_ATTEMPTS} repair attempts: {last_error}",
                    raw_output=raw_output,
                    metadata=metadata,
                ) from exc
            metadata["planner_repair_attempts"] = attempt + 1

    raise PlannerAgentError("Planner Agent failed unexpectedly.", metadata=metadata, raw_output=raw_output)


def failed_candidate_from_planner_error(
    *,
    error: PlannerAgentError,
    goal: PlanningGoalRow,
    workflow_key: str,
    project_id: int | None,
    project_key: str | None,
    manifest_id: int,
    fingerprint: str,
) -> dict[str, Any]:
    partial = error.partial_payload if isinstance(error.partial_payload, dict) else {}
    title = str(partial.get("title") or goal.title or goal.goal_key or "Planner Agent failed").strip()
    description = str(partial.get("description_markdown") or "").strip() or (
        f"Planner Agent could not synthesize an evidence-bound candidate for goal `{goal.goal_key}`.\n\n"
        f"Error: {str(error)}"
    )
    metadata = {
        **dict(error.metadata or {}),
        "generated_by": "planner_agent_v1",
        "planner_agent_error": str(error),
        "planner_raw_output_excerpt": str(error.raw_output or "")[:1000],
    }
    return {
        "manifest_id": manifest_id,
        "goal_key": str(goal.goal_key or ""),
        "candidate_fingerprint": fingerprint,
        "title": title,
        "description_markdown": description,
        "project_id": project_id,
        "project_key": project_key,
        "workflow_key": str(partial.get("workflow_key") or workflow_key),
        "priority": str(partial.get("priority") or goal.priority or "normal"),
        "risk_level": str(partial.get("risk_level") or goal.risk_level or "normal"),
        "confidence": float(partial.get("confidence") or 0.0),
        "rationale": "Planner Agent failed before producing a safe candidate.",
        "expected_evidence_json": "[]",
        "status": "pending",
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
    }


def _description_from_goal(goal: PlanningGoalRow, intent: str) -> str:
    return (
        f"## Goal\n{intent}\n\n"
        f"## Success Metric\n{str(goal.success_metric or 'Define concrete evidence before execution.')}\n\n"
        "## Planner Rationale\nThis candidate was generated from the active Operating Manifest by Planner Agent v1."
    )


def _planner_system_prompt(workflow_keys: set[str]) -> str:
    workflow_enum = ", ".join(sorted(workflow_keys))
    return f"""You are the Synapse Growing Planner Agent.

Return only strict JSON. Do not wrap it in Markdown fences.

Your job is to convert one Goal Markdown PRD into one safe RequirementCandidate.

Allowed workflow_key enum: {workflow_enum}

Workflow descriptions:
- agent_self_repair: Synapse-Network-Growing self-repair, linting, contracts, UI/docs, PR-only operational work.
- gateway_reliability_repair: Gateway reliability/runtime drift repair work.

Rules:
- Do not invent workflow keys.
- Do not include high-risk commands.
- Acceptance must validate the business outcome, not just engine state.
- Every execution_acceptance_steps item needs title, expected_result, and required_commands or required_evidence_types or required_db_lineage.
- Prefer safe command evidence such as pytest, npm test, npm run build, rg checks, and git diff --check.
"""


def _planner_prompt(
    *,
    manifest_payload: Mapping[str, Any],
    goal: PlanningGoalRow,
    project_key: str,
    default_workflow_key: str,
    workflow_keys: set[str],
) -> str:
    return json.dumps(
        {
            "task": "Create one evidence-bound RequirementCandidate from this Goal.",
            "output_schema": {
                "title": "string",
                "description_markdown": "string",
                "workflow_key": sorted(workflow_keys),
                "priority": "low|normal|high|critical",
                "risk_level": "low|normal|high|critical",
                "confidence": "number 0..1",
                "rationale": "string",
                "acceptance_contract": {
                    "acceptance_kind": "business",
                    "execution_acceptance_steps": [
                        {
                            "step_key": "string",
                            "title": "string",
                            "expected_result": "string",
                            "required_commands": ["safe command strings"],
                            "required_evidence_types": ["workflow_command_result or other evidence types"],
                            "required_db_lineage": ["optional db lineage strings"],
                        }
                    ],
                },
            },
            "manifest_steering": dict(manifest_payload),
            "goal": {
                "id": int(goal.id),
                "goal_key": str(goal.goal_key or ""),
                "title": str(goal.title or ""),
                "intent_markdown": str(goal.intent_markdown or ""),
                "success_metric": str(goal.success_metric or ""),
                "domain": str(goal.domain or "ops"),
                "priority": str(goal.priority or "normal"),
                "risk_level": str(goal.risk_level or "normal"),
                "project_key": str(goal.project_key or project_key or ""),
                "default_workflow_key": default_workflow_key,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def _repair_prompt(*, raw_output: str, error: str) -> str:
    return json.dumps(
        {
            "task": "Repair your previous Planner Agent output. Return only strict JSON matching the requested schema.",
            "error": error,
            "previous_output_excerpt": str(raw_output or "")[:4000],
        },
        ensure_ascii=False,
        indent=2,
    )


def _parse_json_payload(raw_output: str) -> dict[str, Any]:
    text = str(raw_output or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlannerAgentRepairableError(f"Planner Agent returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PlannerAgentRepairableError("Planner Agent JSON must be an object.", partial_payload={})
    return parsed


def _normalize_candidate(parsed: dict[str, Any], *, goal: PlanningGoalRow, workflow_keys: set[str]) -> PlannerAgentCandidate:
    title = str(parsed.get("title") or "").strip()
    description = str(parsed.get("description_markdown") or "").strip()
    workflow_key = str(parsed.get("workflow_key") or "").strip()
    if not title:
        raise PlannerAgentRepairableError("Planner Agent candidate requires title.", partial_payload=parsed)
    if not description:
        raise PlannerAgentRepairableError("Planner Agent candidate requires description_markdown.", partial_payload=parsed)
    if not workflow_key:
        raise PlannerAgentRepairableError("Planner Agent candidate requires workflow_key.", partial_payload=parsed)
    workflow_key = _ensure_workflow_key(workflow_key, workflow_keys, partial_payload=parsed)
    acceptance = parsed.get("acceptance_contract")
    if not isinstance(acceptance, dict):
        acceptance = {}
    priority = str(parsed.get("priority") or goal.priority or "normal").strip().lower() or "normal"
    risk_level = str(parsed.get("risk_level") or goal.risk_level or "normal").strip().lower() or "normal"
    confidence = parsed.get("confidence")
    try:
        confidence_value = max(0.0, min(1.0, float(confidence)))
    except Exception:
        confidence_value = 0.72
    return PlannerAgentCandidate(
        title=title,
        description_markdown=description,
        workflow_key=workflow_key,
        priority=priority,
        risk_level=risk_level,
        confidence=confidence_value,
        rationale=str(parsed.get("rationale") or "").strip(),
        acceptance_contract=acceptance,
        metadata={"planner_agent_mode": "llm_synthesis"},
    )


def _ensure_workflow_key(workflow_key: str, workflow_keys: set[str], *, partial_payload: dict[str, Any] | None = None) -> str:
    normalized = str(workflow_key or "").strip()
    if normalized not in workflow_keys:
        raise PlannerAgentError(
            f"planner selected unknown workflow_key: {normalized}",
            partial_payload=partial_payload or {"workflow_key": normalized},
        )
    return normalized
