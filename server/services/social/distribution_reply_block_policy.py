"""Policy helpers for X reply block generation."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import SocialReplyItemRow
from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_core import _record_event
from server.services.social.publishing import SocialPublishError, x_oauth_token_provider


def _json_loads(raw: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def existing_complete_reply_block(
    db: Session, asset: SocialContentAssetRow, *, target_count: int
) -> bool:
    reply_ids = _reply_block_ids(asset)
    if len(reply_ids) < max(1, int(target_count)):
        return False
    rows = (
        db.query(SocialReplyItemRow).filter(SocialReplyItemRow.id.in_(reply_ids)).all()
    )
    if len(rows) < max(1, int(target_count)):
        return False
    return not any(row.status in {"failed", "rejected"} for row in rows)


def _reply_block_ids(asset: SocialContentAssetRow) -> list[int]:
    reply_block = _json_loads(asset.agent_metadata_json).get("reply_block")
    if not isinstance(reply_block, dict):
        return []
    return [
        parsed
        for value in reply_block.get("reply_ids", [])
        if (parsed := _safe_int(value))
    ]


def _safe_int(value: object) -> int:
    if isinstance(value, int):
        return value
    return int(value) if str(value).isdigit() else 0


def require_source_sync_auth_if_needed(
    db: Session,
    asset: SocialContentAssetRow,
    *,
    source_posts: list[dict[str, object]] | None,
    actor: str,
) -> None:
    if source_posts or asset_has_explicit_source_evidence(asset):
        return
    try:
        x_oauth_token_provider.get_access_token()
    except ValueError as exc:
        oauth_status = x_source_auth_status_from_config_error(exc)
        _record_event(
            db,
            asset,
            None,
            "x_source_sync_blocked",
            actor,
            "X source sync is blocked because X OAuth client configuration is missing.",
            {
                "oauth_status": oauth_status,
                "requires_authorization": True,
                "auth_message": str(exc),
            },
        )
        db.commit()
        raise ValueError(
            "X OAuth client configuration missing. Configure X_OAUTH_CLIENT_ID and "
            "X_OAUTH_CLIENT_SECRET, restart backend, then reconnect X before syncing "
            "trend/radar sources."
        ) from exc
    except SocialPublishError as exc:
        _record_event(
            db,
            asset,
            None,
            "x_source_sync_blocked",
            actor,
            "X source sync is blocked because X OAuth is not authorized.",
            {
                "oauth_status": x_source_auth_status_from_error(exc),
                "requires_authorization": True,
                "auth_message": exc.summary,
            },
        )
        db.commit()
        raise ValueError(
            "X token unavailable. Reconnect X before syncing trend/radar sources, "
            "or provide explicit source_posts."
        ) from exc


def asset_has_explicit_source_evidence(asset: SocialContentAssetRow) -> bool:
    return _asset_text_has_x_status(asset) or _asset_has_source_candidates(asset)


def _asset_text_has_x_status(asset: SocialContentAssetRow) -> bool:
    text = f"{asset.body or ''}\n{asset.summary or ''}".lower()
    return "x.com/" in text and "/status/" in text


def _asset_has_source_candidates(asset: SocialContentAssetRow) -> bool:
    reply_block = _json_loads(asset.agent_metadata_json).get("reply_block")
    return bool(
        isinstance(reply_block, dict) and reply_block.get("source_candidate_ids")
    )


def x_source_auth_status_from_error(exc: SocialPublishError) -> str:
    if exc.kind == "x_refresh_failed":
        return "invalid_refresh_token"
    if _summary_indicates_missing_local_secret(exc.summary):
        return "missing_local_secret"
    if exc.kind == "x_auth_failed":
        return "needs_authorization"
    return "error"


def x_source_auth_status_from_config_error(exc: ValueError) -> str:
    summary = str(exc).lower()
    if "x_oauth_client_id" in summary or "x_oauth_client_secret" in summary:
        return "missing_client_config"
    return "error"


def _summary_indicates_missing_local_secret(summary: str | None) -> bool:
    normalized = str(summary or "").lower()
    return any(
        token in normalized for token in ("missing", "not found", "local secret")
    )
