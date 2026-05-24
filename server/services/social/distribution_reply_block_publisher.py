"""Scheduled publisher wrapper for due X reply block assets."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.database_social_distribution import SocialContentAssetRow
from server.services.result_objects import ServiceObjectResult, service_object_result
from server.services.social.distribution_reply_blocks import (
    DEFAULT_REPLY_BLOCK_MAX_SECONDS,
    DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS,
    generate_x_reply_block_candidates,
)


@service_object_result
def run_x_social_daily_reply_block_publisher(db: Session) -> ServiceObjectResult:
    now = datetime.now(timezone.utc)
    rows = (
        db.query(SocialContentAssetRow)
        .filter(
            SocialContentAssetRow.status.in_(("draft", "active", "ready", "proposed"))
        )
        .order_by(
            SocialContentAssetRow.updated_at.asc(), SocialContentAssetRow.id.asc()
        )
        .limit(50)
        .all()
    )
    for asset in rows:
        metadata = _json_loads(asset.agent_metadata_json)
        if str(metadata.get("post_intent") or "") != "engagement_reply":
            continue
        if _planned_at_is_future(str(metadata.get("planned_publish_at") or ""), now):
            continue
        try:
            result = generate_x_reply_block_candidates(
                db,
                asset_id=int(asset.id),
                target_count=5,
                actor="x_social_daily_reply_block_publisher",
                agent_review=True,
                max_seconds=DEFAULT_REPLY_BLOCK_MAX_SECONDS,
                per_reply_timeout_seconds=DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS,
            )
        except ValueError as exc:
            return {
                "processed": False,
                "asset_id": int(asset.id),
                "blocked_reason": str(exc),
                "auto_publish": False,
            }
        return {
            "processed": True,
            "asset_id": int(asset.id),
            "result": dict(result),
            "auto_publish": False,
        }
    return {
        "processed": False,
        "asset_id": None,
        "blocked_reason": "no_due_engagement_reply_asset",
        "auto_publish": False,
    }


def _planned_at_is_future(raw: str, now: datetime) -> bool:
    if not raw.strip():
        return False
    try:
        planned_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return planned_at.astimezone(timezone.utc) > now


def _json_loads(raw: str | None) -> dict[str, object]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
