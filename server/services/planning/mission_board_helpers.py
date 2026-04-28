"""Shared helpers for Mission Board projections."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ACTIVE_REQUIREMENT_STATUSES = {
    "draft",
    "planning",
    "ready",
    "executing",
    "running",
    "awaiting_operator",
    "delivery_ready",
    "ready_for_merge",
    "failed",
    "blocked",
    "needs_revision",
}
TERMINAL_REQUIREMENT_STATUSES = {
    "completed",
    "succeeded",
    "done",
    "cancelled",
    "deleted",
    "superseded",
}


def iso_timestamp(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def mission_item(
    *,
    item_id: str,
    item_type: str,
    title: str,
    status: str,
    risk_level: str = "normal",
    next_action: str = "",
    deep_link: str | None = None,
    evidence_label: str = "",
    updated_at: Any = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": item_type,
        "title": title,
        "status": status,
        "risk_level": risk_level,
        "next_action": next_action,
        "deep_link": deep_link,
        "evidence_label": evidence_label,
        "updated_at": iso_timestamp(updated_at),
    }


def mission_item_priority(item: dict[str, Any]) -> tuple[int, str]:
    status = str(item.get("status") or "")
    item_type = str(item.get("type") or "")
    severity = {
        "failed": 0,
        "blocked": 0,
        "awaiting_operator": 1,
        "needs_review": 1,
        "pending": 2,
        "approved": 2,
        "running": 2,
        "requested": 3,
    }.get(status, 4)
    type_boost = (
        0
        if item_type in {"product_opportunity", "workflow", "requirement_candidate"}
        else 1
    )
    return (severity + type_boost, str(item.get("updated_at") or ""))


def sort_mission_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=mission_item_priority)[:50]
