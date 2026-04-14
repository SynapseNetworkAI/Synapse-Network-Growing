"""Provider-facing full-plan helpers for workflow planning."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from server import config
from server.services.agents.llm_adapter import get_provider


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
    """Resolve the provider used for full-plan generation."""

    backend = str(config.ORCHESTRATION_BACKEND or "").strip().lower()
    if backend == "openai_responses":
        return "openai"
    if backend == "copilot_sdk":
        return "copilot"
    if backend == "codex_cli":
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
            return str(config.CODEX_CLI_MODEL or "").strip()
        return model
    if provider_name == "copilot":
        return str(config.COPILOT_SDK_MODEL or "gpt-4o").strip() or "gpt-4o"
    if provider_name == "codex":
        return str(config.CODEX_CLI_MODEL or "").strip()
    if provider_name == "claude":
        return "claude-3-7-sonnet-latest"
    return "gpt-4o"


def call_full_plan_provider(
    *,
    provider_name: str,
    provider: Any,
    prompt: str,
    model_name: str,
    system_prompt: str,
) -> tuple[str, int]:
    """Call the configured provider and return text plus token usage."""

    timeout = min(config.LLM_TIMEOUT, 90)
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


def plan_with_agent(
    text: str,
    target_path: str | None,
    *,
    planning_hint: str | None,
    system_prompt: str,
    cooldown_until: datetime | None,
    cooldown_reason: str,
    auth_cooldown: timedelta,
    auth_error_snippets: tuple[str, ...],
    provider_backoff_snippets: tuple[str, ...],
    logger: logging.Logger,
    get_provider_fn: Callable[[str], Any],
    normalize_complexity_tier: Callable[[Any], str],
    default_budget_cap: Callable[[str], dict[str, Any]],
    default_complexity_tier: Callable[..., str],
) -> tuple[list[dict[str, Any]] | None, datetime | None, str]:
    """Ask the planner model for implementation sub-steps and normalize the response."""

    if cooldown_until is not None and datetime.now(timezone.utc) < cooldown_until:
        logger.info(
            "Skipping agent full-plan during cooldown until %s (%s)",
            cooldown_until.isoformat(),
            cooldown_reason or "temporary disable",
        )
        return None, cooldown_until, cooldown_reason
    try:
        provider_name = planner_provider_name()
        model_name = planner_model_name(provider_name)
        provider = get_provider_fn(provider_name)
        prompt = text[:4000]
        if target_path:
            prompt = f"Target project path: {target_path}\n\n{prompt}"
        user_prompt = f"{prompt}\n\n"
        if planning_hint:
            user_prompt += f"Planner hint:\n{planning_hint.strip()}\n\n"
        user_prompt += "Return only JSON matching the required schema."
        logger.info(
            "Attempting planner full-plan with provider=%s model=%s",
            provider_name,
            model_name,
        )
        content, _tokens = call_full_plan_provider(
            provider_name=provider_name,
            provider=provider,
            prompt=user_prompt,
            model_name=model_name,
            system_prompt=system_prompt,
        )
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)

        raw_steps = data.get("steps", [])
        if not raw_steps or not isinstance(raw_steps, list):
            return None, None, ""

        steps: list[dict[str, Any]] = []
        target_paths = _split_target_paths(target_path)
        seen_keys: set[str] = set()
        for raw_step in raw_steps:
            key = re.sub(r"[^a-z0-9_]", "_", str(raw_step.get("step_key", "step")).lower())
            if key in seen_keys:
                key = f"{key}_{len(steps)}"
            seen_keys.add(key)
            scope = str(raw_step.get("scope", "backend")).lower()
            steps.append(
                {
                    "step_key": key,
                    "title": str(raw_step.get("title", key)),
                    "scope": scope,
                    "depends_on": [str(dep) for dep in raw_step.get("depends_on", []) if str(dep) in seen_keys],
                    "done_when": str(raw_step.get("done_when", "Step output is produced and ready for review.")),
                    "complexity_tier": normalize_complexity_tier(raw_step.get("complexity_tier")),
                    "budget_cap": dict(
                        raw_step.get("budget_cap")
                        or default_budget_cap(
                            default_complexity_tier(
                                step_type="implementation",
                                scope=scope,
                                target_paths=target_paths,
                            )
                        )
                    ),
                    "allow_escalation": bool(raw_step.get("allow_escalation", True)),
                    "escalation_rule": dict(raw_step.get("escalation_rule") or {}),
                }
            )

        logger.info("Agent full-plan produced %d steps via provider=%s", len(steps), provider_name)
        return steps if steps else None, None, ""
    except Exception as exc:
        message = str(exc).lower()
        if any(snippet in message for snippet in auth_error_snippets):
            cooldown_until = datetime.now(timezone.utc) + auth_cooldown
            cooldown_reason = "copilot_authorization_error"
            logger.warning(
                "Agent full-plan disabled until %s after Copilot authorization error",
                cooldown_until.isoformat(),
            )
        elif any(snippet in message for snippet in provider_backoff_snippets):
            cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=5)
            cooldown_reason = "planner_provider_backoff"
            logger.warning(
                "Agent full-plan disabled until %s after provider error",
                cooldown_until.isoformat(),
            )
        logger.warning("Agent full-plan failed, will fall back to phase-detect mode", exc_info=True)
        return None, cooldown_until, cooldown_reason


__all__ = [
    "planner_provider_name",
    "planner_model_name",
    "call_full_plan_provider",
    "plan_with_agent",
]
