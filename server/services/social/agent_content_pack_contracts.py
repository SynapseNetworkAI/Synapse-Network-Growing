"""Prompt and schema contracts for agent content packs."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from server.services.social.context_tags import ContextTagSnippet
from server.services.social.distribution_asset_signals import AssetSignal
from server.services.social.distribution_content_strategy import (
    platform_format_kind,
    platform_target_length,
)


class PlatformTaskPromptInput(BaseModel):
    asset_title: str
    asset_summary: str | None = None
    asset_body: str | None = None
    asset_metadata: dict[str, object] = Field(default_factory=dict)
    canonical_url: str | None = None
    platform: str
    channel_key: str
    display_name: str


def _code_block_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "language": {"type": "string"},
            "title": {"type": "string"},
            "code": {"type": "string"},
        },
        "required": ["language", "title", "code"],
    }


CANONICAL_ASSET_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "minLength": 1},
        "body": {"type": "string", "minLength": 1},
        "asset_type": {"type": "string", "minLength": 1},
        "source_type": {"type": "string", "minLength": 1},
        "goal_key": {"type": ["string", "null"]},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "code_blocks": {"type": "array", "items": _code_block_schema()},
        "recommended_channels": {"type": "array", "items": {"type": "string"}},
        "source_signal_refs": {"type": "array", "items": {"type": "string"}},
        "generation_reason": {"type": "string"},
    },
    "required": [
        "title",
        "summary",
        "body",
        "asset_type",
        "source_type",
        "goal_key",
        "key_facts",
        "code_blocks",
        "recommended_channels",
        "source_signal_refs",
        "generation_reason",
    ],
}

PLATFORM_DRAFT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
        "properties": {
            "platform_title": {"type": ["string", "null"]},
            "platform_body": {"type": ["string", "null"]},
            "x_format": {"type": ["string", "null"]},
            "tweets": {"type": "array", "items": {"type": "string"}},
            "format_kind": {"type": ["string", "null"]},
            "target_length": {"type": ["string", "null"]},
            "operator_checklist": {"type": ["string", "null"]},
            "risk_level": {"type": "string"},
            "rationale": {"type": "string"},
    },
    "required": [
        "platform_title",
        "platform_body",
        "x_format",
        "tweets",
        "format_kind",
        "target_length",
        "operator_checklist",
        "risk_level",
        "rationale",
    ],
}


def canonical_asset_prompt(
    *,
    asset_type: str,
    local_date: str,
    signals: list[AssetSignal],
    snippets: list[ContextTagSnippet],
) -> tuple[str, str]:
    system_prompt = (
        "You are the Synapse Network Agent Content Pack strategist. Generate one "
        "canonical, public-facing content asset that can be adapted for X, Hacker "
        "News, Reddit, V2EX, DEV, and Hashnode. Use only the provided signals and "
        "resolved source context as facts. Do not invent APIs, claims, metrics, "
        "partner names, or shipped features. Do not expose local paths, workflow "
        "JSON, secrets, stack traces, or branch noise. Return JSON only."
    )
    signal_block = "\n".join(
        f"- {signal.source_ref} | score={signal.score:.2f} | "
        f"{signal.title}: {signal.summary}"
        for signal in signals[:5]
    )
    user_prompt = (
        f"# Asset type\n{asset_type}\n\n"
        f"# Local date\n{local_date}\n\n"
        "# High-quality source signals\n"
        f"{signal_block}\n\n"
        "# Resolved source context\n"
        f"{_context_block(snippets) or 'No required source context for this asset type.'}\n\n"
        "# Output contract\n"
        "Create a structured canonical Asset JSON with title, summary, body, "
        "key_facts, code_blocks, recommended_channels, source_signal_refs, and "
        "generation_reason. The body must be a complete long-form mother draft: "
        "clear thesis, narrative sections, concrete examples, objections, and "
        "conclusion. For tutorials, include accurate code_blocks only from "
        "resolved context."
    )
    return system_prompt, user_prompt


def platform_task_prompt(payload: PlatformTaskPromptInput) -> tuple[str, str]:
    system_prompt = (
        "You are a platform-native developer distribution editor for Synapse "
        "Network. Adapt the canonical Asset into one channel-specific draft. "
        "Preserve facts from the Asset, but change voice and format for the "
        "platform. Do not auto-submit, do not ask for votes, and do not sound "
        "like an ad. Return JSON only."
    )
    canonical_warning = (
        f"Canonical URL: {payload.canonical_url}"
        if payload.canonical_url
        else "Canonical URL missing. For DEV/Hashnode, warn operator before publishing."
    )
    user_prompt = (
        f"# Platform\n{payload.display_name} ({payload.platform} / {payload.channel_key})\n\n"
        f"# Platform guidance\n{_platform_guidance(payload.platform, payload.channel_key)}\n\n"
        f"# Target format\nformat_kind={platform_format_kind(payload.platform)}\n"
        f"target_length={platform_target_length(payload.platform)}\n\n"
        "# Canonical Asset\n"
        f"Title: {payload.asset_title}\n"
        f"Summary: {payload.asset_summary or ''}\n"
        f"Body:\n{payload.asset_body or ''}\n\n"
        "# Structured facts\n"
        f"{json.dumps(payload.asset_metadata, ensure_ascii=False)[:6000]}\n\n"
        f"# Canonical policy\n{canonical_warning}\n\n"
        "# Output contract\n"
        "Return platform_title, platform_body, operator_checklist, risk_level, "
        "rationale, format_kind, and target_length. The operator_checklist must "
        "include Human Gate and platform-specific reminders. For DEV/Hashnode, "
        "write a complete Markdown long article, not a teaser, and include the "
        "canonical URL paste reminder when available. For Reddit/V2EX, write a "
        "substantive community discussion draft. For Hacker News, do not invent "
        "a long post: platform_body should contain only submit_title, submit_url "
        "or canonical_url reminder, and first_comment_draft. For X, strictly "
        "choose exactly one format and include x_format plus tweets: "
        "{\"x_format\":\"single|thread\",\"tweets\":[\"...\"],\"rationale\":\"...\"}. "
        "Use single only for short updates. Use thread for deep reasoning, "
        "tutorials, founder stories, or architecture posts. Each tweet must be "
        "under 280 weighted characters; URLs count as 23 and CJK characters count as 2."
    )
    return system_prompt, user_prompt


def _platform_guidance(platform: str, channel_key: str) -> str:
    normalized = platform.strip()
    if normalized == "x":
        return (
            "Dynamic X Variant: output either one normal tweet or a thread. "
            "Do not output a Premium long post in v1. Write the X Official "
            "Account draft in English, even when the canonical source material "
            "is Chinese."
        )
    if normalized == "hacker_news":
        return (
            "Use factual HN language. Submit a plain title and URL; optional "
            "first comment only. Avoid marketing words, emojis, hype, and vote asks."
        )
    if normalized == "reddit":
        return f"Write for {channel_key}; make it a discussion, not a link drop."
    if normalized == "v2ex":
        return "Use natural Chinese engineering-retrospective style."
    if normalized in {"dev", "devto", "hashnode"}:
        return (
            "Write a complete Markdown developer article with headings, examples, "
            "conclusion, and canonical URL checklist."
        )
    if normalized == "product_hunt":
        return "Launch-only copy. Do not imply it is ready for daily submission."
    return "Use a developer-community tone and keep all claims bounded."


def _context_block(snippets: list[ContextTagSnippet]) -> str:
    blocks: list[str] = []
    for snippet in snippets:
        blocks.append(
            f"## {snippet.ref_key} ({snippet.file_path})\n"
            f"```{snippet.language or ''}\n{snippet.excerpt}\n```"
        )
    return "\n\n".join(blocks)
