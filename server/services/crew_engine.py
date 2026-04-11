from __future__ import annotations

"""Agent execution engine — assembles Persona + Skill + Context and calls LLM.

Uses the LLM adapter layer to support multiple providers (OpenAI, Claude, Copilot).
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from server.services.skill_loader import load_skill
from server.services.context_loader import load_context
from server.services.llm_adapter import get_provider, LLMProvider
from server.config import PROJECT_ROOT, LLM_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT

logger = logging.getLogger("ops-dashboard.crew_engine")


@dataclass
class CrewResult:
    text: str
    files: list[Path] = field(default_factory=list)
    error: str | None = None
    execution_time_ms: int = 0
    model: str = ""
    tokens_used: int = 0


class CrewEngine:
    """Assemble persona + skill + context into an LLM chat completion."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = (project_root or PROJECT_ROOT).resolve()

    def execute(
        self,
        persona: dict,
        skill_name: str,
        task_description: str,
        output_dir: Path | None = None,
        extra_context_files: list[str] | None = None,
    ) -> CrewResult:
        t0 = time.monotonic()
        model = LLM_MODEL

        # 1. Build system prompt from persona
        system_prompt = self._build_system_prompt(persona)

        # 2. Build user message from skill + context + task
        user_message = self._build_user_message(
            skill_name, task_description, extra_context_files
        )

        # 3. Call LLM
        try:
            response_text, tokens = self._call_llm(system_prompt, user_message, model)
        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.exception("LLM call failed")
            return CrewResult(
                text="", error=str(e), execution_time_ms=elapsed, model=model
            )

        elapsed = int((time.monotonic() - t0) * 1000)

        # 4. Write output file
        files: list[Path] = []
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_file = output_dir / "output.md"
            out_file.write_text(response_text, encoding="utf-8")
            files.append(out_file)
            # Write metadata
            meta = {
                "model": model,
                "tokens_used": tokens,
                "execution_time_ms": elapsed,
                "skill": skill_name,
                "persona": persona.get("role", "unknown"),
            }
            (output_dir / "metadata.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

        return CrewResult(
            text=response_text,
            files=files,
            execution_time_ms=elapsed,
            model=model,
            tokens_used=tokens,
        )

    def _build_system_prompt(self, persona: dict) -> str:
        parts = [
            f"You are {persona.get('display_name', 'an AI agent')}.",
            f"Goal: {persona.get('goal', '')}",
        ]
        body = persona.get("body", "")
        if body:
            parts.append(f"\n{body}")
        return "\n".join(parts)

    def _build_user_message(
        self,
        skill_name: str,
        task_description: str,
        extra_files: list[str] | None,
    ) -> str:
        parts = []

        # Context
        ctx = load_context(self.project_root, extra_files)
        if ctx:
            parts.append(ctx)

        # Skill instructions
        try:
            skill_text = load_skill(skill_name)
            parts.append(f"## Skill Instructions\n{skill_text}")
        except FileNotFoundError:
            logger.warning("Skill '%s' not found, proceeding without it", skill_name)

        # Task
        parts.append(f"## Task\n{task_description}")
        parts.append(
            "## Output Format\nRespond in Markdown. Be specific and actionable."
        )

        return "\n\n---\n\n".join(parts)

    def _call_llm(self, system: str, user: str, model: str) -> tuple[str, int]:
        """Dispatch to the configured LLM provider."""
        provider = get_provider()
        logger.info("Calling LLM: provider=%s, model=%s, system=%d chars, user=%d chars",
                     provider.name, model, len(system), len(user))
        return provider.call(system, user, model, LLM_TEMPERATURE, LLM_TIMEOUT)
