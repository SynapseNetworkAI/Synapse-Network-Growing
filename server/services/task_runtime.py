"""Task execution runtimes for legacy, Codex CLI, Copilot SDK, and OpenAI backends."""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from server import config
from server.services.codex_cli import run_codex_exec, start_codex_exec_async
from server.services.copilot_sdk_state import copilot_runtime_paths
from server.services.context_loader import load_context
from server.services.crew_engine import CrewEngine
from server.services.copilot_sdk_bridge import CopilotSDKBridge
from server.services.llm_adapter import OpenAIProvider
from server.services.skill_loader import load_skill

logger = logging.getLogger("ops-dashboard.task_runtime")
_E2E_REQUIREMENT_TEST_ATTEMPTS: dict[int, int] = {}
_CODEX_SECTION_TITLES = {
    "step",
    "project context",
    "capability contract",
    "done when",
    "execution guidance",
    "suggested file scope",
    "implementation plan",
    "validation contract",
    "delivery contract",
    "stale memory verification",
}
_CODEX_NON_MUTATING_STEP_TYPES = {"research", "synthesis", "review", "test"}


def _runtime_timeout_or_default(value: int | None, default: int) -> int:
    if value is None:
        return int(default)
    try:
        return int(value)
    except Exception:
        return int(default)


def _codex_max_active_seconds(timeout_seconds: int) -> int:
    configured = int(config.CODEX_CLI_MAX_ACTIVE_SECONDS or 0)
    if configured <= 0:
        return 0
    if timeout_seconds <= 0:
        return configured
    return max(configured, timeout_seconds)


def _codex_selected_timeout_seconds(timeout_seconds: int) -> int:
    if timeout_seconds > 0:
        return timeout_seconds
    configured = int(config.CODEX_CLI_TASK_TIMEOUT or 0)
    if configured > 0:
        return configured
    return 0


def _codex_sandbox_mode_for_step(step_type: str | None) -> str | None:
    normalized = str(step_type or "").strip().lower()
    if normalized in _CODEX_NON_MUTATING_STEP_TYPES:
        return "read-only"
    return None


@dataclass
class RuntimeEvent:
    event_type: str
    detail: str | None = None


@dataclass
class TaskExecutionResult:
    text: str
    files: list[Path] = field(default_factory=list)
    error: str | None = None
    execution_time_ms: int = 0
    model: str = ""
    tokens_used: int = 0
    runtime_backend: str = "legacy"
    runtime_provider: str = ""
    runtime_session_id: str | None = None
    runtime_selected_agent: str | None = None
    events: list[RuntimeEvent] = field(default_factory=list)
    deferred: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeSelection:
    backend: str
    provider: str
    model: str
    complexity_tier: str = "standard"
    budget_cap: dict[str, Any] = field(default_factory=dict)
    allow_escalation: bool = True
    escalation_rule: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 0
    reason: str = ""


@dataclass
class RoleSessionInfo:
    """Tracks an active Copilot SDK session for a specific role (agent_id)."""
    session_id: str
    output_dir: Path
    last_used_at: float


@dataclass
class OpenAIRoleSessionInfo:
    """Tracks the latest OpenAI response chain head for a specific role."""
    response_id: str
    last_used_at: float


def _normalize_target_path_token(token: str) -> Path | None:
    value = token.strip().strip("`").strip(",.;)")
    if not value.startswith("/"):
        return None
    candidate = Path(value)
    if candidate.exists():
        return candidate if candidate.is_dir() else candidate.parent
    return None


def _extract_target_directories(task_description: str, project_root: Path) -> list[Path]:
    lines = [line.strip() for line in str(task_description or "").splitlines()]
    candidates: list[Path] = []
    capture = False
    inline_target_pattern = re.compile(
        r"(?:^|.*?)(?:\*\*)?Target project(?: path)?:(?:\*\*)?\s*(.+)$",
        re.IGNORECASE,
    )
    for line in lines:
        matched_inline = inline_target_pattern.match(line)
        if matched_inline is not None:
            capture = True
            suffix = matched_inline.group(1).strip()
            if suffix:
                maybe = _normalize_target_path_token(suffix)
                if maybe is not None:
                    candidates.append(maybe)
            continue
        if capture:
            if not line:
                continue
            if line.startswith("## ") or line.startswith("- ") or ":" in line and not line.startswith("/"):
                capture = False
                continue
            maybe = _normalize_target_path_token(line)
            if maybe is not None:
                candidates.append(maybe)
                continue
            capture = False
    normalized: list[Path] = []
    seen: set[str] = set()
    for path in candidates + [project_root]:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        normalized.append(path.resolve())
    return normalized


def _codex_workdirs(task_description: str, project_root: Path, output_dir: Path | None) -> tuple[Path, list[Path]]:
    directories = _extract_target_directories(task_description, project_root)
    cwd = directories[0] if directories else project_root.resolve()
    add_dirs: list[Path] = directories[1:]
    if project_root.resolve() != cwd and project_root.resolve() not in add_dirs:
        add_dirs.append(project_root.resolve())
    if output_dir is not None:
        resolved_output_parent = output_dir.resolve().parent
        if resolved_output_parent != cwd and resolved_output_parent not in add_dirs:
            add_dirs.append(resolved_output_parent)
    return cwd, add_dirs


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path.resolve())
    return result


def _truncate_for_codex(text: str, limit: int) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _compact_persona_for_codex(persona: dict[str, Any], *, resume: bool = False) -> str:
    display_name = str(persona.get("display_name") or persona.get("role") or "Agent").strip()
    goal = str(persona.get("goal") or "").strip()
    if resume:
        return f"{display_name}\nGoal: continue the active session and finish the current step.".strip()
    body = _truncate_for_codex(str(persona.get("body") or "").strip(), max(160, min(config.CODEX_CLI_PERSONA_CHAR_LIMIT, 320)))
    lines = [f"{display_name}"]
    if goal:
        lines.append(f"Goal: {goal}")
    if body:
        lines.append(body)
    return "\n".join(lines).strip()


def _parse_markdown_sections(markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []
    for raw_line in str(markdown or "").splitlines():
        if raw_line.startswith("## "):
            if current_title:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = raw_line[3:].strip()
            current_lines = []
            continue
        current_lines.append(raw_line)
    if current_title:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def _compact_codex_task_packet(task_description: str, *, resume: bool = False) -> str:
    section_char_limit = int(config.CODEX_CLI_SECTION_CHAR_LIMIT)
    prompt_char_limit = int(config.CODEX_CLI_PROMPT_CHAR_LIMIT)
    sections = _parse_markdown_sections(task_description)

    goal = ""
    context_blocks: list[str] = []
    constraint_blocks: list[str] = []
    done_when = ""

    for title, body in sections:
        title_key = str(title or "").strip().lower()
        body_text = str(body or "").strip()
        if not body_text:
            continue
        if title_key == "step" and not goal:
            lines = [line.strip() for line in body_text.splitlines() if line.strip()]
            goal = _truncate_for_codex("\n".join(lines[:3]), section_char_limit)
            continue
        if title_key in {"project context", "suggested file scope", "implementation plan"}:
            context_blocks.append(f"### {title}\n{_truncate_for_codex(body_text, section_char_limit)}")
            continue
        if title_key in {"capability contract", "execution guidance", "validation contract", "delivery contract", "stale memory verification"}:
            constraint_blocks.append(f"### {title}\n{_truncate_for_codex(body_text, section_char_limit)}")
            continue
        if title_key == "done when" and not done_when:
            done_when = _truncate_for_codex(body_text, section_char_limit)

    if not goal:
        goal = _truncate_for_codex(str(task_description or "").strip(), section_char_limit)

    if resume:
        parts = [
            "# Delta",
            goal,
        ]
        if context_blocks:
            parts.extend(["", "# Current Scope", "\n\n".join(context_blocks[:2])])
        if constraint_blocks:
            parts.extend(["", "# Current Constraints", "\n\n".join(constraint_blocks[:3])])
        if done_when:
            parts.extend(["", "# Done When", done_when])
        parts.extend(
            [
                "",
                "# Resume Rules",
                "- Reuse the active session context; do not restate prior analysis.",
                "- Focus only on the current step delta and the latest blocking issue.",
                "- Keep edits minimal and verify only what changed for this step.",
            ]
        )
    else:
        parts = ["# Goal", goal]
        if context_blocks:
            parts.extend(["", "# Context", "\n\n".join(context_blocks[:2])])
        if constraint_blocks:
            parts.extend(["", "# Constraints", "\n\n".join(constraint_blocks[:3])])
        if done_when:
            parts.extend(["", "# Done When", done_when])
        parts.extend(
            [
                "",
                "# Execution Rules",
                "- Start with Suggested File Scope and only widen search if blocked.",
                "- Harness already resolved external workspace policies; do not search outside the target repository for parent AGENTS.md or llms.txt files.",
                "- Prefer changing source code in the target project over writing extra docs.",
                "- Keep edits minimal and verify the changed behavior before finishing.",
            ]
        )
    compact = "\n".join(parts).strip()
    return _truncate_for_codex(compact, prompt_char_limit)


def normalize_copilot_event_type(event_type: str) -> str:
    mapping = {
        "subagent.selected": "subagent_selected",
        "subagent.started": "subagent_started",
        "subagent.completed": "subagent_completed",
        "subagent.failed": "subagent_failed",
        "session.created": "runtime_session_created",
        "session.idle": "runtime_idle",
        "assistant.message": "assistant_output",
        "assistant.message_delta": "assistant_output_chunk",
        "tool.execution_complete": "tool_execution_complete",
        "tool.execution_start": "tool_execution_start",
        "tool.user_requested": "tool_requested",
        "permission.requested": "permission_requested",
        "permission.completed": "permission_completed",
        "user_input.requested": "user_input_requested",
        "user_input.completed": "user_input_completed",
        "elicitation.requested": "elicitation_requested",
        "elicitation.completed": "elicitation_completed",
        "session.resume": "runtime_session_resumed",
    }
    return mapping.get(event_type, event_type.replace(".", "_"))


def _normalize_tier(value: str | None) -> str:
    tier = str(value or "").strip().lower()
    if tier in {"mini", "standard", "max"}:
        return tier
    return "standard"


def _backend_provider_name(backend: str) -> str:
    normalized = str(backend or "").strip().lower()
    if normalized == "openai_responses":
        return "openai"
    if normalized == "copilot_sdk":
        return "copilot"
    if normalized == "codex_cli":
        return "codex"
    return str(config.LLM_PROVIDER or "openai").strip().lower() or "openai"


def _tier_override(override: str | None, fallback: str) -> str:
    value = str(override or "").strip()
    return value or fallback


def _default_runtime_model(*, backend: str, provider: str, tier: str) -> str:
    normalized_backend = str(backend or "").strip().lower()
    normalized_provider = str(provider or "").strip().lower()
    normalized_tier = _normalize_tier(tier)

    if normalized_backend == "codex_cli":
        if normalized_tier == "mini":
            return "gpt-5-codex-mini"
        return str(config.CODEX_CLI_MODEL or config.LLM_MODEL or "gpt-5-codex").strip()
    if normalized_backend == "copilot_sdk":
        return str(config.COPILOT_SDK_MODEL or config.LLM_MODEL or "gpt-4o").strip()
    if normalized_backend == "openai_responses":
        if normalized_tier == "mini" and str(config.LLM_MODEL or "").strip().lower().startswith("gpt-5"):
            return "gpt-5-mini"
        return str(config.LLM_MODEL or "gpt-4o").strip()
    if normalized_provider == "openai" and normalized_tier == "mini" and str(config.LLM_MODEL or "").strip().lower().startswith("gpt-5"):
        return "gpt-5-mini"
    return str(config.LLM_MODEL or "").strip()


def resolve_runtime_selection(
    execution_profile: dict[str, Any] | None = None,
    *,
    step_type: str = "",
    preferred_backend: str | None = None,
) -> RuntimeSelection:
    profile = execution_profile or {}
    tier = _normalize_tier(str(profile.get("complexity_tier") or "standard"))
    budget_cap = profile.get("budget_cap") if isinstance(profile.get("budget_cap"), dict) else {}
    allow_escalation = bool(profile.get("allow_escalation", True))
    escalation_rule = profile.get("escalation_rule") if isinstance(profile.get("escalation_rule"), dict) else {}

    backend_overrides = {
        "mini": config.RUNTIME_TIER_MINI_BACKEND,
        "standard": config.RUNTIME_TIER_STANDARD_BACKEND,
        "max": config.RUNTIME_TIER_MAX_BACKEND,
    }
    provider_overrides = {
        "mini": config.RUNTIME_TIER_MINI_PROVIDER,
        "standard": config.RUNTIME_TIER_STANDARD_PROVIDER,
        "max": config.RUNTIME_TIER_MAX_PROVIDER,
    }
    model_overrides = {
        "mini": config.RUNTIME_TIER_MINI_MODEL,
        "standard": config.RUNTIME_TIER_STANDARD_MODEL,
        "max": config.RUNTIME_TIER_MAX_MODEL,
    }

    backend = _tier_override(backend_overrides.get(tier), preferred_backend or config.ORCHESTRATION_BACKEND or "legacy").lower()
    provider = _tier_override(provider_overrides.get(tier), _backend_provider_name(backend)).lower()
    model = _tier_override(model_overrides.get(tier), _default_runtime_model(backend=backend, provider=provider, tier=tier))
    timeout_seconds = int(budget_cap.get("max_runtime_seconds") or 0) if isinstance(budget_cap, dict) else 0
    reason = f"tier={tier} step_type={step_type or '-'} backend={backend} provider={provider}"
    return RuntimeSelection(
        backend=backend,
        provider=provider,
        model=model,
        complexity_tier=tier,
        budget_cap=budget_cap if isinstance(budget_cap, dict) else {},
        allow_escalation=allow_escalation,
        escalation_rule=escalation_rule if isinstance(escalation_rule, dict) else {},
        timeout_seconds=timeout_seconds,
        reason=reason,
    )


def budget_points_for_tier(tier: str) -> int:
    normalized = _normalize_tier(tier)
    return {
        "mini": 6,
        "standard": 16,
        "max": 32,
    }.get(normalized, 16)


def estimate_runtime_budget_points(
    *,
    tier: str,
    runtime_backend: str,
    execution_time_ms: int = 0,
    tokens_used: int = 0,
) -> int:
    backend_name = str(runtime_backend or "").strip().lower()
    base = budget_points_for_tier(tier)
    runtime_seconds = max(0, int(execution_time_ms or 0) // 1000)
    time_points = min(12, max(0, runtime_seconds // 60))
    token_points = min(18, max(0, int(tokens_used or 0) // 4000))
    if backend_name == "legacy":
        # Legacy/mock runtimes are used for local deterministic tests and lightweight
        # fallbacks, so they should not consume the same budget as real provider calls.
        return max(2, min(12, 2 + time_points + token_points))
    backend_bonus = 2 if backend_name in {"codex_cli", "copilot_sdk"} else 0
    return max(base, min(100, base + time_points + token_points + backend_bonus))


class BaseTaskRuntime:
    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
        runtime_selection: RuntimeSelection | None = None,
        session_hint: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        raise NotImplementedError


class LegacyTaskRuntime(BaseTaskRuntime):
    def __init__(self, project_root: Path | None = None):
        self.engine = CrewEngine(project_root or config.PROJECT_ROOT)

    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
        runtime_selection: RuntimeSelection | None = None,
        session_hint: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        result = self.engine.execute(
            persona=persona,
            skill_name=skill_name,
            task_description=task_description,
            output_dir=output_dir,
            extra_context_files=extra_context_files,
            provider_name=runtime_selection.provider if runtime_selection else None,
            model_override=runtime_selection.model if runtime_selection else None,
            timeout_override=runtime_selection.timeout_seconds if runtime_selection else None,
        )
        return TaskExecutionResult(
            text=result.text,
            files=result.files,
            error=result.error,
            execution_time_ms=result.execution_time_ms,
            model=result.model,
            tokens_used=result.tokens_used,
            runtime_backend=(runtime_selection.backend if runtime_selection else "legacy"),
            runtime_provider=(runtime_selection.provider if runtime_selection else str(config.LLM_PROVIDER or "openai")),
        )


class CodexCLITaskRuntime(BaseTaskRuntime):
    def __init__(self, project_root: Path | None = None):
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.prompt_engine = CrewEngine(self.project_root)

    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
        runtime_selection: RuntimeSelection | None = None,
        session_hint: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        t0 = time.monotonic()
        execution_root = (
            Path(str((session_hint or {}).get("project_root") or "")).resolve()
            if str((session_hint or {}).get("project_root") or "").strip()
            else self.project_root
        )
        selected_model = runtime_selection.model if runtime_selection else (config.CODEX_CLI_MODEL or config.LLM_MODEL)
        selected_timeout = (
            _codex_selected_timeout_seconds(int(runtime_selection.timeout_seconds or 0))
            if runtime_selection
            else _codex_selected_timeout_seconds(0)
        )
        resume_mode = bool(session_hint and session_hint.get("thread_id"))
        sandbox_mode = _codex_sandbox_mode_for_step((session_hint or {}).get("step_type"))
        instructions = _compact_persona_for_codex(persona, resume=resume_mode)
        task_packet = _compact_codex_task_packet(task_description, resume=resume_mode)
        prompt = "\n\n".join(
            [
                "# Role",
                instructions,
                "# Bootstrap Packet" if not resume_mode else "# Delta Packet",
                task_packet,
                "# Output Contract",
                "Do the work directly in the target repository when appropriate. Return a concise final report of what changed, what was verified, and any remaining blockers.",
            ]
        )
        resolved_output_dir = (output_dir or (execution_root / "runtime" / f"codex-task-{int(time.time() * 1000)}")).resolve()
        cwd, add_dirs = _codex_workdirs(task_description, execution_root, resolved_output_dir)
        resume_thread_id = str((session_hint or {}).get("thread_id") or "").strip() or None
        session_key = str((session_hint or {}).get("session_key") or "").strip() or None
        launched = start_codex_exec_async(
            prompt=prompt,
            cwd=cwd,
            output_dir=resolved_output_dir,
            model=selected_model,
            add_dirs=_dedupe_paths(add_dirs),
            resume_thread_id=resume_thread_id,
            append_logs=bool(resume_thread_id),
            sandbox_mode=sandbox_mode,
        )
        metadata = {
            "provider": "codex",
            "backend": "codex_cli",
            "model": selected_model,
            "cwd": str(cwd),
            "add_dirs": [str(path) for path in _dedupe_paths(add_dirs)],
            "command": launched.command,
            "thread_id": launched.thread_id,
            "json_event_count": 0,
            "prompt_chars": len(prompt),
            "timeout_seconds": selected_timeout,
            "max_active_seconds": _codex_max_active_seconds(selected_timeout),
            "pid": launched.pid,
            "state_path": str(launched.state_path),
            "stdout_path": str(launched.stdout_path),
            "stderr_path": str(launched.stderr_path),
            "prompt_path": str(launched.prompt_path),
            "session_key": session_key or "",
            "resume_thread_id": resume_thread_id or "",
            "resume_count": int((session_hint or {}).get("resume_count") or 0),
            "step_type": str((session_hint or {}).get("step_type") or ""),
            "sandbox_mode": sandbox_mode or ("full-auto" if config.CODEX_CLI_FULL_AUTO else config.CODEX_CLI_SANDBOX),
        }
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        (resolved_output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        elapsed = int((time.monotonic() - t0) * 1000)
        return TaskExecutionResult(
            text="",
            files=[launched.output_path],
            execution_time_ms=elapsed,
            model=selected_model,
            runtime_backend="codex_cli",
            runtime_provider="codex",
            runtime_session_id=launched.thread_id,
            events=[
                RuntimeEvent(event_type="runtime_started", detail=f"backend=codex_cli model={selected_model} cwd={cwd}"),
                RuntimeEvent(
                    event_type="runtime_session_resumed" if resume_thread_id else "runtime_session_created",
                    detail=f"thread={resume_thread_id or 'pending-discovery'}",
                ),
            ],
            deferred=True,
            metadata=metadata,
        )


class CopilotSDKTaskRuntime(BaseTaskRuntime):
    def __init__(self, project_root: Path | None = None, bridge: CopilotSDKBridge | None = None):
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.bridge = bridge or CopilotSDKBridge(cwd=self.project_root)
        self.prompt_engine = CrewEngine(self.project_root)
        self._role_sessions: dict[str, RoleSessionInfo] = {}
        self._lock = threading.Lock()

    def clear_role_sessions(self) -> None:
        """Clear all role→session mappings. Called when a requirement finishes."""
        with self._lock:
            cleared = list(self._role_sessions.keys())
            self._role_sessions.clear()
        if cleared:
            logger.info("Cleared role sessions for: %s", ", ".join(cleared))

    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
        runtime_selection: RuntimeSelection | None = None,
        session_hint: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        t0 = time.monotonic()
        model = runtime_selection.model if runtime_selection else config.COPILOT_SDK_MODEL
        timeout_seconds = int(runtime_selection.timeout_seconds or config.COPILOT_SDK_TIMEOUT) if runtime_selection else config.COPILOT_SDK_TIMEOUT
        agent_id = persona.get("role", persona.get("id", "unknown"))
        prompt = self._build_parent_prompt(persona, skill_name, task_description, extra_context_files)
        preferred_agent = self._preferred_runtime_agent(skill_name, task_description)

        with self._lock:
            existing = self._role_sessions.get(agent_id)

        if existing:
            return self._execute_resume(
                t0, model, timeout_seconds, agent_id, existing, prompt, preferred_agent, output_dir,
            )
        return self._execute_new(
            t0, model, timeout_seconds, agent_id, prompt, preferred_agent, output_dir,
        )

    _session_counter: int = 0

    def _execute_new(
        self, t0: float, model: str, timeout_seconds: int, agent_id: str, prompt: str,
        preferred_agent: str | None, output_dir: Path | None,
    ) -> TaskExecutionResult:
        CopilotSDKTaskRuntime._session_counter += 1
        session_id = f"role-{agent_id}-{int(time.time() * 1000)}-{CopilotSDKTaskRuntime._session_counter}"
        resolved_output_dir = (output_dir or (self.project_root / "runtime" / session_id)).resolve()
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        predicted_output = copilot_runtime_paths(resolved_output_dir)["output"]
        payload = self.build_worker_payload(
            action="start",
            session_id=session_id,
            output_dir=resolved_output_dir,
            prompt=prompt,
            preferred_agent=preferred_agent,
            model=model,
            timeout_seconds=timeout_seconds,
        )

        try:
            self.bridge.start_session(payload)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.exception("Copilot SDK runtime failed (new session)")
            return TaskExecutionResult(
                text="",
                error=str(exc),
                execution_time_ms=elapsed,
                model=model,
                runtime_backend="copilot_sdk",
                runtime_provider="copilot",
                events=[RuntimeEvent(event_type="runtime_failed", detail=str(exc))],
            )

        with self._lock:
            self._role_sessions[agent_id] = RoleSessionInfo(
                session_id=session_id,
                output_dir=resolved_output_dir,
                last_used_at=time.time(),
            )

        elapsed = int((time.monotonic() - t0) * 1000)
        return TaskExecutionResult(
            text="",
            files=[predicted_output],
            execution_time_ms=elapsed,
            model=model,
            runtime_backend="copilot_sdk",
            runtime_provider="copilot",
            runtime_session_id=session_id,
            events=[
                RuntimeEvent(event_type="runtime_started", detail=f"backend=copilot_sdk model={model}"),
                RuntimeEvent(event_type="runtime_worker_spawned", detail=f"session={session_id}"),
            ],
            deferred=True,
        )

    def _execute_resume(
        self, t0: float, model: str, timeout_seconds: int, agent_id: str, existing: RoleSessionInfo,
        prompt: str, preferred_agent: str | None, output_dir: Path | None,
    ) -> TaskExecutionResult:
        session_id = existing.session_id
        # Each task gets its own output directory, but reuses the session
        resolved_output_dir = (output_dir or (self.project_root / "runtime" / f"{session_id}-resume-{int(time.time() * 1000)}")).resolve()
        resolved_output_dir.mkdir(parents=True, exist_ok=True)
        predicted_output = copilot_runtime_paths(resolved_output_dir)["output"]
        payload = self.build_worker_payload(
            action="resume",
            session_id=session_id,
            output_dir=resolved_output_dir,
            prompt=prompt,
            preferred_agent=preferred_agent,
            model=model,
            timeout_seconds=timeout_seconds,
        )

        try:
            self.bridge.resume_session(payload)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "Copilot SDK session resume failed for role %s (session=%s), falling back to new session",
                agent_id, session_id,
            )
            # Fallback: remove stale session and create a new one
            with self._lock:
                self._role_sessions.pop(agent_id, None)
            return self._execute_new(t0, model, timeout_seconds, agent_id, prompt, preferred_agent, output_dir)

        with self._lock:
            self._role_sessions[agent_id] = RoleSessionInfo(
                session_id=session_id,
                output_dir=resolved_output_dir,
                last_used_at=time.time(),
            )

        elapsed = int((time.monotonic() - t0) * 1000)
        return TaskExecutionResult(
            text="",
            files=[predicted_output],
            execution_time_ms=elapsed,
            model=model,
            runtime_backend="copilot_sdk",
            runtime_provider="copilot",
            runtime_session_id=session_id,
            events=[
                RuntimeEvent(event_type="runtime_started", detail=f"backend=copilot_sdk model={model} (resumed)"),
                RuntimeEvent(event_type="runtime_session_resumed", detail=f"session={session_id} role={agent_id}"),
            ],
            deferred=True,
        )

    def build_worker_payload(
        self,
        *,
        action: str,
        session_id: str,
        output_dir: Path,
        prompt: str | None = None,
        preferred_agent: str | None = None,
        assume_already_idle: bool = False,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict:
        paths = copilot_runtime_paths(output_dir)
        payload = {
            "action": action,
            "sessionId": session_id,
            "cwd": str(self.project_root),
            "customAgents": self._build_custom_agents(),
            "outputDir": str(output_dir),
            "statePath": str(paths["state"]),
            "eventsPath": str(paths["events"]),
            "stdoutPath": str(paths["stdout"]),
            "stderrPath": str(paths["stderr"]),
            "assumeAlreadyIdle": assume_already_idle,
        }
        if preferred_agent:
            payload["preferredAgent"] = preferred_agent
        if action == "start":
            payload["model"] = model or config.COPILOT_SDK_MODEL
        if prompt:
            payload["prompt"] = prompt
        timeout_seconds = timeout_seconds or config.COPILOT_SDK_TIMEOUT
        if timeout_seconds > 0:
            payload["timeoutMs"] = timeout_seconds * 1000
        return payload

    def _build_parent_prompt(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        extra_context_files: list[str] | None,
    ) -> str:
        system_prompt = self.prompt_engine._build_system_prompt(persona)
        user_message = self.prompt_engine._build_user_message(skill_name, task_description, extra_context_files)
        return "\n\n".join([
            "# Parent Session Role",
            system_prompt,
            "# Task Packet",
            user_message,
            "# Runtime Guidance",
            "Use the best matching custom agent for each sub-task. Prefer researcher for exploration, editor for modifications, and db-analyst for schema/query work.",
        ])

    def _build_custom_agents(self) -> list[dict]:
        agents = [
            {
                "name": "researcher",
                "displayName": "Research Agent",
                "description": "Analyzes repository structure, reads files, and answers questions using read-only tools.",
                "tools": ["view", "grep", "glob"],
                "prompt": "You are a research assistant. Explore the repository, identify patterns, and summarize findings. Never edit files.",
                "infer": True,
            },
            {
                "name": "editor",
                "displayName": "Editor Agent",
                "description": "Implements targeted code and docs changes, then validates them with local commands.",
                "tools": ["view", "grep", "glob", "edit", "bash"],
                "prompt": "You are a code editor. Make minimal, focused changes and prefer validation after editing.",
                "infer": True,
            },
        ]

        db_agent = {
            "name": "db-analyst",
            "displayName": "DB Analyst",
            "description": "Analyzes schemas, SQL, data workflows, and database-related issues.",
            "tools": ["view", "grep", "glob"],
            "prompt": "You are a database analyst. Focus on schema structure, queries, migrations, and data contracts.",
            "infer": True,
        }
        mcp_server = self._db_analyst_mcp_server()
        if mcp_server:
            db_agent["mcpServers"] = {"db-analyst": mcp_server}
        agents.append(db_agent)
        return agents

    def _db_analyst_mcp_server(self) -> dict | None:
        command = config.COPILOT_SDK_DB_ANALYST_MCP_COMMAND.strip()
        if not command:
            return None
        try:
            args = json.loads(config.COPILOT_SDK_DB_ANALYST_MCP_ARGS_JSON or "[]")
        except json.JSONDecodeError:
            args = []
        if not isinstance(args, list):
            args = []
        return {"command": command, "args": args}

    def _preferred_runtime_agent(self, skill_name: str, task_description: str) -> str | None:
        text = f"{skill_name} {task_description}".lower()
        db_terms = {"sql", "schema", "database", "migration", "query", "table", "postgres", "sqlite", "db"}
        research_terms = {"audit", "analyze", "research", "investigate", "compare", "review"}
        if any(term in text for term in db_terms):
            return "db-analyst"
        if any(term in text for term in research_terms):
            return "researcher"
        return None

    def _write_artifacts(self, output_dir: Path | None, text: str, metadata: dict, events: list) -> list[Path]:
        if not output_dir:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        out_file = output_dir / "output.md"
        out_file.write_text(text, encoding="utf-8")
        files.append(out_file)
        (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if events:
            (output_dir / "runtime-events.json").write_text(
                json.dumps([{"type": event.type, "detail": event.detail} for event in events], indent=2),
                encoding="utf-8",
            )
        return files

    def _normalize_event_type(self, event_type: str) -> str:
        return normalize_copilot_event_type(event_type)


class E2ETaskRuntime(BaseTaskRuntime):
    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
        runtime_selection: RuntimeSelection | None = None,
        session_hint: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        del persona, output_dir, extra_context_files, runtime_selection
        requirement_id = _extract_requirement_id(task_description)
        if "[workflow_step:implementation]" in task_description:
            return _e2e_result("Implementation output ready for review.")
        if "[workflow_step:review]" in task_description:
            return _e2e_result("Review passed and output is coherent.")
        if "[workflow_step:bugfix]" in task_description:
            return _e2e_result("Bugfix applied to resolve the failed validation.")
        if "[workflow_step:test]" in task_description:
            attempt_no = _E2E_REQUIREMENT_TEST_ATTEMPTS.get(requirement_id, 0) + 1
            _E2E_REQUIREMENT_TEST_ATTEMPTS[requirement_id] = attempt_no
            if attempt_no == 1:
                return _e2e_result("", error="Validation failed: issue reproduced in end-to-end check.")
            return _e2e_result("Validation passed after bugfix.")
        return _e2e_result(f"E2E runtime completed task for skill {skill_name}.")


def _e2e_result(text: str, error: str | None = None) -> TaskExecutionResult:
    return TaskExecutionResult(
        text=text,
        error=error,
        execution_time_ms=5,
        model="deterministic-e2e",
        runtime_backend="e2e",
        runtime_provider="deterministic",
    )


def _extract_requirement_id(task_description: str) -> int:
    match = re.search(r"Requirement #(\d+)", task_description)
    if not match:
        return 0
    return int(match.group(1))


_copilot_sdk_runtime_instance: CopilotSDKTaskRuntime | None = None
_copilot_sdk_runtime_lock = threading.Lock()
_openai_responses_runtime_instance: "OpenAIResponsesTaskRuntime | None" = None
_openai_responses_runtime_lock = threading.Lock()
_codex_cli_runtime_instance: "CodexCLITaskRuntime | None" = None
_codex_cli_runtime_lock = threading.Lock()


class OpenAIResponsesTaskRuntime(BaseTaskRuntime):
    def __init__(self, project_root: Path | None = None, provider: OpenAIProvider | None = None):
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.prompt_engine = CrewEngine(self.project_root)
        self.provider = provider or OpenAIProvider()
        self._role_sessions: dict[str, OpenAIRoleSessionInfo] = {}
        self._lock = threading.Lock()

    def clear_role_sessions(self) -> None:
        with self._lock:
            cleared = list(self._role_sessions.keys())
            self._role_sessions.clear()
        if cleared:
            logger.info("Cleared OpenAI role sessions for: %s", ", ".join(cleared))

    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
        runtime_selection: RuntimeSelection | None = None,
        session_hint: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        t0 = time.monotonic()
        model = runtime_selection.model if runtime_selection else config.LLM_MODEL
        timeout_seconds = int(runtime_selection.timeout_seconds or config.LLM_TIMEOUT) if runtime_selection else config.LLM_TIMEOUT
        agent_id = str(persona.get("role", persona.get("id", "unknown")))
        instructions = self.prompt_engine._build_system_prompt(persona)
        user_message = self.prompt_engine._build_user_message(skill_name, task_description, extra_context_files)

        with self._lock:
            existing = self._role_sessions.get(agent_id)
        previous_response_id = existing.response_id if existing else None

        try:
            response = self.provider.create_response(
                instructions=instructions,
                user_input=user_message,
                model=model,
                temperature=config.LLM_TEMPERATURE,
                timeout=timeout_seconds,
                background=True,
                previous_response_id=previous_response_id,
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.exception("OpenAI Responses runtime failed")
            return TaskExecutionResult(
                text="",
                error=str(exc),
                execution_time_ms=elapsed,
                model=model,
                runtime_backend="openai_responses",
                runtime_provider="openai",
                events=[RuntimeEvent(event_type="runtime_failed", detail=str(exc))],
            )

        response_id = str(response.get("id") or "")
        if not response_id:
            elapsed = int((time.monotonic() - t0) * 1000)
            error = "OpenAI Responses API did not return a response id"
            return TaskExecutionResult(
                text="",
                error=error,
                execution_time_ms=elapsed,
                model=model,
                runtime_backend="openai_responses",
                runtime_provider="openai",
                events=[RuntimeEvent(event_type="runtime_failed", detail=error)],
            )

        with self._lock:
            self._role_sessions[agent_id] = OpenAIRoleSessionInfo(
                response_id=response_id,
                last_used_at=time.time(),
            )

        metadata = {
            "provider": "openai",
            "backend": "openai_responses",
            "model": model,
            "response_id": response_id,
            "previous_response_id": previous_response_id,
            "conversation_id": self._conversation_id(response),
            "status": str(response.get("status") or ""),
        }
        predicted_output = self._write_metadata(output_dir, metadata)

        elapsed = int((time.monotonic() - t0) * 1000)
        events = [
            RuntimeEvent(event_type="runtime_started", detail=f"backend=openai_responses model={model}"),
        ]
        if previous_response_id:
            events.append(
                RuntimeEvent(
                    event_type="runtime_session_resumed",
                    detail=f"previous_response_id={previous_response_id} role={agent_id}",
                )
            )

        status = str(response.get("status") or "")
        if status == "completed":
            text = self.provider.extract_response_text(response)
            metadata["status"] = status
            files = self._write_completed_output(output_dir, text, metadata)
            return TaskExecutionResult(
                text=text,
                files=files,
                execution_time_ms=elapsed,
                model=model,
                tokens_used=self.provider.extract_response_tokens(response),
                runtime_backend="openai_responses",
                runtime_provider="openai",
                runtime_session_id=response_id,
                events=events,
            )

        if status in {"failed", "cancelled", "incomplete"}:
            error = self.provider.extract_response_error(response) or f"OpenAI response ended with status '{status}'"
            return TaskExecutionResult(
                text="",
                files=[predicted_output] if predicted_output else [],
                error=error,
                execution_time_ms=elapsed,
                model=model,
                runtime_backend="openai_responses",
                runtime_provider="openai",
                runtime_session_id=response_id,
                events=events + [RuntimeEvent(event_type="runtime_failed", detail=error)],
            )

        return TaskExecutionResult(
            text="",
            files=[predicted_output] if predicted_output else [],
            execution_time_ms=elapsed,
            model=model,
            runtime_backend="openai_responses",
            runtime_provider="openai",
            runtime_session_id=response_id,
            events=events,
            deferred=True,
        )

    @staticmethod
    def _conversation_id(response: dict) -> str | None:
        conversation = response.get("conversation")
        if isinstance(conversation, dict):
            conversation_id = conversation.get("id")
            if conversation_id:
                return str(conversation_id)
        return None

    @staticmethod
    def _write_metadata(output_dir: Path | None, metadata: dict) -> Path | None:
        if not output_dir:
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return output_dir / "output.md"

    @staticmethod
    def _write_completed_output(output_dir: Path | None, text: str, metadata: dict) -> list[Path]:
        if not output_dir:
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "output.md"
        output_path.write_text(text, encoding="utf-8")
        (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        return [output_path]


def get_task_runtime(project_root: Path | None = None, *, backend: str | None = None) -> BaseTaskRuntime:
    if config.E2E_MODE:
        return E2ETaskRuntime()
    selected_backend = (backend or config.ORCHESTRATION_BACKEND or "legacy").lower()
    if selected_backend == "codex_cli":
        global _codex_cli_runtime_instance
        with _codex_cli_runtime_lock:
            if _codex_cli_runtime_instance is None:
                _codex_cli_runtime_instance = CodexCLITaskRuntime(project_root=project_root)
            return _codex_cli_runtime_instance
    if selected_backend == "copilot_sdk":
        global _copilot_sdk_runtime_instance
        with _copilot_sdk_runtime_lock:
            if _copilot_sdk_runtime_instance is None:
                _copilot_sdk_runtime_instance = CopilotSDKTaskRuntime(project_root=project_root)
            return _copilot_sdk_runtime_instance
    if selected_backend == "openai_responses":
        global _openai_responses_runtime_instance
        with _openai_responses_runtime_lock:
            if _openai_responses_runtime_instance is None:
                _openai_responses_runtime_instance = OpenAIResponsesTaskRuntime(project_root=project_root)
            return _openai_responses_runtime_instance
    return LegacyTaskRuntime(project_root=project_root)


def get_copilot_sdk_runtime() -> CopilotSDKTaskRuntime | None:
    """Return the singleton CopilotSDKTaskRuntime instance, or None if not active."""
    return _copilot_sdk_runtime_instance


def get_openai_responses_runtime() -> OpenAIResponsesTaskRuntime | None:
    """Return the singleton OpenAIResponsesTaskRuntime instance, or None if not active."""
    return _openai_responses_runtime_instance


def get_codex_cli_runtime() -> CodexCLITaskRuntime | None:
    """Return the singleton CodexCLITaskRuntime instance, or None if not active."""
    return _codex_cli_runtime_instance


def clear_runtime_session_caches() -> None:
    runtime = get_copilot_sdk_runtime()
    if runtime is not None:
        runtime.clear_role_sessions()
    openai_runtime = get_openai_responses_runtime()
    if openai_runtime is not None:
        openai_runtime.clear_role_sessions()
