"""Read-only source sync bridge for X reply block generation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database_social_distribution import SocialContentAssetRow
from server.services.result_objects import ServiceObjectResult
from server.services.social.distribution_core import _record_event
from server.services.social.publishing import run_x_social_trend_radar_sweep


def _bounded_sync_list(values: Any, *, limit: int = 20) -> list[object]:
    if not isinstance(values, list):
        return []
    return [item for item in values[:limit]]


def _sync_int(result: ServiceObjectResult, key: str) -> int:
    return int(result.get(key) or 0)


def _sync_bool(result: ServiceObjectResult, key: str) -> bool:
    return bool(result.get(key))


def _reply_source_sync_core(result: ServiceObjectResult) -> dict[str, object]:
    return {
        "read_only": _sync_bool(result, "read_only"),
        "external_actions": _bounded_sync_list(result.get("external_actions")),
        "connector": str(result.get("connector") or ""),
        "x_read_connector_configured": _sync_bool(
            result, "x_read_connector_configured"
        ),
        "diagnostic": str(result.get("diagnostic") or ""),
    }


def _reply_source_sync_inventory(result: ServiceObjectResult) -> dict[str, object]:
    return {
        "created_trend_ids": _bounded_sync_list(result.get("created_trend_ids")),
        "retained_trend_ids": _bounded_sync_list(result.get("retained_trend_ids")),
        "retained_count": _sync_int(result, "retained_count"),
        "filtered_count": _sync_int(result, "filtered_count"),
        "watchlist_active_count": _sync_int(result, "watchlist_active_count"),
        "due_watchlist_count": _sync_int(result, "due_watchlist_count"),
        "synced_handles": _bounded_sync_list(result.get("synced_handles")),
        "skipped_short_text_count": _sync_int(result, "skipped_short_text_count"),
        "skipped_low_relevance_count": _sync_int(result, "skipped_low_relevance_count"),
        "duplicate_count": _sync_int(result, "duplicate_count"),
    }


def _reply_source_sync_budget(result: ServiceObjectResult) -> dict[str, object]:
    return {
        "budget_exhausted": _sync_bool(result, "budget_exhausted"),
        "budget_local_date": result.get("budget_local_date"),
        "budget_remaining_requests": _sync_int(result, "budget_remaining_requests"),
        "budget_remaining_source_posts": _sync_int(
            result, "budget_remaining_source_posts"
        ),
        "rate_limited": _sync_bool(result, "rate_limited"),
    }


def _reply_source_sync_summary(result: ServiceObjectResult) -> dict[str, object]:
    return {
        **_reply_source_sync_core(result),
        **_reply_source_sync_inventory(result),
        **_reply_source_sync_budget(result),
    }


def sync_reply_sources_from_watchlist(
    db: Session, asset: SocialContentAssetRow, *, actor: str
) -> ServiceObjectResult:
    result = run_x_social_trend_radar_sweep(db, min_relevance_score=0.70)
    summary = _reply_source_sync_summary(result)
    _record_event(
        db,
        asset,
        None,
        "x_reply_block_source_sync_attempted",
        actor,
        summary["diagnostic"]
        or "Ran read-only X watchlist sync before reply block generation.",
        summary,
    )
    db.commit()
    return ServiceObjectResult(root=summary)
