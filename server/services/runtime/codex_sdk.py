"""Codex Python SDK helpers.

The SDK import stays optional so the repository can keep using the existing
``codex_cli`` backend when the experimental Python SDK/runtime package is not
installed.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from typing import Any, Callable

from server import config

logger = logging.getLogger("ops-dashboard.codex_sdk")

_GENERIC_MODEL_ALIASES = {"", "openai", "claude", "copilot", "codex", "responses", "gpt"}


@dataclass
class CodexSDKPlanResult:
    text: str
    thread_id: str | None
    turn_id: str | None
    usage: dict[str, Any] | None
    status: str
    execution_time_ms: int
    output_path: Path | None
    metadata: dict[str, Any]


def resolve_codex_sdk_model(model: str | None = None) -> str:
    """Resolve the effective model for Codex SDK calls."""

    raw = str(model if model is not None else (config.CODEX_SDK_MODEL or config.LLM_MODEL or "")).strip()
    if raw.lower() in _GENERIC_MODEL_ALIASES:
        return str(config.CODEX_SDK_MODEL or config.LLM_MODEL or "").strip()
    return raw


def _load_codex_class() -> Any:
    try:
        from codex_app_server import Codex  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Codex Python SDK is not available. Install the experimental "
            "`codex-app-server-sdk`/`codex-cli-bin` runtime package, ensure local "
            "Codex auth/session is configured, or fall back to "
            "`ORCHESTRATION_BACKEND=codex_cli`."
        ) from exc
    return Codex


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        try:
            return _jsonable(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _jsonable(value.dict())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        return {
            str(key): _jsonable(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def _first_text_from_item(item: Any) -> str:
    for attr in ("text", "content", "message", "final_response"):
        value = getattr(item, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            for part in value:
                nested = _first_text_from_item(part)
                if nested:
                    return nested
    if isinstance(item, dict):
        for key in ("text", "content", "message", "final_response"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list):
                for part in value:
                    nested = _first_text_from_item(part)
                    if nested:
                        return nested
    return ""


def _extract_final_response(result: Any) -> str:
    final_response = getattr(result, "final_response", None)
    if isinstance(final_response, str) and final_response.strip():
        return final_response.strip()
    if isinstance(result, dict):
        final_response = result.get("final_response") or result.get("finalResponse")
        if isinstance(final_response, str) and final_response.strip():
            return final_response.strip()
    items = getattr(result, "items", None)
    if items is None and isinstance(result, dict):
        items = result.get("items")
    if isinstance(items, list):
        for item in reversed(items):
            text = _first_text_from_item(item)
            if text:
                return text
    return ""


def _extract_usage(result: Any) -> dict[str, Any] | None:
    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, dict):
        usage = result.get("usage")
    payload = _jsonable(usage)
    return payload if isinstance(payload, dict) else None


def _extract_turn_id(result: Any) -> str | None:
    for attr in ("turn_id", "turnId", "id"):
        value = getattr(result, attr, None)
        if value:
            return str(value)
    if isinstance(result, dict):
        for key in ("turn_id", "turnId", "id"):
            value = result.get(key)
            if value:
                return str(value)
    return None


def _thread_id(thread: Any) -> str | None:
    value = getattr(thread, "id", None)
    if value:
        return str(value)
    if isinstance(thread, dict) and thread.get("id"):
        return str(thread["id"])
    return None


def run_codex_sdk_plan(
    *,
    prompt: str,
    cwd: Path,
    output_path: Path | None = None,
    model: str | None = None,
    timeout: int | None = None,
    sandbox_mode: str | None = None,
    resume_thread_id: str | None = None,
    codex_factory: Callable[[], Any] | None = None,
) -> CodexSDKPlanResult:
    """Run a planner turn through the experimental Codex Python SDK."""

    t0 = time.monotonic()
    resolved_model = resolve_codex_sdk_model(model)
    selected_timeout = int(timeout if timeout is not None else config.CODEX_SDK_PLAN_TIMEOUT)
    sandbox = str(sandbox_mode or "read-only").strip() or "read-only"
    output_path = output_path.expanduser() if output_path is not None else None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    factory = codex_factory or _load_codex_class()
    metadata: dict[str, Any] = {
        "provider": "codex",
        "backend": "codex_sdk",
        "model": resolved_model,
        "cwd": str(cwd),
        "sandbox_mode": sandbox,
        "timeout_seconds": selected_timeout,
        "resume_thread_id": str(resume_thread_id or ""),
    }
    try:
        with factory() as codex:
            thread_kwargs: dict[str, Any] = {"cwd": str(cwd), "sandbox": sandbox}
            if resolved_model:
                thread_kwargs["model"] = resolved_model
            if resume_thread_id:
                thread = codex.thread_resume(str(resume_thread_id), **thread_kwargs)
            else:
                thread = codex.thread_start(**thread_kwargs)
            thread_id = _thread_id(thread) or str(resume_thread_id or "") or None
            result = thread.run(prompt)
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise RuntimeError(
            "Codex Python SDK planner failed. Check codex-cli-bin, local Codex "
            "auth/session, and codex app-server compatibility. You can fall back "
            f"to ORCHESTRATION_BACKEND=codex_cli. Detail: {detail}"
        ) from exc

    elapsed = int((time.monotonic() - t0) * 1000)
    text = _extract_final_response(result)
    usage = _extract_usage(result)
    turn_id = _extract_turn_id(result)
    status = str(getattr(result, "status", "") or "")
    if isinstance(result, dict):
        status = str(result.get("status") or status)
    metadata.update(
        {
            "thread_id": thread_id,
            "turn_id": turn_id or "",
            "usage": usage or {},
            "status": status,
            "execution_time_ms": elapsed,
            "result": _jsonable(result),
        }
    )
    if output_path is not None:
        output_path.write_text(text, encoding="utf-8")
        (output_path.parent / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    logger.info(
        "event=codex_sdk_plan_completed cwd=%s model=%s elapsed_ms=%s thread_id=%s",
        str(cwd),
        resolved_model or "(default)",
        elapsed,
        thread_id or "",
    )
    return CodexSDKPlanResult(
        text=text,
        thread_id=thread_id,
        turn_id=turn_id,
        usage=usage,
        status=status,
        execution_time_ms=elapsed,
        output_path=output_path,
        metadata=metadata,
    )


__all__ = ["CodexSDKPlanResult", "resolve_codex_sdk_model", "run_codex_sdk_plan"]
