"""Deployment event ledger helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow
from server.database_deployments import DeploymentEventRow
from server.schemas_deployment_events import DeploymentEventOut


def record_deployment_event(
    db: Session,
    record: DeploymentRecordRow,
    *,
    event_type: str,
    actor: str | None = None,
    status_from: str | None = None,
    status_to: str | None = None,
    summary: str | None = None,
    payload: dict[str, Any] | None = None,
) -> DeploymentEventRow:
    row = DeploymentEventRow(
        deployment_record_id=int(record.id),
        event_type=event_type,
        actor=_clean(actor),
        status_from=_clean(status_from),
        status_to=_clean(status_to),
        summary=_clean(summary),
        payload_json=_json_dump(payload or {}),
    )
    db.add(row)
    return row


def list_deployment_events(db: Session, record_id: int) -> list[DeploymentEventOut]:
    rows = (
        db.query(DeploymentEventRow)
        .filter(DeploymentEventRow.deployment_record_id == int(record_id))
        .order_by(DeploymentEventRow.id.asc())
        .all()
    )
    return [_event_out(row) for row in rows]


def _event_out(row: DeploymentEventRow) -> DeploymentEventOut:
    return DeploymentEventOut(
        id=int(row.id),
        deployment_record_id=int(row.deployment_record_id),
        event_type=str(row.event_type or ""),
        actor=_clean(row.actor),
        status_from=_clean(row.status_from),
        status_to=_clean(row.status_to),
        summary=_clean(row.summary),
        payload=_json_object(row.payload_json),
        created_at=row.created_at,
    )


def _clean(value: str | None) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def _json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_object(value: str | None) -> dict[str, object]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
