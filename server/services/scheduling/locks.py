"""Database-backed scheduler leases."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import SchedulerLockRow, utcnow


def acquire_scheduler_lock(
    db: Session,
    *,
    lock_key: str,
    owner_id: str,
    ttl_seconds: int,
    metadata: dict[str, Any] | None = None,
) -> SchedulerLockRow | None:
    now = utcnow()
    ttl = max(1, int(ttl_seconds or 300))
    expires_at = now + timedelta(seconds=ttl)
    row = db.query(SchedulerLockRow).filter(SchedulerLockRow.lock_key == lock_key).first()
    if row is not None:
        current_expires = _ensure_utc(row.expires_at)
        if str(row.status or "") == "held" and current_expires is not None and current_expires > now:
            return None
        row.owner_id = str(owner_id)
        row.status = "held"
        row.acquired_at = now
        row.expires_at = expires_at
        row.heartbeat_at = now
        row.metadata_json = _json_dumps(metadata or {})
        db.add(row)
        db.flush()
        return row

    row = SchedulerLockRow(
        lock_key=str(lock_key),
        owner_id=str(owner_id),
        status="held",
        acquired_at=now,
        expires_at=expires_at,
        heartbeat_at=now,
        metadata_json=_json_dumps(metadata or {}),
    )
    db.add(row)
    db.flush()
    return row


def release_scheduler_lock(db: Session, *, lock_key: str, owner_id: str | None = None) -> None:
    row = db.query(SchedulerLockRow).filter(SchedulerLockRow.lock_key == lock_key).first()
    if row is None:
        return
    if owner_id is not None and str(row.owner_id or "") != str(owner_id):
        return
    row.status = "released"
    row.heartbeat_at = utcnow()
    db.add(row)
    db.flush()


def scheduler_lock_snapshot(db: Session, lock_key: str) -> dict[str, object]:
    row = db.query(SchedulerLockRow).filter(SchedulerLockRow.lock_key == lock_key).first()
    if row is None:
        return {"lock_key": lock_key, "status": "missing", "held": False, "stale": False}
    now = utcnow()
    expires_at = _ensure_utc(row.expires_at)
    held = str(row.status or "") == "held" and expires_at is not None and expires_at > now
    stale = str(row.status or "") == "held" and expires_at is not None and expires_at <= now
    return {
        "lock_key": str(row.lock_key),
        "owner_id": str(row.owner_id or ""),
        "status": str(row.status or ""),
        "held": bool(held),
        "stale": bool(stale),
        "acquired_at": row.acquired_at.isoformat() if row.acquired_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "heartbeat_at": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
    }


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
