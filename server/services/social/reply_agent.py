"""Agent-backed generation for human-reviewed X reply drafts."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from server import config
from server.database import SocialRepostCandidateRow
from server.services.agents.llm_adapter import get_provider
from server.services.runtime.codex_cli import (
    CodexExecResult,
    filter_codex_stderr,
    run_codex_exec,
)

SOCIAL_REPLY_CONTEXT_MAX_CHARS = 1100
SOCIAL_REPLY_SKILL_MAX_CHARS = 900
SOCIAL_REPLY_BLOCKED_FRAGMENTS = (
    "/users/",
    "api-key",
    "authorization:",
    "bearer token",
    "private key",
    "secret token",
    "workflow json",
    "acceptance matrix",
    "required_commands",
    "execution_acceptance_steps",
    "raw agent output",
)
SOCIAL_REPLY_RISK_LEVELS = {"normal", "elevated", "blocked"}
SOCIAL_REPLY_CODEX_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "suggested_reply": {"type": "string", "minLength": 1},
        "risk_level": {"type": "string", "enum": ["normal", "elevated", "blocked"]},
        "rationale": {"type": "string", "minLength": 1},
    },
    "required": ["suggested_reply", "risk_level", "rationale"],
}


@dataclass(frozen=True)
class GeneratedXReply:
    suggested_reply: str
    risk_level: str
    rationale: str
    model: str | None = None
    generation_metadata: dict[str, Any] | None = None


def _bounded_excerpt(value: str, *, max_chars: int = 1000) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}... [Truncated]"


def _read_context_file(path: Path, *, max_chars: int, required: bool = False) -> str:
    if not path.is_file():
        if required:
            raise ValueError(
                f"agent_reply_generation_config_error: required context file missing: {path.name}"
            )
        return ""
    return _bounded_excerpt(
        path.read_text(encoding="utf-8", errors="replace"), max_chars=max_chars
    )


def _normalize_for_check(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _extract_first_json_object(raw: str) -> str | None:
    text = str(raw or "")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", text):
        start = match.start()
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return text[start : start + end]
    return None


def _strip_json_fence(raw_text: str) -> str:
    raw = str(raw_text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    return raw


def _load_generated_reply_json(raw_text: str) -> dict[str, Any]:
    raw = _strip_json_fence(raw_text)
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        json_object = _extract_first_json_object(raw)
        if not json_object:
            raise ValueError(
                "agent_reply_generation_failed: Agent did not return JSON"
            ) from exc
        try:
            loaded = json.loads(json_object)
        except json.JSONDecodeError as nested_exc:
            raise ValueError(
                "agent_reply_generation_failed: Agent returned invalid JSON"
            ) from nested_exc
    if not isinstance(loaded, dict):
        raise ValueError("agent_reply_generation_failed: Agent JSON must be an object")
    return loaded


def _string_field(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value:
            return str(value).strip()
    return ""


def _parse_generated_reply(raw_text: str) -> GeneratedXReply:
    data = _load_generated_reply_json(raw_text)
    suggested_reply = _string_field(data, "suggested_reply", "reply")
    rationale = _string_field(data, "rationale", "generation_reason")
    risk_level = _string_field(data, "risk_level").lower() or "normal"
    if not suggested_reply or not rationale:
        raise ValueError(
            "agent_reply_generation_failed: Agent response must include suggested_reply and rationale"
        )
    if risk_level not in SOCIAL_REPLY_RISK_LEVELS:
        risk_level = "normal"
    return GeneratedXReply(
        suggested_reply=suggested_reply,
        risk_level=risk_level,
        rationale=_bounded_excerpt(rationale, max_chars=900),
    )


def _build_reply_generation_prompt(
    candidate: SocialRepostCandidateRow,
) -> tuple[str, str, tuple[str, ...]]:
    root = config.PROJECT_ROOT
    product_context = _read_context_file(
        root / ".agents" / "product-marketing-context.md",
        max_chars=SOCIAL_REPLY_CONTEXT_MAX_CHARS,
        required=True,
    )
    social_skill = _read_context_file(
        root / ".agents" / "skills" / "social-content" / "SKILL.md",
        max_chars=SOCIAL_REPLY_SKILL_MAX_CHARS,
        required=True,
    )
    system_prompt = (
        "You are the Synapse Network X reply agent. "
        "Write one public reply for the official @SynapseNetworkA account. "
        "The reply must be specific to the source post, positive, natural, and add a useful Synapse angle. "
        "Do not write generic agreement such as 'Great point'. "
        "Do not auto-publish, ask to follow, mention private paths, expose secrets, cite workflow internals, or make financial return promises. "
        "Do not fabricate that Synapse has already partnered with or been mentioned by the source author. "
        "Return JSON only: {'suggested_reply':'...', 'risk_level':'normal|elevated|blocked', 'rationale':'...'}."
    )
    source_text = _bounded_excerpt(str(candidate.source_text or ""), max_chars=1600)
    suggested_quote = _bounded_excerpt(
        str(candidate.suggested_quote or ""), max_chars=900
    )
    user_prompt = (
        f"# Product context\n{product_context}\n\n"
        f"# Social reply guidance\n{social_skill}\n\n"
        "# Source X post\n"
        f"Author: @{candidate.author_handle or 'unknown'}\n"
        f"URL: {candidate.source_url or '-'}\n"
        f"Text:\n{source_text}\n\n"
        "# Existing Synapse angle from candidate generation\n"
        f"{suggested_quote or '-'}\n\n"
        "# Task\n"
        "Generate a concise reply draft that responds to the actual source post. "
        "Add one concrete value-add perspective about agent infrastructure, governed API access, budgets, payment rails, provider monetization, or settlement only when relevant. "
        "Avoid repeating the same generic Synapse thesis across unrelated posts. "
        "If the source post is not suitable for a brand reply, set risk_level to elevated or blocked and explain why in rationale. "
        "Return strict JSON only."
    )
    return system_prompt, user_prompt, ("product-marketing-context", "social-content")


def _reply_codex_prompt(system_prompt: str, user_prompt: str) -> str:
    return (
        "# Role\n"
        "You are a social reply copy agent for Synapse Network.\n\n"
        "# System constraints\n"
        f"{system_prompt}\n\n"
        "# Task context\n"
        f"{user_prompt}\n\n"
        "# Required output\n"
        "Return only valid JSON matching this exact schema:\n"
        '{"suggested_reply":"public X reply text","risk_level":"normal","rationale":"why this reply fits the source post"}\n'
        "No markdown fences. No explanation. No extra keys."
    )


def _reply_codex_output_path() -> Path:
    out_dir = config.PROJECT_ROOT / "runtime" / "social-publishing-codex"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{uuid.uuid4().hex}-reply.json"


def _codex_failure_detail(result: CodexExecResult, *, model: str | None) -> str:
    stderr = filter_codex_stderr(result.stderr, max_lines=8) or result.stderr
    stdout = result.stdout or result.text
    return (
        "agent_reply_generation_failed: codex_cli_failed "
        f"provider=codex model={model or '(default)'} exit_code={result.exit_code} "
        f"output_artifact={str(result.output_path) if result.output_path else '-'} "
        f"stderr={_bounded_excerpt(stderr or '-', max_chars=520)} "
        f"stdout={_bounded_excerpt(stdout or '-', max_chars=360)}"
    )


def _codex_nonzero_can_use_reply_json(result: CodexExecResult) -> bool:
    if result.exit_code == 0:
        return True
    if not str(result.text or "").strip():
        return False
    try:
        _parse_generated_reply(result.text)
    except ValueError:
        return False
    return True


def _is_codex_model_compatibility_result(result: CodexExecResult) -> bool:
    message = f"{result.stdout}\n{result.stderr}\n{result.text}".lower()
    return (
        "requires a newer version of codex" in message
        or "not supported when using codex with a chatgpt account" in message
    )


def _social_codex_fallback_models(primary_model: str) -> list[str]:
    raw = str(getattr(config, "SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "") or "").strip()
    models: list[str] = []
    for item in re.split(r"[,\\s]+", raw):
        model = item.strip()
        if model and model != primary_model and model not in models:
            models.append(model)
    return models


def _run_reply_codex_once(
    system_prompt: str, user_prompt: str, *, model: str, timeout: int
) -> CodexExecResult:
    output_path = _reply_codex_output_path()
    return run_codex_exec(
        prompt=_reply_codex_prompt(system_prompt, user_prompt),
        cwd=config.PROJECT_ROOT,
        output_path=output_path,
        model=model,
        timeout=timeout,
        add_dirs=[config.PROJECT_ROOT],
        output_schema=SOCIAL_REPLY_CODEX_OUTPUT_SCHEMA,
        sandbox_mode="read-only",
    )


def _call_reply_codex(
    system_prompt: str, user_prompt: str, *, model: str, timeout: int
) -> tuple[str, dict[str, Any], str]:
    result = _run_reply_codex_once(
        system_prompt, user_prompt, model=model, timeout=timeout
    )
    used_model = model
    used_fallback = False
    attempted_models = [model]
    while result.exit_code != 0 and _is_codex_model_compatibility_result(result):
        next_model = next(
            (
                candidate
                for candidate in _social_codex_fallback_models(model)
                if candidate not in attempted_models
            ),
            "",
        )
        if not next_model:
            break
        result = _run_reply_codex_once(
            system_prompt, user_prompt, model=next_model, timeout=timeout
        )
        used_model = next_model
        used_fallback = True
        attempted_models.append(next_model)
    metadata = {
        "provider": "codex",
        "model": used_model,
        "requested_model": model,
        "fallback_used": used_fallback,
        "attempted_models": attempted_models,
        "exit_code": int(result.exit_code),
        "output_artifact": str(result.output_path) if result.output_path else None,
        "thread_id": result.thread_id,
        "json_event_count": int(result.json_event_count or 0),
        "execution_time_ms": int(result.execution_time_ms or 0),
    }
    if not _codex_nonzero_can_use_reply_json(result):
        raise ValueError(_codex_failure_detail(result, model=used_model))
    return result.text, metadata, used_model


def _validate_generated_reply(
    candidate: SocialRepostCandidateRow, generated: GeneratedXReply
) -> None:
    combined = f"{generated.suggested_reply}\n{generated.rationale}"
    normalized = _normalize_for_check(combined)
    if any(fragment in normalized for fragment in SOCIAL_REPLY_BLOCKED_FRAGMENTS):
        raise ValueError(
            "agent_reply_generation_failed: Agent leaked internal prompt, path, or workflow language"
        )
    if re.search(
        r"\b(api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{12,}",
        combined,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "agent_reply_generation_failed: Agent leaked credential-shaped text"
        )
    if re.search(
        r"/(?:Users|home|workspace|tmp)/[A-Za-z0-9._/\-]*",
        combined,
        flags=re.IGNORECASE,
    ):
        raise ValueError("agent_reply_generation_failed: Agent leaked a local path")
    if re.search(
        r"\b(great point|love this|agree\b|exactly this)\b[.! ]*$",
        generated.suggested_reply.strip(),
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "agent_reply_generation_failed: Agent returned a generic low-value reply"
        )
    if re.search(
        r"\b(guaranteed profit|risk[- ]?free return|100x|private key|seed phrase|send funds)\b",
        combined,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "agent_reply_generation_failed: Agent produced unsafe financial or credential language"
        )
    source_text = _normalize_for_check(candidate.source_text or "")
    reply_text = _normalize_for_check(generated.suggested_reply)
    if len(source_text) > 80 and source_text[:120] in reply_text:
        raise ValueError(
            "agent_reply_generation_failed: Agent copied too much source text"
        )


def generate_x_reply_for_candidate(
    candidate: SocialRepostCandidateRow,
    *,
    timeout_seconds: int | None = None,
) -> GeneratedXReply:
    system_prompt, user_prompt, context_sources = _build_reply_generation_prompt(
        candidate
    )
    model = config.SOCIAL_CONTENT_LLM_MODEL
    requested_timeout = timeout_seconds if timeout_seconds is not None else config.SOCIAL_CONTENT_LLM_TIMEOUT
    timeout = min(max(int(requested_timeout or 180), 30), 900)
    if config.SOCIAL_CONTENT_LLM_PROVIDER == "codex":
        raw_text, metadata, model = _call_reply_codex(
            system_prompt, user_prompt, model=model, timeout=timeout
        )
    else:
        provider = get_provider(config.SOCIAL_CONTENT_LLM_PROVIDER)
        raw_text, _tokens = provider.call(
            system_prompt, user_prompt, model, 0.7, timeout
        )
        metadata = {"provider": config.SOCIAL_CONTENT_LLM_PROVIDER, "model": model}
    generated = _parse_generated_reply(raw_text)
    generated = GeneratedXReply(
        suggested_reply=generated.suggested_reply,
        risk_level=generated.risk_level,
        rationale=generated.rationale,
        model=model,
        generation_metadata={**metadata, "context_sources": list(context_sources)},
    )
    _validate_generated_reply(candidate, generated)
    return generated
