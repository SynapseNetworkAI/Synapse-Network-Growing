"""Inventory helpers for the X daily planner."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import SocialPostDraftRow, utcnow
from server.services.social import publishing

DAILY_PLANNER_ACTIVE_STATUSES = {"generating", "needs_review", "approved"}


def _daily_planner_raw_metadata(row: SocialPostDraftRow) -> dict[str, Any]:
    data = publishing._json_loads(row.raw_agent_output_json, {})
    return data if isinstance(data, dict) else {}


def _daily_planner_posts_for_local_date(
    db: Session, *, account_id: int, local_date: str
) -> list[SocialPostDraftRow]:
    rows = (
        db.query(SocialPostDraftRow)
        .filter(
            SocialPostDraftRow.platform == "x",
            SocialPostDraftRow.account_id == account_id,
            SocialPostDraftRow.source_type == "daily_planner",
        )
        .order_by(SocialPostDraftRow.id.desc())
        .limit(100)
        .all()
    )
    return [
        row
        for row in rows
        if str(_daily_planner_raw_metadata(row).get("planner_local_date") or "")
        == local_date
    ]


def active_daily_planner_posts(
    rows: list[SocialPostDraftRow],
) -> list[SocialPostDraftRow]:
    return [
        row for row in rows if str(row.status or "") in DAILY_PLANNER_ACTIVE_STATUSES
    ]


def _normalize_utc(value: datetime | None) -> datetime:
    current = value or utcnow()
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _daily_planner_row_updated_at(row: SocialPostDraftRow) -> datetime:
    return _normalize_utc(row.updated_at or row.created_at)


def _expire_stale_daily_planner_generating_posts(
    db: Session,
    rows: list[SocialPostDraftRow],
    *,
    now: datetime | None = None,
) -> list[int]:
    comparison_now = _normalize_utc(now)
    cutoff = comparison_now - timedelta(
        minutes=int(config.X_DAILY_PLANNER_GENERATING_TIMEOUT_MINUTES)
    )
    expired_ids: list[int] = []
    for row in rows:
        if str(row.status or "") != "generating":
            continue
        if _daily_planner_row_updated_at(row) > cutoff:
            continue
        row.status = "failed"
        row.failure_summary = (
            "daily_planner_generation_timeout: draft stayed generating for more "
            f"than {config.X_DAILY_PLANNER_GENERATING_TIMEOUT_MINUTES} minutes; "
            "it no longer counts toward today's draft inventory."
        )
        row.policy_check_json = publishing._json_dumps(
            publishing.run_content_policy_check(row.body_text or "").model_dump()
        )
        raw = _daily_planner_raw_metadata(row)
        raw.update(
            {
                "status": "failed",
                "source": "x_social_daily_content_planner",
                "error": row.failure_summary,
                "generating_timeout_minutes": int(
                    config.X_DAILY_PLANNER_GENERATING_TIMEOUT_MINUTES
                ),
            }
        )
        row.raw_agent_output_json = publishing._json_dumps(raw)
        publishing._record_event(
            db,
            row,
            "daily_planner_generation_timeout",
            actor="x_social_daily_content_planner",
            summary=row.failure_summary,
            payload={
                "generating_timeout_minutes": int(
                    config.X_DAILY_PLANNER_GENERATING_TIMEOUT_MINUTES
                )
            },
        )
        expired_ids.append(int(row.id))
    if expired_ids:
        db.commit()
    return expired_ids


def daily_planner_inventory(
    db: Session, *, account_id: int, local_date: str
) -> tuple[list[SocialPostDraftRow], list[SocialPostDraftRow]]:
    rows = _daily_planner_posts_for_local_date(
        db, account_id=account_id, local_date=local_date
    )
    return rows, active_daily_planner_posts(rows)


def _daily_planner_slot(row: SocialPostDraftRow) -> int:
    raw = _daily_planner_raw_metadata(row)
    try:
        slot = int(raw.get("planner_slot") or 0)
    except (TypeError, ValueError):
        slot = 0
    if slot > 0:
        return slot
    match = re.search(r":slot-(\d+)$", str(raw.get("planner_run_key") or ""))
    return int(match.group(1)) if match else 0


def _next_daily_planner_slot(
    rows: list[SocialPostDraftRow], *, target_count: int = 3
) -> int:
    used = {
        _daily_planner_slot(row)
        for row in rows
        if str(row.status or "") in DAILY_PLANNER_ACTIVE_STATUSES
    }
    for slot in range(1, max(1, int(target_count)) + 1):
        if slot not in used:
            return slot
    return max(used or {0}) + 1
