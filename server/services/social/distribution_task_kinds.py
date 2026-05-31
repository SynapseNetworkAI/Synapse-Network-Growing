"""Task-kind routing for social distribution assets."""

from __future__ import annotations

from dataclasses import dataclass

from server.database_social_distribution import SocialContentAssetRow
from server.services.social.distribution_task_type_backfill import infer_task_type_for_asset
from server.services.social.distribution_task_types import (
    CONTENT_DISTRIBUTION,
    LEGACY_UNCLASSIFIED,
    MANUAL_PLATFORM_POST,
    MULTI_PLATFORM_CAMPAIGN,
    X_ARTICLE_PACK,
    X_MEDIA_POST,
    X_REPLY_BLOCK,
)


@dataclass(frozen=True)
class SocialDistributionTaskKind:
    code: str
    label: str
    action: str


CONTENT_DISTRIBUTION_KIND = SocialDistributionTaskKind(
    code="content_distribution",
    label="通用内容发布",
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
LEGACY_UNCLASSIFIED_KIND = SocialDistributionTaskKind(
    code="legacy_unclassified",
    label="历史/未分类",
    action="review_legacy_content_task",
)


def task_kind_for_asset(asset: SocialContentAssetRow) -> SocialDistributionTaskKind:
    task_type, _ = infer_task_type_for_asset(asset)
    if task_type == X_ARTICLE_PACK:
        return X_ARTICLE_PACK_KIND
    if task_type == X_MEDIA_POST:
        return X_MEDIA_POST_KIND
    if task_type == X_REPLY_BLOCK:
        return X_REPLY_BLOCK_KIND
    if task_type == MULTI_PLATFORM_CAMPAIGN:
        return MULTI_PLATFORM_KIND
    if task_type == MANUAL_PLATFORM_POST:
        return MANUAL_PLATFORM_POST_KIND
    if task_type == LEGACY_UNCLASSIFIED:
        return LEGACY_UNCLASSIFIED_KIND
    if task_type == CONTENT_DISTRIBUTION:
        return CONTENT_DISTRIBUTION_KIND
    return CONTENT_DISTRIBUTION_KIND
