"""Queued notification dispatch with dedupe, cooldown, and retry control."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from server import config
from server.database import NotificationDeliveryRow, NotificationEventRow, NotificationFingerprintRow
from server.services.runtime.notification_policy import (
    normalize_risk_level,
    normalize_severity,
    priority_for,
    resolve_notification_policy,
    risk_rank,
    severity_rank,
)

logger = logging.getLogger("ops-dashboard.notifications")

_ONE_SHOT_EVENTS = {
    "human_gate_request.created",
    "human_gate_request.decided",
    "pr_opened",
    "branch_pushed",
    "workflow_run_started",
    "workflow_run_succeeded",
    "requirement_created",
    "approval_auto_approved",
}

_RETRY_DELAYS_SECONDS = (0, 30, 120, 600)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def _cooldown_seconds(priority: str, event_type: str, channel: str) -> int:
    if channel == "approval" and event_type.endswith(".pending_reminder"):
        return int(config.NOTIFICATION_APPROVAL_REMINDER_SECONDS)
    if priority == "p0":
        return int(config.NOTIFICATION_P0_COOLDOWN_SECONDS)
    if priority == "p1":
        return int(config.NOTIFICATION_P1_COOLDOWN_SECONDS)
    return int(config.NOTIFICATION_DEFAULT_COOLDOWN_SECONDS)


def enqueue_notification_event(
    db: Session,
    *,
    event_type: str,
    object_type: str,
    object_key: str,
    service_name: str,
    summary: str,
    next_action: str | None = None,
    severity: str = "normal",
    risk_level: str = "normal",
    status: str | None = None,
    requires_human: bool = False,
    workflow_key: str | None = None,
    current_state: str | None = None,
    actor_or_source: str = "system",
    occurred_at: datetime | None = None,
    object_refs: dict[str, object] | None = None,
    links: dict[str, str] | None = None,
    event_key: str | None = None,
    dispatch_immediately: bool = True,
) -> NotificationEventRow | None:
    """Persist a raw notification event and optionally dispatch it immediately.

    Business code should call this function instead of sending to Lark directly.
    The dispatcher is the only layer that decides whether the event is delivered,
    suppressed, retried, or dead-lettered.
    """

    policy = resolve_notification_policy(
        event_type=event_type,
        object_type=object_type,
        object_key=object_key,
        severity=severity,
        risk_level=risk_level,
        status=status,
        requires_human=requires_human,
        workflow_key=workflow_key,
        current_state=current_state,
    )
    if not policy.should_send_now or policy.channel in {"none", "digest"}:
        return None

    refs = dict(object_refs or {})
    refs.setdefault("priority", policy.priority)
    refs.setdefault("risk_level", risk_level)
    if workflow_key:
        refs.setdefault("workflow_key", workflow_key)
    if current_state:
        refs.setdefault("current_state", current_state)

    payload = {
        "service": service_name,
        "event_type": event_type,
        "occurred_at": _isoformat(occurred_at),
        "status_or_severity": f"{policy.priority} · {status or severity}",
        "summary": summary,
        "next_action": next_action or policy.next_action,
        "actor_or_source": actor_or_source,
        "object_refs": refs,
        "links": links or {},
        "priority": policy.priority,
        "risk_level": risk_level,
        "severity": severity,
        "workflow_key": workflow_key or "",
        "current_state": current_state or "",
        "policy_reason": policy.reason,
        "source_event_key": event_key or "",
    }
    row = NotificationEventRow(
        channel=policy.channel,
        event_type=event_type,
        priority=policy.priority,
        severity=normalize_severity(severity),
        risk_level=normalize_risk_level(risk_level),
        object_type=object_type,
        object_key=object_key,
        fingerprint_key=policy.dedupe_key,
        payload_json=_json_dump(payload),
        status="queued",
        next_attempt_at=_utcnow(),
    )
    db.add(row)
    db.flush()

    if dispatch_immediately and config.NOTIFICATION_DISPATCHER_ENABLED:
        dispatch_notification_queue(db, event_id=int(row.id), limit=1)
        db.refresh(row)
    return row


def dispatch_notification_queue(db: Session, *, limit: int = 50, event_id: int | None = None) -> list[NotificationEventRow]:
    """Consume queued notification events and apply suppression/retry policy."""

    now = _utcnow()
    query = db.query(NotificationEventRow).filter(NotificationEventRow.status == "queued")
    if event_id is not None:
        query = query.filter(NotificationEventRow.id == int(event_id))
    else:
        query = query.filter((NotificationEventRow.next_attempt_at.is_(None)) | (NotificationEventRow.next_attempt_at <= now))
    events = query.order_by(NotificationEventRow.id.asc()).limit(max(1, int(limit))).all()
    processed: list[NotificationEventRow] = []
    for event in events:
        _dispatch_one(db, event, now=now)
        processed.append(event)
    db.flush()
    return processed


def _dispatch_one(db: Session, event: NotificationEventRow, *, now: datetime) -> None:
    fingerprint = _load_or_create_fingerprint(db, event, now=now)
    previous_severity = str(fingerprint.severity or "normal")
    previous_risk = str(fingerprint.risk_level or "normal")
    is_upgrade = severity_rank(event.severity) > severity_rank(previous_severity) or risk_rank(event.risk_level) > risk_rank(previous_risk)

    fingerprint.occurrence_count = int(fingerprint.occurrence_count or 0) + 1
    fingerprint.last_seen_at = now
    fingerprint.latest_payload_json = event.payload_json
    fingerprint.priority = event.priority
    if is_upgrade:
        fingerprint.escalation_level = int(fingerprint.escalation_level or 0) + 1
        fingerprint.severity = event.severity
        fingerprint.risk_level = event.risk_level

    if _should_suppress(event, fingerprint, now=now, is_upgrade=is_upgrade):
        event.status = "suppressed"
        event.suppressed_reason = _suppression_reason(event, fingerprint, now=now)
        fingerprint.suppressed_count = int(fingerprint.suppressed_count or 0) + 1
        return

    if _channel_rate_limited(db, event, now=now):
        if str(event.channel or "") == "alert":
            _deliver_alert_rollup(db, event, fingerprint, now=now)
            event.status = "suppressed"
            event.suppressed_reason = "alert storm rollup emitted"
            fingerprint.suppressed_count = int(fingerprint.suppressed_count or 0) + 1
            return
        event.next_attempt_at = now + timedelta(seconds=60)
        event.suppressed_reason = "channel rate limit; deferred"
        return

    payload = _json_load(event.payload_json, {})
    if int(fingerprint.suppressed_count or 0) > 0:
        payload["summary"] = (
            f"{payload.get('summary', '')}\n\n"
            f"同类事件累计 {int(fingerprint.occurrence_count or 0)} 次，"
            f"已抑制 {int(fingerprint.suppressed_count or 0)} 条重复通知。"
        ).strip()
        payload.setdefault("object_refs", {})["suppressed_count"] = int(fingerprint.suppressed_count or 0)
        payload.setdefault("object_refs", {})["occurrence_count"] = int(fingerprint.occurrence_count or 0)

    from server.services.runtime.alerting import deliver_lark_notification

    event.attempt_count = int(event.attempt_count or 0) + 1
    delivery = deliver_lark_notification(
        db,
        channel=str(event.channel or ""),
        event_type=str(event.event_type or ""),
        event_key=f"notification:event:{int(event.id)}:attempt:{int(event.attempt_count)}",
        object_type=str(event.object_type or ""),
        object_key=str(event.object_key or ""),
        service_name=str(payload.get("service") or "Synapse Ops"),
        status_or_severity=str(payload.get("status_or_severity") or event.severity),
        summary=str(payload.get("summary") or ""),
        next_action=str(payload.get("next_action") or ""),
        actor_or_source=str(payload.get("actor_or_source") or "notification_dispatcher"),
        occurred_at=now,
        object_refs=dict(payload.get("object_refs") or {}),
        links=dict(payload.get("links") or {}),
        extra_fields={key: value for key, value in payload.items() if key not in {"service", "event_type", "status_or_severity", "summary", "next_action", "actor_or_source", "object_refs", "links"}},
        event_id=int(event.id),
        fingerprint_key=str(event.fingerprint_key or ""),
    )
    event.delivery_id = int(delivery.id)
    if delivery.status in {"sent", "skipped", "dry_run"}:
        event.status = "delivered"
        event.suppressed_reason = None
        fingerprint.last_sent_at = now
        fingerprint.cooldown_until = now + timedelta(seconds=_cooldown_seconds(event.priority, event.event_type, event.channel))
        fingerprint.suppressed_count = 0
        return

    _handle_failed_delivery(db, event, fingerprint, now=now)


def _load_or_create_fingerprint(db: Session, event: NotificationEventRow, *, now: datetime) -> NotificationFingerprintRow:
    row = db.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.fingerprint_key == event.fingerprint_key).first()
    if row is not None:
        return row
    row = NotificationFingerprintRow(
        fingerprint_key=str(event.fingerprint_key or ""),
        channel=str(event.channel or ""),
        event_type=str(event.event_type or ""),
        priority=str(event.priority or "p2"),
        severity=str(event.severity or "normal"),
        risk_level=str(event.risk_level or "normal"),
        status="open",
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=0,
        suppressed_count=0,
        latest_payload_json=event.payload_json,
    )
    db.add(row)
    db.flush()
    return row


def _should_suppress(
    event: NotificationEventRow,
    fingerprint: NotificationFingerprintRow,
    *,
    now: datetime,
    is_upgrade: bool,
) -> bool:
    if is_upgrade:
        return False
    if str(event.event_type or "") in _ONE_SHOT_EVENTS and fingerprint.last_sent_at is not None:
        return True
    cooldown_until = _aware(fingerprint.cooldown_until)
    return cooldown_until is not None and cooldown_until > now


def _suppression_reason(event: NotificationEventRow, fingerprint: NotificationFingerprintRow, *, now: datetime) -> str:
    if str(event.event_type or "") in _ONE_SHOT_EVENTS and fingerprint.last_sent_at is not None:
        return "one-shot event already delivered"
    cooldown_until = _aware(fingerprint.cooldown_until)
    if cooldown_until and cooldown_until > now:
        return f"cooldown until {cooldown_until.isoformat()}"
    return "duplicate suppressed"


def _channel_rate_limited(db: Session, event: NotificationEventRow, *, now: datetime) -> bool:
    limit_by_channel = {
        "alert": int(config.NOTIFICATION_ALERT_BURST_PER_MINUTE),
        "approval": 10,
        "requirement": 10,
        "release": 10,
    }
    limit = limit_by_channel.get(str(event.channel or ""), 10)
    if limit <= 0:
        return False
    window_start = now - timedelta(seconds=60)
    sent_count = (
        db.query(func.count(NotificationDeliveryRow.id))
        .filter(
            NotificationDeliveryRow.channel == str(event.channel or ""),
            NotificationDeliveryRow.created_at >= window_start,
        )
        .scalar()
        or 0
    )
    return int(sent_count) >= int(limit)


def _deliver_alert_rollup(
    db: Session,
    event: NotificationEventRow,
    fingerprint: NotificationFingerprintRow,
    *,
    now: datetime,
) -> None:
    """Emit one alert rollup for storm mode instead of paging every event."""

    bucket = int(now.timestamp() // 300)
    rollup_key = f"notification:alert_storm_rollup:{bucket}"
    existing = db.query(NotificationDeliveryRow).filter(NotificationDeliveryRow.event_key == rollup_key).first()
    if existing is not None:
        return

    from server.services.runtime.alerting import deliver_lark_notification

    deliver_lark_notification(
        db,
        channel="alert",
        event_type="alert_storm_rollup",
        event_key=rollup_key,
        object_type="notification_channel",
        object_key="alert",
        service_name="Synapse Ops",
        status_or_severity=f"{event.priority} · storm",
        summary=(
            "Alert storm mode is active. "
            f"Latest fingerprint `{event.fingerprint_key}` has occurred "
            f"{int(fingerprint.occurrence_count or 0)} times; repeated notifications are being suppressed."
        ),
        next_action="Open Ops Console notification status, inspect active alerts, and resolve the shared root cause.",
        actor_or_source="notification_dispatcher",
        occurred_at=now,
        object_refs={
            "priority": event.priority,
            "risk_level": event.risk_level,
            "fingerprint_key": event.fingerprint_key,
            "suppressed_count": int(fingerprint.suppressed_count or 0) + 1,
        },
        event_id=int(event.id),
        fingerprint_key=f"alert:alert_storm_rollup:channel:alert:{bucket}",
    )


def _handle_failed_delivery(
    db: Session,
    event: NotificationEventRow,
    fingerprint: NotificationFingerprintRow,
    *,
    now: datetime,
) -> None:
    max_attempts = int(config.NOTIFICATION_MAX_DELIVERY_ATTEMPTS)
    if int(event.attempt_count or 0) >= max_attempts:
        event.status = "dead_letter"
        event.suppressed_reason = f"delivery failed after {max_attempts} attempts"
        if str(event.event_type or "") != "lark_alert_delivery_failed":
            _enqueue_lark_delivery_failed(db, event, now=now)
        return
    event.status = "queued"
    attempt_index = min(int(event.attempt_count or 0), len(_RETRY_DELAYS_SECONDS) - 1)
    delay = _RETRY_DELAYS_SECONDS[attempt_index]
    event.next_attempt_at = now + timedelta(seconds=delay)
    event.suppressed_reason = f"delivery failed; retry in {delay}s"
    fingerprint.suppressed_count = int(fingerprint.suppressed_count or 0) + 1


def _enqueue_lark_delivery_failed(db: Session, event: NotificationEventRow, *, now: datetime) -> None:
    fingerprint_key = f"alert:lark_alert_delivery_failed:channel:{event.channel}:delivery:high"
    existing = db.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.fingerprint_key == fingerprint_key).first()
    existing_cooldown = _aware(existing.cooldown_until) if existing is not None else None
    if existing_cooldown is not None and existing_cooldown > now:
        return
    enqueue_notification_event(
        db,
        event_type="lark_alert_delivery_failed",
        object_type="notification_event",
        object_key=str(int(event.id)),
        service_name="Synapse Ops",
        summary=f"Lark notification delivery failed for {event.channel}/{event.event_type}.",
        next_action="Check Lark webhook configuration and dispatcher dead-letter events.",
        severity="high",
        risk_level="high",
        status="failed",
        actor_or_source="notification_dispatcher",
        object_refs={"notification_event_id": int(event.id), "channel": event.channel, "fingerprint_key": event.fingerprint_key},
        event_key=fingerprint_key,
        dispatch_immediately=False,
    )


def _isoformat(value: datetime | None) -> str:
    if value is None:
        value = _utcnow()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
