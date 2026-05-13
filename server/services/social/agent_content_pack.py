"""Structured-output helpers for agent-generated content packs."""

from __future__ import annotations

from typing import Any

from server.services.social.context_tags import (
    ContextTagSnippet,
    InsufficientSourceContextError,
    resolve_required_context_tag,
)
from server.services.social.agent_content_pack_contracts import (
    CANONICAL_ASSET_OUTPUT_SCHEMA,
    CANONICAL_ARTICLE_EXPANSION_OUTPUT_SCHEMA,
    PLATFORM_DRAFT_OUTPUT_SCHEMA,
    CanonicalArticleExpansionPromptInput,
    PlatformTaskPromptInput,
    canonical_asset_prompt,
    canonical_article_expansion_prompt,
    platform_task_prompt,
)
from server.services.social.agent_content_pack_models import (
    AgentContentGenerationError,
    AgentDistributionDraft,
    CanonicalArticleExpansion,
    CanonicalAssetPack,
    CanonicalCodeBlock,
)
from server.services.social.agent_content_pack_runtime import (
    _call_content_agent as _runtime_call_content_agent,
)
from server.services.social.agent_content_pack_safety import validate_public_safe_text
from server.services.social.agent_json_output import parse_agent_json_output
from server.services.social.distribution_content_strategy import (
    normalize_x_payload,
    platform_format_kind,
    platform_target_length,
    text_length_metadata,
)
from server.services.social.distribution_asset_signals import AssetSignal, _public_safe

_call_content_agent = _runtime_call_content_agent


def generate_canonical_asset_pack(
    *,
    asset_type: str,
    local_date: str,
    signals: list[AssetSignal],
) -> CanonicalAssetPack:
    context_refs = _required_context_refs_for_asset(asset_type, signals)
    snippets = _resolve_context_refs(context_refs)
    system_prompt, user_prompt = canonical_asset_prompt(
        asset_type=asset_type,
        local_date=local_date,
        signals=signals,
        snippets=snippets,
    )
    raw_text, metadata, model = _call_content_agent(
        system_prompt,
        user_prompt,
        output_schema=CANONICAL_ASSET_OUTPUT_SCHEMA,
        artifact_prefix="canonical-asset",
    )
    parsed = parse_agent_json_output(raw_text)
    pack = _canonical_pack_from_payload(parsed.data)
    pack.generation_metadata = {
        **metadata,
        "generated_by": "agent_content_pack_v1",
        "model": model,
        "parser_excerpt": parsed.excerpt,
    }
    pack.context_refs = context_refs
    pack.context_sources = [snippet.ref_key for snippet in snippets]
    validate_public_safe_text(f"{pack.title}\n{pack.summary}\n{pack.body}")
    return pack


def generate_platform_task_draft(
    *,
    asset_title: str,
    asset_summary: str | None,
    asset_body: str | None,
    asset_metadata: dict[str, object],
    canonical_url: str | None,
    platform: str,
    channel_key: str,
    display_name: str,
) -> AgentDistributionDraft:
    system_prompt, user_prompt = platform_task_prompt(
        PlatformTaskPromptInput(
            asset_title=asset_title,
            asset_summary=asset_summary,
            asset_body=asset_body,
            asset_metadata=asset_metadata,
            canonical_url=canonical_url,
            platform=platform,
            channel_key=channel_key,
            display_name=display_name,
        )
    )
    raw_text, metadata, model = _call_content_agent(
        system_prompt,
        user_prompt,
        output_schema=PLATFORM_DRAFT_OUTPUT_SCHEMA,
        artifact_prefix=f"platform-{platform}-{channel_key}",
    )
    parsed = parse_agent_json_output(raw_text)
    draft = _platform_draft_from_payload(
        parsed.data, platform=platform, asset_title=asset_title
    )
    draft.metadata = {
        **metadata,
        **draft.metadata,
        "generated_by": "agent_content_pack_v1",
        "platform": platform,
        "channel_key": channel_key,
        "model": model,
        "parser_excerpt": parsed.excerpt,
        "human_gate_required": True,
        "auto_publish": False,
    }
    if (
        platform in {"dev", "devto", "hashnode"}
        and not str(canonical_url or "").strip()
    ):
        draft.metadata["warning"] = "canonical_url_missing"
    validate_public_safe_text(f"{draft.title}\n{draft.body}\n{draft.checklist}")
    _validate_platform_body_density(platform, draft.body)
    return draft


def generate_canonical_article_expansion(
    *,
    asset_title: str,
    asset_summary: str | None,
    source_material: str | None,
    source_plan: str | None,
    canonical_url: str | None,
    skill_context: dict[str, str],
) -> CanonicalArticleExpansion:
    system_prompt, user_prompt = canonical_article_expansion_prompt(
        CanonicalArticleExpansionPromptInput(
            asset_title=asset_title,
            asset_summary=asset_summary,
            source_material=source_material,
            source_plan=source_plan,
            canonical_url=canonical_url,
            skill_context=skill_context,
        )
    )
    raw_text, metadata, model = _call_content_agent(
        system_prompt,
        user_prompt,
        output_schema=CANONICAL_ARTICLE_EXPANSION_OUTPUT_SCHEMA,
        artifact_prefix="canonical-article-expansion",
    )
    parsed = parse_agent_json_output(raw_text)
    article = _canonical_article_expansion_from_payload(parsed.data)
    article.metadata = {
        **metadata,
        "generated_by": "asset_expansion_agent_v1",
        "model": model,
        "parser_excerpt": parsed.excerpt,
        "skill_context": sorted(skill_context),
        "human_gate_required": True,
        "auto_publish": False,
    }
    validate_public_safe_text(
        f"{article.title}\n{article.summary}\n{article.body_markdown}"
    )
    return article


def _required_context_refs_for_asset(
    asset_type: str, signals: list[AssetSignal]
) -> list[str]:
    combined = " ".join(
        [asset_type]
        + [signal.title for signal in signals]
        + [signal.summary for signal in signals]
        + [signal.source_ref for signal in signals]
    ).lower()
    refs = [
        ref
        for ref, required in (
            (
                "synapse-network-sdk:quickstart",
                _needs_sdk_context(asset_type, combined),
            ),
            (
                "synapse-network-mcp-server:spring_boot_mcp",
                _contains_any(combined, ("mcp", "spring boot")),
            ),
            (
                "synapse-network-provider:onboarding",
                _contains_any(combined, ("provider", "onboarding")),
            ),
        )
        if required
    ]
    return list(dict.fromkeys(refs))


def _needs_sdk_context(asset_type: str, combined: str) -> bool:
    return asset_type == "developer_education" or _contains_any(
        combined, ("quickstart", "sdk")
    )


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _resolve_context_refs(refs: list[str]) -> list[ContextTagSnippet]:
    snippets: list[ContextTagSnippet] = []
    for ref in refs:
        try:
            snippets.append(resolve_required_context_tag(ref))
        except InsufficientSourceContextError as exc:
            raise AgentContentGenerationError(str(exc)) from exc
    return snippets


def _canonical_pack_from_payload(payload: dict[str, Any]) -> CanonicalAssetPack:
    return CanonicalAssetPack(
        title=_required_text(payload, "title"),
        summary=_required_text(payload, "summary"),
        body=_required_text(payload, "body"),
        asset_type=_required_text(payload, "asset_type"),
        source_type=str(payload.get("source_type") or "asset_planner"),
        goal_key=_optional_text(payload.get("goal_key")),
        key_facts=_string_list(payload.get("key_facts")),
        code_blocks=[
            CanonicalCodeBlock(
                language=str(item.get("language") or ""),
                title=str(item.get("title") or ""),
                code=str(item.get("code") or ""),
            )
            for item in payload.get("code_blocks", [])
            if isinstance(item, dict)
        ],
        recommended_channels=_string_list(payload.get("recommended_channels")),
        source_signal_refs=_string_list(payload.get("source_signal_refs")),
        generation_reason=str(payload.get("generation_reason") or ""),
    )


def _platform_draft_from_payload(
    payload: dict[str, Any], *, platform: str = "", asset_title: str = ""
) -> AgentDistributionDraft:
    if platform == "x":
        title, body, metadata = normalize_x_payload(payload, fallback_title=asset_title)
    else:
        title = _required_text(payload, "platform_title")
        body = _required_text(payload, "platform_body")
        metadata = {
            "format_kind": str(payload.get("format_kind") or "").strip()
            or platform_format_kind(platform),
            "target_length": str(payload.get("target_length") or "").strip()
            or platform_target_length(platform),
            **text_length_metadata(platform, body),
        }
    return AgentDistributionDraft(
        title=title,
        body=body,
        checklist=_platform_checklist(payload, platform),
        risk_level=str(payload.get("risk_level") or "normal"),
        rationale=str(payload.get("rationale") or ""),
        metadata=metadata,
    )


def _canonical_article_expansion_from_payload(
    payload: dict[str, Any],
) -> CanonicalArticleExpansion:
    return CanonicalArticleExpansion(
        title=_required_text(payload, "title"),
        summary=_required_text(payload, "summary"),
        body_markdown=_required_text(payload, "body_markdown"),
        key_facts=_string_list(payload.get("key_facts")),
        generation_reason=str(payload.get("generation_reason") or ""),
    )


def _validate_platform_body_density(platform: str, body: str) -> None:
    max_chars = 0
    if platform == "x":
        max_chars = 4000
    elif platform in {"reddit", "v2ex"}:
        max_chars = 2000
    if max_chars and len(body) > max_chars:
        raise AgentContentGenerationError(
            "agent_content_generation_failed: "
            f"{platform}_body_exceeds_density_limit max_chars={max_chars}"
        )


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise AgentContentGenerationError(
            f"agent_content_generation_failed: {key}_empty"
        )
    return _public_safe(value)


def _platform_checklist(payload: dict[str, Any], platform: str) -> str:
    value = str(payload.get("operator_checklist") or "").strip()
    if value:
        return _public_safe(value)
    if platform == "x" and (payload.get("x_format") or payload.get("tweets")):
        return "Human Gate required. Verify every tweet is under 280 weighted chars before publishing."
    raise AgentContentGenerationError(
        "agent_content_generation_failed: operator_checklist_empty"
    )


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return _public_safe(text) if text else None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_public_safe(str(item)) for item in value if str(item or "").strip()]
