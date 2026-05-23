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
X_REPLY_BLOCK_KIND = SocialDistributionTaskKind(
    code="x_reply_block",
    label="X 回复块",
    action="generate_x_reply_candidates",
)


def task_kind_for_asset(asset: SocialContentAssetRow) -> SocialDistributionTaskKind:
    metadata = _json_object(getattr(asset, "agent_metadata_json", None))
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
