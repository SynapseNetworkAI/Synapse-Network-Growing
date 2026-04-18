"""Unified Lark notification and alert delivery helpers."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import NotificationDeliveryRow

logger = logging.getLogger("ops-dashboard.alerting")

_CHANNEL_WEBHOOKS = {
    "requirement": lambda: config.LARK_REQUIREMENT_WEBHOOK_URL,
    "alert": lambda: config.LARK_ALERT_WEBHOOK_URL,
    "release": lambda: config.LARK_RELEASE_WEBHOOK_URL,
}

_CHANNEL_TEMPLATES = {
    "requirement": "blue",
    "alert": "red",
    "release": "green",
}


def _isoformat(value: datetime | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def build_ops_url(path: str | None) -> str | None:
    """Build an absolute Ops Console URL for a relative route."""

    base = str(config.OPS_BASE_URL or "").strip().rstrip("/")
    route = str(path or "").strip()
    if not base or not route:
        return None
    if not route.startswith("/"):
        route = f"/{route}"
    return f"{base}{route}"


def notification_service_label(
    *,
    service_name: str | None = None,
    display_name: str | None = None,
    project_key: str | None = None,
) -> str:
    """Return the most specific human-facing service label for a notification."""

    return (
        str(service_name or "").strip()
        or str(display_name or "").strip()
        or str(project_key or "").strip()
        or "Synapse Ops"
    )


def _lark_link_block(links: dict[str, str]) -> str:
    rows = [f"- [{label}]({url})" for label, url in links.items() if str(url).strip()]
    return "\n".join(rows) if rows else "-"


def _lark_context_block(payload: dict[str, object]) -> str:
    refs = dict(payload.get("object_refs") or {})
    rows = []
    for key in ("requirement_id", "execution_id", "release_id", "fingerprint_key", "project_key"):
        value = refs.get(key)
        if value not in (None, "", []):
            rows.append(f"- {key}: `{value}`")
    return "\n".join(rows) if rows else "-"


def build_lark_card(payload: dict[str, object], *, channel: str) -> dict[str, object]:
    """Build a structured Lark interactive card payload for an Ops notification."""

    service = str(payload.get("service") or "Synapse Ops")
    event_type = str(payload.get("event_type") or "event")
    occurred_at = str(payload.get("occurred_at") or _isoformat(None))
    status_or_severity = str(payload.get("status_or_severity") or "-")
    actor_or_source = str(payload.get("actor_or_source") or "system")
    summary = str(payload.get("summary") or "").strip() or "No summary provided."
    next_action = str(payload.get("next_action") or "").strip() or "No action required."
    links = {
        str(label): str(url)
        for label, url in dict(payload.get("links") or {}).items()
        if str(label).strip() and str(url).strip()
    }

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": _CHANNEL_TEMPLATES.get(channel, "blue"),
                "title": {"tag": "plain_text", "content": f"[{service}] {event_type}"},
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**发生时间**\n{occurred_at}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**状态/级别**\n{status_or_severity}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**来源**\n{actor_or_source}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**事件类型**\n{event_type}"}},
                    ],
                },
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**发生了什么**\n{summary}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**需要做什么**\n{next_action}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**相关链接**\n{_lark_link_block(links)}"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**上下文**\n{_lark_context_block(payload)}"}},
            ],
        },
    }


def _send_lark_payload(
    payload: dict[str, object],
    *,
    webhook_url: str,
    timeout_sec: int = 10,
) -> tuple[bool, str | None]:
    request = urllib.request.Request(
        webhook_url,
        data=_json_dump(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
        return True, response_text
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return False, detail or f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def deliver_lark_notification(
    db: Session,
    *,
    channel: str,
    event_type: str,
    event_key: str,
    object_type: str,
    object_key: str,
    service_name: str,
    status_or_severity: str,
    summary: str,
    next_action: str,
    actor_or_source: str = "system",
    occurred_at: datetime | None = None,
    object_refs: dict[str, object] | None = None,
    links: dict[str, str] | None = None,
) -> NotificationDeliveryRow:
    """Persist and deliver a single Lark notification, skipping duplicate event keys."""

    existing = db.query(NotificationDeliveryRow).filter(NotificationDeliveryRow.event_key == event_key).first()
    if existing is not None:
        return existing

    payload = {
        "service": service_name,
        "event_type": event_type,
        "occurred_at": _isoformat(occurred_at),
        "status_or_severity": status_or_severity,
        "summary": summary,
        "next_action": next_action,
        "actor_or_source": actor_or_source,
        "object_refs": object_refs or {},
        "links": links or {},
    }
    row = NotificationDeliveryRow(
        channel=channel,
        event_type=event_type,
        event_key=event_key,
        object_type=object_type,
        object_key=object_key,
        service_name=service_name,
        status="pending",
        payload_json=_json_dump(payload),
    )
    db.add(row)
    db.flush()

    webhook_url = str(_CHANNEL_WEBHOOKS.get(channel, lambda: "")() or "").strip()
    if not webhook_url:
        row.status = "skipped"
        row.response_excerpt = "Webhook not configured"
        row.updated_at = row.updated_at
        logger.info("event=lark_notification_skipped channel=%s event_type=%s", channel, event_type)
        db.flush()
        return row

    success, response_text = _send_lark_payload(build_lark_card(payload, channel=channel), webhook_url=webhook_url)
    row.status = "sent" if success else "failed"
    row.response_excerpt = str(response_text or "")[:1000] or None
    row.delivered_at = datetime.now(timezone.utc) if success else None
    db.flush()
    if success:
        logger.info("event=lark_notification_sent channel=%s event_type=%s", channel, event_type)
    else:
        logger.warning(
            "event=lark_notification_failed channel=%s event_type=%s detail=%s",
            channel,
            event_type,
            str(response_text or "")[:500],
        )
    return row


def send_lark_text_alert(
    text: str,
    *,
    webhook_url: str | None = None,
    keyword: str | None = None,
    timeout_sec: int = 10,
) -> tuple[bool, str | None]:
    """Backward-compatible text alert helper for legacy callers."""

    target = (webhook_url or config.LARK_ALERT_WEBHOOK_URL or config.LARK_BOT_WEBHOOK_URL or "").strip()
    if not target:
        return False, "Lark webhook not configured"

    prefix = (keyword or config.LARK_BOT_KEYWORD or "告警").strip() or "告警"
    body_text = text.strip()
    if prefix and prefix not in body_text:
        body_text = f"{prefix}\n{body_text}"

    return _send_lark_payload(
        {
            "msg_type": "text",
            "content": {"text": body_text},
        },
        webhook_url=target,
        timeout_sec=timeout_sec,
    )
