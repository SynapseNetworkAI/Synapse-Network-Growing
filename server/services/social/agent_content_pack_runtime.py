"""Runtime adapters for social content pack Agent calls."""

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
from server.services.social.agent_content_pack_models import (
    AgentContentGenerationError,
)
from server.services.social.agent_json_output import (
    AgentJsonParseError,
    bounded_excerpt,
    parse_agent_json_output,
)


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
    return not _is_codex_error_payload(parsed.data)


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
