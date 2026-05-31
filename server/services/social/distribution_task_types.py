"""Task type policy for social publishing workflows."""

from __future__ import annotations

from typing import Iterable

CONTENT_DISTRIBUTION = "content_distribution"
LEGACY_UNCLASSIFIED = "legacy_unclassified"
X_ARTICLE_PACK = "x_article_pack"
X_MEDIA_POST = "x_media_post"
X_REPLY_BLOCK = "x_reply_block"
MULTI_PLATFORM_CAMPAIGN = "multi_platform_campaign"
MANUAL_PLATFORM_POST = "manual_platform_post"

DEFAULT_TASK_TYPE = MULTI_PLATFORM_CAMPAIGN

X_ONLY_TASK_TYPES = {X_ARTICLE_PACK, X_MEDIA_POST, X_REPLY_BLOCK}
VALID_TASK_TYPES = {
    CONTENT_DISTRIBUTION,
    X_ARTICLE_PACK,
    X_MEDIA_POST,
    X_REPLY_BLOCK,
    MULTI_PLATFORM_CAMPAIGN,
    MANUAL_PLATFORM_POST,
}

GENERATOR_KEYS = {
    CONTENT_DISTRIBUTION: "multi_platform_distribution_generator",
    X_ARTICLE_PACK: "x_article_pack_generator",
    X_MEDIA_POST: "x_media_post_generator",
    X_REPLY_BLOCK: "x_reply_block_generator",
    MULTI_PLATFORM_CAMPAIGN: "multi_platform_distribution_generator",
    MANUAL_PLATFORM_POST: "manual_platform_post_generator",
}


def normalize_social_task_type(
    value: str | None,
    *,
    post_intent: str | None = None,
    target_platforms: Iterable[str] | None = None,
) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_TASK_TYPES:
        return raw
    intent = str(post_intent or "").strip().lower()
    if intent == "engagement_reply":
        return X_REPLY_BLOCK
    platforms = {str(item).strip().lower() for item in target_platforms or [] if item}
    if len(platforms) > 1:
        return MULTI_PLATFORM_CAMPAIGN
    return DEFAULT_TASK_TYPE


def task_type_target_platforms(task_type: str, requested: list[str]) -> list[str]:
    if task_type in X_ONLY_TASK_TYPES:
        non_x = [item for item in requested if item != "x"]
        if non_x:
            raise ValueError(
                f"{task_type} is X-only; choose multi_platform_campaign for other channels."
            )
        return ["x"]
    if task_type == MANUAL_PLATFORM_POST and len(requested) > 1:
        raise ValueError("manual_platform_post supports exactly one platform.")
    if task_type == MULTI_PLATFORM_CAMPAIGN:
        return requested or ["x", "v2ex", "hacker_news", "devto"]
    return requested or ["x"]


def task_type_label(task_type: str) -> str:
    if task_type == X_ARTICLE_PACK:
        return "X Article Pack"
    if task_type == X_MEDIA_POST:
        return "X Media Post"
    if task_type == X_REPLY_BLOCK:
        return "X Reply Block"
    if task_type == MULTI_PLATFORM_CAMPAIGN:
        return "Multi-platform Campaign"
    if task_type == MANUAL_PLATFORM_POST:
        return "Manual Platform Post"
    if task_type == CONTENT_DISTRIBUTION:
        return "General Content Distribution"
    if task_type == LEGACY_UNCLASSIFIED:
        return "Legacy / Unclassified"
    return task_type


def generator_key_for_task_type(task_type: str) -> str:
    return GENERATOR_KEYS.get(task_type, GENERATOR_KEYS[DEFAULT_TASK_TYPE])


def channel_selection_mode(task_type: str) -> str:
    if task_type in X_ONLY_TASK_TYPES:
        return "locked_x"
    if task_type == MULTI_PLATFORM_CAMPAIGN:
        return "multi_platform"
    if task_type == CONTENT_DISTRIBUTION:
        return "multi_platform"
    return "single_manual_platform"
