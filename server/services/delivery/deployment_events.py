"""Deployment event ledger helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from server.database import DeploymentEventRow, DeploymentRecordRow
from server.schemas_deployment_events import DeploymentEventOut

_DELIVERY_MESSAGE_MARKER = "__delivery_event__"


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
    next_sequence = _next_sequence(db, int(record.id))
    row = DeploymentEventRow(
        deployment_record_id=int(record.id),
        sequence=next_sequence,
        event_type=event_type,
        step_key=_clean(actor),
        message=_json_dump(
            {
                _DELIVERY_MESSAGE_MARKER: True,
                "actor": _clean(actor),
                "status_from": _clean(status_from),
                "status_to": _clean(status_to),
                "summary": _clean(summary),
                "payload": payload or {},
            }
        ),
    )
    db.add(row)
    db.flush()
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
    payload = _json_object(row.message)
    is_delivery_event = bool(payload.get(_DELIVERY_MESSAGE_MARKER))
    return DeploymentEventOut(
        id=int(row.id),
        deployment_record_id=int(row.deployment_record_id),
        event_type=str(row.event_type or ""),
        actor=_clean(payload.get("actor"))
        if is_delivery_event
        else _clean(row.step_key),
        status_from=_clean(payload.get("status_from")) if is_delivery_event else None,
        status_to=_clean(payload.get("status_to")) if is_delivery_event else None,
        summary=_clean(payload.get("summary"))
        if is_delivery_event
        else _clean(row.message),
        payload=_payload_object(payload) if is_delivery_event else {},
        created_at=row.created_at,
    )


def _next_sequence(db: Session, record_id: int) -> int:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :record_id)"),
        {"namespace": 42_101, "record_id": int(record_id)},
    )
    return int(
        (
            db.query(func.coalesce(func.max(DeploymentEventRow.sequence), 0))
            .filter(DeploymentEventRow.deployment_record_id == int(record_id))
            .scalar()
            or 0
        )
        + 1
    )


def _clean(value: object | None) -> str | None:
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


def _payload_object(value: dict[str, object]) -> dict[str, object]:
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else {}
