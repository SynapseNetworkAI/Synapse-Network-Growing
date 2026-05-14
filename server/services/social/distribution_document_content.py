"""Markdown and structured content helpers for social distribution documents."""

from __future__ import annotations

import json
from typing import Any

from server.database_social_distribution import (
    SocialContentAssetRow,
    SocialDistributionTaskRow,
)
from server.services.social.distribution_core import (
    _clean_optional,
    _normalize_platform,
)
from server.services.social.distribution_content_strategy import (
    X_LONG_POST_SOFT_LIMIT,
    platform_format_kind,
    platform_target_length,
    x_format_from_metadata,
    x_long_post_text_from_metadata,
    x_tweets_from_metadata,
    x_weighted_character_count,
)


def build_source_plan_payload(
    *,
    title: str,
    source_material: str | None,
    target_audience: str | None,
    target_platforms: list[str],
    canonical_url: str | None,
    source_doc_path: str | None,
) -> dict[str, object]:
    platforms = clean_platform_list(target_platforms) or [
        "x",
        "v2ex",
        "hacker_news",
        "devto",
    ]
    material = str(source_material or "").strip()
    core_points = extract_core_points(material)
    plan = {
        "core_angle": title.strip(),
        "target_audience": _clean_optional(target_audience)
        or "solo founders, developers, and agent workflow builders",
        "target_platforms": platforms,
        "source_doc_path": _clean_optional(source_doc_path),
        "canonical_url": _clean_optional(canonical_url),
        "core_points": core_points,
        "platform_matrix": [
            build_platform_plan(platform, title=title, core_points=core_points)
            for platform in platforms
        ],
        "asset_needs": [
            "source article or outline",
            "one public-safe architecture fact",
            "one human-gate or evidence example",
        ],
        "acceptance_steps": [
            "Source plan document exists.",
            "Each selected platform has a platform_draft document.",
            "X public action requires operator confirmation.",
            "Non-X platforms require manual published_url before live.",
        ],
    }
    validate_source_plan_payload(plan)
    return plan


def validate_source_plan_payload(plan: dict[str, object]) -> None:
    required = (
        "core_angle",
        "target_audience",
        "target_platforms",
        "platform_matrix",
        "acceptance_steps",
    )
    missing = [key for key in required if not plan.get(key)]
    if missing:
        raise ValueError(f"content_plan_invalid: missing {', '.join(missing)}")
    if not isinstance(plan.get("target_platforms"), list):
        raise ValueError("content_plan_invalid: target_platforms must be a list.")
    if not isinstance(plan.get("platform_matrix"), list):
        raise ValueError("content_plan_invalid: platform_matrix must be a list.")


def source_plan_markdown(plan: dict[str, object]) -> str:
    matrix = (
        plan.get("platform_matrix")
        if isinstance(plan.get("platform_matrix"), list)
        else []
    )
    lines = [
        "# Content Implementation Plan",
        "",
        f"Core angle: {plan.get('core_angle')}",
        f"Audience: {plan.get('target_audience')}",
        "",
        "## Core Points",
    ]
    lines.extend(f"- {point}" for point in plan.get("core_points", []) if point)
    lines.extend(["", "## Platform Matrix"])
    for item in matrix:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('platform')}: {item.get('angle')} Action: {item.get('operator_action')}"
            )
    lines.extend(["", "## Acceptance Steps"])
    lines.extend(f"- {step}" for step in plan.get("acceptance_steps", []) if step)
    return "\n".join(lines).strip()


def platform_document_markdown(
    asset: SocialContentAssetRow, task: SocialDistributionTaskRow
) -> str:
    metadata = parse_json_object(task.metadata_json)
    normalized = _normalize_platform(task.platform)
    if normalized == "x":
        return x_platform_document_markdown(asset, task, metadata)
    if normalized == "hacker_news":
        return hn_platform_document_markdown(asset, task, metadata)
    parts = [
        f"# {task.platform_title or asset.title}",
        "",
        f"Platform: {task.platform} / {task.channel_key}",
        f"Format: {metadata.get('format_kind') or platform_format_kind(task.platform)}",
        f"Target length: {metadata.get('target_length') or platform_target_length(task.platform)}",
        "",
        "## Draft",
        task.platform_body or "",
    ]
    if task.operator_checklist:
        parts.extend(["", "## Operator Checklist", task.operator_checklist])
    if asset.canonical_url:
        parts.extend(["", f"Canonical URL: {asset.canonical_url}"])
    return "\n".join(parts).strip()


def canonical_article_markdown(
    asset: SocialContentAssetRow, source_plan: dict[str, Any] | None = None
) -> str:
    plan = source_plan or {}
    core_points = plan.get("core_points") if isinstance(plan.get("core_points"), list) else []
    matrix = plan.get("platform_matrix") if isinstance(plan.get("platform_matrix"), list) else []
    audience = str(plan.get("target_audience") or "").strip()
    body = str(asset.body or asset.summary or "").strip()
    lines = [
        f"# {asset.title}",
        "",
        "## Thesis",
        asset.summary
        or "A source content task should become one complete canonical article before platform adaptation.",
    ]
    if audience:
        lines.extend(["", "## Audience", audience])
    if core_points:
        lines.extend(["", "## Core Points"])
        lines.extend(f"- {point}" for point in core_points if point)
    if body:
        lines.extend(["", "## Source Material", body])
    lines.extend(
        [
            "",
            "## Narrative Draft",
            "This article starts from the source task, expands the main argument, "
            "and gives each platform enough substance to adapt without shrinking "
            "the idea into a teaser.",
            "",
            "A solo-company operating system is valuable because it reduces context "
            "switching, keeps workflow evidence attached to the work, and lets a "
            "human operator review direction before public distribution.",
            "",
            "The practical pattern is: write one canonical article, derive platform "
            "documents from that article, and keep publishing actions human-gated. "
            "That preserves both leverage and accountability.",
        ]
    )
    if matrix:
        lines.extend(["", "## Platform Adaptation Plan"])
        for item in matrix:
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('platform')}: {item.get('angle')} ({item.get('operator_action')})"
                )
    if asset.canonical_url:
        lines.extend(["", f"Canonical URL: {asset.canonical_url}"])
    return "\n".join(lines).strip()


def x_platform_document_markdown(
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow,
    metadata: dict[str, Any],
) -> str:
    tweets = x_tweets_from_metadata(metadata, task.platform_body)
    x_format = x_format_from_metadata(metadata, tweets)
    parts = [
        f"# {task.platform_title or asset.title}",
        "",
        f"Platform: {task.platform} / {task.channel_key}",
        f"Format: {_x_format_label(x_format)}",
        (
            "Counting: plain character count; Premium long post soft max=4000"
            if x_format == "long_post"
            else "Counting: conservative weighted chars; URLs=23, CJK/wide chars=2"
        ),
        "",
    ]
    if x_format == "long_post":
        post_text = x_long_post_text_from_metadata(metadata, task.platform_body)
        parts.extend(["## X Long Post", f"Character count: {len(post_text)}/{X_LONG_POST_SOFT_LIMIT}", "", post_text])
    elif x_format == "thread":
        parts.append("## Thread")
        for index, tweet in enumerate(tweets):
            parts.extend(
                [
                    "",
                    f"### Tweet {index + 1}/{len(tweets)} ({x_weighted_character_count(tweet)}/280)",
                    tweet,
                ]
            )
    else:
        tweet = tweets[0] if tweets else str(task.platform_body or "")
        parts.extend(["## Tweet", f"Weighted count: {x_weighted_character_count(tweet)}/280", "", tweet])
    if task.operator_checklist:
        parts.extend(["", "## Operator Checklist", task.operator_checklist])
    return "\n".join(parts).strip()


def _x_format_label(x_format: str) -> str:
    if x_format == "long_post":
        return "X Premium Long Post"
    if x_format == "thread":
        return "X Thread"
    return "Single X Post"


def hn_platform_document_markdown(
    asset: SocialContentAssetRow,
    task: SocialDistributionTaskRow,
    metadata: dict[str, Any],
) -> str:
    parts = [
        f"# {task.platform_title or asset.title}",
        "",
        f"Platform: {task.platform} / {task.channel_key}",
        f"Format: {metadata.get('format_kind') or 'hn_submission'}",
        f"Target length: {metadata.get('target_length') or platform_target_length(task.platform)}",
        "",
        "## Submission",
        task.platform_body or "",
    ]
    if asset.canonical_url:
        parts.extend(["", f"Canonical URL: {asset.canonical_url}"])
    if task.operator_checklist:
        parts.extend(["", "## Operator Checklist", task.operator_checklist])
    return "\n".join(parts).strip()


def summary_from_text(value: str | None) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    return text[:240]


def clean_platform_list(values: list[str]) -> list[str]:
    return list(
        dict.fromkeys(
            _normalize_platform(str(value)) for value in values if str(value).strip()
        )
    )


def list_from_metadata(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def parse_json_object(value: str | None) -> dict[str, Any]:
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_platform_plan(
    platform: str, *, title: str, core_points: list[str]
) -> dict[str, str]:
    normalized = _normalize_platform(platform)
    base = core_points[0] if core_points else title
    if normalized == "x":
        return {
            "platform": normalized,
            "angle": f"Strong hook around {base}",
            "operator_action": "Human-gated API publish",
        }
    if normalized in {"v2ex", "hacker_news", "reddit"}:
        return {
            "platform": normalized,
            "angle": f"Engineering tradeoff and evidence for {base}",
            "operator_action": "Copy, post manually, then mark live",
        }
    if normalized in {"devto", "hashnode"}:
        return {
            "platform": normalized,
            "angle": f"Long-form tutorial or architecture article for {base}",
            "operator_action": "Set canonical URL, post manually, then mark live",
        }
    return {
        "platform": normalized,
        "angle": base,
        "operator_action": "Manual publish and status backfill",
    }


def extract_core_points(material: str) -> list[str]:
    points: list[str] = []
    for raw in material.splitlines():
        line = raw.strip().lstrip("-*0123456789.、) ").strip()
        if len(line) >= 12:
            points.append(line[:180])
        if len(points) >= 5:
            break
    return points or [
        "Turn one source task into platform-specific drafts with human-gated publishing."
    ]
