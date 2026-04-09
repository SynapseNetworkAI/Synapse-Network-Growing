"""Task execution runtimes for legacy and Copilot SDK backends."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from server import config
from server.services.context_loader import load_context
from server.services.crew_engine import CrewEngine
from server.services.copilot_sdk_bridge import CopilotSDKBridge
from server.services.skill_loader import load_skill

logger = logging.getLogger("ops-dashboard.task_runtime")


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
    runtime_session_id: str | None = None
    runtime_selected_agent: str | None = None
    events: list[RuntimeEvent] = field(default_factory=list)


class BaseTaskRuntime:
    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
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
    ) -> TaskExecutionResult:
        result = self.engine.execute(
            persona=persona,
            skill_name=skill_name,
            task_description=task_description,
            output_dir=output_dir,
            extra_context_files=extra_context_files,
        )
        return TaskExecutionResult(
            text=result.text,
            files=result.files,
            error=result.error,
            execution_time_ms=result.execution_time_ms,
            model=result.model,
            tokens_used=result.tokens_used,
            runtime_backend="legacy",
        )


class CopilotSDKTaskRuntime(BaseTaskRuntime):
    def __init__(self, project_root: Path | None = None, bridge: CopilotSDKBridge | None = None):
        self.project_root = (project_root or config.PROJECT_ROOT).resolve()
        self.bridge = bridge or CopilotSDKBridge(cwd=self.project_root)
        self.prompt_engine = CrewEngine(self.project_root)

    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
    ) -> TaskExecutionResult:
        t0 = time.monotonic()
        model = config.COPILOT_SDK_MODEL
        prompt = self._build_parent_prompt(persona, skill_name, task_description, extra_context_files)
        preferred_agent = self._preferred_runtime_agent(skill_name, task_description)
        payload = {
            "model": model,
            "sessionId": f"task-{int(time.time() * 1000)}",
            "prompt": prompt,
            "cwd": str(self.project_root),
            "timeoutMs": config.COPILOT_SDK_TIMEOUT * 1000,
            "preferredAgent": preferred_agent,
            "customAgents": self._build_custom_agents(),
        }

        try:
            bridge_result = self.bridge.run_session(payload, timeout=config.COPILOT_SDK_TIMEOUT)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.exception("Copilot SDK runtime failed")
            return TaskExecutionResult(
                text="",
                error=str(exc),
                execution_time_ms=elapsed,
                model=model,
                runtime_backend="copilot_sdk",
                events=[RuntimeEvent(event_type="runtime_failed", detail=str(exc))],
            )

        elapsed = int((time.monotonic() - t0) * 1000)
        files = self._write_artifacts(
            output_dir=output_dir,
            text=bridge_result.content,
            metadata={
                "model": model,
                "tokens_used": bridge_result.tokens_used,
                "execution_time_ms": elapsed,
                "skill": skill_name,
                "persona": persona.get("role", "unknown"),
                "runtime_backend": "copilot_sdk",
                "runtime_session_id": bridge_result.session_id,
                "runtime_selected_agent": bridge_result.selected_agent,
            },
            events=bridge_result.events,
        )

        normalized_events = [
            RuntimeEvent(event_type=self._normalize_event_type(event.type), detail=event.detail)
            for event in bridge_result.events
        ]
        normalized_events.insert(0, RuntimeEvent(event_type="runtime_started", detail=f"backend=copilot_sdk model={model}"))
        normalized_events.append(RuntimeEvent(event_type="runtime_completed", detail=bridge_result.selected_agent or ""))

        return TaskExecutionResult(
            text=bridge_result.content,
            files=files,
            execution_time_ms=elapsed,
            model=model,
            tokens_used=bridge_result.tokens_used,
            runtime_backend="copilot_sdk",
            runtime_session_id=bridge_result.session_id,
            runtime_selected_agent=bridge_result.selected_agent,
            events=normalized_events,
        )

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
            "tool.user_requested": "tool_requested",
        }
        return mapping.get(event_type, event_type.replace(".", "_"))


def get_task_runtime(project_root: Path | None = None) -> BaseTaskRuntime:
    backend = (config.ORCHESTRATION_BACKEND or "legacy").lower()
    if backend == "copilot_sdk":
        return CopilotSDKTaskRuntime(project_root=project_root)
    return LegacyTaskRuntime(project_root=project_root)