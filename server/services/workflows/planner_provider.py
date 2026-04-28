"""Planner adapter layer for plan agent model calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from server import config
from server.services.agents.llm_adapter import get_provider
from server.services.runtime.codex_cli import CodexExecResult, run_codex_exec
from server.services.runtime.codex_sdk import run_codex_sdk_plan

SUPPORTED_PLANNER_BACKENDS = {"openai", "claude", "copilot", "codex_cli", "codex_sdk"}
_GENERIC_MODEL_ALIASES = {"", "openai", "claude", "copilot", "codex", "responses", "gpt"}


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


@dataclass
class PlannerRequest:
    prompt: str
    system_prompt: str = ""
    raw_prompt: bool = False
    cwd: str | Path | None = None
    output_path: str | Path | None = None
    add_dirs: list[str | Path] = field(default_factory=list)
    resume_session_id: str | None = None
    metadata: dict[str, Any] | None = None
    backend: str | None = None
    model: str | None = None
    timeout: int | None = None


@dataclass
class PlannerResponse:
    text: str
    tokens: int = 0
    backend: str = ""
    model: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class PlannerAdapter(Protocol):
    backend: str

    def generate(self, request: PlannerRequest) -> PlannerResponse:
        """Generate planner text for the supplied request."""


def resolve_planner_backend(backend: str | None = None) -> str:
    """Resolve planner backend without coupling planner selection to execution runtime."""

    explicit = str(backend or config.PLANNER_BACKEND or "").strip().lower()
    if explicit:
        if explicit not in SUPPORTED_PLANNER_BACKENDS:
            raise ValueError(
                f"Unsupported PLANNER_BACKEND '{explicit}'. "
                f"Choose from: {', '.join(sorted(SUPPORTED_PLANNER_BACKENDS))}"
            )
        return explicit

    orchestration_backend = str(config.ORCHESTRATION_BACKEND or "").strip().lower()
    if orchestration_backend in {"codex_cli", "codex_sdk"}:
        return orchestration_backend
    if orchestration_backend == "copilot_sdk":
        return "copilot"
    if orchestration_backend == "openai_responses":
        return "openai"

    provider_name = str(config.LLM_PROVIDER or "").strip().lower()
    if provider_name == "codex":
        return "codex_cli"
    if provider_name in {"openai", "claude", "copilot"}:
        return provider_name
    return "openai"


def resolve_planner_model(backend: str, model: str | None = None) -> str:
    """Resolve the effective model for a planner backend."""

    requested = str(model or config.PLANNER_MODEL or "").strip()
    if requested:
        return requested

    normalized = str(backend or "").strip().lower()
    llm_model = str(config.LLM_MODEL or "").strip()
    if normalized == "codex_sdk":
        if llm_model.lower() in _GENERIC_MODEL_ALIASES:
            return str(config.CODEX_SDK_MODEL or "gpt-5.4").strip()
        return str(config.CODEX_SDK_MODEL or llm_model or "gpt-5.4").strip()
    if normalized == "codex_cli":
        if llm_model.lower() in _GENERIC_MODEL_ALIASES:
            return str(config.CODEX_CLI_MODEL or "gpt-5-codex").strip()
        return str(config.CODEX_CLI_MODEL or llm_model or "gpt-5-codex").strip()
    if normalized == "copilot":
        return str(config.COPILOT_SDK_MODEL or llm_model or "gpt-4o").strip()
    if normalized == "claude":
        return llm_model if llm_model else "claude-3-7-sonnet-latest"
    return llm_model if llm_model else "gpt-4o"


def _planner_timeout(request: PlannerRequest, *, backend: str) -> int:
    if request.timeout is not None:
        return int(request.timeout)
    configured = int(getattr(config, "PLANNER_TIMEOUT", 0) or 0)
    if configured > 0:
        return configured
    if backend == "codex_sdk":
        return int(config.CODEX_SDK_PLAN_TIMEOUT)
    return int(config.LLM_TIMEOUT or 300)


def _target_cwd(raw: str | Path | None) -> Path:
    return Path(raw or config.PROJECT_ROOT).expanduser().resolve()


def _target_output_path(raw: str | Path | None) -> Path:
    return Path(raw or (Path(config.PROJECT_ROOT) / "runtime" / "plans" / "last-plan.md")).expanduser()


def _prompt_for_runtime(request: PlannerRequest) -> str:
    if request.raw_prompt or not str(request.system_prompt or "").strip():
        return request.prompt
    return "\n\n".join(
        [
            "# System Instructions",
            str(request.system_prompt).strip(),
            "# User Request",
            str(request.prompt).strip(),
        ]
    )


def _update_metadata(metadata: dict[str, Any] | None, values: dict[str, Any]) -> None:
    if metadata is not None:
        metadata.update(values)


def _is_codex_cli_model_compatibility_result(result: CodexExecResult) -> bool:
    message = "\n".join([str(result.stderr or ""), str(result.stdout or ""), str(result.text or "")]).lower()
    return (
        "requires a newer version of codex" in message
        or "not supported when using codex with a chatgpt account" in message
        or "model_not_supported" in message
    )


def _planner_codex_fallback_models(primary_model: str) -> list[str]:
    candidates = [primary_model]
    raw = str(config.PLANNER_FALLBACK_MODEL or "").strip()
    if raw:
        candidates.extend(item.strip() for item in raw.split(",") if item.strip())
    candidates.extend(["gpt-5.4", "gpt-5.3-codex"])
    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidates:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


class LLMPlannerAdapter:
    def __init__(self, provider_name: str):
        self.backend = provider_name
        self.provider_name = provider_name

    def generate(self, request: PlannerRequest) -> PlannerResponse:
        model = resolve_planner_model(self.backend, request.model)
        timeout = _planner_timeout(request, backend=self.backend)
        provider = get_provider(self.provider_name)
        if self.provider_name == "openai" and hasattr(provider, "create_response"):
            response = provider.create_response(
                instructions=request.system_prompt,
                user_input=request.prompt,
                model=model,
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
        else:
            content, tokens = provider.call(
                request.system_prompt,
                request.prompt,
                model,
                0.1,
                timeout,
            )
        text = str(content or "").strip()
        if not text:
            raise RuntimeError(f"{self.provider_name} planner returned empty output")
        _update_metadata(
            request.metadata,
            {
                "planning_backend": self.backend,
                "planning_model": model,
            },
        )
        return PlannerResponse(text=text, tokens=int(tokens or 0), backend=self.backend, model=model)


class CodexCliPlannerAdapter:
    backend = "codex_cli"

    def generate(self, request: PlannerRequest) -> PlannerResponse:
        started_at = datetime.now(timezone.utc)
        model = resolve_planner_model(self.backend, request.model)
        timeout = _planner_timeout(request, backend=self.backend)
        cwd = _target_cwd(request.cwd)
        output_path = _target_output_path(request.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = _prompt_for_runtime(request)
        prompt_path = output_path.with_suffix(".prompt.md")
        prompt_path.write_text(prompt, encoding="utf-8")
        add_dirs = [Path(path).expanduser().resolve() for path in request.add_dirs]
        resume_thread_id = str(request.resume_session_id or "").strip() or None
        attempted_models: list[str] = []
        result: CodexExecResult | None = None
        used_model = model
        for candidate_model in _planner_codex_fallback_models(model):
            attempted_models.append(candidate_model)
            result = run_codex_exec(
                prompt=prompt,
                cwd=cwd,
                output_path=output_path,
                model=candidate_model,
                timeout=timeout,
                add_dirs=add_dirs,
                sandbox_mode="read-only",
                resume_thread_id=resume_thread_id,
            )
            used_model = candidate_model
            if result.exit_code == 0 or not _is_codex_cli_model_compatibility_result(result):
                break
            try:
                if output_path.exists():
                    output_path.unlink()
            except OSError:
                pass
        if result is None:
            raise RuntimeError("codex cli planner did not run")
        completed_at = datetime.now(timezone.utc)
        text = str(result.text or "").strip()
        if result.exit_code != 0:
            excerpt = (result.stderr or result.stdout or text or "codex planner failed").strip()
            raise RuntimeError(excerpt[:2000])
        if not text:
            raise RuntimeError("codex cli planner returned empty output")
        _update_metadata(
            request.metadata,
            {
                "planning_session_id": result.thread_id,
                "planning_prompt_path": str(prompt_path),
                "planning_output_path": str(output_path),
                "planning_command": list(result.command),
                "planning_backend": self.backend,
                "planning_model": used_model,
                "planning_requested_model": model,
                "planning_attempted_models": attempted_models,
                "planning_resumed_from_session_id": str(request.resume_session_id or "").strip() or None,
                "planning_started_at": started_at.isoformat(),
                "planning_completed_at": completed_at.isoformat(),
                "planning_json_event_count": result.json_event_count,
            },
        )
        return PlannerResponse(text=text, tokens=0, backend=self.backend, model=used_model)


class CodexSdkPlannerAdapter:
    backend = "codex_sdk"

    def generate(self, request: PlannerRequest) -> PlannerResponse:
        started_at = datetime.now(timezone.utc)
        model = resolve_planner_model(self.backend, request.model)
        timeout = _planner_timeout(request, backend=self.backend)
        cwd = _target_cwd(request.cwd)
        output_path = _target_output_path(request.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        prompt = _prompt_for_runtime(request)
        prompt_path = output_path.with_suffix(".prompt.md")
        prompt_path.write_text(prompt, encoding="utf-8")
        result = run_codex_sdk_plan(
            prompt=prompt,
            cwd=cwd,
            output_path=output_path,
            model=model,
            timeout=timeout,
            sandbox_mode="read-only",
            resume_thread_id=str(request.resume_session_id or "").strip() or None,
        )
        completed_at = datetime.now(timezone.utc)
        text = str(result.text or "").strip()
        if not text:
            raise RuntimeError("codex sdk planner returned empty output")
        _update_metadata(
            request.metadata,
            {
                "planning_session_id": result.thread_id,
                "planning_turn_id": result.turn_id,
                "planning_prompt_path": str(prompt_path),
                "planning_output_path": str(output_path),
                "planning_backend": self.backend,
                "planning_model": model,
                "planning_resumed_from_session_id": str(request.resume_session_id or "").strip() or None,
                "planning_started_at": started_at.isoformat(),
                "planning_completed_at": completed_at.isoformat(),
                "planning_usage": result.usage or {},
                "planning_status": result.status,
            },
        )
        return PlannerResponse(text=text, tokens=0, backend=self.backend, model=model)


def resolve_planner_adapter(backend: str | None = None) -> PlannerAdapter:
    """Return the configured planner adapter."""

    resolved = resolve_planner_backend(backend)
    if resolved == "codex_cli":
        return CodexCliPlannerAdapter()
    if resolved == "codex_sdk":
        return CodexSdkPlannerAdapter()
    return LLMPlannerAdapter(resolved)


def generate_planner_text(request: PlannerRequest) -> PlannerResponse:
    """Generate planner output through the configured adapter."""

    adapter = resolve_planner_adapter(request.backend)
    return adapter.generate(request)


__all__ = [
    "SUPPORTED_PLANNER_BACKENDS",
    "PlannerAdapter",
    "PlannerRequest",
    "PlannerResponse",
    "LLMPlannerAdapter",
    "CodexCliPlannerAdapter",
    "CodexSdkPlannerAdapter",
    "resolve_planner_backend",
    "resolve_planner_model",
    "resolve_planner_adapter",
    "generate_planner_text",
]
