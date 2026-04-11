"""Incident taxonomy and recovery narrative helpers."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import ArtifactRow, RequirementRow, WorkflowRunRow


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _first_target_path(requirement: RequirementRow) -> str | None:
    value = str(getattr(requirement, "target_project_path", "") or "").strip()
    if not value:
        return None
    for item in value.splitlines():
        candidate = item.strip()
        if candidate:
            return candidate
    return None


def _display_name(requirement: RequirementRow) -> str:
    target_path = _first_target_path(requirement)
    if not target_path:
        return "Org Ops"
    return target_path.rsplit("/", 1)[-1]


def _severity_rank(value: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(str(value), 0)


def _incident_record(
    *,
    requirement: RequirementRow,
    artifact: ArtifactRow,
    incident_key: str,
    family: str,
    code: str,
    severity: str,
    recovery_status: str,
    title: str,
    summary: str,
    recommended_action: str,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    target_path = _first_target_path(requirement)
    return {
        "incident_key": incident_key,
        "requirement_id": int(requirement.id),
        "workflow_run_id": int(artifact.workflow_run_id) if artifact.workflow_run_id is not None else None,
        "step_id": int(artifact.step_id) if artifact.step_id is not None else None,
        "source_artifact_id": int(artifact.id),
        "source_artifact_type": str(artifact.artifact_type),
        "incident_family": family,
        "incident_code": code,
        "severity": severity,
        "recovery_status": recovery_status,
        "title": title,
        "summary": summary,
        "recommended_action": recommended_action,
        "project_root_path": target_path,
        "project_display_name": _display_name(requirement),
        "evidence": evidence or [],
        "occurred_at": artifact.created_at.isoformat() if artifact.created_at else None,
    }


def classify_artifact_incident(requirement: RequirementRow, artifact: ArtifactRow) -> dict[str, Any] | None:
    payload = _json_loads(getattr(artifact, "machine_readable_payload", None), {})
    artifact_type = str(getattr(artifact, "artifact_type", "") or "")
    incident_key = f"{artifact_type}:{int(artifact.id)}"

    if artifact_type == "bug_report":
        step_type = str(payload.get("step_type") or "workflow")
        verification_type = str(payload.get("verification_type") or "unknown")
        failed_checks = [
            str(item.get("check_key") or "")
            for item in payload.get("failed_checks") or []
            if isinstance(item, dict) and str(item.get("check_key") or "").strip()
        ]
        code = {
            "review": "manual_review_failure",
            "test": "automated_validation_failure",
            "bugfix": "bugfix_regression_failure",
        }.get(step_type, "workflow_step_failure")
        return _incident_record(
            requirement=requirement,
            artifact=artifact,
            incident_key=incident_key,
            family="verification",
            code=code,
            severity="high" if step_type in {"test", "bugfix"} else "medium",
            recovery_status="bugfix_loop_active" if step_type in {"implementation", "review", "test", "bugfix"} else "needs_revision",
            title=f"Verification incident: {step_type}",
            summary=(
                f"{verification_type} verification failed in `{step_type}`"
                + (f" with checks `{', '.join(failed_checks)}`." if failed_checks else ".")
            ),
            recommended_action="Inspect the failing evidence, confirm root cause, and continue through the bugfix + re-validation loop.",
            evidence=[
                {
                    "failed_checks": failed_checks,
                    "verification_type": verification_type,
                    "error": str(payload.get("error") or artifact.content_summary or ""),
                }
            ],
        )

    if artifact_type == "capability_interrupt":
        event_type = str(payload.get("event_type") or "capability_interrupt")
        denied = [str(item) for item in (payload.get("approval_policy") or {}).get("deny_reasons") or [] if str(item).strip()]
        return _incident_record(
            requirement=requirement,
            artifact=artifact,
            incident_key=incident_key,
            family="governance",
            code=event_type,
            severity="high" if event_type == "capability_denied" else "medium",
            recovery_status="operator_review_required",
            title=f"Policy incident: {event_type}",
            summary=str(artifact.content_summary or artifact.human_readable_body or "Execution was interrupted by policy."),
            recommended_action="Update project policy or route the work to an allowed path before resuming execution.",
            evidence=[{"deny_reasons": denied, "approval_type": payload.get("approval_type")}],
        )

    if artifact_type == "stale_memory_verification":
        status = str(payload.get("verification_status") or "fresh")
        if status == "fresh":
            return None
        findings = [str(item) for item in payload.get("stale_findings") or [] if str(item).strip()]
        return _incident_record(
            requirement=requirement,
            artifact=artifact,
            incident_key=incident_key,
            family="context_integrity",
            code="stale_memory_blocked",
            severity="high",
            recovery_status="replan_required",
            title="Context incident: stale memory blocked",
            summary="Step dispatch was blocked because context artifacts or handoff memory were considered stale.",
            recommended_action="Revise or re-plan the requirement so the next dispatch uses fresh artifacts and current requirement facts.",
            evidence=[{"stale_findings": findings, "step_key": payload.get("step_key")}],
        )

    if artifact_type == "bugfix_circuit_breaker":
        followups = payload.get("followup_requirements") or []
        return _incident_record(
            requirement=requirement,
            artifact=artifact,
            incident_key=incident_key,
            family="recovery_loop",
            code="bugfix_circuit_breaker",
            severity="critical",
            recovery_status="operator_review_required",
            title="Recovery incident: bugfix circuit breaker",
            summary=str(payload.get("reason") or artifact.content_summary or "Repeated failures triggered a circuit breaker."),
            recommended_action="Stop auto-retries, inspect the repeated error fingerprint, and handle the operator review or infra incident follow-up requirement.",
            evidence=[{"followup_requirements": followups, "failed_step_id": payload.get("failed_step_id")}],
        )

    if artifact_type == "runtime_lifecycle":
        phase = str(payload.get("phase") or "")
        note = str(payload.get("note") or "")
        last_error = str(payload.get("last_error_message") or "")
        if phase not in {"failed", "paused"}:
            return None
        if phase == "paused" and "paused by user" in note.lower():
            return None
        code = "runtime_failure" if phase == "failed" else "runtime_pause"
        summary = last_error or note or str(artifact.content_summary or "Runtime was interrupted.")
        return _incident_record(
            requirement=requirement,
            artifact=artifact,
            incident_key=incident_key,
            family="runtime_orchestration",
            code=code,
            severity="high" if phase == "failed" else "medium",
            recovery_status="runtime_recovery_required",
            title=f"Runtime incident: {phase}",
            summary=summary,
            recommended_action="Inspect runtime session, recent events, and cleanup state before re-dispatching the step.",
            evidence=[
                {
                    "runtime_backend": payload.get("runtime_backend"),
                    "runtime_session_id": payload.get("runtime_session_id"),
                    "selected_agent": payload.get("runtime_selected_agent"),
                }
            ],
        )

    return None


def list_requirement_incidents(db: Session, requirement_id: int) -> list[dict[str, Any]]:
    requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    if requirement is None:
        return []
    artifacts = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type.in_(
            (
                "bug_report",
                "capability_interrupt",
                "stale_memory_verification",
                "bugfix_circuit_breaker",
                "runtime_lifecycle",
            )
        ),
    ).order_by(ArtifactRow.id.asc()).all()
    incidents = [classify_artifact_incident(requirement, artifact) for artifact in artifacts]
    filtered = [item for item in incidents if item is not None]
    filtered.sort(
        key=lambda item: (
            -_severity_rank(str(item.get("severity") or "")),
            str(item.get("occurred_at") or ""),
            int(item.get("source_artifact_id") or 0),
        ),
        reverse=False,
    )
    filtered.sort(
        key=lambda item: (
            -_severity_rank(str(item.get("severity") or "")),
            -(int(item.get("source_artifact_id") or 0)),
        )
    )
    return filtered


def list_open_incidents(db: Session) -> list[dict[str, Any]]:
    requirements = db.query(RequirementRow).all()
    incidents: list[dict[str, Any]] = []
    active_runs = {
        int(run.requirement_id): run
        for run in db.query(WorkflowRunRow).all()
    }
    for requirement in requirements:
        if str(requirement.status or "") == "deleted":
            continue
        requirement_incidents = list_requirement_incidents(db, int(requirement.id))
        if not requirement_incidents:
            continue
        for incident in requirement_incidents:
            run = active_runs.get(int(requirement.id))
            if run is not None and incident.get("workflow_run_id") not in {None, int(run.id)}:
                continue
            incidents.append(incident)
    return incidents
