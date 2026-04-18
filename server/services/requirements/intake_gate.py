"""Requirement materialization fingerprint gate."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import RequirementIntakeFingerprintRow, RequirementRow, WorkflowRunRow, utcnow

ACTIVE_REQUIREMENT_STATUSES = {
    "draft",
    "ready",
    "running",
    "blocked",
    "needs_revision",
    "delivery_ready",
}
ACTIVE_WORKFLOW_STATUSES = {"running", "awaiting_operator"}
DEFAULT_INTAKE_COOLDOWN_SECONDS = 6 * 3600


@dataclass(frozen=True)
class IntakeGateDecision:
    action: str
    reason: str
    fingerprint_key: str
    linked_requirement_id: int | None = None
    cooldown_until: datetime | None = None
    status: str = "open"


def build_requirement_intake_fingerprint_key(
    *,
    source_kind: str,
    source_key: str,
    project_key: str | None,
    project_root_path: str | None,
    fingerprint: str,
) -> str:
    scope = _normalize(project_key) or _normalize(project_root_path) or "unknown-project"
    seed = "|".join([
        _normalize(source_kind),
        _normalize(source_key),
        scope,
        _normalize(fingerprint),
    ])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"{_normalize(source_kind)}:{_normalize(source_key)}:{hashlib.sha1(scope.encode('utf-8')).hexdigest()[:10]}:{digest}"


def should_materialize_requirement(
    db: Session,
    *,
    source_kind: str,
    source_key: str,
    fingerprint: str,
    project_key: str | None = None,
    project_root_path: str | None = None,
    severity: str = "normal",
    active_requirement: RequirementRow | None = None,
    linked_requirement: RequirementRow | None = None,
    latest_evidence: dict[str, Any] | None = None,
    cooldown_seconds: int = DEFAULT_INTAKE_COOLDOWN_SECONDS,
) -> IntakeGateDecision:
    """Decide whether a repeated bug/error fingerprint may create a requirement."""

    key = build_requirement_intake_fingerprint_key(
        source_kind=source_kind,
        source_key=source_key,
        project_key=project_key,
        project_root_path=project_root_path,
        fingerprint=fingerprint,
    )
    now = utcnow()
    row = db.query(RequirementIntakeFingerprintRow).filter(RequirementIntakeFingerprintRow.fingerprint_key == key).first()
    if row is None:
        row = RequirementIntakeFingerprintRow(
            fingerprint_key=key,
            source_kind=str(source_kind or ""),
            source_key=str(source_key or ""),
            project_key=str(project_key or "").strip() or None,
            project_root_path=str(project_root_path or "").strip() or None,
            status="open",
            first_seen_at=now,
            occurrence_count=0,
        )
        db.add(row)
        db.flush()

    _touch(row, now=now, latest_evidence=latest_evidence)

    candidate = active_requirement or linked_requirement or _linked_requirement(db, row)
    if candidate is not None:
        row.linked_requirement_id = int(candidate.id)
        row.linked_workflow_run_id = int(candidate.active_workflow_run_id) if candidate.active_workflow_run_id is not None else row.linked_workflow_run_id
        if _is_active_requirement(candidate) or _has_active_workflow(db, candidate):
            row.status = "linked_requirement"
            db.flush()
            return IntakeGateDecision(
                action="reuse_requirement",
                reason="active requirement/workflow already handles this fingerprint",
                fingerprint_key=key,
                linked_requirement_id=int(candidate.id),
                cooldown_until=row.cooldown_until,
                status=row.status,
            )
        if str(row.status or "") == "resolved":
            row.status = "reopened"
            db.flush()
            return IntakeGateDecision(
                action="reopen_regression",
                reason="fingerprint reappeared after a resolved requirement",
                fingerprint_key=key,
                linked_requirement_id=int(candidate.id),
                cooldown_until=row.cooldown_until,
                status=row.status,
            )
        row.status = "suppressed"
        row.suppressed_count = int(row.suppressed_count or 0) + 1
        row.cooldown_until = now + timedelta(seconds=max(60, int(cooldown_seconds or DEFAULT_INTAKE_COOLDOWN_SECONDS)))
        db.flush()
        return IntakeGateDecision(
            action="suppress",
            reason="linked requirement is terminal but not marked resolved by release/observing",
            fingerprint_key=key,
            linked_requirement_id=int(candidate.id),
            cooldown_until=row.cooldown_until,
            status=row.status,
        )

    cooldown_until = _ensure_utc(row.cooldown_until)
    if cooldown_until is not None and cooldown_until > now and _severity_rank(severity) < _severity_rank("critical"):
        row.status = "cooldown"
        row.suppressed_count = int(row.suppressed_count or 0) + 1
        db.flush()
        return IntakeGateDecision(
            action="suppress",
            reason="fingerprint is inside materialization cooldown",
            fingerprint_key=key,
            cooldown_until=row.cooldown_until,
            status=row.status,
        )

    row.status = "open" if str(row.status or "") not in {"resolved", "reopened"} else str(row.status)
    db.flush()
    return IntakeGateDecision(
        action="create_requirement",
        reason="fingerprint is eligible for requirement materialization",
        fingerprint_key=key,
        cooldown_until=row.cooldown_until,
        status=row.status,
    )


def mark_requirement_intake_materialized(
    db: Session,
    *,
    fingerprint_key: str,
    requirement: RequirementRow,
    workflow_run_id: int | None = None,
) -> None:
    row = db.query(RequirementIntakeFingerprintRow).filter(RequirementIntakeFingerprintRow.fingerprint_key == fingerprint_key).first()
    if row is None:
        return
    row.status = "linked_requirement"
    row.linked_requirement_id = int(requirement.id)
    row.linked_workflow_run_id = workflow_run_id or (int(requirement.active_workflow_run_id) if requirement.active_workflow_run_id is not None else row.linked_workflow_run_id)
    row.last_materialized_at = utcnow()
    db.add(row)
    db.flush()


def mark_requirement_intake_resolved(
    db: Session,
    *,
    fingerprint_key: str,
    release_id: int | None = None,
    resolution: dict[str, Any] | None = None,
) -> None:
    row = db.query(RequirementIntakeFingerprintRow).filter(RequirementIntakeFingerprintRow.fingerprint_key == fingerprint_key).first()
    if row is None:
        return
    row.status = "resolved"
    row.resolved_at = utcnow()
    row.linked_release_id = release_id or row.linked_release_id
    row.resolution_json = _json_dumps(resolution or {})
    db.add(row)
    db.flush()


def _touch(row: RequirementIntakeFingerprintRow, *, now: datetime, latest_evidence: dict[str, Any] | None) -> None:
    row.last_seen_at = now
    row.occurrence_count = int(row.occurrence_count or 0) + 1
    if latest_evidence is not None:
        row.latest_evidence_json = _json_dumps(latest_evidence)


def _linked_requirement(db: Session, row: RequirementIntakeFingerprintRow) -> RequirementRow | None:
    if row.linked_requirement_id is None:
        return None
    return db.query(RequirementRow).filter(RequirementRow.id == int(row.linked_requirement_id)).first()


def _is_active_requirement(requirement: RequirementRow) -> bool:
    return str(requirement.status or "") in ACTIVE_REQUIREMENT_STATUSES


def _has_active_workflow(db: Session, requirement: RequirementRow) -> bool:
    if requirement.active_workflow_run_id is None:
        return False
    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == int(requirement.active_workflow_run_id)).first()
    return run is not None and str(run.status or "") in ACTIVE_WORKFLOW_STATUSES


def _severity_rank(value: str) -> int:
    return {"low": 0, "normal": 1, "medium": 1, "high": 2, "critical": 3}.get(str(value or "").lower(), 1)


def _normalize(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "-")[:96]


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
