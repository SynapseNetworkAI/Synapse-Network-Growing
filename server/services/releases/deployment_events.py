"""Append-only deployment event log helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from server.database import DeploymentEventRow, DeploymentRecordRow

DEPLOYMENT_EVENT_TYPES = {
    "stdout",
    "stderr",
    "step_started",
    "step_finished",
    "runner_status",
    "local_deploy_force_reset",
}
DEFAULT_EVENT_LIMIT = 200
MAX_EVENT_LIMIT = 1000


@dataclass(frozen=True)
class DeploymentEventsPage:
    items: list[DeploymentEventRow]
    next_sequence: int
    has_more: bool


def _normalize_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip().lower()
    return normalized if normalized in DEPLOYMENT_EVENT_TYPES else "runner_status"


def append_deployment_event(
    db: Session,
    *,
    deployment_record_id: int,
    event_type: str,
    message: str,
    step_key: str | None = None,
) -> DeploymentEventRow:
    """Append a full deployment event message without business-level truncation."""

    record = db.get(DeploymentRecordRow, int(deployment_record_id))
    if record is None:
        raise ValueError("Deployment record not found.")
    # stdout/stderr buffers flush from different threads. Serialize sequence
    # assignment per deployment record so chunked logs remain append-only.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :record_id)"),
        {"namespace": 42_100, "record_id": int(deployment_record_id)},
    )
    next_sequence = (
        db.query(func.coalesce(func.max(DeploymentEventRow.sequence), 0))
        .filter(DeploymentEventRow.deployment_record_id == int(deployment_record_id))
        .scalar()
        or 0
    ) + 1
    event = DeploymentEventRow(
        deployment_record_id=int(deployment_record_id),
        sequence=int(next_sequence),
        event_type=_normalize_event_type(event_type),
        step_key=(str(step_key).strip() if step_key else None),
        message=str(message or ""),
    )
    db.add(event)
    db.flush()
    return event


def list_deployment_events(
    db: Session,
    *,
    deployment_record_id: int,
    after_sequence: int = 0,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> DeploymentEventsPage:
    record = db.get(DeploymentRecordRow, int(deployment_record_id))
    if record is None:
        raise ValueError("Deployment record not found.")
    bounded_limit = max(1, min(int(limit or DEFAULT_EVENT_LIMIT), MAX_EVENT_LIMIT))
    cursor = max(0, int(after_sequence or 0))
    rows = (
        db.query(DeploymentEventRow)
        .filter(
            DeploymentEventRow.deployment_record_id == int(deployment_record_id),
            DeploymentEventRow.sequence > cursor,
        )
        .order_by(DeploymentEventRow.sequence.asc(), DeploymentEventRow.id.asc())
        .limit(bounded_limit + 1)
        .all()
    )
    has_more = len(rows) > bounded_limit
    items = rows[:bounded_limit]
    next_sequence = int(items[-1].sequence) if items else cursor
    return DeploymentEventsPage(
        items=items, next_sequence=next_sequence, has_more=has_more
    )
