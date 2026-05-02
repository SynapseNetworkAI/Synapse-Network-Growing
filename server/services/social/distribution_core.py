"""Core helpers for social distribution workflows."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionEventRow,
    SocialDistributionTaskRow,
)

TASK_STATUSES = {
    "planned",
    "draft_ready",
    "needs_review",
    "approved",
    "submitted",
    "live",
    "removed",
    "rejected",
    "skipped",
    "failed",
}
ASSET_STATUSES = {
    "draft",
    "proposed",
    "approved",
    "active",
    "ready",
    "distributed",
    "archived",
    "rejected",
    "failed",
}
ACCOUNT_STATUSES = {
    "planned",
    "registered",
    "active",
    "paused",
    "needs_setup",
    "retired",
}
PLATFORM_ORDER = (
    "x",
    "hacker_news",
    "reddit",
    "v2ex",
    "devto",
    "dev",
    "hashnode",
    "product_hunt",
)


def _record_event(
    db: Session,
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow | None,
    event_type: str,
    actor: str,
    summary: str | None,
    payload: dict[str, object],
) -> None:
    db.add(
        SocialDistributionEventRow(
            asset_id=int(asset.id),
            task_id=int(task.id) if task else None,
            event_type=event_type,
            actor=actor.strip() or "system",
            summary=summary,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    )


def _clean_optional(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def _validate_task_status(status: str) -> None:
    if status.strip() not in TASK_STATUSES:
        raise ValueError(f"unknown distribution task status: {status}")


def _validate_asset_status(status: str) -> None:
    if status.strip() not in ASSET_STATUSES:
        raise ValueError(f"unknown content asset status: {status}")


def _validate_account_status(status: str) -> None:
    if status.strip() not in ACCOUNT_STATUSES:
        raise ValueError(f"unknown distribution account status: {status}")


def _normalize_platform(platform: str) -> str:
    return "devto" if platform.strip() == "dev" else platform.strip()
