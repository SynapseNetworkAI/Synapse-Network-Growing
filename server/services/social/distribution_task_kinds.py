"""Task-kind routing for social distribution assets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from server.database_social_distribution import SocialContentAssetRow


@dataclass(frozen=True)
class SocialDistributionTaskKind:
    code: str
    label: str
    action: str


CONTENT_DISTRIBUTION_KIND = SocialDistributionTaskKind(
    code="content_distribution",
    label="内容分发",
    action="approve_and_generate_platform_docs",
)
MULTI_PLATFORM_KIND = SocialDistributionTaskKind(
    code="multi_platform_campaign",
    label="多平台分发",
    action="approve_and_generate_platform_docs",
)
X_ARTICLE_PACK_KIND = SocialDistributionTaskKind(
    code="x_article_pack",
    label="X Article",
    action="generate_x_article_pack",
)
X_MEDIA_POST_KIND = SocialDistributionTaskKind(
    code="x_media_post",
    label="X 图文帖",
    action="approve_and_generate_platform_docs",
)
X_REPLY_BLOCK_KIND = SocialDistributionTaskKind(
    code="x_reply_block",
    label="X 回复块",
    action="generate_x_reply_candidates",
)
MANUAL_PLATFORM_POST_KIND = SocialDistributionTaskKind(
    code="manual_platform_post",
    label="人工平台帖",
    action="approve_and_generate_platform_docs",
)


def task_kind_for_asset(asset: SocialContentAssetRow) -> SocialDistributionTaskKind:
    metadata = _json_object(getattr(asset, "agent_metadata_json", None))
    task_type = str(metadata.get("task_type") or "").strip().lower()
    if task_type == "x_article_pack":
        return X_ARTICLE_PACK_KIND
    if task_type == "x_media_post":
        return X_MEDIA_POST_KIND
    if task_type == "x_reply_block":
        return X_REPLY_BLOCK_KIND
    if task_type == "multi_platform_campaign":
        return MULTI_PLATFORM_KIND
    if task_type == "manual_platform_post":
        return MANUAL_PLATFORM_POST_KIND
    post_intent = str(metadata.get("post_intent") or "").strip().lower()
    asset_type = str(getattr(asset, "asset_type", "") or "").strip().lower()
    target_platforms = metadata.get("target_platforms")
    is_x_only = target_platforms == ["x"] or target_platforms == ("x",)
    if post_intent == "engagement_reply" or asset_type in {"reply", "engagement_reply"}:
        return X_REPLY_BLOCK_KIND
    if post_intent == "reply" and is_x_only:
        return X_REPLY_BLOCK_KIND
    return CONTENT_DISTRIBUTION_KIND


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
