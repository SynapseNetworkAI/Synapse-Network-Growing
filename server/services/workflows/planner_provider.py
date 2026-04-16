"""Provider-facing planner helpers for workflow planning."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server import config
from server.services.runtime.codex_cli import run_codex_exec
from server.services.runtime.codex_sdk import run_codex_sdk_plan


def _split_target_paths(raw_path: str | None) -> list[str]:
    """Normalize a newline-delimited target path field into unique paths."""

    if not raw_path:
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for raw in str(raw_path).splitlines():
        path = raw.strip()
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def planner_provider_name() -> str:
    """Resolve the provider used for planner generation."""

    backend = str(config.ORCHESTRATION_BACKEND or "").strip().lower()
    if backend == "openai_responses":
        return "openai"
    if backend == "copilot_sdk":
        return "copilot"
    if backend in {"codex_cli", "codex_sdk"}:
        return "codex"
    explicit = str(config.LLM_PROVIDER or "").strip().lower()
    if explicit:
        return explicit
    return "openai"


def planner_model_name(provider_name: str) -> str:
    """Resolve the effective planner model for a provider."""

    model = str(config.LLM_MODEL or "").strip()
    if model:
        if provider_name == "codex" and model.lower() in {"openai", "claude", "copilot", "codex", "responses", "gpt"}:
            if str(config.ORCHESTRATION_BACKEND or "").strip().lower() == "codex_sdk":
                return str(config.CODEX_SDK_MODEL or "").strip()
            return str(config.CODEX_CLI_MODEL or "").strip()
        return model
    if provider_name == "copilot":
        return str(config.COPILOT_SDK_MODEL or "gpt-4o").strip() or "gpt-4o"
    if provider_name == "codex":
        if str(config.ORCHESTRATION_BACKEND or "").strip().lower() == "codex_sdk":
            return str(config.CODEX_SDK_MODEL or config.LLM_MODEL or "").strip()
        return str(config.CODEX_CLI_MODEL or "").strip()
    if provider_name == "claude":
        return "claude-3-7-sonnet-latest"
    return "gpt-4o"


def call_planner_provider(
    *,
    provider_name: str,
    provider: Any,
    prompt: str,
    model_name: str,
    system_prompt: str,
    raw_prompt: bool = False,
    raw_cwd: str | Path | None = None,
    raw_output_path: str | Path | None = None,
    raw_add_dirs: list[str | Path] | None = None,
    raw_resume_session_id: str | None = None,
    metadata_out: dict[str, Any] | None = None,
) -> tuple[str, int]:
    """Call the configured provider and return text plus token usage."""

    backend = str(config.ORCHESTRATION_BACKEND or "").strip().lower()
    timeout = config.CODEX_SDK_PLAN_TIMEOUT if provider_name == "codex" and backend == "codex_sdk" else min(config.LLM_TIMEOUT, 90)
    if provider_name == "codex" and backend == "codex_sdk":
        started_at = datetime.now(timezone.utc)
        cwd = Path(raw_cwd or config.PROJECT_ROOT).expanduser().resolve()
        output_path = Path(raw_output_path or (Path(config.PROJECT_ROOT) / "runtime" / "plans" / "last-plan.md")).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path = output_path.with_suffix(".prompt.md")
        sdk_prompt = prompt if raw_prompt or not system_prompt else "\n\n".join(
            [
                "# System Instructions",
                system_prompt.strip(),
                "# User Request",
                prompt,
            ]
        )
        prompt_path.write_text(sdk_prompt, encoding="utf-8")
        result = run_codex_sdk_plan(
            prompt=sdk_prompt,
            cwd=cwd,
            output_path=output_path,
            model=model_name,
            timeout=timeout,
            sandbox_mode="read-only",
            resume_thread_id=str(raw_resume_session_id or "").strip() or None,
        )
        completed_at = datetime.now(timezone.utc)
        if metadata_out is not None:
            metadata_out.update(
                {
                    "planning_session_id": result.thread_id,
                    "planning_turn_id": result.turn_id,
                    "planning_prompt_path": str(prompt_path),
                    "planning_output_path": str(output_path),
                    "planning_backend": "codex_sdk",
                    "planning_model": model_name,
                    "planning_resumed_from_session_id": str(raw_resume_session_id or "").strip() or None,
                    "planning_started_at": started_at.isoformat(),
                    "planning_completed_at": completed_at.isoformat(),
                    "planning_usage": result.usage or {},
                    "planning_status": result.status,
                }
            )
        content = str(result.text or "").strip()
        if not content:
            raise RuntimeError("codex sdk planning returned empty output")
        return content, 0
    if raw_prompt and provider_name == "codex":
        started_at = datetime.now(timezone.utc)
        cwd = Path(raw_cwd or config.PROJECT_ROOT).expanduser().resolve()
        output_path = Path(raw_output_path or (Path(config.PROJECT_ROOT) / "runtime" / "plans" / "last-plan.md")).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path = output_path.with_suffix(".prompt.md")
        prompt_path.write_text(prompt, encoding="utf-8")
        result = run_codex_exec(
            prompt=prompt,
            cwd=cwd,
            output_path=output_path,
            model=model_name,
            timeout=timeout,
            add_dirs=[Path(path).expanduser().resolve() for path in raw_add_dirs or []],
            sandbox_mode="read-only",
            resume_thread_id=str(raw_resume_session_id or "").strip() or None,
        )
        completed_at = datetime.now(timezone.utc)
        if metadata_out is not None:
            metadata_out.update(
                {
                    "planning_session_id": result.thread_id,
                    "planning_prompt_path": str(prompt_path),
                    "planning_output_path": str(output_path),
                    "planning_command": list(result.command),
                    "planning_backend": "codex_cli",
                    "planning_model": model_name,
                    "planning_resumed_from_session_id": str(raw_resume_session_id or "").strip() or None,
                    "planning_started_at": started_at.isoformat(),
                    "planning_completed_at": completed_at.isoformat(),
                    "planning_json_event_count": result.json_event_count,
                }
            )
        content = str(result.text or "").strip()
        if result.exit_code != 0:
            excerpt = (result.stderr or result.stdout or content or "codex raw planning failed").strip()
            raise RuntimeError(excerpt[:2000])
        if not content:
            raise RuntimeError("codex raw planning returned empty output")
        return content, 0
    if provider_name == "openai" and hasattr(provider, "create_response"):
        response = provider.create_response(
            instructions=system_prompt,
            user_input=prompt,
            model=model_name,
            temperature=0.1,
            timeout=timeout,
            background=False,
            previous_response_id=None,
        )
        content = provider.extract_response_text(response)
        tokens = provider.extract_response_tokens(response)
        error = provider.extract_response_error(response)
        if error:
            raise RuntimeError(error)
        return content, tokens
    return provider.call(
        system_prompt,
        prompt,
        model_name,
        0.1,
        timeout,
    )


__all__ = [
    "planner_provider_name",
    "planner_model_name",
    "call_planner_provider",
]
