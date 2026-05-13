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


class CanonicalArticleExpansionPromptInput(BaseModel):
    asset_title: str
    asset_summary: str | None = None
    source_material: str | None = None
    source_plan: str | None = None
    canonical_url: str | None = None
    skill_context: dict[str, str] = Field(default_factory=dict)


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

CANONICAL_ARTICLE_EXPANSION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "summary": {"type": "string", "minLength": 1},
        "body_markdown": {"type": "string", "minLength": 1},
        "key_facts": {"type": "array", "items": {"type": "string"}},
        "generation_reason": {"type": "string"},
    },
    "required": [
        "title",
        "summary",
        "body_markdown",
        "key_facts",
        "generation_reason",
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
        "include the canonical URL paste reminder when available. Respect "
        "platform length limits as soft maximums; never pad, repeat, or invent "
        "details to reach length. For DEV/Hashnode, adapt the complete Markdown "
        "canonical article without making it longer. For Reddit/V2EX, write a "
        "substantive community discussion draft focused on 1-2 concrete "
        "decisions. For Hacker News, keep the submission factual and restrained. "
        "For X, write the X Official Account draft in English even when the "
        "canonical source material is Chinese. Strictly choose exactly one "
        "Dynamic X Variant and include x_format plus tweets: "
        "{\"x_format\":\"single|thread\",\"tweets\":[\"...\"],\"rationale\":\"...\"}. "
        "Use single only for short updates. Use thread for deep reasoning, "
        "tutorials, founder stories, or architecture posts. Each tweet must be "
        "under 280 weighted characters; URLs count as 23 and CJK characters count as 2. "
        "Do not output a Premium long post in v1."
    )
    return system_prompt, user_prompt


def canonical_article_expansion_prompt(
    payload: CanonicalArticleExpansionPromptInput,
) -> tuple[str, str]:
    system_prompt = (
        "You are the Synapse Network build-in-public canonical article editor. "
        "Expand a short outline into one complete, true, reusable article for "
        "developer distribution. Use only the provided source material and skill "
        "context as facts. Do not invent technical details, metrics, customers, "
        "APIs, shipped features, or private implementation paths. Write with a "
        "pragmatic solo-founder engineering voice: concrete tradeoffs, real "
        "constraints, and useful detail. No marketing hype, success-guru tone, "
        "padding, or filler. Return JSON only."
    )
    skills_block = "\n\n".join(
        f"## {name}\n{_compact_text(content, max_chars=650)}"
        for name, content in payload.skill_context.items()
        if str(content or "").strip()
    )
    user_prompt = (
        f"# Asset title\n{payload.asset_title}\n\n"
        f"# Asset summary\n{_compact_text(payload.asset_summary, max_chars=420)}\n\n"
        f"# Source material / outline\n{_compact_text(payload.source_material, max_chars=2400)}\n\n"
        f"# Source plan\n{_compact_text(payload.source_plan, max_chars=900)}\n\n"
        f"# Canonical URL\n{payload.canonical_url or 'none'}\n\n"
        "# Skill context\n"
        f"{skills_block or 'No additional skill context provided.'}\n\n"
        "# Expansion rules\n"
        "- Write a canonical_article mother draft in Markdown.\n"
        "- Natural length only: if the facts support 1200 Chinese characters, stop there; if they support more, write more.\n"
        "- Prefer concise high-density output; a complete 700-1400 Chinese-character article is better than a padded long one.\n"
        "- No minimum length. No padding. Stop when the useful content is complete.\n"
        "- Include concrete engineering decisions, tradeoffs, costs, workflow details, and what was deliberately not built.\n"
        "- If source material is too thin, write a concise but complete article instead of inventing details.\n\n"
        "# Output contract\n"
        "Return title, summary, body_markdown, key_facts, generation_reason."
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
            "Use factual Hacker News language. Keep title and submission note "
            "restrained, technical, and evidence-based. Avoid marketing words, "
            "emojis, launch hype, and vague claims."
        )
    if normalized == "reddit":
        return (
            f"Write for {channel_key}; make it a discussion, not a link drop. "
            "MAX_LENGTH=2000 characters, no minimum. Extract only the 1-2 most "
            "counterintuitive or debatable technical decisions from the article. "
            "Do not cover everything if that would dilute the post."
        )
    if normalized == "v2ex":
        return (
            "Use natural Chinese engineering-retrospective style. MAX_LENGTH=2000 "
            "characters, no minimum. Pick the 1-2 details most likely to trigger "
            "developer discussion. Avoid product-announcement tone and AI-sounding filler."
        )
    if normalized in {"dev", "devto", "hashnode"}:
        return (
            "Use the complete canonical article or a close Markdown adaptation. "
            "Do not make it longer. Keep structure, code, and facts intact. Include "
            "canonical URL checklist."
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


def _compact_text(value: str | None, *, max_chars: int) -> str:
    text = "\n".join(line.rstrip() for line in str(value or "").strip().splitlines())
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}\n...[truncated for focused generation]"
