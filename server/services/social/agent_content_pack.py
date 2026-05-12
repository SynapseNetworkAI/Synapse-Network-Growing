"""Structured-output helpers for agent-generated content packs."""

from __future__ import annotations

import re
import uuid
from typing import Any

from server import config
from server.services.agents.llm_adapter import get_provider
from server.services.runtime.codex_cli import (
    CodexExecResult,
    filter_codex_stderr,
    run_codex_exec,
)
from server.services.social.context_tags import (
    ContextTagSnippet,
    InsufficientSourceContextError,
    resolve_required_context_tag,
)
from server.services.social.agent_content_pack_contracts import (
    CANONICAL_ASSET_OUTPUT_SCHEMA,
    PLATFORM_DRAFT_OUTPUT_SCHEMA,
    PlatformTaskPromptInput,
    canonical_asset_prompt,
    platform_task_prompt,
)
from server.services.social.agent_content_pack_models import (
    AgentContentGenerationError,
    AgentDistributionDraft,
    CanonicalAssetPack,
    CanonicalCodeBlock,
)
from server.services.social.agent_content_pack_safety import validate_public_safe_text
from server.services.social.agent_json_output import (
    AgentJsonParseError,
    bounded_excerpt,
    parse_agent_json_output,
)
from server.services.social.distribution_content_strategy import (
    normalize_x_payload,
    platform_format_kind,
    platform_target_length,
    text_length_metadata,
)
from server.services.social.distribution_asset_signals import AssetSignal, _public_safe


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
    return draft


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


def _call_content_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    output_schema: dict[str, Any],
    artifact_prefix: str,
) -> tuple[str, dict[str, object], str]:
    model = config.SOCIAL_CONTENT_LLM_MODEL
    timeout = min(max(int(config.SOCIAL_CONTENT_LLM_TIMEOUT or 180), 30), 900)
    if config.SOCIAL_CONTENT_LLM_PROVIDER == "codex":
        return _call_content_codex(
            system_prompt,
            user_prompt,
            output_schema=output_schema,
            artifact_prefix=artifact_prefix,
            model=model,
            timeout=timeout,
        )
    provider = get_provider(config.SOCIAL_CONTENT_LLM_PROVIDER)
    raw_text, tokens = provider.call(system_prompt, user_prompt, model, 0.7, timeout)
    return (
        raw_text,
        {
            "provider": config.SOCIAL_CONTENT_LLM_PROVIDER,
            "model": model,
            "tokens": int(tokens or 0),
        },
        model,
    )


def _call_content_codex(
    system_prompt: str,
    user_prompt: str,
    *,
    output_schema: dict[str, Any],
    artifact_prefix: str,
    model: str,
    timeout: int,
) -> tuple[str, dict[str, object], str]:
    attempted_models = [model]
    result = _run_content_codex_for_model(
        system_prompt,
        user_prompt,
        output_schema=output_schema,
        artifact_prefix=artifact_prefix,
        model=model,
        timeout=timeout,
    )
    used_model = model
    while result.exit_code != 0 and _is_codex_model_compatibility_result(result):
        next_model = _next_content_codex_model(model, attempted_models)
        if not next_model:
            break
        attempted_models.append(next_model)
        used_model = next_model
        result = _run_content_codex_for_model(
            system_prompt,
            user_prompt,
            output_schema=output_schema,
            artifact_prefix=artifact_prefix,
            model=next_model,
            timeout=timeout,
        )
        if result.exit_code == 0:
            break
    metadata = _content_codex_metadata(result, used_model, attempted_models)
    if not _codex_result_has_json(result):
        raise AgentContentGenerationError(
            _codex_failure_detail(result, model=used_model)
        )
    return result.text, metadata, used_model


def _run_content_codex_for_model(
    system_prompt: str,
    user_prompt: str,
    *,
    output_schema: dict[str, Any],
    artifact_prefix: str,
    model: str,
    timeout: int,
) -> CodexExecResult:
    output_path = _content_codex_output_path(artifact_prefix)
    return run_codex_exec(
        prompt=_content_codex_prompt(system_prompt, user_prompt),
        cwd=config.PROJECT_ROOT,
        output_path=output_path,
        model=model,
        timeout=timeout,
        add_dirs=[config.PROJECT_ROOT],
        output_schema=output_schema,
        sandbox_mode="read-only",
    )


def _next_content_codex_model(primary_model: str, attempted_models: list[str]) -> str:
    return next(
        (
            candidate
            for candidate in _content_codex_fallback_models(primary_model)
            if candidate not in attempted_models
        ),
        "",
    )


def _content_codex_metadata(
    result: CodexExecResult, used_model: str, attempted_models: list[str]
) -> dict[str, object]:
    return {
        "provider": "codex",
        "model": used_model,
        "attempted_models": attempted_models,
        "exit_code": int(result.exit_code),
        "output_artifact": str(result.output_path) if result.output_path else None,
        "thread_id": result.thread_id,
        "json_event_count": int(result.json_event_count or 0),
        "execution_time_ms": int(result.execution_time_ms or 0),
    }


def _content_codex_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        "# System\n"
        f"{system_prompt}\n\n"
        "# Task\n"
        f"{user_prompt}\n\n"
        "# Required output\n"
        "Return only valid JSON. No markdown fences. No explanation."
    )


def _content_codex_output_path(prefix: str):
    out_dir = config.PROJECT_ROOT / "runtime" / "social-content-pack-codex"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]+", "-", prefix).strip("-")[:80]
    return out_dir / f"{safe_prefix}-{uuid.uuid4().hex}.json"


def _codex_result_has_json(result: CodexExecResult) -> bool:
    if not str(result.text or "").strip():
        return False
    try:
        parsed = parse_agent_json_output(result.text)
    except AgentJsonParseError:
        return False
    if _is_codex_error_payload(parsed.data):
        return False
    return True


def _is_codex_error_payload(payload: dict[str, Any]) -> bool:
    if str(payload.get("type") or "").lower() == "error":
        return True
    error = payload.get("error")
    return isinstance(error, dict) and bool(error.get("message"))


def _is_codex_model_compatibility_result(result: CodexExecResult) -> bool:
    message = f"{result.stderr}\n{result.stdout}\n{result.text}".lower()
    return (
        "requires a newer version of codex" in message
        or "not supported when using codex with a chatgpt account" in message
    )


def _content_codex_fallback_models(primary_model: str) -> list[str]:
    raw = str(getattr(config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "") or "").strip()
    candidates = [value.strip() for value in raw.split(",") if value.strip()]
    return [
        candidate
        for candidate in dict.fromkeys(candidates)
        if candidate != primary_model
    ]


def _codex_failure_detail(result: CodexExecResult, *, model: str | None) -> str:
    stderr = filter_codex_stderr(result.stderr, max_lines=8) or result.stderr
    stdout = result.stdout or result.text
    return (
        "agent_content_generation_failed: codex_cli_failed "
        f"model={model or '(default)'} exit_code={result.exit_code} "
        f"artifact={str(result.output_path) if result.output_path else '-'} "
        f"stderr={bounded_excerpt(stderr or '-', max_chars=520)} "
        f"stdout={bounded_excerpt(stdout or '-', max_chars=360)}"
    )


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
    if platform == "x" and (payload.get("x_format") or payload.get("tweets")):
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
