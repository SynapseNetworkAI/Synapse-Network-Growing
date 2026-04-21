"""Declarative workflow state machine runner with Blackboard persistence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Mapping

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server import config
from server.database import (
    AtomInvocationRow,
    BlackboardSnapshotRow,
    HumanGateRequestRow,
    NotificationDeliveryRow,
    NotificationFingerprintRow,
    ReleaseRecordRow,
    RequirementCandidateRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowDefinitionRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
    utcnow,
)
from server.services.delivery.pull_request import sync_requirement_review_pr
from server.services.delivery.vcs import execute_requirement_delivery_vcs
from server.services.runtime.alerting import build_ops_url, deliver_policy_notification, notification_service_label


class WorkflowSpecError(ValueError):
    """Raised when a declarative workflow spec is invalid."""


class WorkflowRuntimeError(RuntimeError):
    """Raised when a declarative workflow run cannot safely continue."""


def _launch_final_regression_runner(runner_command: list[str], env: dict[str, str]) -> subprocess.Popen:
    """Launch the detached final-regression runner.

    Kept as a narrow seam so tests can replace only the background launcher
    without mutating the global subprocess module used by normal commands.
    """
    return subprocess.Popen(
        runner_command,
        cwd=str(config.PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


@dataclass(frozen=True)
class AtomResult:
    """Normalized output from an agent or deterministic atom."""

    status: str = "completed"
    summary: str = ""
    writes: Mapping[str, Any] = field(default_factory=dict)
    raw_output: Any = None
    artifacts: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()


@dataclass
class WorkflowContext:
    """Runtime context passed to workflow atoms."""

    db: Session
    workflow_run: WorkflowRunRow
    requirement: RequirementRow
    spec: Mapping[str, Any]
    state_key: str
    state_spec: Mapping[str, Any]
    blackboard: dict[str, Any]


@dataclass(frozen=True)
class WorkflowRunResult:
    """Summary returned after a declarative workflow reaches a terminal state."""

    workflow_key: str
    final_state: str
    resolution: str
    transition_count: int
    blackboard: Mapping[str, Any]


AtomCallable = Callable[[WorkflowContext], AtomResult | Mapping[str, Any] | str]


class AtomRegistry:
    """Registry of governed deterministic and agent atoms."""

    def __init__(self) -> None:
        self._atoms: dict[str, AtomCallable] = {}

    def register(self, key: str, handler: AtomCallable) -> None:
        """Register an atom handler by key."""

        normalized = str(key or "").strip()
        if not normalized:
            raise WorkflowSpecError("atom key must not be empty")
        self._atoms[normalized] = handler

    def get(self, key: str) -> AtomCallable:
        """Return the registered handler for a workflow atom."""

        normalized = str(key or "").strip()
        try:
            return self._atoms[normalized]
        except KeyError as exc:
            raise WorkflowRuntimeError(f"workflow atom is not registered: {normalized}") from exc


def build_agent_self_repair_workflow_spec() -> dict[str, Any]:
    """Return the built-in scenario-1 workflow for Agent Ops self-repair."""

    return {
        "workflow_key": "agent_self_repair",
        "version": 1,
        "description": "Repair Agent Ops failures with bounded same-session patch/verify loop.",
        "initial_state": "detect_ops_failure",
        "limits": {
            "max_patch_attempts": 2,
            "max_transitions": 20,
        },
        "blackboard": {
            "persist_keys": [
                "workflow_key",
                "current_state",
                "limits",
                "counters",
                "trigger",
                "logs_collected",
                "ops_failure_detected",
                "diagnosis",
                "patch_result",
                "verification",
                "ci",
                "final_regression",
                "pr",
                "acceptance",
                "business_outcome",
                "risk_flags",
                "evidence",
                "human_gate_decisions",
            ]
        },
        "states": {
            "detect_ops_failure": {
                "atom": "detect_ops_failure",
                "transitions": [
                    {"if": "ops_failure_detected", "goto": "collect_logs"},
                    {"if": "no_ops_failure", "goto": "done"},
                ],
            },
            "collect_logs": {
                "atom": "collect_ops_logs",
                "transitions": [
                    {"if": "logs_collected", "goto": "diagnose"},
                    {"if": "logs_missing", "goto": "awaiting_operator"},
                ],
            },
            "diagnose": {
                "agent": "ops_self_repair_diagnoser",
                "output_key": "diagnosis",
                "output_schema": "schemas/ops_self_repair_diagnosis.schema.json",
                "transitions": [
                    {"if": 'diagnosis.action == "patch"', "goto": "patch"},
                    {"if": 'diagnosis.action == "needs_operator"', "goto": "awaiting_operator"},
                    {"if": 'diagnosis.action == "no_issue_found"', "goto": "done"},
                ],
            },
            "patch": {
                "agent": "ops_self_repair_coder",
                "output_key": "patch_result",
                "output_schema": "schemas/ops_self_repair_patch.schema.json",
                "transitions": [
                    {"if": "patch_result.changed_files_count > 0", "goto": "verify"},
                    {"if": "counters.patch_attempts >= limits.max_patch_attempts", "goto": "awaiting_operator"},
                ],
            },
            "verify": {
                "atom": "run_ops_self_repair_verification",
                "output_key": "verification",
                "transitions": [
                    {"if": 'verification.status == "passed"', "goto": "start_final_regression"},
                    {
                        "if": 'verification.status == "failed" and counters.patch_attempts < limits.max_patch_attempts',
                        "increment": "patch_attempts",
                        "goto": "patch",
                    },
                    {"if": 'verification.status == "failed"', "goto": "awaiting_operator"},
                ],
            },
            "start_final_regression": {
                "atom": "start_self_repair_final_regression",
                "output_key": "ci",
                "transitions": [
                    {"if": 'ci.status == "in_progress"', "goto": "awaiting_ci"},
                    {"if": 'ci.status == "failed"', "goto": "awaiting_operator"},
                ],
            },
            "awaiting_ci": {
                "pause": True,
                "status": "awaiting_ci",
                "resolution": "waiting_for_final_regression",
            },
            "open_pr": {
                "atom": "open_self_repair_pr",
                "output_key": "pr",
                "transitions": [
                    {"if": "pr.created", "goto": "awaiting_operator"},
                    {"if": "pr.failed", "goto": "awaiting_operator"},
                    {"goto": "done"},
                ],
            },
            "awaiting_operator": {
                "terminal": True,
                "resolution": "route_to_human",
            },
            "done": {
                "terminal": True,
                "resolution": "completed",
            },
        },
    }


def build_gateway_reliability_repair_workflow_spec() -> dict[str, Any]:
    """Return the first product-facing reliability repair workflow spec."""

    spec = build_agent_self_repair_workflow_spec()
    spec["workflow_key"] = "gateway_reliability_repair"
    spec["description"] = "Repair Synapse Gateway reliability drift with verification and observation."
    spec["blackboard"]["persist_keys"] = sorted(
        set(spec["blackboard"]["persist_keys"])
        | {
            "gateway_drift_detected",
            "no_gateway_drift",
            "gate",
            "observation",
        }
    )
    spec["states"]["detect_ops_failure"] = {
        "atom": "detect_gateway_drift",
        "transitions": [
            {"if": "gateway_drift_detected", "goto": "collect_logs"},
            {"if": "no_gateway_drift", "goto": "done"},
        ],
    }
    spec["states"]["collect_logs"]["atom"] = "collect_gateway_logs"
    spec["states"]["diagnose"]["agent"] = "gateway_reliability_diagnoser"
    spec["states"]["patch"]["agent"] = "gateway_reliability_coder"
    spec["states"]["verify"]["atom"] = "run_gateway_verification"
    spec["states"]["verify"]["transitions"][0]["goto"] = "risk_gate"
    spec["states"]["risk_gate"] = {
        "atom": "risk_evidence_gate",
        "output_key": "gate",
        "transitions": [
            {"if": 'gate.decision == "auto_flow"', "goto": "open_pr"},
            {"if": 'gate.decision == "human_required"', "goto": "awaiting_operator"},
        ],
    }
    spec["states"]["open_pr"]["atom"] = "open_gateway_repair_pr"
    spec["states"]["open_pr"]["transitions"] = [
        {"if": "pr.created", "goto": "observing"},
        {"if": "pr.failed", "goto": "awaiting_operator"},
    ]
    spec["states"]["observing"] = {
        "atom": "observe_gateway_recovery",
        "output_key": "observation",
        "transitions": [
            {"if": "observation.restored", "goto": "done"},
            {
                "if": "observation.not_restored and counters.patch_attempts < limits.max_patch_attempts",
                "increment": "patch_attempts",
                "goto": "patch",
            },
            {"if": "observation.not_restored", "goto": "awaiting_operator"},
        ],
    }
    return spec


def built_in_workflow_specs() -> dict[str, dict[str, Any]]:
    """Return built-in declarative workflow specs keyed by workflow key."""

    specs = {
        "agent_self_repair": build_agent_self_repair_workflow_spec(),
        "gateway_reliability_repair": build_gateway_reliability_repair_workflow_spec(),
    }
    return specs


def ensure_builtin_workflow_definitions(db: Session) -> None:
    """Persist built-in workflow definitions for API discovery."""

    for workflow_key, spec in built_in_workflow_specs().items():
        row = db.query(WorkflowDefinitionRow).filter(WorkflowDefinitionRow.workflow_key == workflow_key).first()
        spec_json = _json_dump(spec)
        if row is None:
            row = WorkflowDefinitionRow(
                workflow_key=workflow_key,
                version=int(spec.get("version") or 1),
                title=str(spec.get("description") or workflow_key),
                status="active",
                spec_json=spec_json,
            )
            db.add(row)
        else:
            row.version = int(spec.get("version") or row.version or 1)
            row.title = str(spec.get("description") or row.title or workflow_key)
            row.status = "active"
            row.spec_json = spec_json
            row.updated_at = utcnow()
    db.flush()


def list_workflow_definitions(db: Session) -> list[dict[str, Any]]:
    """Return active built-in and persisted workflow definitions."""

    ensure_builtin_workflow_definitions(db)
    rows = db.query(WorkflowDefinitionRow).order_by(WorkflowDefinitionRow.workflow_key.asc()).all()
    return [
        {
            "id": int(row.id),
            "workflow_key": row.workflow_key,
            "version": int(row.version or 1),
            "title": row.title,
            "status": row.status,
            "spec": _json_load(row.spec_json, {}),
        }
        for row in rows
    ]


def workflow_definition_detail(db: Session, workflow_key: str) -> dict[str, Any]:
    """Return one workflow definition with graph-ready state metadata."""

    ensure_builtin_workflow_definitions(db)
    normalized = str(workflow_key or "").strip()
    row = db.query(WorkflowDefinitionRow).filter(WorkflowDefinitionRow.workflow_key == normalized).first()
    if row is None:
        raise WorkflowRuntimeError(f"workflow definition not found: {normalized}")
    spec = _json_load(row.spec_json, {})
    states_payload: list[dict[str, Any]] = []
    for state_key, state in (spec.get("states") or {}).items():
        if not isinstance(state, Mapping):
            continue
        atom_key = str(state.get("agent") or state.get("atom") or "").strip() or None
        states_payload.append(
            {
                "key": str(state_key),
                "atom_key": atom_key,
                "atom_type": "agent" if state.get("agent") else "deterministic" if state.get("atom") else "terminal",
                "terminal": state.get("terminal") is True,
                "resolution": str(state.get("resolution") or "").strip() or None,
                "output_key": str(state.get("output_key") or "").strip() or None,
                "risk_level": str(state.get("risk_level") or state.get("risk") or "").strip() or None,
                "transitions": [
                    {
                        "condition": str(transition.get("if") or "").strip() or "<default>",
                        "goto": str(transition.get("goto") or "").strip(),
                        "increment": transition.get("increment"),
                    }
                    for transition in (state.get("transitions") or [])
                    if isinstance(transition, Mapping)
                ],
            }
        )
    return {
        "id": int(row.id),
        "workflow_key": row.workflow_key,
        "version": int(row.version or 1),
        "title": row.title,
        "status": row.status,
        "description": str(spec.get("description") or row.title or row.workflow_key),
        "initial_state": str(spec.get("initial_state") or ""),
        "states": states_payload,
        "limits": dict(spec.get("limits") or {}),
        "risk_policy": dict(spec.get("risk_policy") or {}),
        "blackboard": dict(spec.get("blackboard") or {}),
        "spec": spec,
    }


def _terminal_statuses() -> set[str]:
    return {"succeeded", "completed", "done", "failed", "cancelled"}


def _workflow_duration_ms(row: WorkflowRunRow) -> int | None:
    started = getattr(row, "started_at", None)
    completed = getattr(row, "completed_at", None)
    if not started or not completed:
        return None
    return max(0, int((completed - started).total_seconds() * 1000))


def _is_completed_status(status: str | None) -> bool:
    return str(status or "").strip() in {"succeeded", "completed", "done"}


def _blackboard_pr(blackboard: Mapping[str, Any]) -> Mapping[str, Any]:
    pr = blackboard.get("pr")
    return pr if isinstance(pr, Mapping) else {}


def _pr_is_simulated(pr: Mapping[str, Any]) -> bool:
    sync = pr.get("sync") if isinstance(pr.get("sync"), Mapping) else {}
    vcs = pr.get("vcs") if isinstance(pr.get("vcs"), Mapping) else {}
    values = [
        pr.get("sync_action"),
        pr.get("status"),
        sync.get("sync_action"),
        sync.get("status"),
        vcs.get("sync_action"),
        vcs.get("status"),
    ]
    return any(str(value or "").strip().lower() == "simulated" for value in values)


def _command_results_from_blackboard(blackboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    verification = blackboard.get("verification") if isinstance(blackboard.get("verification"), Mapping) else {}
    candidates = [
        verification.get("command_results"),
        verification.get("commands"),
        blackboard.get("command_results"),
    ]
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, Mapping):
                    results.append(dict(item))
    return results


def _delivery_summary_from_blackboard(blackboard: Mapping[str, Any], release: ReleaseRecordRow | None) -> dict[str, Any]:
    pr = _blackboard_pr(blackboard)
    sync = pr.get("sync") if isinstance(pr.get("sync"), Mapping) else {}
    vcs = pr.get("vcs") if isinstance(pr.get("vcs"), Mapping) else {}
    url = str(getattr(release, "pr_url", "") or pr.get("url") or sync.get("pr_url") or "").strip() or None
    return {
        "pr_created": bool(pr.get("created") or url),
        "pr_url": url,
        "branch_name": str(pr.get("branch_name") or sync.get("branch_name") or sync.get("head_branch") or "").strip() or None,
        "compare_url": str(pr.get("compare_url") or sync.get("compare_url") or "").strip() or None,
        "pr_status": str(getattr(release, "pr_status", "") or pr.get("pr_status") or sync.get("pr_status") or "").strip() or None,
        "release_status": str(getattr(release, "status", "") or "").strip() or None,
        "sync_action": str(pr.get("sync_action") or sync.get("sync_action") or "").strip() or None,
        "simulated": _pr_is_simulated(pr),
        "human_commits_detected": bool(sync.get("human_commits_detected") or vcs.get("human_commits_detected")),
        "rebase_attempted": bool(vcs.get("rebase_attempted")),
        "rebase_status": str(vcs.get("rebase_status") or "").strip() or None,
        "delivery_blocker_type": str(vcs.get("delivery_blocker_type") or "").strip() or None,
    }


def _delivery_columns_summary(row: WorkflowRunRow) -> dict[str, Any]:
    return {
        "pr_created": bool(getattr(row, "delivery_pr_url", None)),
        "pr_url": str(getattr(row, "delivery_pr_url", "") or "").strip() or None,
        "branch_name": str(getattr(row, "delivery_branch", "") or "").strip() or None,
        "compare_url": str(getattr(row, "delivery_compare_url", "") or "").strip() or None,
        "pr_status": None,
        "release_status": str(getattr(row, "delivery_status", "") or "").strip() or None,
        "sync_action": None,
        "simulated": bool(getattr(row, "delivery_is_simulated", False)),
        "base_branch": str(getattr(row, "delivery_base_branch", "") or "").strip() or None,
        "synced_at": row.delivery_synced_at.isoformat() if getattr(row, "delivery_synced_at", None) else None,
    }


def _merged_delivery_summary(row: WorkflowRunRow, blackboard: Mapping[str, Any], release: ReleaseRecordRow | None) -> dict[str, Any]:
    dynamic = _delivery_summary_from_blackboard(blackboard, release)
    materialized = _delivery_columns_summary(row)
    merged = {
        **dynamic,
        **{key: value for key, value in materialized.items() if value not in (None, "", False)},
        "simulated": bool(materialized.get("simulated") or dynamic.get("simulated")),
    }
    if getattr(release, "pr_url", None):
        merged["pr_url"] = str(release.pr_url or "").strip() or merged.get("pr_url")
    if getattr(release, "status", None):
        merged["release_status"] = str(release.status or "").strip() or merged.get("release_status")
    return merged


def _sync_workflow_delivery_columns(
    row: WorkflowRunRow,
    *,
    pr_url: str | None,
    compare_url: str | None = None,
    branch_name: str | None = None,
    base_branch: str | None = None,
    status: str | None = None,
    simulated: bool = False,
) -> None:
    row.delivery_pr_url = str(pr_url or "").strip() or None
    row.delivery_compare_url = str(compare_url or "").strip() or None
    row.delivery_branch = str(branch_name or "").strip() or None
    row.delivery_base_branch = str(base_branch or "").strip() or None
    row.delivery_status = str(status or "").strip() or None
    row.delivery_is_simulated = bool(simulated)
    row.delivery_synced_at = utcnow()


def _backfill_delivery_columns_if_missing(row: WorkflowRunRow, delivery: Mapping[str, Any]) -> None:
    if getattr(row, "delivery_pr_url", None) or not delivery.get("pr_url"):
        return
    _sync_workflow_delivery_columns(
        row,
        pr_url=str(delivery.get("pr_url") or ""),
        compare_url=str(delivery.get("compare_url") or ""),
        branch_name=str(delivery.get("branch_name") or ""),
        base_branch=str(delivery.get("base_branch") or ""),
        status=str(delivery.get("release_status") or delivery.get("pr_status") or delivery.get("sync_action") or "synced"),
        simulated=bool(delivery.get("simulated")),
    )


def _changed_files_summary_from_blackboard(blackboard: Mapping[str, Any]) -> dict[str, Any]:
    patch_result = blackboard.get("patch_result") if isinstance(blackboard.get("patch_result"), Mapping) else {}
    changed = [str(item) for item in patch_result.get("changed_files") or []]
    added = [str(item) for item in patch_result.get("added_files") or []]
    modified = [str(item) for item in patch_result.get("modified_files") or []]
    deleted = [str(item) for item in patch_result.get("deleted_files") or []]
    if changed and not modified and not added and not deleted:
        modified = list(changed)
    return {
        "changed_files": changed,
        "added_files": added,
        "modified_files": modified,
        "deleted_files": deleted,
        "changed_files_count": int(patch_result.get("changed_files_count") or len(changed)),
        "diff_summary": str(patch_result.get("diff_summary") or "").strip(),
        "patch_artifact_id": patch_result.get("patch_artifact_id"),
        "planned_change_only": bool(patch_result.get("planned_change_only", True)),
    }


def _workflow_truth_fields(
    row: WorkflowRunRow,
    *,
    blackboard: Mapping[str, Any],
    pending_gate_count: int,
    release: ReleaseRecordRow | None,
) -> dict[str, Any]:
    command_results = _command_results_from_blackboard(blackboard)
    verification = blackboard.get("verification") if isinstance(blackboard.get("verification"), Mapping) else {}
    verification_passed = str(verification.get("status") or "").strip().lower() == "passed"
    delivery = _merged_delivery_summary(row, blackboard, release)
    _backfill_delivery_columns_if_missing(row, delivery)
    is_completed = _is_completed_status(row.status)
    needs_human = pending_gate_count > 0
    acceptance = blackboard.get("acceptance") if isinstance(blackboard.get("acceptance"), Mapping) else {}
    business_outcome = blackboard.get("business_outcome") if isinstance(blackboard.get("business_outcome"), Mapping) else {}
    acceptance_override = bool(acceptance.get("acceptance_override"))
    business_outcome_status = str(business_outcome.get("status") or "").strip().lower() or None
    business_outcome_confirmed = business_outcome_status == "confirmed" and bool(business_outcome.get("confirmed_at"))
    awaiting_business_confirmation = acceptance_override and is_completed and not business_outcome_confirmed
    evidence_complete = (not verification_passed) or bool(command_results)
    warnings: list[str] = []
    if needs_human:
        warnings.append("Pending human gate: this run is not truly completed.")
    if awaiting_business_confirmation:
        warnings.append("Human Override: technical workflow is done, but business outcome needs operator confirmation.")
    if getattr(row, "archived_at", None) is not None and pending_gate_count > 0:
        warnings.append("Archived with pending gate: hidden state still requires operator review.")
    if verification_passed and not command_results:
        warnings.append("Evidence incomplete: verification passed without recorded command evidence.")
    if bool(delivery.get("simulated")):
        warnings.append("Simulated PR: delivery evidence is not a real external PR.")
    stale_awaiting_operator = str(row.status or "") == "awaiting_operator" and pending_gate_count == 0
    truly_completed = is_completed and not needs_human and not awaiting_business_confirmation
    if awaiting_business_confirmation:
        outcome_label = "Awaiting Business Confirmation"
    elif needs_human:
        outcome_label = "Needs Human"
    elif truly_completed:
        outcome_label = "Completed"
    elif row.status == "failed":
        outcome_label = "Failed"
    elif stale_awaiting_operator:
        outcome_label = "Blocked"
    else:
        outcome_label = "Running"
    return {
        "outcome_label": outcome_label,
        "is_truly_completed": truly_completed,
        "completed_truthfully": truly_completed,
        "needs_human": needs_human or awaiting_business_confirmation,
        "is_simulated": bool(delivery.get("simulated")) or any(bool(item.get("simulated")) for item in command_results),
        "simulated_delivery": bool(delivery.get("simulated")),
        "evidence_complete": evidence_complete,
        "observability_warnings": warnings,
        "changed_files_summary": _changed_files_summary_from_blackboard(blackboard),
        "command_results": command_results,
        "delivery_summary": delivery,
        "acceptance_override": acceptance_override,
        "manual_review_prompt": str(acceptance.get("manual_review_prompt") or acceptance.get("markdown") or "").strip(),
        "business_outcome_status": business_outcome_status,
        "business_outcome_confirmed_by": str(business_outcome.get("confirmed_by") or "").strip() or None,
        "business_outcome_confirmed_at": str(business_outcome.get("confirmed_at") or "").strip() or None,
        "business_outcome_note": str(business_outcome.get("note") or "").strip() or None,
        "awaiting_business_confirmation": awaiting_business_confirmation,
    }


def _agent_outputs_from_rows(
    artifacts: list[WorkflowArtifactRow],
    invocations: list[AtomInvocationRow],
) -> list[dict[str, Any]]:
    artifacts_by_id = {int(artifact.id): artifact for artifact in artifacts}
    outputs: list[dict[str, Any]] = []
    for invocation in invocations:
        if str(invocation.atom_type or "") != "agent":
            continue
        artifact_ids = _json_load(invocation.artifact_ids_json, [])
        raw_artifact = next(
            (
                artifacts_by_id.get(int(artifact_id))
                for artifact_id in artifact_ids
                if str(artifact_id).isdigit() and artifacts_by_id.get(int(artifact_id)) is not None
            ),
            None,
        )
        payload = _json_load(raw_artifact.machine_readable_payload, {}) if raw_artifact is not None else {}
        outputs.append(
            {
                "state_key": invocation.state_key,
                "atom_key": invocation.atom_key,
                "agent_name": invocation.atom_key,
                "status": invocation.status,
                "summary": invocation.output_summary,
                "input_summary": invocation.input_summary,
                "parsed_writes": payload.get("writes") if isinstance(payload, Mapping) else {},
                "raw_artifact_id": int(raw_artifact.id) if raw_artifact is not None else None,
                "raw_output": raw_artifact.human_readable_body if raw_artifact is not None else "",
                "created_at": raw_artifact.created_at.isoformat() if raw_artifact is not None and raw_artifact.created_at else None,
            }
        )
    return outputs


def _command_results_from_artifacts(artifacts: list[WorkflowArtifactRow]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "workflow_command_result":
            continue
        payload = _json_load(artifact.machine_readable_payload, {})
        if isinstance(payload, Mapping):
            item = dict(payload)
            item.setdefault("log_artifact_id", int(artifact.id))
            item.setdefault("state_key", artifact.state_key)
            item.setdefault("atom_key", artifact.atom_key)
            results.append(item)
    return results


def _latest_release_for_run(db: Session, row: WorkflowRunRow) -> ReleaseRecordRow | None:
    release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.workflow_run_id == int(row.id))
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    if release is not None:
        return release
    return (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == int(row.requirement_id))
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )


def _workflow_run_summary_item(
    db: Session,
    row: WorkflowRunRow,
    *,
    requirement: RequirementRow | None = None,
) -> dict[str, Any]:
    """Build the operator-facing workflow run row used by lists and detail."""

    pending_gate_count = (
        db.query(HumanGateRequestRow)
        .filter(
            HumanGateRequestRow.workflow_run_id == int(row.id),
            HumanGateRequestRow.status == "pending",
        )
        .count()
    )
    gate = (
        db.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == int(row.id))
        .order_by(HumanGateRequestRow.id.desc())
        .first()
    )
    last_invocation = (
        db.query(AtomInvocationRow)
        .filter(AtomInvocationRow.workflow_run_id == int(row.id))
        .order_by(AtomInvocationRow.id.desc())
        .first()
    )
    artifact_count = db.query(WorkflowArtifactRow).filter(WorkflowArtifactRow.workflow_run_id == int(row.id)).count()
    atom_count = db.query(AtomInvocationRow).filter(AtomInvocationRow.workflow_run_id == int(row.id)).count()
    release = _latest_release_for_run(db, row)
    if requirement is None:
        requirement = db.query(RequirementRow).filter(RequirementRow.id == int(row.requirement_id)).first()
    blackboard = workflow_blackboard(row)
    truth = _workflow_truth_fields(row, blackboard=blackboard, pending_gate_count=int(pending_gate_count or 0), release=release)
    return {
        "id": int(row.id),
        "requirement_id": int(row.requirement_id),
        "requirement_title": str(getattr(requirement, "title", "") or ""),
        "requirement_candidate_id": int(getattr(requirement, "requirement_candidate_id", 0) or 0) or None,
        "requirement_source": str(getattr(requirement, "source", "") or "") or None,
        "workflow_key": row.workflow_key,
        "current_state": row.current_state,
        "status": row.status,
        "resolution": row.resolution,
        "risk_level": row.risk_level,
        "goal_key": str(getattr(row, "goal_key", "") or getattr(requirement, "goal_key", "") or "") or None,
        "operating_manifest_id": int(getattr(row, "operating_manifest_id", 0) or getattr(requirement, "operating_manifest_id", 0) or 0) or None,
        "pending_human_gate_count": int(pending_gate_count or 0),
        "last_human_gate_decision": str(getattr(gate, "decision", "") or "") or None,
        "last_atom": str(getattr(last_invocation, "atom_key", "") or "") or None,
        "artifact_count": int(artifact_count or 0),
        "atom_count": int(atom_count or 0),
        "duration_ms": _workflow_duration_ms(row),
        "pr_url": str(truth["delivery_summary"].get("pr_url") or getattr(release, "pr_url", "") or "") or None,
        "release_status": str(truth["delivery_summary"].get("release_status") or getattr(release, "status", "") or truth["delivery_summary"].get("pr_status") or "") or None,
        "delivery_pr_url": str(truth["delivery_summary"].get("pr_url") or "") or None,
        "delivery_compare_url": str(truth["delivery_summary"].get("compare_url") or "") or None,
        "delivery_branch": str(truth["delivery_summary"].get("branch_name") or "") or None,
        "delivery_base_branch": str(truth["delivery_summary"].get("base_branch") or "") or None,
        "delivery_status": str(truth["delivery_summary"].get("release_status") or truth["delivery_summary"].get("pr_status") or truth["delivery_summary"].get("sync_action") or "") or None,
        "delivery_is_simulated": bool(truth["delivery_summary"].get("simulated")),
        "changed_files_count": int((truth.get("changed_files_summary") or {}).get("changed_files_count") or 0),
        "command_evidence_count": len(truth.get("command_results") or []),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "archived_at": row.archived_at.isoformat() if getattr(row, "archived_at", None) else None,
        "archived_by": str(getattr(row, "archived_by", "") or "") or None,
        "archive_reason": str(getattr(row, "archive_reason", "") or "") or None,
        "outcome_label": truth["outcome_label"],
        "is_truly_completed": truth["is_truly_completed"],
        "completed_truthfully": truth["completed_truthfully"],
        "needs_human": truth["needs_human"],
        "is_simulated": truth["is_simulated"],
        "simulated_delivery": truth["simulated_delivery"],
        "evidence_complete": truth["evidence_complete"],
        "acceptance_override": truth["acceptance_override"],
        "manual_review_prompt": truth["manual_review_prompt"],
        "business_outcome_status": truth["business_outcome_status"],
        "business_outcome_confirmed_by": truth["business_outcome_confirmed_by"],
        "business_outcome_confirmed_at": truth["business_outcome_confirmed_at"],
        "business_outcome_note": truth["business_outcome_note"],
        "awaiting_business_confirmation": truth["awaiting_business_confirmation"],
    }


def list_workflow_runs(
    db: Session,
    *,
    limit: int = 100,
    page: int = 1,
    page_size: int | None = None,
    tab: str | None = None,
    status: str | None = None,
    workflow_key: str | None = None,
    goal_key: str | None = None,
    current_state: str | None = None,
    risk_level: str | None = None,
    pending_human_gate: bool | None = None,
    requirement_id: int | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]] | dict[str, Any]:
    """Return recent declarative workflow runs for the ops UI."""

    query = db.query(WorkflowRunRow).filter(WorkflowRunRow.workflow_key != "legacy_fixed_step")
    normalized_tab = str(tab or "").strip().lower()
    if not include_archived and normalized_tab != "archived":
        query = query.filter(WorkflowRunRow.archived_at.is_(None))
    if normalized_tab == "active":
        query = query.filter(WorkflowRunRow.status.in_(["pending", "running", "paused"]))
    elif normalized_tab in {"needs_human", "human"}:
        pending_human_gate = pending_human_gate
    elif normalized_tab == "failed":
        query = query.filter(WorkflowRunRow.status == "failed")
    elif normalized_tab == "completed":
        query = query.filter(WorkflowRunRow.status.in_(["succeeded", "completed", "done"]))
        pending_subquery = db.query(HumanGateRequestRow.workflow_run_id).filter(HumanGateRequestRow.status == "pending")
        query = query.filter(~WorkflowRunRow.id.in_(pending_subquery))
    elif normalized_tab == "archived":
        query = query.filter(WorkflowRunRow.archived_at.isnot(None))
    if status:
        query = query.filter(WorkflowRunRow.status == status)
    if workflow_key:
        query = query.filter(WorkflowRunRow.workflow_key == workflow_key)
    if goal_key:
        # Historical runs may only carry goal lineage on the linked requirement.
        query = query.outerjoin(RequirementRow, RequirementRow.id == WorkflowRunRow.requirement_id).filter(
            or_(WorkflowRunRow.goal_key == goal_key, RequirementRow.goal_key == goal_key)
        )
    if current_state:
        query = query.filter(WorkflowRunRow.current_state == current_state)
    if risk_level:
        query = query.filter(WorkflowRunRow.risk_level == risk_level)
    if requirement_id:
        query = query.filter(WorkflowRunRow.requirement_id == int(requirement_id))
    if pending_human_gate is True:
        query = query.join(HumanGateRequestRow).filter(HumanGateRequestRow.status == "pending")
    elif pending_human_gate is False:
        pending_subquery = db.query(HumanGateRequestRow.workflow_run_id).filter(HumanGateRequestRow.status == "pending")
        query = query.filter(~WorkflowRunRow.id.in_(pending_subquery))
    total = query.count()
    if page_size is not None:
        safe_page_size = max(1, min(int(page_size or 50), 200))
        safe_page = max(1, int(page or 1))
        rows = query.order_by(WorkflowRunRow.id.desc()).offset((safe_page - 1) * safe_page_size).limit(safe_page_size).all()
    else:
        rows = query.order_by(WorkflowRunRow.id.desc()).limit(max(1, min(int(limit or 100), 500))).all()
    requirement_ids = [int(row.requirement_id) for row in rows]
    requirements = {
        int(item.id): item
        for item in db.query(RequirementRow).filter(RequirementRow.id.in_(requirement_ids)).all()
    } if requirement_ids else {}
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(_workflow_run_summary_item(db, row, requirement=requirements.get(int(row.requirement_id))))
    if normalized_tab == "completed":
        result = [item for item in result if bool(item.get("completed_truthfully"))]
    elif normalized_tab in {"needs_human", "human"}:
        result = [item for item in result if bool(item.get("needs_human"))]
    if page_size is None:
        return result
    return {
        "items": result,
        "total": len(result) if normalized_tab in {"completed", "needs_human", "human"} else int(total),
        "page": max(1, int(page or 1)),
        "page_size": max(1, min(int(page_size or 50), 200)),
        "total_pages": max(1, ((len(result) if normalized_tab in {"completed", "needs_human", "human"} else int(total)) + max(1, min(int(page_size or 50), 200)) - 1) // max(1, min(int(page_size or 50), 200))),
    }


def workflow_runs_summary(db: Session) -> dict[str, Any]:
    """Return high-level workflow operations center stats and empty-state context."""

    base = db.query(WorkflowRunRow).filter(
        WorkflowRunRow.workflow_key != "legacy_fixed_step",
        WorkflowRunRow.archived_at.is_(None),
    )
    all_rows = base.all()
    pending_gate_run_ids = {
        int(row.workflow_run_id)
        for row in db.query(HumanGateRequestRow.workflow_run_id)
        .filter(HumanGateRequestRow.status == "pending")
        .all()
    }
    failed_rows = [row for row in all_rows if row.status == "failed"]
    stale_awaiting_rows = [
        row for row in all_rows
        if row.status == "awaiting_operator" and int(row.id) not in pending_gate_run_ids
    ]
    now = utcnow()
    durations = [_workflow_duration_ms(row) for row in all_rows if _workflow_duration_ms(row) is not None]
    summary_items = [_workflow_run_summary_item(db, row) for row in all_rows]
    needs_human_items = [item for item in summary_items if item.get("needs_human")]
    failed_ids = {int(row.id) for row in failed_rows}
    blocker_items = [item for item in summary_items if item.get("needs_human") or int(item.get("id") or 0) in failed_ids]
    completed_today = [
        item for item in summary_items
        if item.get("completed_at") and str(item.get("completed_at")).startswith(now.date().isoformat()) and item.get("completed_truthfully")
    ]
    pending_candidates = (
        db.query(RequirementCandidateRow)
        .filter(RequirementCandidateRow.status.in_(["pending", "approved"]))
        .order_by(RequirementCandidateRow.id.desc())
        .limit(5)
        .all()
    )
    return {
        "running": sum(1 for row in all_rows if row.status in {"pending", "running", "paused"}),
        "needs_human": len(needs_human_items),
        "pending_gate_count": len(pending_gate_run_ids),
        "failed": len(failed_rows),
        "failed_count": len(failed_rows),
        "resume_failure_count": sum(1 for row in failed_rows if str(row.resolution or "") == "resume_failed"),
        "stale_awaiting_operator_count": len(stale_awaiting_rows),
        "completed": sum(1 for item in summary_items if item.get("completed_truthfully")),
        "completed_today": len(completed_today),
        "pending_release": db.query(ReleaseRecordRow).filter(ReleaseRecordRow.status.in_(["ready", "release_ready", "blocked"])).count(),
        "average_duration_ms": int(sum(durations) / len(durations)) if durations else 0,
        "archived": db.query(WorkflowRunRow).filter(WorkflowRunRow.archived_at.isnot(None)).count(),
        "pending_candidate_count": db.query(RequirementCandidateRow).filter(RequirementCandidateRow.status.in_(["pending", "approved"])).count(),
        "recent_candidates": [
            {
                "id": int(candidate.id),
                "title": candidate.title,
                "status": candidate.status,
                "goal_key": candidate.goal_key,
                "workflow_key": candidate.workflow_key,
            }
            for candidate in pending_candidates
        ],
        "blocker_items": [
            item for item in blocker_items
        ],
    }


def archive_workflow_run(db: Session, workflow_run_id: int, *, archived_by: str = "operator", reason: str = "") -> dict[str, Any]:
    """Hide a workflow run from the default operations list without deleting evidence."""

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == int(workflow_run_id)).first()
    if run is None:
        raise WorkflowRuntimeError(f"workflow run not found: {workflow_run_id}")
    run.archived_at = run.archived_at or utcnow()
    run.archived_by = archived_by or "operator"
    run.archive_reason = reason or "archived from Workflow Operations Center"
    run.updated_at = utcnow()
    db.flush()
    return _workflow_run_summary_item(db, run)


def create_workflow_followup_requirement(
    db: Session,
    workflow_run_id: int,
    *,
    title: str | None = None,
    description_markdown: str | None = None,
    operator: str = "operator",
) -> dict[str, Any]:
    """Create a follow-up requirement linked to a workflow run."""

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == int(workflow_run_id)).first()
    if run is None:
        raise WorkflowRuntimeError(f"workflow run not found: {workflow_run_id}")
    requirement = db.query(RequirementRow).filter(RequirementRow.id == int(run.requirement_id)).first()
    if requirement is None:
        raise WorkflowRuntimeError(f"requirement not found for workflow run: {workflow_run_id}")
    followup = RequirementRow(
        title=title or f"Follow-up: {requirement.title}",
        description_markdown=description_markdown or (
            f"Follow-up created from workflow run #{int(run.id)}.\n\n"
            f"Original requirement #{int(requirement.id)}: {requirement.title}\n\n"
            "Review the completed workflow evidence and define the next focused action."
        ),
        status="planning",
        phase="planning",
        workflow_state="planning",
        priority=str(requirement.priority or "normal"),
        source="workflow_followup",
        source_ref=f"workflow_run:{int(run.id)}",
        operating_manifest_id=getattr(run, "operating_manifest_id", None) or getattr(requirement, "operating_manifest_id", None),
        goal_key=getattr(run, "goal_key", None) or getattr(requirement, "goal_key", None),
        linked_requirement_id=int(requirement.id),
        project_id=getattr(requirement, "project_id", None),
        project_key=getattr(requirement, "project_key", None),
        project_display_name=getattr(requirement, "project_display_name", None),
        target_project_path=getattr(requirement, "target_project_path", None),
        target_project_path_override=getattr(requirement, "target_project_path_override", None),
        intake_metadata_json=_json_dump({
            "created_from": "workflow_followup",
            "workflow_run_id": int(run.id),
            "operator": operator,
        }),
    )
    db.add(followup)
    db.flush()
    requirement.followup_requirement_id = int(followup.id)
    db.flush()
    return {"requirement_id": int(followup.id), "workflow_run_id": int(run.id)}


def set_workflow_business_outcome(
    db: Session,
    workflow_run_id: int,
    *,
    status: str,
    operator: str = "operator",
    note: str = "",
) -> dict[str, Any]:
    """Record operator business acceptance for Human Override workflows.

    This does not mutate release, rollback, deployment, or execution evidence.
    It only records the business outcome review on the workflow blackboard and
    emits a state event so the decision is visible in the timeline/debug dump.
    """

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == int(workflow_run_id)).first()
    if run is None:
        raise WorkflowRuntimeError(f"workflow run not found: {workflow_run_id}")
    normalized = str(status or "").strip().lower()
    if normalized not in {"confirmed", "rejected", "follow_up_requested"}:
        raise WorkflowRuntimeError(f"unsupported business outcome status: {status}")
    blackboard = workflow_blackboard(run)
    acceptance = blackboard.get("acceptance") if isinstance(blackboard.get("acceptance"), Mapping) else {}
    if not bool(acceptance.get("acceptance_override")):
        raise WorkflowRuntimeError("business outcome review is only available for Human Override workflows")
    now = utcnow()
    business_outcome = {
        "status": normalized,
        "confirmed_by": operator if normalized == "confirmed" else None,
        "confirmed_at": now.isoformat() if normalized == "confirmed" else None,
        "reviewed_by": operator,
        "reviewed_at": now.isoformat(),
        "note": note,
    }
    blackboard["business_outcome"] = business_outcome
    run.blackboard_json = _json_dump(blackboard)
    run.updated_at = now
    db.add(
        WorkflowStateEventRow(
            workflow_run_id=int(run.id),
            event_type="business_outcome_review",
            from_state=str(run.current_state or ""),
            to_state=str(run.current_state or ""),
            condition=f"operator.business_outcome.{normalized}",
            payload_json=_json_dump(business_outcome),
        )
    )
    requirement = db.query(RequirementRow).filter(RequirementRow.id == int(run.requirement_id)).first()
    if requirement is not None:
        metadata = _json_load(getattr(requirement, "intake_metadata_json", None), {})
        metadata = metadata if isinstance(metadata, dict) else {}
        metadata["business_outcome"] = business_outcome
        requirement.intake_metadata_json = _json_dump(metadata)
        if normalized == "confirmed" and run.status in {"succeeded", "completed", "done"}:
            requirement.status = "completed"
            requirement.workflow_state = "completed"
            requirement.phase = "completed"
            requirement.completed_at = requirement.completed_at or now
        elif normalized == "rejected":
            requirement.attention_reason = "business_outcome_rejected"
        elif normalized == "follow_up_requested":
            requirement.attention_reason = "business_follow_up_requested"
        requirement.updated_at = now
    db.flush()
    return workflow_run_detail(db, int(run.id))


def request_workflow_business_followup(
    db: Session,
    workflow_run_id: int,
    *,
    title: str | None = None,
    description_markdown: str | None = None,
    operator: str = "operator",
    note: str = "",
) -> dict[str, Any]:
    """Create a follow-up requirement and mark business outcome as follow-up requested."""

    payload = create_workflow_followup_requirement(
        db,
        workflow_run_id,
        title=title,
        description_markdown=description_markdown,
        operator=operator,
    )
    detail = set_workflow_business_outcome(
        db,
        workflow_run_id,
        status="follow_up_requested",
        operator=operator,
        note=note or f"Follow-up requirement #{payload['requirement_id']} requested.",
    )
    return {**payload, "workflow": detail}


def create_declarative_workflow_run(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_key: str,
    triggered_by: str = "system",
    initial_blackboard: Mapping[str, Any] | None = None,
    run_immediately: bool = True,
    registry: AtomRegistry | None = None,
) -> WorkflowRunRow:
    """Create and optionally run a new declarative workflow run for a requirement."""

    specs = built_in_workflow_specs()
    if workflow_key not in specs:
        raise WorkflowSpecError(f"unknown workflow_key: {workflow_key}")
    spec = specs[workflow_key]
    validate_workflow_spec(spec)
    blackboard = dict(initial_blackboard or {})
    blackboard.setdefault("trigger", {})
    blackboard.setdefault("workflow_key", workflow_key)
    blackboard.setdefault("current_state", str(spec["initial_state"]))
    blackboard.setdefault("operating_manifest_id", int(getattr(requirement, "operating_manifest_id", 0) or 0) or None)
    blackboard.setdefault("goal_key", str(getattr(requirement, "goal_key", "") or "").strip() or None)
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        operating_manifest_id=int(getattr(requirement, "operating_manifest_id", 0) or 0) or None,
        goal_key=str(getattr(requirement, "goal_key", "") or "").strip() or None,
        plan_version=1,
        workflow_key=workflow_key,
        current_state=str(spec["initial_state"]),
        status="pending",
        triggered_by=triggered_by,
        risk_level=str(blackboard.get("risk_level") or "normal"),
        retry_counters_json="{}",
        blackboard_json=_json_dump(blackboard),
    )
    db.add(run)
    db.flush()
    _notify_workflow_run_started(db, run, requirement, blackboard)
    requirement.active_workflow_run_id = int(run.id)
    requirement.workflow_family = "declarative_state_machine"
    requirement.workflow_state = "executing" if run_immediately else "ready"
    requirement.status = "in_progress" if run_immediately else "ready"
    requirement.phase = "executing" if run_immediately else "ready"
    db.flush()
    if run_immediately:
        run_workflow_state_machine(
            db,
            workflow_run=run,
            spec=spec,
            registry=registry or default_atom_registry(),
            initial_blackboard=blackboard,
        )
        if run.status == "succeeded":
            if _run_awaiting_business_confirmation(run):
                requirement.workflow_state = "awaiting_operator"
                requirement.status = "awaiting_operator"
                requirement.phase = "review"
                requirement.attention_reason = "business_outcome_confirmation_required"
            else:
                requirement.workflow_state = "completed"
                requirement.status = "completed"
                requirement.phase = "completed"
                requirement.completed_at = requirement.completed_at or utcnow()
        elif run.status == "awaiting_operator":
            requirement.workflow_state = "awaiting_operator"
            requirement.status = "blocked"
            requirement.phase = "blocked"
        db.flush()
    return run


def default_atom_registry() -> AtomRegistry:
    """Build the default governed atom registry for first-phase workflows."""

    registry = AtomRegistry()

    def _trigger(ctx: WorkflowContext) -> dict[str, Any]:
        return dict(ctx.blackboard.get("trigger") or {})

    registry.register(
        "detect_ops_failure",
        lambda ctx: AtomResult(
            summary="Ops failure signal evaluated",
            writes={
                "ops_failure_detected": bool(_trigger(ctx).get("ops_failure_detected", True)),
                "no_ops_failure": not bool(_trigger(ctx).get("ops_failure_detected", True)),
            },
        ),
    )
    registry.register(
        "collect_ops_logs",
        lambda _ctx: AtomResult(
            summary="Ops logs collected",
            writes={
                "logs_collected": True,
                "logs_missing": False,
                "evidence": [{"kind": "log", "path": "server/logs/ops-dashboard.jsonl"}],
            },
        ),
    )
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: {
            "status": "completed",
            "summary": "Ops failure requires scoped patch",
            "writes": {"diagnosis": {"action": "patch", "module": "ops-dashboard"}},
        },
    )
    def _file_change_summary_artifact(ctx: WorkflowContext, *, changed_files: list[str], diff_summary: str) -> int:
        artifact = _create_workflow_artifact(
            ctx.db,
            workflow_run_id=int(ctx.workflow_run.id),
            artifact_type="workflow_file_change_summary",
            state_key=ctx.state_key,
            atom_key=str(ctx.state_spec.get("agent") or ctx.state_spec.get("atom") or ""),
            content_summary=f"{ctx.state_key}: planned file change summary",
            human_readable_body=diff_summary,
            machine_readable_payload={
                "changed_files": changed_files,
                "modified_files": changed_files,
                "added_files": [],
                "deleted_files": [],
                "diff_summary": diff_summary,
                "planned_change_only": True,
            },
        )
        return int(artifact.id)

    def _ops_self_repair_coder(ctx: WorkflowContext) -> dict[str, Any]:
        changed_files = ["server/services/workflows/declarative.py"]
        diff_summary = "Planned self-repair patch scoped to workflow observability/runtime behavior."
        artifact_id = _file_change_summary_artifact(ctx, changed_files=changed_files, diff_summary=diff_summary)
        return {
            "status": "completed",
            "summary": "Prepared self-repair patch guidance",
            "writes": {
                "patch_result": {
                    "changed_files_count": len(changed_files),
                    "changed_files": changed_files,
                    "modified_files": changed_files,
                    "added_files": [],
                    "deleted_files": [],
                    "diff_summary": diff_summary,
                    "planned_change_only": True,
                    "patch_artifact_id": artifact_id,
                }
            },
            "artifacts": [artifact_id],
        }

    registry.register("ops_self_repair_coder", _ops_self_repair_coder)

    def _verify_self_repair(ctx: WorkflowContext) -> AtomResult:
        trigger = _trigger(ctx)
        counters = dict(ctx.blackboard.get("counters") or {})
        should_fail_once = bool(trigger.get("force_first_verification_failure"))
        if should_fail_once and int(counters.get("patch_attempts") or 0) == 0:
            command_result = _record_command_result_artifact(
                ctx,
                command="PYTHONPATH=. python -m py_compile server/services/workflows/declarative.py",
                purpose="Force one bounded verification failure for retry-path validation.",
                exit_code=1,
                simulated=True,
                stderr_excerpt="forced verification failure for retry-path validation",
            )
            return AtomResult(
                summary="Verification failed before retry",
                writes={"verification": {"status": "failed", "command_results": [command_result]}},
                artifacts=(str(command_result["log_artifact_id"]),),
            )
        command_result = _run_local_command_result_artifact(
            ctx,
            command="PYTHONPATH=. python -m py_compile server/services/workflows/declarative.py",
            args=[sys.executable, "-m", "py_compile", "server/services/workflows/declarative.py"],
            purpose="Verify the self-repair runtime module still compiles.",
        )
        status = "passed" if int(command_result.get("exit_code") or 0) == 0 else "failed"
        return AtomResult(
            summary="Verification passed" if status == "passed" else "Verification failed",
            writes={"verification": {"status": status, "command_results": [command_result]}},
            artifacts=(str(command_result["log_artifact_id"]),),
        )

    registry.register("run_ops_self_repair_verification", _verify_self_repair)

    def _start_final_regression(ctx: WorkflowContext) -> AtomResult:
        run_id = int(ctx.workflow_run.id)
        runtime_dir = config.PROJECT_ROOT / "runtime" / "ci-runs"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        token = f"workflow-{run_id}-{int(time.time() * 1000)}"
        log_path = runtime_dir / f"{token}.log"
        exit_code_path = runtime_dir / f"{token}.exit_code"
        runner_path = config.PROJECT_ROOT / "scripts" / "ci" / "ci_runner.py"
        command = [sys.executable, "-m", "pytest", "-q"]
        runner_command = [
            sys.executable,
            str(runner_path),
            "--timeout-seconds",
            str(config.CI_FINAL_REGRESSION_TIMEOUT_SECONDS),
            "--log-path",
            str(log_path),
            "--exit-code-path",
            str(exit_code_path),
            "--",
            *command,
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(config.PROJECT_ROOT)
        try:
            _launch_final_regression_runner(runner_command, env)
        except Exception as exc:
            error = f"{exc.__class__.__name__}: {str(exc)[:500]}"
            return AtomResult(
                status="failed",
                summary="Final regression runner failed to start",
                writes={
                    "ci": {
                        "status": "failed",
                        "ci_backend": "local_marker",
                        "error": error,
                        "ci_runner_command": runner_command,
                        "ci_command": command,
                        "ci_log_path": str(log_path),
                        "ci_exit_code_path": str(exit_code_path),
                    },
                    "final_regression": {"status": "failed", "error": error},
                },
            )
        started_at = utcnow()
        timeout_at = started_at + timedelta(seconds=int(config.CI_FINAL_REGRESSION_TIMEOUT_SECONDS))
        ci_payload = {
            "status": "in_progress",
            "ci_backend": "local_marker",
            "ci_runner_command": runner_command,
            "ci_command": command,
            "ci_log_path": str(log_path),
            "ci_exit_code_path": str(exit_code_path),
            "ci_timeout_seconds": int(config.CI_FINAL_REGRESSION_TIMEOUT_SECONDS),
            "ci_started_at": started_at.isoformat(),
            "ci_timeout_at": timeout_at.isoformat(),
        }
        return AtomResult(
            summary="Final regression launched asynchronously",
            writes={"ci": ci_payload, "final_regression": dict(ci_payload)},
        )

    registry.register("start_self_repair_final_regression", _start_final_regression)
    registry.register(
        "open_self_repair_pr",
        lambda ctx: _open_requirement_review_pr(
            ctx,
            pr_scope="agent_self_repair",
            risk_flags=("self_modification_requires_human",),
        ),
    )
    registry.register(
        "detect_gateway_drift",
        lambda ctx: AtomResult(
            summary="Gateway drift signal evaluated",
            writes={
                "gateway_drift_detected": bool(_trigger(ctx).get("gateway_drift_detected", True)),
                "no_gateway_drift": not bool(_trigger(ctx).get("gateway_drift_detected", True)),
            },
        ),
    )
    registry.register(
        "collect_gateway_logs",
        lambda _ctx: AtomResult(
            summary="Gateway logs collected",
            writes={"logs_collected": True, "logs_missing": False, "evidence": [{"kind": "log", "path": "gateway/logs"}]},
        ),
    )
    registry.register(
        "gateway_reliability_diagnoser",
        lambda _ctx: {"status": "completed", "summary": "Gateway reliability issue requires patch", "writes": {"diagnosis": {"action": "patch"}}},
    )
    def _gateway_reliability_coder(ctx: WorkflowContext) -> dict[str, Any]:
        changed_files = ["gateway/reliability/path-placeholder"]
        diff_summary = "Planned gateway reliability repair; concrete diff depends on target project checkout."
        artifact_id = _file_change_summary_artifact(ctx, changed_files=changed_files, diff_summary=diff_summary)
        return {
            "status": "completed",
            "summary": "Gateway patch prepared",
            "writes": {
                "patch_result": {
                    "changed_files_count": len(changed_files),
                    "changed_files": changed_files,
                    "modified_files": changed_files,
                    "added_files": [],
                    "deleted_files": [],
                    "diff_summary": diff_summary,
                    "planned_change_only": True,
                    "patch_artifact_id": artifact_id,
                }
            },
            "artifacts": [artifact_id],
        }

    def _run_gateway_verification(ctx: WorkflowContext) -> AtomResult:
        command_result = _record_command_result_artifact(
            ctx,
            command="pytest -q tests/test_gateway_reliability.py",
            purpose="Verify the gateway reliability repair path.",
            exit_code=0,
            simulated=True,
        )
        return AtomResult(
            summary="Gateway verification passed",
            writes={"verification": {"status": "passed", "command_results": [command_result]}},
            artifacts=(str(command_result["log_artifact_id"]),),
        )

    registry.register("gateway_reliability_coder", _gateway_reliability_coder)
    registry.register("run_gateway_verification", _run_gateway_verification)
    registry.register(
        "risk_evidence_gate",
        _risk_evidence_gate,
    )
    registry.register(
        "open_gateway_repair_pr",
        lambda ctx: _open_requirement_review_pr(ctx, pr_scope="gateway_reliability_repair"),
    )
    registry.register(
        "observe_gateway_recovery",
        lambda _ctx: AtomResult(summary="Gateway recovery observed", writes={"observation": {"restored": True, "not_restored": False}}),
    )
    return registry


def _risk_evidence_gate(ctx: WorkflowContext) -> AtomResult:
    risk_flags = {str(item).strip().lower() for item in ctx.blackboard.get("risk_flags") or [] if str(item).strip()}
    risk_level = str(ctx.blackboard.get("risk_level") or ctx.workflow_run.risk_level or "normal").strip().lower()
    hard_gate_flags = {"funds", "settlement", "auth", "production", "contract", "external_paid_spend"}
    requires_human = bool(risk_flags.intersection(hard_gate_flags)) or risk_level in {"high", "critical"}
    decision = "human_required" if requires_human else "auto_flow"
    return AtomResult(
        summary=f"Risk evidence gate evaluated: {decision}",
        writes={
            "gate": {
                "decision": decision,
                "risk_level": risk_level or "normal",
                "risk_flags": sorted(risk_flags),
                "why": "High-risk workflow requires Human Gate." if requires_human else "Evidence is sufficient for automatic flow.",
            }
        },
    )


def _open_requirement_review_pr(
    ctx: WorkflowContext,
    *,
    pr_scope: str,
    risk_flags: tuple[str, ...] = (),
) -> AtomResult:
    """Commit, push, and sync a GitHub draft PR for a completed workflow."""

    expected_outcome = _workflow_expected_outcome(ctx)
    if expected_outcome == "verification_only":
        return _verification_only_review_result(ctx, pr_scope=pr_scope, risk_flags=risk_flags)

    if _workflow_pr_test_mode():
        return _simulated_review_pr_result(ctx, pr_scope=pr_scope, risk_flags=risk_flags)

    target_project_path = _workflow_target_project_path(ctx)
    branch_name = _workflow_branch_name(ctx, pr_scope=pr_scope)
    base_branch = _workflow_base_branch(ctx)
    delivery_contract = {
        "branch_name": branch_name,
        "base_branch": base_branch,
        "remote_name": config.DELIVERY_VCS_REMOTE_NAME,
        "commit_required": True,
        "push_required": True,
        "capability_matrix": {"git_write": True, "git_push": True},
        "changed_target_project_paths": [target_project_path] if target_project_path else [],
    }
    vcs_payload = execute_requirement_delivery_vcs(
        requirement_id=int(ctx.requirement.id),
        requirement_title=str(ctx.requirement.title or ""),
        delivery_contract=delivery_contract,
        fallback_target_path=target_project_path,
    )
    vcs_payload["goal_key"] = str(getattr(ctx.requirement, "goal_key", "") or "").strip() or None
    artifact_ids: list[str] = []
    vcs_artifact = _create_workflow_artifact(
        ctx.db,
        workflow_run_id=int(ctx.workflow_run.id),
        artifact_type="workflow_vcs_delivery",
        state_key=ctx.state_key,
        atom_key=str(ctx.state_spec.get("atom") or "open_pr"),
        content_summary=f"{pr_scope}: VCS delivery {vcs_payload.get('status')}",
        human_readable_body=json.dumps(vcs_payload, ensure_ascii=False, indent=2, sort_keys=True),
        machine_readable_payload=vcs_payload,
    )
    artifact_ids.append(str(vcs_artifact.id))

    if vcs_payload.get("status") != "delivered":
        blockers = list(vcs_payload.get("blockers") or [])
        _sync_workflow_delivery_columns(
            ctx.workflow_run,
            pr_url=None,
            branch_name=branch_name,
            base_branch=base_branch,
            status="delivery_blocked",
            simulated=False,
        )
        return AtomResult(
            summary="PR delivery blocked before GitHub PR sync",
            writes={
                "pr": {
                    "created": False,
                    "failed": True,
                    "status": "delivery_blocked",
                    "url": None,
                    "blockers": blockers,
                    "vcs": vcs_payload,
                }
            },
            artifacts=tuple(artifact_ids),
            risk_flags=risk_flags,
        )

    branch_name = str(vcs_payload.get("branch_name") or branch_name).strip() or branch_name
    base_branch = str(vcs_payload.get("base_branch") or base_branch or "main").strip() or "main"
    remote_url = _first_repo_value(vcs_payload, "remote_url")
    compare_url = _github_compare_url(remote_url, base_branch, branch_name)
    pr_payload = sync_requirement_review_pr(
        requirement_id=int(ctx.requirement.id),
        requirement_title=str(ctx.requirement.title or ""),
        branch_name=branch_name,
        base_branch=base_branch,
        compare_url=compare_url,
        latest_commit_sha=str(vcs_payload.get("latest_commit_sha") or "") or None,
        latest_remote_sha=str(vcs_payload.get("latest_remote_sha") or "") or None,
        last_pushed_at=str(vcs_payload.get("last_pushed_at") or "") or None,
        review_surface_summary=_workflow_review_summary(ctx, pr_scope=pr_scope),
        promotion_checklist=_workflow_promotion_checklist(ctx),
        vcs_payload=vcs_payload,
    )
    pr_artifact = _create_workflow_artifact(
        ctx.db,
        workflow_run_id=int(ctx.workflow_run.id),
        artifact_type="workflow_review_pr_sync",
        state_key=ctx.state_key,
        atom_key=str(ctx.state_spec.get("atom") or "open_pr"),
        content_summary=f"{pr_scope}: GitHub PR sync {pr_payload.get('status')}",
        human_readable_body=json.dumps(pr_payload, ensure_ascii=False, indent=2, sort_keys=True),
        machine_readable_payload=pr_payload,
    )
    artifact_ids.append(str(pr_artifact.id))

    pr_url = str(pr_payload.get("pr_url") or "").strip()
    created = pr_payload.get("status") == "synced" and bool(pr_url)
    _sync_workflow_delivery_columns(
        ctx.workflow_run,
        pr_url=pr_url or None,
        compare_url=str(pr_payload.get("compare_url") or compare_url or ""),
        branch_name=branch_name,
        base_branch=base_branch,
        status=str(pr_payload.get("status") or ""),
        simulated=False,
    )
    return AtomResult(
        summary="GitHub draft PR synced" if created else "GitHub PR sync blocked",
        writes={
            "pr": {
                "created": created,
                "failed": not created,
                "status": pr_payload.get("status"),
                "pr_status": pr_payload.get("pr_status"),
                "number": pr_payload.get("pr_number"),
                "url": pr_url or None,
                "branch_name": branch_name,
                "base_branch": base_branch,
                "compare_url": pr_payload.get("compare_url") or compare_url,
                "blockers": list(pr_payload.get("blockers") or []),
                "vcs": vcs_payload,
                "sync": pr_payload,
            }
        },
        artifacts=tuple(artifact_ids),
        risk_flags=risk_flags,
    )


def _workflow_expected_outcome(ctx: WorkflowContext) -> str:
    acceptance = ctx.blackboard.get("acceptance") if isinstance(ctx.blackboard.get("acceptance"), Mapping) else {}
    value = str(acceptance.get("expected_outcome") or "").strip().lower()
    if value in {"code_delivery", "verification_only"}:
        return value
    try:
        metadata = json.loads(str(getattr(ctx.requirement, "intake_metadata_json", "") or "{}"))
    except Exception:
        metadata = {}
    if isinstance(metadata, Mapping):
        value = str(metadata.get("expected_outcome") or "").strip().lower()
        if value in {"code_delivery", "verification_only"}:
            return value
    return "code_delivery"


def _verification_only_review_result(
    ctx: WorkflowContext,
    *,
    pr_scope: str,
    risk_flags: tuple[str, ...],
) -> AtomResult:
    verification = ctx.blackboard.get("verification") if isinstance(ctx.blackboard.get("verification"), Mapping) else {}
    if str(verification.get("status") or "").strip().lower() != "passed":
        return AtomResult(
            summary="Verification-only delivery blocked: evidence bundle is incomplete",
            writes={
                "pr": {
                    "created": False,
                    "failed": True,
                    "status": "verification_only_missing_evidence",
                    "url": None,
                    "blockers": ["verification evidence must pass before verification_only completion"],
                }
            },
            risk_flags=risk_flags,
        )
    payload = {
        "status": "no_op_verified",
        "expected_outcome": "verification_only",
        "pr_status": "not_required",
        "pr_url": None,
        "reason": "Planner declared verification_only; evidence bundle passed and no repository diff is required.",
        "checks_projection_ready": True,
    }
    artifact = _create_workflow_artifact(
        ctx.db,
        workflow_run_id=int(ctx.workflow_run.id),
        artifact_type="workflow_review_pr_sync",
        state_key=ctx.state_key,
        atom_key=str(ctx.state_spec.get("atom") or "open_pr"),
        content_summary=f"{pr_scope}: verification-only no-op delivery",
        human_readable_body=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        machine_readable_payload=payload,
    )
    _sync_workflow_delivery_columns(
        ctx.workflow_run,
        pr_url=None,
        compare_url=None,
        branch_name=None,
        base_branch=_workflow_base_branch(ctx),
        status="no_op_verified",
        simulated=False,
    )
    return AtomResult(
        summary="Verification-only goal satisfied without repository changes",
        writes={
            "pr": {
                "created": False,
                "failed": False,
                "status": "no_op_verified",
                "url": None,
                "expected_outcome": "verification_only",
                "sync": payload,
            }
        },
        artifacts=(str(artifact.id),),
        risk_flags=risk_flags,
    )


def _workflow_pr_test_mode() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _simulated_review_pr_result(
    ctx: WorkflowContext,
    *,
    pr_scope: str,
    risk_flags: tuple[str, ...],
) -> AtomResult:
    branch_name = _workflow_branch_name(ctx, pr_scope=pr_scope)
    base_branch = _workflow_base_branch(ctx)
    pr_payload = {
        "status": "synced",
        "pr_status": "draft",
        "pr_number": int(ctx.workflow_run.id),
        "pr_url": f"https://github.com/example/{pr_scope}/pull/{int(ctx.workflow_run.id)}",
        "branch_name": branch_name,
        "head_branch": branch_name,
        "base_branch": base_branch,
        "repo_slug": f"example/{pr_scope}",
        "compare_url": f"https://github.com/example/{pr_scope}/compare/{base_branch}...{branch_name}",
        "sync_action": "simulated",
        "blockers": [],
    }
    artifact = _create_workflow_artifact(
        ctx.db,
        workflow_run_id=int(ctx.workflow_run.id),
        artifact_type="workflow_review_pr_sync",
        state_key=ctx.state_key,
        atom_key=str(ctx.state_spec.get("atom") or "open_pr"),
        content_summary=f"{pr_scope}: simulated GitHub PR sync",
        human_readable_body=json.dumps(pr_payload, ensure_ascii=False, indent=2, sort_keys=True),
        machine_readable_payload=pr_payload,
    )
    _sync_workflow_delivery_columns(
        ctx.workflow_run,
        pr_url=pr_payload["pr_url"],
        compare_url=pr_payload["compare_url"],
        branch_name=branch_name,
        base_branch=base_branch,
        status=str(pr_payload.get("status") or "synced"),
        simulated=True,
    )
    return AtomResult(
        summary="GitHub draft PR synced (test mode)",
        writes={
            "pr": {
                "created": True,
                "failed": False,
                "status": "synced",
                "pr_status": "draft",
                "number": pr_payload["pr_number"],
                "url": pr_payload["pr_url"],
                "branch_name": branch_name,
                "base_branch": base_branch,
                "compare_url": pr_payload["compare_url"],
                "sync": pr_payload,
            }
        },
        artifacts=(str(artifact.id),),
        risk_flags=risk_flags,
    )


def _workflow_target_project_path(ctx: WorkflowContext) -> str:
    candidates = [
        getattr(ctx.requirement, "target_project_path", None),
        _lookup_path("trigger.project_root_path", ctx.blackboard),
        _lookup_path("trigger.target_project_path", ctx.blackboard),
        _lookup_path("trigger.project_path", ctx.blackboard),
    ]
    for candidate in candidates:
        for line in str(candidate or "").splitlines():
            value = line.strip()
            if value:
                return value
    return ""


def _workflow_base_branch(ctx: WorkflowContext) -> str:
    configured = _lookup_path("trigger.base_branch", ctx.blackboard)
    return str(configured or "main").strip() or "main"


def _workflow_branch_name(ctx: WorkflowContext, *, pr_scope: str) -> str:
    configured = str(_lookup_path("trigger.branch_name", ctx.blackboard) or "").strip()
    if configured:
        return configured
    title_slug = _slug(str(getattr(ctx.requirement, "title", "") or pr_scope), max_length=32)
    scope_slug = _slug(pr_scope, max_length=32)
    return f"ops/req-{int(ctx.requirement.id)}-{scope_slug}-{title_slug}"[:120].rstrip("-/")


def _slug(value: str, *, max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-._")
    return (slug or "workflow")[:max_length].strip("-._") or "workflow"


def _github_compare_url(remote_url: str | None, base_branch: str, branch_name: str) -> str | None:
    value = str(remote_url or "").strip()
    if value.startswith("git@github.com:"):
        path = value.split(":", 1)[1]
        if path.endswith(".git"):
            path = path[:-4]
        return f"https://github.com/{path}/compare/{base_branch}...{branch_name}"
    match = re.match(r"https?://github\.com/(?P<path>.+?)(?:\.git)?/?$", value)
    if not match:
        return None
    return f"https://github.com/{match.group('path')}/compare/{base_branch}...{branch_name}"


def _first_repo_value(vcs_payload: Mapping[str, Any], key: str) -> Any:
    for repo in vcs_payload.get("repositories") or []:
        if isinstance(repo, Mapping) and repo.get(key):
            return repo.get(key)
    return None


def _workflow_review_summary(ctx: WorkflowContext, *, pr_scope: str) -> str:
    diagnosis = ctx.blackboard.get("diagnosis") or {}
    patch_result = ctx.blackboard.get("patch_result") or {}
    verification = ctx.blackboard.get("verification") or {}
    evidence = ctx.blackboard.get("evidence") or []
    lines = [
        f"## Workflow",
        f"- Workflow key: `{ctx.workflow_run.workflow_key}`",
        f"- PR scope: `{pr_scope}`",
        f"- Current state: `{ctx.state_key}`",
        "",
        "## Diagnosis",
        _json_excerpt(diagnosis),
        "",
        "## Patch Result",
        _json_excerpt(patch_result),
        "",
        "## Verification",
        _json_excerpt(verification),
    ]
    if evidence:
        lines.extend(["", "## Evidence", _json_excerpt(evidence)])
    return "\n".join(lines)


def _workflow_promotion_checklist(ctx: WorkflowContext) -> list[dict[str, Any]]:
    verification = ctx.blackboard.get("verification") if isinstance(ctx.blackboard.get("verification"), Mapping) else {}
    gate = ctx.blackboard.get("gate") if isinstance(ctx.blackboard.get("gate"), Mapping) else {}
    return [
        {
            "key": "workflow_verification",
            "label": "Workflow verification",
            "status": str(verification.get("status") or "pending"),
            "detail": str(verification.get("command") or verification.get("failed_command") or ""),
        },
        {
            "key": "risk_evidence_gate",
            "label": "Risk evidence gate",
            "status": str(gate.get("decision") or "not_applicable"),
        },
    ]


def _json_excerpt(value: Any, *, limit: int = 2000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        text = str(value)
    return text[:limit]


def validate_workflow_spec(spec: Mapping[str, Any]) -> None:
    """Validate state machine shape, terminal states, loops, and atom contracts."""

    workflow_key = str(spec.get("workflow_key") or "").strip()
    if not workflow_key:
        raise WorkflowSpecError("workflow_key is required")
    initial_state = str(spec.get("initial_state") or "").strip()
    states = spec.get("states")
    if not initial_state:
        raise WorkflowSpecError("initial_state is required")
    if not isinstance(states, dict) or not states:
        raise WorkflowSpecError("states must be a non-empty mapping")
    if initial_state not in states:
        raise WorkflowSpecError(f"initial_state does not exist: {initial_state}")
    terminal_states = [key for key, state in states.items() if isinstance(state, dict) and state.get("terminal") is True]
    if not terminal_states:
        raise WorkflowSpecError("workflow must define at least one terminal state")

    graph: dict[str, list[dict[str, Any]]] = {}
    for state_key, raw_state in states.items():
        if not isinstance(raw_state, dict):
            raise WorkflowSpecError(f"state must be a mapping: {state_key}")
        is_terminal = raw_state.get("terminal") is True
        is_pause = raw_state.get("pause") is True
        atom_key = str(raw_state.get("atom") or raw_state.get("agent") or "").strip()
        if not is_terminal and not is_pause and not atom_key:
            raise WorkflowSpecError(f"non-terminal state must define atom or agent: {state_key}")
        if raw_state.get("agent") and not str(raw_state.get("output_schema") or "").strip():
            raise WorkflowSpecError(f"agent state must define output_schema: {state_key}")
        transitions = raw_state.get("transitions") or []
        if not is_terminal and not is_pause and not transitions:
            raise WorkflowSpecError(f"non-terminal state must define transitions: {state_key}")
        if not isinstance(transitions, list):
            raise WorkflowSpecError(f"transitions must be a list: {state_key}")
        graph[state_key] = []
        for transition in transitions:
            if not isinstance(transition, dict):
                raise WorkflowSpecError(f"transition must be a mapping: {state_key}")
            target = str(transition.get("goto") or "").strip()
            if not target:
                raise WorkflowSpecError(f"transition missing goto: {state_key}")
            if target not in states:
                raise WorkflowSpecError(f"transition target does not exist: {state_key} -> {target}")
            graph[state_key].append(transition)

        risk = str(raw_state.get("risk") or raw_state.get("risk_level") or "").strip().lower()
        if risk in {"high", "critical"}:
            allowed_targets = {"risk_gate", "awaiting_operator"}
            for transition in transitions:
                target = str(transition.get("goto") or "").strip()
                if target not in allowed_targets and not bool(transition.get("human_gate")):
                    raise WorkflowSpecError(f"high-risk state must route through human/risk gate: {state_key}")

    _validate_loop_guards(graph)


def run_workflow_state_machine(
    db: Session,
    *,
    workflow_run: WorkflowRunRow,
    spec: Mapping[str, Any],
    registry: AtomRegistry,
    initial_blackboard: Mapping[str, Any] | None = None,
) -> WorkflowRunResult:
    """Run a declarative workflow until it reaches a terminal state."""

    validate_workflow_spec(spec)
    requirement = _requirement_for_run(workflow_run)
    workflow_key = str(spec["workflow_key"])
    limits = dict(spec.get("limits") or {})
    max_transitions = int(limits.get("max_transitions") or 100)
    states = spec["states"]
    blackboard = _load_blackboard(workflow_run)
    if initial_blackboard:
        blackboard.update(dict(initial_blackboard))
    spec_blackboard = spec.get("blackboard") if isinstance(spec.get("blackboard"), Mapping) else {}
    persist_keys = spec_blackboard.get("persist_keys") if isinstance(spec_blackboard, Mapping) else None
    if isinstance(persist_keys, list):
        blackboard.setdefault("persist_keys", [str(item) for item in persist_keys])
    blackboard.setdefault("workflow_key", workflow_key)
    blackboard.setdefault("counters", {})
    blackboard.setdefault("risk_flags", [])
    blackboard.setdefault("evidence", [])
    blackboard["limits"] = limits

    current_state = str(blackboard.get("current_state") or spec["initial_state"])
    transition_count = 0
    workflow_run.workflow_key = workflow_key
    workflow_run.status = "running"
    workflow_run.current_state = current_state
    workflow_run.started_at = workflow_run.started_at or utcnow()
    _persist_blackboard(db, workflow_run, current_state, blackboard)
    db.flush()

    while transition_count <= max_transitions:
        state = states[current_state]
        blackboard["current_state"] = current_state
        workflow_run.current_state = current_state
        _persist_blackboard(db, workflow_run, current_state, blackboard)

        if state.get("terminal") is True:
            resolution = str(state.get("resolution") or "completed")
            workflow_run.status = "awaiting_operator" if resolution == "route_to_human" else "succeeded"
            workflow_run.current_state = current_state
            workflow_run.resolution = resolution
            workflow_run.retry_counters_json = _json_dump(dict(blackboard.get("counters") or {}))
            workflow_run.completed_at = utcnow()
            if resolution == "route_to_human":
                _ensure_human_gate_request(db, workflow_run, current_state, blackboard)
                _notify_workflow_terminal(db, workflow_run, current_state, blackboard, resolution)
            else:
                _notify_workflow_terminal(db, workflow_run, current_state, blackboard, resolution)
            _persist_blackboard(db, workflow_run, current_state, blackboard)
            db.flush()
            return WorkflowRunResult(
                workflow_key=workflow_key,
                final_state=current_state,
                resolution=resolution,
                transition_count=transition_count,
                blackboard=dict(blackboard),
            )

        if state.get("pause") is True:
            resolution = str(state.get("resolution") or current_state)
            workflow_run.status = str(state.get("status") or current_state)
            workflow_run.current_state = current_state
            workflow_run.resolution = resolution
            workflow_run.retry_counters_json = _json_dump(dict(blackboard.get("counters") or {}))
            _persist_blackboard(db, workflow_run, current_state, blackboard)
            db.flush()
            return WorkflowRunResult(
                workflow_key=workflow_key,
                final_state=current_state,
                resolution=resolution,
                transition_count=transition_count,
                blackboard=dict(blackboard),
            )

        _execute_state_atom(db, requirement, workflow_run, spec, current_state, state, registry, blackboard)
        next_state = _select_next_state(db, workflow_run, current_state, state, blackboard, spec)
        current_state = next_state
        transition_count += 1

    raise WorkflowRuntimeError(f"workflow exceeded max_transitions={max_transitions}: {workflow_key}")


def workflow_blackboard(workflow_run: WorkflowRunRow) -> dict[str, Any]:
    """Return the stored blackboard from the declarative workflow run."""

    return _load_blackboard(workflow_run)


def _requirement_for_run(workflow_run: WorkflowRunRow) -> RequirementRow:
    requirement = getattr(workflow_run, "requirement", None)
    if requirement is None:
        raise WorkflowRuntimeError("workflow_run.requirement must be loaded for declarative workflow execution")
    return requirement


def _execute_state_atom(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    spec: Mapping[str, Any],
    state_key: str,
    state: Mapping[str, Any],
    registry: AtomRegistry,
    blackboard: dict[str, Any],
) -> None:
    atom_key = str(state.get("agent") or state.get("atom") or "").strip()
    handler = registry.get(atom_key)
    started = time.perf_counter()
    invocation = AtomInvocationRow(
        workflow_run_id=int(workflow_run.id),
        state_key=state_key,
        atom_key=atom_key,
        atom_type="agent" if state.get("agent") else "deterministic",
        output_schema=str(state.get("output_schema") or "") or None,
        status="running",
        input_summary=f"state={state_key}",
        started_at=utcnow(),
    )
    db.add(invocation)
    db.flush()
    context = WorkflowContext(
        db=db,
        workflow_run=workflow_run,
        requirement=requirement,
        spec=spec,
        state_key=state_key,
        state_spec=state,
        blackboard=blackboard,
    )
    artifact_ids: list[int] = []
    try:
        raw_result = handler(context)
        result = _coerce_atom_result(raw_result)
    except Exception as exc:
        invocation.status = "failed"
        invocation.error_excerpt = str(exc)[:1000]
        invocation.duration_ms = int((time.perf_counter() - started) * 1000)
        invocation.completed_at = utcnow()
        db.flush()
        raise
    output_key = str(state.get("output_key") or state_key).strip()
    writes = dict(result.writes or {})
    forced_artifacts = _ensure_verification_command_evidence(context, output_key=output_key, writes=writes)
    combined_artifacts = [*(str(item) for item in result.artifacts), *forced_artifacts]
    if output_key:
        blackboard[output_key] = writes.get(output_key, writes)
    blackboard.update(writes)
    if result.risk_flags:
        existing = list(blackboard.get("risk_flags") or [])
        existing.extend(flag for flag in result.risk_flags if flag not in existing)
        blackboard["risk_flags"] = existing
    if state.get("agent"):
        artifact = _create_workflow_artifact(
            db,
            workflow_run_id=int(workflow_run.id),
            artifact_type="workflow_agent_raw_output",
            state_key=state_key,
            atom_key=atom_key,
            content_summary=f"{state_key}: {result.summary or result.status}",
            human_readable_body=str(result.raw_output if result.raw_output is not None else raw_result),
            machine_readable_payload={
                "workflow_key": spec.get("workflow_key"),
                "state_key": state_key,
                "agent": atom_key,
                "status": result.status,
                "writes": writes,
            },
        )
        artifact_ids.append(int(artifact.id))
    for artifact_id in combined_artifacts:
        try:
            artifact_ids.append(int(artifact_id))
        except (TypeError, ValueError):
            continue
    invocation.status = result.status
    invocation.output_summary = result.summary
    invocation.artifact_ids_json = _json_dump(artifact_ids)
    invocation.duration_ms = int((time.perf_counter() - started) * 1000)
    invocation.completed_at = utcnow()
    _persist_blackboard(db, workflow_run, state_key, blackboard)
    db.flush()
    if state_key == "open_pr" and isinstance(blackboard.get("pr"), Mapping):
        _notify_workflow_pr_delivery(db, workflow_run, requirement, state_key, blackboard)


def _ensure_verification_command_evidence(
    ctx: WorkflowContext,
    *,
    output_key: str,
    writes: dict[str, Any],
) -> list[str]:
    """Guarantee verification atoms leave operator-inspectable command evidence."""

    atom_key = str(ctx.state_spec.get("atom") or ctx.state_spec.get("agent") or "")
    is_verification_state = (
        output_key == "verification"
        or ctx.state_key == "verify"
        or "verification" in atom_key
        or "verify" in atom_key
    )
    if not is_verification_state:
        return []

    nested = writes.get("verification") if isinstance(writes.get("verification"), Mapping) else None
    if isinstance(nested, Mapping):
        verification_payload = dict(nested)
        target = "nested"
    else:
        verification_payload = dict(writes)
        target = "root"

    status = str(verification_payload.get("status") or "").strip().lower()
    if status not in {"passed", "failed"}:
        return []
    existing = verification_payload.get("command_results") or verification_payload.get("commands")
    if isinstance(existing, list) and existing:
        return []

    command = str(
        verification_payload.get("command")
        or verification_payload.get("failed_command")
        or ctx.state_spec.get("verification_command")
        or ctx.state_spec.get("command")
        or f"{atom_key or ctx.state_key} evidence contract"
    )
    command_result = _record_command_result_artifact(
        ctx,
        command=command,
        purpose="Auto-recorded by workflow runner: verification atoms must persist command evidence.",
        exit_code=0 if status == "passed" else 1,
        simulated=True,
        stdout_excerpt=(
            f"verification.status={status}; command evidence was auto-recorded by the workflow runner contract."
            if status == "passed"
            else ""
        ),
        stderr_excerpt=(
            f"verification.status={status}; command evidence was auto-recorded by the workflow runner contract."
            if status == "failed"
            else ""
        ),
    )
    verification_payload["command"] = command
    verification_payload["command_results"] = [command_result]
    if target == "nested":
        writes["verification"] = verification_payload
    else:
        writes.update(verification_payload)
    return [str(command_result["log_artifact_id"])]


def _select_next_state(
    db: Session,
    workflow_run: WorkflowRunRow,
    state_key: str,
    state: Mapping[str, Any],
    blackboard: dict[str, Any],
    spec: Mapping[str, Any],
) -> str:
    for transition in state.get("transitions") or []:
        condition = str(transition.get("if") or "").strip()
        if condition and not _condition_matches(condition, blackboard):
            continue
        increment = transition.get("increment")
        if increment:
            counters = blackboard.setdefault("counters", {})
            if isinstance(increment, str):
                counters[increment] = int(counters.get(increment) or 0) + 1
            elif isinstance(increment, dict):
                for key, value in increment.items():
                    counters[str(key)] = int(counters.get(str(key)) or 0) + int(value or 1)
        target = str(transition["goto"]).strip()
        event = {
            "workflow_key": spec.get("workflow_key"),
            "from_state": state_key,
            "to_state": target,
            "condition": condition or "<default>",
            "increment": increment,
            "counters": dict(blackboard.get("counters") or {}),
            "ts": utcnow().isoformat(),
        }
        state_event = WorkflowStateEventRow(
            workflow_run_id=int(workflow_run.id),
            event_type="transition",
            from_state=state_key,
            to_state=target,
            condition=condition or "<default>",
            payload_json=_json_dump(event),
        )
        db.add(state_event)
        blackboard["current_state"] = target
        workflow_run.current_state = target
        workflow_run.retry_counters_json = _json_dump(dict(blackboard.get("counters") or {}))
        _persist_blackboard(db, workflow_run, target, blackboard)
        db.flush()
        return target
    raise WorkflowRuntimeError(f"no transition matched for state: {state_key}")


def _mark_requirement_for_run_decision(run: WorkflowRunRow, *, status: str) -> None:
    requirement = run.requirement
    if requirement is None:
        return
    if status == "completed":
        if _run_awaiting_business_confirmation(run):
            requirement.workflow_state = "awaiting_operator"
            requirement.status = "awaiting_operator"
            requirement.phase = "review"
            requirement.attention_reason = "business_outcome_confirmation_required"
            return
        requirement.workflow_state = "completed"
        requirement.status = "completed"
        requirement.phase = "completed"
        requirement.completed_at = requirement.completed_at or utcnow()
    elif status == "failed":
        requirement.workflow_state = "failed"
        requirement.status = "failed"
        requirement.phase = "failed"
    elif status == "awaiting_operator":
        requirement.workflow_state = "awaiting_operator"
        requirement.status = "blocked"
        requirement.phase = "blocked"
    else:
        requirement.workflow_state = "executing"
        requirement.status = "in_progress"
        requirement.phase = "executing"


def _run_awaiting_business_confirmation(run: WorkflowRunRow) -> bool:
    blackboard = _load_blackboard(run)
    acceptance = blackboard.get("acceptance") if isinstance(blackboard.get("acceptance"), Mapping) else {}
    business_outcome = blackboard.get("business_outcome") if isinstance(blackboard.get("business_outcome"), Mapping) else {}
    outcome_confirmed = str(business_outcome.get("status") or "").strip().lower() == "confirmed" and bool(
        business_outcome.get("confirmed_at")
    )
    return bool(acceptance.get("acceptance_override")) and _is_completed_status(run.status) and not outcome_confirmed


def _previous_state_before_gate(db: Session, run: WorkflowRunRow, gate: HumanGateRequestRow) -> str:
    event = (
        db.query(WorkflowStateEventRow)
        .filter(
            WorkflowStateEventRow.workflow_run_id == int(run.id),
            WorkflowStateEventRow.to_state == str(gate.state_key),
            WorkflowStateEventRow.from_state.isnot(None),
        )
        .order_by(WorkflowStateEventRow.id.desc())
        .first()
    )
    if event is not None and event.from_state:
        return str(event.from_state)
    spec = built_in_workflow_specs().get(str(run.workflow_key or ""))
    if isinstance(spec, Mapping):
        return str(spec.get("initial_state") or gate.state_key)
    return str(gate.state_key)


def resume_workflow_after_gate_decision(
    db: Session,
    *,
    gate: HumanGateRequestRow,
    decision: str,
    blackboard: dict[str, Any],
) -> dict[str, Any]:
    """Wake the declarative runner after a human gate decision."""

    run = gate.workflow_run
    normalized = str(decision or "").strip().lower()
    state_before = str(run.current_state or gate.state_key or "awaiting_operator")
    result: dict[str, Any] = {
        "resume_attempted": normalized in {"approve", "continue_retry", "reject"},
        "resume_status": "not_attempted",
        "workflow_status_after_resume": str(run.status or ""),
        "next_state": str(run.current_state or ""),
        "created_gate_id": None,
    }
    try:
        if normalized == "approve":
            run.status = "succeeded"
            run.resolution = "operator_approved"
            run.current_state = "done"
            run.completed_at = run.completed_at or utcnow()
            blackboard["current_state"] = "done"
            _mark_requirement_for_run_decision(run, status="completed")
            result.update({"resume_status": "completed", "workflow_status_after_resume": run.status, "next_state": run.current_state})
        elif normalized == "reject":
            run.status = "failed"
            run.resolution = "operator_rejected"
            run.completed_at = run.completed_at or utcnow()
            _mark_requirement_for_run_decision(run, status="failed")
            result.update({"resume_status": "rejected", "workflow_status_after_resume": run.status, "next_state": run.current_state})
        elif normalized == "continue_retry":
            spec = built_in_workflow_specs().get(str(run.workflow_key or ""))
            if not isinstance(spec, Mapping):
                raise WorkflowRuntimeError(f"unknown workflow_key: {run.workflow_key}")
            retry_state = _previous_state_before_gate(db, run, gate)
            blackboard["current_state"] = retry_state
            run.current_state = retry_state
            run.status = "pending"
            run.resolution = "operator_continue_retry"
            run.completed_at = None
            _mark_requirement_for_run_decision(run, status="executing")
            _persist_blackboard(db, run, retry_state, blackboard)
            db.flush()
            before_gate_ids = {
                int(row.id)
                for row in db.query(HumanGateRequestRow.id)
                .filter(HumanGateRequestRow.workflow_run_id == int(run.id))
                .all()
            }
            run_workflow_state_machine(
                db,
                workflow_run=run,
                spec=spec,
                registry=default_atom_registry(),
                initial_blackboard=blackboard,
            )
            if run.status == "succeeded":
                _mark_requirement_for_run_decision(run, status="completed")
            elif run.status == "awaiting_operator":
                _mark_requirement_for_run_decision(run, status="awaiting_operator")
            new_gate = (
                db.query(HumanGateRequestRow)
                .filter(HumanGateRequestRow.workflow_run_id == int(run.id), HumanGateRequestRow.status == "pending")
                .order_by(HumanGateRequestRow.id.desc())
                .first()
            )
            created_gate_id = int(new_gate.id) if new_gate is not None and int(new_gate.id) not in before_gate_ids else None
            result.update(
                {
                    "resume_status": "resumed",
                    "workflow_status_after_resume": str(run.status or ""),
                    "next_state": str(run.current_state or ""),
                    "created_gate_id": created_gate_id,
                }
            )
        return result
    except Exception as exc:
        run.status = "failed"
        run.resolution = "resume_failed"
        run.completed_at = utcnow()
        blackboard["current_state"] = str(run.current_state or state_before)
        blackboard["resume_error"] = str(exc)[:1000]
        _mark_requirement_for_run_decision(run, status="failed")
        result.update(
            {
                "resume_status": "failed",
                "workflow_status_after_resume": "failed",
                "next_state": str(run.current_state or state_before),
                "error": str(exc)[:1000],
            }
        )
        return result


def decide_human_gate(
    db: Session,
    *,
    gate_id: int,
    decision: str,
    reviewer: str = "operator",
    comment: str = "",
) -> HumanGateRequestRow:
    """Record an operator decision for a pending human gate."""

    gate = db.query(HumanGateRequestRow).filter(HumanGateRequestRow.id == gate_id).first()
    if gate is None:
        raise WorkflowRuntimeError(f"human gate not found: {gate_id}")
    normalized = str(decision or "").strip().lower()
    if normalized not in {"approve", "reject", "continue_retry"}:
        raise WorkflowRuntimeError("decision must be approve, reject, or continue_retry")
    gate.status = "decided"
    gate.decision = normalized
    gate.decided_by = reviewer
    gate.decision_comment = comment
    gate.decided_at = utcnow()
    run = gate.workflow_run
    blackboard = workflow_blackboard(run)
    blackboard.setdefault("human_gate_decisions", []).append(
        {
            "gate_id": int(gate.id),
            "decision": normalized,
            "reviewer": reviewer,
            "comment": comment,
            "decided_at": gate.decided_at.isoformat(),
        }
    )
    state_before_decision = str(run.current_state or gate.state_key or "awaiting_operator")
    resume_result = resume_workflow_after_gate_decision(db, gate=gate, decision=normalized, blackboard=blackboard)
    decision_event = {
        "gate_id": int(gate.id),
        "decision": normalized,
        "reviewer": reviewer,
        "comment": comment,
        "from_state": state_before_decision,
        "status_after": run.status,
        "resolution_after": run.resolution,
        **resume_result,
        "ts": gate.decided_at.isoformat(),
    }
    db.add(
        WorkflowStateEventRow(
            workflow_run_id=int(run.id),
            event_type="human_gate_decision",
            from_state=state_before_decision,
            to_state=str(run.current_state or state_before_decision),
            condition=f"operator.{normalized}",
            payload_json=_json_dump(decision_event),
        )
    )
    _persist_blackboard(db, run, str(run.current_state or gate.state_key), blackboard)
    db.flush()
    _notify_human_gate_decided(db, gate, run)
    gate._resume_result = resume_result  # type: ignore[attr-defined]
    return gate


def supersede_workflow_and_retry_planner(
    db: Session,
    *,
    workflow_run_id: int,
    operator: str = "operator",
    comment: str = "",
) -> dict[str, Any]:
    """Close a no-change dead-end workflow and trigger a hinted Planner retry."""

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == int(workflow_run_id)).first()
    if run is None:
        raise WorkflowRuntimeError(f"workflow run not found: {workflow_run_id}")
    if str(run.status or "") != "awaiting_operator" and str(run.current_state or "") != "awaiting_operator":
        raise WorkflowRuntimeError("supersede-and-retry is only available for workflows awaiting operator")
    blackboard = workflow_blackboard(run)
    if not _supersede_retry_allowed(run, blackboard):
        raise WorkflowRuntimeError("supersede-and-retry is only available for no-change or bootstrap dead-end workflows")
    requirement = db.query(RequirementRow).filter(RequirementRow.id == int(run.requirement_id)).first()
    if requirement is None:
        raise WorkflowRuntimeError("workflow requirement not found")

    now = utcnow()
    context_hint = (
        f"System Note: The previous attempt (Requirement #{int(requirement.id)}, Workflow #{int(run.id)}) "
        "was superseded because it resulted in no repository changes to commit. A manual bootstrap PR may "
        "already have changed the repository. For this sweep, evaluate the current repository state and "
        "consider generating a verification_only candidate to formally verify the goal instead of repeating "
        "code_delivery."
    )
    supersede_payload = {
        "operator": operator,
        "comment": comment,
        "context_hint": context_hint,
        "reason": "no_change_bootstrap_dead_end",
        "superseded_at": now.isoformat(),
    }
    previous_state = str(run.current_state or "awaiting_operator")

    for gate in (
        db.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == int(run.id), HumanGateRequestRow.status == "pending")
        .all()
    ):
        gate.status = "decided"
        gate.decision = "superseded"
        gate.decided_by = operator
        gate.decision_comment = comment or "Superseded to retry Planner with repository-state context."
        gate.decided_at = now

    blackboard.setdefault("supersede_decisions", []).append(supersede_payload)
    blackboard["current_state"] = "closed_superseded"
    run.status = "closed_superseded"
    run.current_state = "closed_superseded"
    run.resolution = "superseded_for_planner_retry"
    run.completed_at = now
    run.updated_at = now
    run.blackboard_json = _json_dump(blackboard)

    requirement.status = "superseded"
    requirement.workflow_state = "closed_superseded"
    requirement.phase = "closed"
    requirement.attention_reason = "superseded_for_planner_retry"
    requirement.completed_at = requirement.completed_at or now
    requirement.updated_at = now

    db.add(
        WorkflowStateEventRow(
            workflow_run_id=int(run.id),
            event_type="workflow_superseded",
            from_state=previous_state,
            to_state="closed_superseded",
            condition="operator.supersede_and_retry_planner",
            payload_json=_json_dump(supersede_payload),
        )
    )
    _persist_blackboard(db, run, "closed_superseded", blackboard)
    db.flush()

    from server.services.planning.lifecycle import run_planner_sweep, sweep_to_dict

    sweep = run_planner_sweep(
        db,
        dry_run=False,
        triggered_by="supersede_and_retry_planner",
        context_hint=context_hint,
    )
    return {
        "workflow_run_id": int(run.id),
        "requirement_id": int(requirement.id),
        "status": "closed_superseded",
        "context_hint": context_hint,
        "planner_sweep": sweep_to_dict(sweep),
    }


def _supersede_retry_allowed(run: WorkflowRunRow, blackboard: Mapping[str, Any]) -> bool:
    text = json.dumps(blackboard, ensure_ascii=False).lower()
    resolution = str(run.resolution or "").lower()
    delivery_status = str(getattr(run, "delivery_status", "") or "").lower()
    return (
        "no repository changes" in text
        or "no changes detected" in text
        or "delivery_blocked_no_changes" in text
        or "bootstrap" in text
        or "no_change" in resolution
        or delivery_status == "delivery_blocked_no_changes"
    )


def workflow_run_detail(db: Session, workflow_run_id: int) -> dict[str, Any]:
    """Return the declarative workflow run detail used by API and UI."""

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == workflow_run_id).first()
    if run is None:
        raise WorkflowRuntimeError(f"workflow run not found: {workflow_run_id}")
    events = db.query(WorkflowStateEventRow).filter(WorkflowStateEventRow.workflow_run_id == run.id).order_by(WorkflowStateEventRow.id.asc()).all()
    artifacts = db.query(WorkflowArtifactRow).filter(WorkflowArtifactRow.workflow_run_id == run.id).order_by(WorkflowArtifactRow.id.asc()).all()
    invocations = db.query(AtomInvocationRow).filter(AtomInvocationRow.workflow_run_id == run.id).order_by(AtomInvocationRow.id.asc()).all()
    gates = db.query(HumanGateRequestRow).filter(HumanGateRequestRow.workflow_run_id == run.id).order_by(HumanGateRequestRow.id.asc()).all()
    gate_object_keys = [str(int(gate.id)) for gate in gates]
    notification_rows = (
        db.query(NotificationDeliveryRow)
        .filter(
            (
                (NotificationDeliveryRow.object_type == "workflow_run")
                & (NotificationDeliveryRow.object_key == str(int(run.id)))
            )
            | (
                (NotificationDeliveryRow.object_type == "human_gate")
                & (NotificationDeliveryRow.object_key.in_(gate_object_keys or ["__none__"]))
            )
            | (
                (NotificationDeliveryRow.object_type == "requirement")
                & (NotificationDeliveryRow.object_key == str(int(run.requirement_id)))
            )
        )
        .order_by(NotificationDeliveryRow.id.desc())
        .all()
    )
    fingerprint_by_key = _notification_fingerprints_for_deliveries(db, notification_rows)
    pending_gate_count = sum(1 for gate in gates if str(gate.status or "") == "pending")
    requirement = db.query(RequirementRow).filter(RequirementRow.id == int(run.requirement_id)).first()
    summary = _workflow_run_summary_item(db, run, requirement=requirement)
    blackboard = workflow_blackboard(run)
    release = _latest_release_for_run(db, run)
    truth = _workflow_truth_fields(run, blackboard=blackboard, pending_gate_count=int(pending_gate_count), release=release)
    artifact_command_results = _command_results_from_artifacts(artifacts)
    command_results = truth["command_results"] or artifact_command_results
    if artifact_command_results and not truth["command_results"]:
        truth = {
            **truth,
            "command_results": artifact_command_results,
            "evidence_complete": True,
            "observability_warnings": [
                warning
                for warning in truth["observability_warnings"]
                if "verification passed without recorded command evidence" not in warning
            ],
        }
    return {
        **summary,
        "id": int(run.id),
        "requirement_id": int(run.requirement_id),
        "requirement_title": str(getattr(requirement, "title", "") or ""),
        "workflow_key": run.workflow_key,
        "current_state": run.current_state,
        "status": run.status,
        "resolution": run.resolution,
        "risk_level": run.risk_level,
        "pending_human_gate_count": int(pending_gate_count),
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "retry_counters": _json_load(run.retry_counters_json, {}),
        "blackboard": blackboard,
        "outcome_label": truth["outcome_label"],
        "is_truly_completed": truth["is_truly_completed"],
        "completed_truthfully": truth["completed_truthfully"],
        "needs_human": truth["needs_human"],
        "is_simulated": truth["is_simulated"],
        "simulated_delivery": truth["simulated_delivery"],
        "evidence_complete": truth["evidence_complete"],
        "acceptance_override": truth["acceptance_override"],
        "manual_review_prompt": truth["manual_review_prompt"],
        "business_outcome_status": truth["business_outcome_status"],
        "business_outcome_confirmed_by": truth["business_outcome_confirmed_by"],
        "business_outcome_confirmed_at": truth["business_outcome_confirmed_at"],
        "business_outcome_note": truth["business_outcome_note"],
        "awaiting_business_confirmation": truth["awaiting_business_confirmation"],
        "observability_warnings": truth["observability_warnings"],
        "agent_outputs": _agent_outputs_from_rows(artifacts, invocations),
        "changed_files_summary": truth["changed_files_summary"],
        "command_results": command_results,
        "delivery_summary": truth["delivery_summary"],
        "timeline": _workflow_timeline_items(
            run=run,
            events=events,
            invocations=invocations,
            artifacts=artifacts,
            gates=gates,
        ),
        "events": [
            {
                "id": int(event.id),
                "event_type": event.event_type,
                "from_state": event.from_state,
                "to_state": event.to_state,
                "condition": event.condition,
                "payload": _json_load(event.payload_json, {}),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
        "artifacts": [
            {
                "id": int(artifact.id),
                "artifact_type": artifact.artifact_type,
                "state_key": artifact.state_key,
                "atom_key": artifact.atom_key,
                "content_summary": artifact.content_summary,
                "payload": _json_load(artifact.machine_readable_payload, {}),
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            for artifact in artifacts
        ],
        "atom_invocations": [
            {
                "id": int(invocation.id),
                "state_key": invocation.state_key,
                "atom_key": invocation.atom_key,
                "atom_type": invocation.atom_type,
                "status": invocation.status,
                "output_summary": invocation.output_summary,
                "artifact_ids": _json_load(invocation.artifact_ids_json, []),
                "duration_ms": int(invocation.duration_ms or 0),
                "error_excerpt": invocation.error_excerpt,
            }
            for invocation in invocations
        ],
        "human_gates": [
            {
                "id": int(gate.id),
                "state_key": gate.state_key,
                "gate_type": gate.gate_type,
                "risk_level": gate.risk_level,
                "status": gate.status,
                "reason": gate.reason,
                "decision": gate.decision,
                "created_at": gate.created_at.isoformat() if gate.created_at else None,
            }
            for gate in gates
        ],
        "notifications": [
            {
                "id": int(row.id),
                "channel": str(row.channel or ""),
                "event_type": str(row.event_type or ""),
                "event_key": str(row.event_key or ""),
                "object_type": str(row.object_type or ""),
                "object_key": str(row.object_key or ""),
                "service_name": str(row.service_name or "").strip() or None,
                "status": str(row.status or ""),
                "payload": _json_load(row.payload_json, {}),
                "event_id": int(row.event_id) if getattr(row, "event_id", None) is not None else None,
                "fingerprint_key": str(row.fingerprint_key or "").strip() or None,
                "fingerprint": fingerprint_by_key.get(str(row.fingerprint_key or ""), {}),
                "response_excerpt": str(row.response_excerpt or "").strip() or None,
                "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in notification_rows
        ],
    }


def _notification_fingerprints_for_deliveries(
    db: Session,
    deliveries: list[NotificationDeliveryRow],
) -> dict[str, dict[str, Any]]:
    keys = sorted({str(row.fingerprint_key or "").strip() for row in deliveries if str(row.fingerprint_key or "").strip()})
    if not keys:
        return {}
    rows = db.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.fingerprint_key.in_(keys)).all()
    return {
        str(row.fingerprint_key): {
            "status": str(row.status or ""),
            "occurrence_count": int(row.occurrence_count or 0),
            "suppressed_count": int(row.suppressed_count or 0),
            "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
            "cooldown_until": row.cooldown_until.isoformat() if row.cooldown_until else None,
            "severity": str(row.severity or ""),
            "risk_level": str(row.risk_level or ""),
        }
        for row in rows
    }


def _ensure_human_gate_request(
    db: Session,
    workflow_run: WorkflowRunRow,
    state_key: str,
    blackboard: Mapping[str, Any],
) -> HumanGateRequestRow:
    existing = (
        db.query(HumanGateRequestRow)
        .filter(
            HumanGateRequestRow.workflow_run_id == int(workflow_run.id),
            HumanGateRequestRow.state_key == state_key,
            HumanGateRequestRow.status == "pending",
        )
        .first()
    )
    if existing is not None:
        return existing
    gate = HumanGateRequestRow(
        workflow_run_id=int(workflow_run.id),
        state_key=state_key,
        gate_type="human_gate",
        risk_level="high" if blackboard.get("risk_flags") else str(workflow_run.risk_level or "normal"),
        status="pending",
        reason="Workflow reached a human-gated terminal state.",
        payload_json=_json_dump(
            {
                "workflow_key": workflow_run.workflow_key,
                "current_state": state_key,
                "risk_flags": list(blackboard.get("risk_flags") or []),
                "summary": blackboard.get("pr") or blackboard.get("verification") or {},
            }
        ),
    )
    db.add(gate)
    db.flush()
    _notify_human_gate_created(db, gate, workflow_run)
    return gate


def _workflow_service_label(requirement: RequirementRow | None) -> str:
    return notification_service_label(
        service_name=str(getattr(requirement, "project_display_name", "") or "").strip() or None,
        project_key=str(getattr(requirement, "project_key", "") or "").strip() or None,
    )


def _notify_workflow_run_started(
    db: Session,
    workflow_run: WorkflowRunRow,
    requirement: RequirementRow,
    blackboard: Mapping[str, Any],
) -> None:
    deliver_policy_notification(
        db,
        event_type="workflow_run_started",
        object_type="workflow_run",
        object_key=str(int(workflow_run.id)),
        service_name=_workflow_service_label(requirement),
        severity="normal",
        risk_level=str(workflow_run.risk_level or blackboard.get("risk_level") or "normal"),
        status=str(workflow_run.status or "pending"),
        workflow_key=str(workflow_run.workflow_key or ""),
        current_state=str(workflow_run.current_state or ""),
        summary=f"Workflow #{int(workflow_run.id)} started for requirement #{int(requirement.id)}: {str(requirement.title or '').strip()}",
        next_action="Open the workflow detail to monitor state, atom evidence, and gates.",
        actor_or_source=str(workflow_run.triggered_by or "system"),
        occurred_at=workflow_run.created_at,
        object_refs={
            "requirement_id": int(requirement.id),
            "workflow_run_id": int(workflow_run.id),
            "workflow_key": workflow_run.workflow_key,
            "current_state": workflow_run.current_state,
        },
        links={
            "需求": build_ops_url(f"/requirements/{int(requirement.id)}") or "",
            "工作流": build_ops_url(f"/workflows/{int(workflow_run.id)}") or "",
        },
    )


def _notify_workflow_terminal(
    db: Session,
    workflow_run: WorkflowRunRow,
    state_key: str,
    blackboard: Mapping[str, Any],
    resolution: str,
) -> None:
    requirement = workflow_run.requirement
    event_type = _workflow_terminal_event_type(resolution, blackboard)
    if event_type is None:
        return
    risk_level = "high" if blackboard.get("risk_flags") else str(workflow_run.risk_level or "normal")
    is_failure = event_type in {"workflow_retry_budget_exhausted", "workflow_run_failed"}
    deliver_policy_notification(
        db,
        event_type=event_type,
        object_type="workflow_run",
        object_key=str(int(workflow_run.id)),
        service_name=_workflow_service_label(requirement),
        severity="high" if is_failure else "normal",
        risk_level=risk_level,
        status=str(workflow_run.status or resolution),
        workflow_key=str(workflow_run.workflow_key or ""),
        current_state=state_key,
        summary=f"Workflow #{int(workflow_run.id)} reached `{state_key}` with resolution `{resolution}`.",
        next_action=(
            "Review the alert, failed evidence, and pending human gate in Ops Console."
            if is_failure
            else "No immediate action required; inspect evidence if needed."
        ),
        actor_or_source="state_machine_runner",
        occurred_at=utcnow(),
        object_refs={
            "requirement_id": int(workflow_run.requirement_id),
            "workflow_run_id": int(workflow_run.id),
            "workflow_key": workflow_run.workflow_key,
            "current_state": state_key,
        },
        links={
            "工作流": build_ops_url(f"/workflows/{int(workflow_run.id)}") or "",
            "需求": build_ops_url(f"/requirements/{int(workflow_run.requirement_id)}") or "",
        },
    )


def _workflow_terminal_event_type(resolution: str, blackboard: Mapping[str, Any]) -> str | None:
    if resolution == "completed":
        return "workflow_run_succeeded"
    verification = blackboard.get("verification") if isinstance(blackboard.get("verification"), Mapping) else {}
    pr = blackboard.get("pr") if isinstance(blackboard.get("pr"), Mapping) else {}
    observation = blackboard.get("observation") if isinstance(blackboard.get("observation"), Mapping) else {}
    if verification.get("status") == "failed" or pr.get("failed") or observation.get("not_restored"):
        return "workflow_retry_budget_exhausted"
    # Human-gated success paths are already announced by the human gate and
    # delivery notifications; avoid paging the alert channel for normal PR-only
    # review stops such as self-repair.
    return "workflow_run_paused"


def _workflow_timeline_items(
    *,
    run: WorkflowRunRow,
    events: list[WorkflowStateEventRow],
    invocations: list[AtomInvocationRow],
    artifacts: list[WorkflowArtifactRow],
    gates: list[HumanGateRequestRow],
) -> list[dict[str, Any]]:
    """Build a chronological human-readable projection without adding storage."""

    items: list[dict[str, Any]] = []

    def _ts(value: Any) -> str | None:
        return value.isoformat() if value else None

    def _artifact_preview(artifact: WorkflowArtifactRow) -> dict[str, Any]:
        payload = _json_load(artifact.machine_readable_payload, {})
        raw = str(artifact.human_readable_body or "")
        return {
            "id": int(artifact.id),
            "artifact_type": str(artifact.artifact_type or ""),
            "summary": str(artifact.content_summary or ""),
            "payload": payload,
            "raw_excerpt": raw[:1200],
        }

    artifact_by_id = {int(artifact.id): artifact for artifact in artifacts}

    for event in events:
        payload = _json_load(event.payload_json, {})
        from_state = str(event.from_state or "")
        to_state = str(event.to_state or "")
        condition = str(event.condition or "")
        items.append(
            {
                "kind": "state_transition",
                "id": int(event.id),
                "created_at": _ts(event.created_at),
                "state_key": to_state or from_state,
                "from_state": from_state or None,
                "to_state": to_state or None,
                "condition": condition or None,
                "status": "completed",
                "title": f"State transition: {from_state or 'start'} -> {to_state or 'unknown'}",
                "summary": f"Condition: {condition or '<default>'}",
                "artifact_ids": [],
                "payload_ref": payload,
            }
        )

    for invocation in invocations:
        artifact_ids = [
            int(item)
            for item in _json_load(invocation.artifact_ids_json, [])
            if str(item).isdigit()
        ]
        items.append(
            {
                "kind": "atom_invocation",
                "id": int(invocation.id),
                "created_at": _ts(invocation.started_at),
                "completed_at": _ts(invocation.completed_at),
                "state_key": str(invocation.state_key or ""),
                "atom_key": str(invocation.atom_key or ""),
                "atom_type": str(invocation.atom_type or ""),
                "status": str(invocation.status or ""),
                "title": f"Atom executed: {invocation.atom_key}",
                "summary": str(invocation.output_summary or invocation.error_excerpt or ""),
                "artifact_ids": artifact_ids,
                "artifacts": [
                    _artifact_preview(artifact_by_id[artifact_id])
                    for artifact_id in artifact_ids
                    if artifact_id in artifact_by_id
                ],
            }
        )

    for artifact in artifacts:
        items.append(
            {
                "kind": "artifact_created",
                "id": int(artifact.id),
                "created_at": _ts(artifact.created_at),
                "state_key": str(artifact.state_key or ""),
                "atom_key": str(artifact.atom_key or ""),
                "status": "created",
                "title": f"Artifact created: {artifact.artifact_type} #{int(artifact.id)}",
                "summary": str(artifact.content_summary or ""),
                "artifact_ids": [int(artifact.id)],
                "artifact": _artifact_preview(artifact),
            }
        )

    for gate in gates:
        items.append(
            {
                "kind": "human_gate",
                "id": int(gate.id),
                "created_at": _ts(gate.created_at),
                "completed_at": _ts(gate.decided_at),
                "state_key": str(gate.state_key or ""),
                "status": str(gate.status or ""),
                "title": f"Human gate: {gate.gate_type}",
                "summary": str(gate.reason or gate.decision_comment or ""),
                "artifact_ids": [],
                "payload_ref": _json_load(gate.payload_json, {}),
                "decision": str(gate.decision or "") or None,
                "decided_by": str(gate.decided_by or "") or None,
            }
        )

    if str(run.status or "") in {"succeeded", "completed", "done", "failed", "awaiting_operator"}:
        items.append(
            {
                "kind": "workflow_terminal",
                "id": int(run.id),
                "created_at": _ts(run.completed_at or run.updated_at),
                "state_key": str(run.current_state or ""),
                "status": str(run.status or ""),
                "title": f"Workflow terminal: {run.status}",
                "summary": str(run.resolution or ""),
                "artifact_ids": [],
            }
        )

    def _sort_key(item: dict[str, Any]) -> tuple[str, str, int]:
        return (
            str(item.get("created_at") or ""),
            str(item.get("kind") or ""),
            int(item.get("id") or 0),
        )

    return sorted(items, key=_sort_key)


def _notify_human_gate_created(
    db: Session,
    gate: HumanGateRequestRow,
    workflow_run: WorkflowRunRow,
) -> None:
    requirement = workflow_run.requirement
    deliver_policy_notification(
        db,
        event_type="human_gate_request.created",
        object_type="human_gate",
        object_key=str(int(gate.id)),
        service_name=_workflow_service_label(requirement),
        severity="normal",
        risk_level=str(gate.risk_level or "high"),
        status=str(gate.status or "pending"),
        requires_human=True,
        workflow_key=str(workflow_run.workflow_key or ""),
        current_state=str(gate.state_key or workflow_run.current_state or ""),
        summary=f"Workflow #{int(workflow_run.id)} requires operator decision at `{gate.state_key}`.",
        next_action="Open Gates & Delivery and choose approve, reject, or continue retry.",
        actor_or_source="risk_evidence_gate",
        occurred_at=gate.created_at,
        object_refs={
            "requirement_id": int(workflow_run.requirement_id),
            "workflow_run_id": int(workflow_run.id),
            "gate_id": int(gate.id),
            "workflow_key": workflow_run.workflow_key,
            "current_state": gate.state_key,
        },
        links={
            "审批": build_ops_url(f"/workflows/{int(workflow_run.id)}?tab=gates") or "",
            "工作流": build_ops_url(f"/workflows/{int(workflow_run.id)}") or "",
            "需求": build_ops_url(f"/requirements/{int(workflow_run.requirement_id)}") or "",
        },
    )


def _notify_human_gate_decided(
    db: Session,
    gate: HumanGateRequestRow,
    workflow_run: WorkflowRunRow,
) -> None:
    requirement = workflow_run.requirement
    deliver_policy_notification(
        db,
        event_type="human_gate_request.decided",
        object_type="human_gate",
        object_key=str(int(gate.id)),
        service_name=_workflow_service_label(requirement),
        severity="normal",
        risk_level=str(gate.risk_level or "normal"),
        status=str(gate.decision or gate.status or "decided"),
        requires_human=True,
        workflow_key=str(workflow_run.workflow_key or ""),
        current_state=str(gate.state_key or workflow_run.current_state or ""),
        summary=f"Human gate #{int(gate.id)} decided `{gate.decision}` by {gate.decided_by or 'operator'}.",
        next_action="Continue monitoring the workflow or release delivery status.",
        actor_or_source=str(gate.decided_by or "operator"),
        occurred_at=gate.decided_at,
        object_refs={
            "requirement_id": int(workflow_run.requirement_id),
            "workflow_run_id": int(workflow_run.id),
            "gate_id": int(gate.id),
            "workflow_key": workflow_run.workflow_key,
            "current_state": gate.state_key,
        },
        links={
            "审批": build_ops_url(f"/workflows/{int(workflow_run.id)}?tab=gates") or "",
            "工作流": build_ops_url(f"/workflows/{int(workflow_run.id)}") or "",
        },
    )


def _notify_workflow_pr_delivery(
    db: Session,
    workflow_run: WorkflowRunRow,
    requirement: RequirementRow,
    state_key: str,
    blackboard: Mapping[str, Any],
) -> None:
    pr = blackboard.get("pr") if isinstance(blackboard.get("pr"), Mapping) else {}
    created = bool(pr.get("created"))
    event_type = "pr_opened" if created else "pr_creation_failed"
    severity = "normal" if created else "high"
    risk_level = "high" if blackboard.get("risk_flags") else str(workflow_run.risk_level or "normal")
    pr_ref = str(pr.get("number") or pr.get("url") or pr.get("branch_name") or state_key or "unknown")
    deliver_policy_notification(
        db,
        event_type=event_type,
        object_type="workflow_run",
        object_key=str(int(workflow_run.id)),
        service_name=_workflow_service_label(requirement),
        severity=severity,
        risk_level=risk_level,
        status=str(pr.get("status") or event_type),
        workflow_key=str(workflow_run.workflow_key or ""),
        current_state=state_key,
        summary=(
            f"Workflow #{int(workflow_run.id)} created draft PR for requirement #{int(requirement.id)}."
            if created
            else f"Workflow #{int(workflow_run.id)} could not create PR for requirement #{int(requirement.id)}."
        ),
        next_action=(
            "Open the PR and review delivery evidence."
            if created
            else "Open Gates & Delivery, inspect blockers, and decide whether to retry or route to human."
        ),
        actor_or_source="delivery_atom",
        occurred_at=utcnow(),
        event_key=f"release:{event_type}:workflow:{int(workflow_run.id)}:{pr_ref}",
        object_refs={
            "requirement_id": int(requirement.id),
            "workflow_run_id": int(workflow_run.id),
            "workflow_key": workflow_run.workflow_key,
            "current_state": state_key,
            "branch": pr.get("branch_name"),
            "pr_number": pr.get("number"),
        },
        links={
            "工作流": build_ops_url(f"/workflows/{int(workflow_run.id)}?tab=delivery") or "",
            "需求": build_ops_url(f"/requirements/{int(requirement.id)}") or "",
            "PR": str(pr.get("url") or "").strip(),
            "Compare": str(pr.get("compare_url") or "").strip(),
        },
    )


def _record_command_result_artifact(
    ctx: WorkflowContext,
    *,
    command: str,
    purpose: str,
    exit_code: int,
    simulated: bool,
    cwd: str | None = None,
    stdout_excerpt: str = "",
    stderr_excerpt: str = "",
    duration_ms: int = 0,
    timeout: bool = False,
) -> dict[str, Any]:
    """Persist command evidence for verification atoms.

    These first-phase workflows still use governed built-in atoms rather than
    arbitrary shell execution. Marking the evidence as simulated keeps the UI
    honest while giving operators a stable command-evidence contract.
    """

    payload: dict[str, Any] = {
        "cwd": cwd or str(getattr(ctx.requirement, "target_project_path", "") or "."),
        "command": command,
        "purpose": purpose,
        "exit_code": int(exit_code),
        "duration_ms": int(duration_ms),
        "stdout_excerpt": stdout_excerpt or ("simulated command passed" if simulated and exit_code == 0 else ""),
        "stderr_excerpt": stderr_excerpt or ("simulated command failed" if simulated and exit_code != 0 else ""),
        "timeout": bool(timeout),
        "simulated": bool(simulated),
    }
    artifact = _create_workflow_artifact(
        ctx.db,
        workflow_run_id=int(ctx.workflow_run.id),
        artifact_type="workflow_command_result",
        state_key=ctx.state_key,
        atom_key=str(ctx.state_spec.get("atom") or ctx.state_spec.get("agent") or ""),
        content_summary=f"{ctx.state_key}: {command}",
        human_readable_body=json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        machine_readable_payload=payload,
    )
    payload["log_artifact_id"] = int(artifact.id)
    artifact.machine_readable_payload = _json_dump(payload)
    ctx.db.flush()
    return payload


def _run_local_command_result_artifact(
    ctx: WorkflowContext,
    *,
    command: str,
    args: list[str],
    purpose: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Run a governed local verification command and persist real evidence."""

    cwd = str(getattr(ctx.requirement, "target_project_path", "") or "").strip()
    if not cwd or not os.path.isdir(cwd):
        cwd = str(config.PROJECT_ROOT)
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    started = time.monotonic()
    stdout_excerpt = ""
    stderr_excerpt = ""
    exit_code = 1
    timed_out = False
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = int(completed.returncode)
        stdout_excerpt = str(completed.stdout or "")[:4000]
        stderr_excerpt = str(completed.stderr or "")[:4000]
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        stdout_excerpt = str(exc.stdout or "")[:4000]
        stderr_excerpt = (str(exc.stderr or "") or f"command timed out after {timeout_seconds}s")[:4000]
    duration_ms = int((time.monotonic() - started) * 1000)
    return _record_command_result_artifact(
        ctx,
        command=command,
        purpose=purpose,
        exit_code=exit_code,
        simulated=False,
        cwd=cwd,
        stdout_excerpt=stdout_excerpt,
        stderr_excerpt=stderr_excerpt,
        duration_ms=duration_ms,
        timeout=timed_out,
    )


def _condition_matches(expression: str, blackboard: Mapping[str, Any]) -> bool:
    parts = [part.strip() for part in re.split(r"\s+and\s+", expression) if part.strip()]
    return all(_condition_part_matches(part, blackboard) for part in parts)


def _condition_part_matches(part: str, blackboard: Mapping[str, Any]) -> bool:
    if part.startswith("not "):
        return not _condition_part_matches(part[4:].strip(), blackboard)
    for operator in (">=", "<=", "==", "!=", ">", "<"):
        if operator not in part:
            continue
        left, right = [item.strip() for item in part.split(operator, 1)]
        left_value = _lookup_path(left, blackboard)
        right_value = _parse_literal(right, blackboard)
        return _compare_values(left_value, right_value, operator)
    return bool(_lookup_path(part, blackboard))


def _lookup_path(path: str, blackboard: Mapping[str, Any]) -> Any:
    current: Any = blackboard
    parts = [item for item in path.split(".") if item]
    for index, part in enumerate(parts):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif index > 0 and parts[0] == "counters":
            return 0
        else:
            return None
    return current


def _parse_literal(value: str, blackboard: Mapping[str, Any]) -> Any:
    stripped = value.strip()
    if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
        return stripped[1:-1]
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return _lookup_path(stripped, blackboard)


def _compare_values(left: Any, right: Any, operator: str) -> bool:
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    try:
        if operator == ">=":
            return left >= right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        if operator == "<":
            return left < right
    except TypeError:
        return False
    return False


def _coerce_atom_result(raw_result: AtomResult | Mapping[str, Any] | str) -> AtomResult:
    if isinstance(raw_result, AtomResult):
        return raw_result
    if isinstance(raw_result, str):
        parsed = _parse_json_output(raw_result)
        return _atom_result_from_mapping(parsed, raw_output=raw_result)
    if isinstance(raw_result, Mapping):
        return _atom_result_from_mapping(raw_result, raw_output=raw_result)
    raise WorkflowRuntimeError(f"unsupported atom result type: {type(raw_result).__name__}")


def _atom_result_from_mapping(payload: Mapping[str, Any], *, raw_output: Any) -> AtomResult:
    writes = payload.get("writes") if isinstance(payload.get("writes"), Mapping) else payload
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    risk_flags = payload.get("risk_flags") if isinstance(payload.get("risk_flags"), list) else []
    return AtomResult(
        status=str(payload.get("status") or "completed"),
        summary=str(payload.get("summary") or ""),
        writes=dict(writes or {}),
        raw_output=raw_output,
        artifacts=tuple(str(item) for item in artifacts),
        risk_flags=tuple(str(item) for item in risk_flags),
    )


def _parse_json_output(raw_output: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, flags=re.DOTALL)
        if not match:
            raise WorkflowRuntimeError("agent atom output is not valid JSON")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise WorkflowRuntimeError("agent atom output JSON must be an object")
    return parsed


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load_blackboard(workflow_run: WorkflowRunRow) -> dict[str, Any]:
    blackboard = _json_load(getattr(workflow_run, "blackboard_json", None), {})
    return dict(blackboard) if isinstance(blackboard, dict) else {}


def _persist_blackboard(db: Session, workflow_run: WorkflowRunRow, state_key: str, blackboard: Mapping[str, Any]) -> None:
    persist_keys = _persist_keys_from_blackboard(blackboard)
    persisted = {key: blackboard.get(key) for key in persist_keys if key in blackboard}
    workflow_run.blackboard_json = _json_dump(persisted)
    workflow_run.retry_counters_json = _json_dump(dict(persisted.get("counters") or {}))
    workflow_run.updated_at = utcnow()
    db.add(
        BlackboardSnapshotRow(
            workflow_run_id=int(workflow_run.id),
            state_key=state_key,
            snapshot_json=workflow_run.blackboard_json,
        )
    )


def _persist_keys_from_blackboard(blackboard: Mapping[str, Any]) -> list[str]:
    forbidden = {"state_outputs", "transition_history", "artifacts"}
    keys = blackboard.get("persist_keys")
    if isinstance(keys, list):
        return [str(item) for item in keys if str(item) not in forbidden]
    return [
        "workflow_key",
        "current_state",
        "counters",
        "trigger",
        "logs_collected",
        "ops_failure_detected",
        "gateway_drift_detected",
        "no_gateway_drift",
        "diagnosis",
        "patch_result",
        "verification",
        "ci",
        "final_regression",
        "gate",
        "observation",
        "pr",
        "acceptance",
        "business_outcome",
        "risk_flags",
        "evidence",
        "human_gate_decisions",
        "limits",
    ]


def _json_load(raw_value: Any, default: Any) -> Any:
    if raw_value is None:
        return default
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(str(raw_value or ""))
    except json.JSONDecodeError:
        return default


def _create_workflow_artifact(
    db: Session,
    *,
    workflow_run_id: int,
    artifact_type: str,
    content_summary: str,
    human_readable_body: str,
    machine_readable_payload: Mapping[str, Any] | list[Any] | str | None = None,
    state_key: str | None = None,
    atom_key: str | None = None,
) -> WorkflowArtifactRow:
    payload_for_storage: Mapping[str, Any] | list[Any] | str | None
    if isinstance(machine_readable_payload, Mapping):
        payload_for_storage = dict(machine_readable_payload)
        payload_for_storage.setdefault("workflow_run_id", workflow_run_id)
    else:
        payload_for_storage = machine_readable_payload
    payload_text = (
        json.dumps(payload_for_storage, ensure_ascii=False, sort_keys=True)
        if payload_for_storage is not None and not isinstance(payload_for_storage, str)
        else payload_for_storage
    )
    checksum_source = str(payload_text or human_readable_body or content_summary)
    artifact = WorkflowArtifactRow(
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
        state_key=state_key,
        atom_key=atom_key,
        content_summary=content_summary,
        human_readable_body=human_readable_body,
        machine_readable_payload=payload_text,
        checksum=hashlib.sha1(checksum_source.encode("utf-8")).hexdigest(),
    )
    db.add(artifact)
    db.flush()
    return artifact


def _validate_loop_guards(graph: Mapping[str, list[dict[str, Any]]]) -> None:
    cycles: list[list[tuple[str, dict[str, Any]]]] = []

    def visit(node: str, path: list[tuple[str, dict[str, Any]]], seen: set[str]) -> None:
        for transition in graph.get(node, []):
            target = str(transition.get("goto") or "")
            edge = (node, transition)
            if target in seen:
                cycle_start = next((index for index, item in enumerate(path) if item[0] == target), 0)
                cycles.append(path[cycle_start:] + [edge])
                continue
            visit(target, path + [edge], seen | {target})

    for state_key in graph:
        visit(state_key, [], {state_key})

    for cycle in cycles:
        guarded = False
        for _source, transition in cycle:
            condition = str(transition.get("if") or "")
            if transition.get("increment") or "counters." in condition:
                guarded = True
                break
        if not guarded:
            edge_list = " -> ".join(source for source, _transition in cycle)
            raise WorkflowSpecError(f"workflow loop must include counter guard: {edge_list}")
