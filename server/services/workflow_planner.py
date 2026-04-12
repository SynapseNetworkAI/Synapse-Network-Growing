"""Agent-driven planner for requirement-first workflows.

Uses the configured LLM provider to analyse the requirement and produce a
full ordered step plan, then generates dynamic file_scope based on
target_project_path.

Mode 1 (full-plan, default): agent returns a JSON step list with step_key,
title, scope, depends_on, and done_when for each step.

Mode 2 (phase-detect, fallback): agent returns 4 boolean flags and Python
generates the fixed step set deterministically.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import AgentRow, ArtifactRow, RequirementRow
from server.services.acceptance import acceptance_contract_for_requirement
from server.services.agent_loader import ensure_agents_loaded
from server.services.execution_resolver import suggest_task_execution
from server.services.llm_adapter import get_provider
from server.services.project_intelligence import resolve_requirement_routing
from server.services.project_policy import (
    CAPABILITY_KEYS,
    aggregate_execution_controls,
    apply_project_policies_to_scope,
    project_policy_to_dict,
    resolve_project_policies_for_target,
)

logger = logging.getLogger("ops-dashboard.workflow_planner")

PRIMARY_GROWING_PROJECT = "/Users/cliff/workspace/agent/Synapse-Network-Growing"
PRIMARY_SYNAPSE_PROJECT = "/Users/cliff/workspace/agent/Synapse-Network"

_RELEASE_MODE_RANK = {"disabled": 0, "manual": 1, "auto": 2}
_FULL_PLAN_DISABLED_UNTIL: datetime | None = None
_FULL_PLAN_DISABLED_REASON: str = ""
_FULL_PLAN_AUTH_COOLDOWN = timedelta(minutes=10)
_FULL_PLAN_AUTH_ERROR_SNIPPETS = (
    "not authorized to use this copilot feature",
    "you are not authorized to use this copilot feature",
    "enterprise-managed users",
)
_FULL_PLAN_PROVIDER_COOLDOWN_SNIPPETS = (
    "insufficient_quota",
    "model_not_found",
    "rate_limit",
    "too many requests",
    "does not exist",
    "you exceeded your current quota",
)
_FULL_PLAN_SYSTEM_PROMPT = """You are a workflow planning model for a multi-agent software delivery system.
Return strict JSON only, with no markdown fences or commentary.

Schema:
{
  "steps": [
    {
      "step_key": "short_snake_case_id",
      "title": "Human readable step title",
      "scope": "infrastructure|backend|frontend|test|docs",
      "complexity_tier": "mini|standard|max",
      "budget_cap": {
        "max_input_tokens": 6000,
        "max_output_tokens": 1500,
        "max_attempts": 2,
        "max_runtime_seconds": 600
      },
      "allow_escalation": true,
      "escalation_rule": {
        "next_tier": "standard|max|stay",
        "when": ["step_failed_twice", "review_or_test_blocker"],
        "max_escalations": 1
      },
      "depends_on": ["prior_step_key"],
      "done_when": "Concrete completion criteria for this step"
    }
  ]
}

Rules:
- Plan only implementation sub-steps. Research, synthesis, review, test, and closeout are added by the harness.
- Keep between 1 and 5 implementation sub-steps.
- Use dependency chains that reference earlier step_key values only.
- Prefer concrete scopes: backend, frontend, infrastructure, test, or docs.
- Use terse titles, avoid repeating the full requirement title in every step.
- Let the requirement decide whether work is docs-only, code-only, or mixed.
- Annotate every implementation step with complexity tier, budget cap, and escalation rule.
- The harness enforces project boundaries and verification governance. Do not assume a primary repository.
- If the work is simple, return a single implementation step.
"""

# ---------------------------------------------------------------------------
# Mode 1: Full-plan (agent decides everything)
# ---------------------------------------------------------------------------


@dataclass
class _AgentStep:
    step_key: str
    title: str
    scope: str
    depends_on: list[str]
    done_when: str
    complexity_tier: str = ""
    budget_cap: dict[str, Any] = field(default_factory=dict)
    allow_escalation: bool = True
    escalation_rule: dict[str, Any] = field(default_factory=dict)


def _split_target_paths(raw_path: str | None) -> list[str]:
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


_TIER_BUDGETS: dict[str, dict[str, int]] = {
    "mini": {
        "max_input_tokens": 6000,
        "max_output_tokens": 1500,
        "max_attempts": 2,
        "max_runtime_seconds": 600,
    },
    "standard": {
        "max_input_tokens": 14000,
        "max_output_tokens": 4000,
        "max_attempts": 3,
        "max_runtime_seconds": 1800,
    },
    "max": {
        "max_input_tokens": 24000,
        "max_output_tokens": 8000,
        "max_attempts": 4,
        "max_runtime_seconds": 3600,
    },
}


def _default_budget_cap(tier: str) -> dict[str, int]:
    return dict(_TIER_BUDGETS.get(tier, _TIER_BUDGETS["standard"]))


def _normalize_complexity_tier(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"mini", "standard", "max"}:
        return normalized
    return ""


def _default_complexity_tier(*, step_type: str, scope: str = "", target_paths: list[str] | None = None) -> str:
    target_paths = target_paths or []
    if step_type == "closeout":
        return "mini"
    if step_type in {"implementation", "bugfix", "review", "test"}:
        if len(target_paths) > 1 and step_type in {"implementation", "bugfix", "review", "test"}:
            return "max"
        if scope == "docs" and len(target_paths) <= 1:
            return "mini"
        return "standard"
    if step_type == "research":
        return "mini" if len(target_paths) <= 1 else "standard"
    return "standard"


def _default_escalation_rule(tier: str, *, allow_escalation: bool) -> dict[str, Any]:
    if not allow_escalation:
        return {
            "next_tier": "stay",
            "when": [],
            "max_escalations": 0,
        }
    next_tier = "standard" if tier == "mini" else "max"
    return {
        "next_tier": next_tier,
        "when": [
            "step_failed_twice",
            "changed_files_over_threshold",
            "multi_project_change_detected",
            "review_or_test_blocker",
        ],
        "changed_files_threshold": 8,
        "max_escalations": 1,
    }


def _build_execution_profile(
    *,
    step_type: str,
    scope: str = "",
    target_paths: list[str] | None = None,
    complexity_tier: str | None = None,
    budget_cap: dict[str, Any] | None = None,
    allow_escalation: bool | None = None,
    escalation_rule: dict[str, Any] | None = None,
    expected_outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    tier = _normalize_complexity_tier(complexity_tier) or _default_complexity_tier(
        step_type=step_type,
        scope=scope,
        target_paths=target_paths,
    )
    escalation_allowed = True if allow_escalation is None else bool(allow_escalation)
    if tier == "max" and allow_escalation is None:
        escalation_allowed = False
    return {
        "complexity_tier": tier,
        "budget_cap": dict(budget_cap or _default_budget_cap(tier)),
        "allow_escalation": escalation_allowed,
        "escalation_rule": dict(escalation_rule or _default_escalation_rule(tier, allow_escalation=escalation_allowed)),
        "expected_outputs": list(expected_outputs or []),
    }


def _plan_with_agent(text: str, target_path: str | None) -> list[_AgentStep] | None:
    """Pass the requirement directly to the agent; it decides the step plan."""
    global _FULL_PLAN_DISABLED_REASON, _FULL_PLAN_DISABLED_UNTIL
    if _FULL_PLAN_DISABLED_UNTIL is not None and datetime.now(timezone.utc) < _FULL_PLAN_DISABLED_UNTIL:
        logger.info(
            "Skipping agent full-plan during cooldown until %s (%s)",
            _FULL_PLAN_DISABLED_UNTIL.isoformat(),
            _FULL_PLAN_DISABLED_REASON or "temporary disable",
        )
        return None
    try:
        provider_name = _planner_provider_name()
        model_name = _planner_model_name(provider_name)
        provider = get_provider(provider_name)
        prompt = text[:4000]
        if target_path:
            prompt = f"Target project path: {target_path}\n\n{prompt}"
        user_prompt = (
            f"{prompt}\n\n"
            "Return only JSON matching the required schema."
        )
        logger.info(
            "Attempting planner full-plan with provider=%s model=%s",
            provider_name,
            model_name,
        )
        content, _tokens = _call_full_plan_provider(
            provider_name=provider_name,
            provider=provider,
            prompt=user_prompt,
            model_name=model_name,
        )
        content = content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)

        raw_steps = data.get("steps", [])
        if not raw_steps or not isinstance(raw_steps, list):
            return None

        steps: list[_AgentStep] = []
        target_paths = _split_target_paths(target_path)
        seen_keys: set[str] = set()
        for s in raw_steps:
            key = re.sub(r"[^a-z0-9_]", "_", str(s.get("step_key", "step")).lower())
            if key in seen_keys:
                key = f"{key}_{len(steps)}"
            seen_keys.add(key)
            scope = str(s.get("scope", "backend")).lower()
            steps.append(_AgentStep(
                step_key=key,
                title=str(s.get("title", key)),
                scope=scope,
                depends_on=[str(d) for d in s.get("depends_on", []) if str(d) in seen_keys],
                done_when=str(s.get("done_when", "Step output is produced and ready for review.")),
                complexity_tier=_normalize_complexity_tier(s.get("complexity_tier")),
                budget_cap=dict(s.get("budget_cap") or _default_budget_cap(
                    _default_complexity_tier(step_type="implementation", scope=scope, target_paths=target_paths)
                )),
                allow_escalation=bool(s.get("allow_escalation", True)),
                escalation_rule=dict(s.get("escalation_rule") or {}),
            ))

        logger.info("Agent full-plan produced %d steps via provider=%s", len(steps), provider_name)
        return steps if steps else None

    except Exception as exc:
        message = str(exc).lower()
        if any(snippet in message for snippet in _FULL_PLAN_AUTH_ERROR_SNIPPETS):
            _FULL_PLAN_DISABLED_UNTIL = datetime.now(timezone.utc) + _FULL_PLAN_AUTH_COOLDOWN
            _FULL_PLAN_DISABLED_REASON = "copilot_authorization_error"
            logger.warning(
                "Agent full-plan disabled until %s after Copilot authorization error",
                _FULL_PLAN_DISABLED_UNTIL.isoformat(),
            )
        elif any(snippet in message for snippet in _FULL_PLAN_PROVIDER_COOLDOWN_SNIPPETS):
            _FULL_PLAN_DISABLED_UNTIL = datetime.now(timezone.utc) + timedelta(minutes=5)
            _FULL_PLAN_DISABLED_REASON = "planner_provider_backoff"
            logger.warning(
                "Agent full-plan disabled until %s after provider error",
                _FULL_PLAN_DISABLED_UNTIL.isoformat(),
            )
        logger.warning("Agent full-plan failed, will fall back to phase-detect mode", exc_info=True)
        return None


def _planner_provider_name() -> str:
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


def _planner_model_name(provider_name: str) -> str:
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


def _call_full_plan_provider(
    *,
    provider_name: str,
    provider: Any,
    prompt: str,
    model_name: str,
) -> tuple[str, int]:
    timeout = min(config.LLM_TIMEOUT, 90)
    if provider_name == "openai" and hasattr(provider, "create_response"):
        response = provider.create_response(
            instructions=_FULL_PLAN_SYSTEM_PROMPT,
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
        _FULL_PLAN_SYSTEM_PROMPT,
        prompt,
        model_name,
        0.1,
        timeout,
    )


# ---------------------------------------------------------------------------
# Mode 2: Phase-detect (keyword fallback — no agent call)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowRoleAssignments:
    researcher_agent_id: str
    synthesizer_agent_id: str
    implementer_agent_id: str
    reviewer_agent_id: str
    tester_agent_id: str


@dataclass
class _DetectedPhases:
    """Which implementation sub-phases the requirement text implies."""
    design: bool = False
    frontend: bool = False
    backend: bool = False
    test_impl: bool = False

    @property
    def has_sub_steps(self) -> bool:
        return sum([self.design, self.frontend, self.backend, self.test_impl]) >= 2


def _detect_phases_with_agent(text: str) -> _DetectedPhases:
    """Keyword-based phase detection (used as fallback when full-plan agent fails)."""
    return _detect_phases_fallback(text)


def _detect_phases_fallback(text: str) -> _DetectedPhases:
    """Keyword fallback when the agent call is unavailable."""
    _DESIGN = re.compile(r"方案设计|架构|architecture|设计文档|design|schema|DDL|数据模型", re.IGNORECASE)
    _FRONTEND = re.compile(r"前端|frontend|UI|页面|组件|React|Vue|sdk\.ts|analytics\.ts|埋点.*(前端|SDK)", re.IGNORECASE)
    _BACKEND = re.compile(r"后端|backend|API|服务端|server|endpoint|kafka|clickhouse|数据库|中间件|接受埋点", re.IGNORECASE)
    _TEST = re.compile(r"自动化测试|测试方案|test.*(方案|实现|代码)|验证数据|e2e|集成测试|pytest|vitest", re.IGNORECASE)
    return _DetectedPhases(
        design=bool(_DESIGN.search(text)),
        frontend=bool(_FRONTEND.search(text)),
        backend=bool(_BACKEND.search(text)),
        test_impl=bool(_TEST.search(text)),
    )


# ---------------------------------------------------------------------------
# Dynamic file_scope helpers
# ---------------------------------------------------------------------------

def _base_file_scope() -> dict:
    """Always-included read/write for outputs and docs."""
    return {
        "allowed_read_globs": ["roles/**", "docs/**", "campaigns/**", "demos/**", "README.md"],
        "allowed_write_globs": ["roles/**", "docs/**", "campaigns/**", "demos/**", "README.md"],
        "blocked_globs": [".git/**", "node_modules/**"],
    }


def _project_file_scope(target_project_path: str | None, *, write: bool = True) -> dict:
    """Extend base scope with the target project path."""
    scope = _base_file_scope()
    if not target_project_path:
        return scope
    p = target_project_path.rstrip("/")
    scope["allowed_read_globs"].append(f"{p}/**")
    if write:
        scope["allowed_write_globs"].append(f"{p}/**")
    return scope


def _review_file_scope(target_project_path: str | None) -> dict:
    """Reviewers/testers can read the project but only write to roles/docs."""
    return _project_file_scope(target_project_path, write=False)


def _build_research_and_synthesis_steps(requirement: RequirementRow, target_path: str | None) -> list[dict[str, Any]]:
    project_note = f"\nTarget project: {target_path}" if target_path else ""
    target_paths = _split_target_paths(target_path)
    research_outputs = [
        {"artifact_type": "research_report", "description": "Research findings, constraints, existing code paths, and risks."},
    ]
    synthesis_outputs = [
        {"artifact_type": "synthesis_report", "description": "Execution strategy, change plan, and verification outline."},
    ]
    return [
        {
            "step_key": "research",
            "step_type": "research",
            "title": "Research context",
            "assigned_role": "researcher",
            "depends_on": [],
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _review_file_scope(target_path),
            "expected_outputs": research_outputs,
            "validation_targets": [],
            "done_when_markdown": (
                "Research output identifies relevant code paths, project constraints, likely risks, and concrete implementation options. "
                "Do not modify production code in this step."
                f"{project_note}"
            ),
            "failure_policy": {"on_failure": "requirement_revision", "max_retries": 0},
            **_build_execution_profile(
                step_type="research",
                target_paths=target_paths,
                expected_outputs=research_outputs,
            ),
        },
        {
            "step_key": "synthesis",
            "step_type": "synthesis",
            "title": "Synthesize plan",
            "assigned_role": "synthesizer",
            "depends_on": ["research"],
            "required_artifacts": [
                {"artifact_type": "research_report", "purpose": "research_context", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _review_file_scope(target_path),
            "expected_outputs": synthesis_outputs,
            "validation_targets": [],
            "done_when_markdown": (
                "Synthesis output turns research findings into a concrete execution plan with files, sequencing, and verification intent. "
                "Do not modify production code in this step."
                f"{project_note}"
            ),
            "failure_policy": {"on_failure": "requirement_revision", "max_retries": 0},
            **_build_execution_profile(
                step_type="synthesis",
                target_paths=target_paths,
                expected_outputs=synthesis_outputs,
            ),
        },
    ]


def _prepend_context_steps(workflow_steps: list[dict[str, Any]], requirement: RequirementRow, target_path: str | None) -> list[dict[str, Any]]:
    context_steps = _build_research_and_synthesis_steps(requirement, target_path)
    for step in workflow_steps:
        key = str(step.get("step_key") or "")
        if key in {"research", "synthesis"}:
            continue
        depends_on = list(step.get("depends_on") or [])
        if not depends_on:
            step["depends_on"] = ["synthesis"]
    return context_steps + workflow_steps


def _scope_to_file_scope(scope: str, target_path: str | None) -> dict:
    """Map an agent-plan scope string to a file_scope dict.

    - infrastructure / backend / frontend / test: full read+write on target project
    - docs: base read+write only (roles/**, docs/**)
    """
    if scope in ("infrastructure", "backend", "frontend", "test"):
        return _project_file_scope(target_path, write=True)
    return _base_file_scope()  # docs, unknown


# ---------------------------------------------------------------------------
# Mode 1: Build workflow steps from agent full-plan
# ---------------------------------------------------------------------------

_SCOPE_CONSTRAINTS = {
    "infrastructure": (
        "SCOPE: Only create infrastructure artifacts (SQL DDL, docker-compose, config files, CI setup). "
        "Do NOT write application code (Python, TypeScript, etc.) in this step."
    ),
    "backend": (
        "SCOPE: Only implement backend/API/server-side code (endpoints, services, middleware, database). "
        "Do NOT implement frontend code in this step."
    ),
    "frontend": (
        "SCOPE: Only implement frontend/client-side code (components, hooks, SDK, styles). "
        "Do NOT implement backend/API code in this step."
    ),
    "test": (
        "SCOPE: Only implement automated tests (unit, integration, e2e). "
        "Do NOT modify production application code in this step."
    ),
    "docs": (
        "SCOPE: Only produce documentation (runbooks, architecture docs, ops guides). "
        "Do NOT write implementation code in this step."
    ),
}


def _build_steps_from_agent_plan(
    requirement: RequirementRow,
    agent_steps: list[_AgentStep],
    target_path: str | None,
) -> tuple[list[dict], list[str]]:
    """Convert agent-produced _AgentStep list to workflow step dicts."""
    result: list[dict] = []
    keys: list[str] = [s.step_key for s in agent_steps]
    project_note = f"\nTarget project: {target_path}" if target_path else ""
    target_paths = _split_target_paths(target_path)

    for step in agent_steps:
        step_scope = step.scope
        scope_constraint = _SCOPE_CONSTRAINTS.get(step_scope, "")
        done_when = step.done_when
        if scope_constraint and "SCOPE:" not in done_when:
            done_when = f"{scope_constraint}\n\n{done_when}"
        done_when += project_note
        expected_outputs = [
            {"artifact_type": "step_output", "description": f"{step.title} — implementation output."},
        ]

        result.append({
            "step_key": step.step_key,
            "step_type": "implementation",
            "title": step.title,
            "assigned_role": "implementer",
            "depends_on": step.depends_on,
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _scope_to_file_scope(step_scope, target_path),
            "expected_outputs": expected_outputs,
            "validation_targets": [],
            "done_when_markdown": done_when,
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
            **_build_execution_profile(
                step_type="implementation",
                scope=step_scope,
                target_paths=target_paths,
                complexity_tier=step.complexity_tier,
                budget_cap=step.budget_cap,
                allow_escalation=step.allow_escalation,
                escalation_rule=step.escalation_rule,
                expected_outputs=expected_outputs,
            ),
        })

    return result, keys


def _slugify_branch_fragment(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "requirement"


def _merge_release_mode(project_policies: list[dict[str, Any]]) -> str:
    if not project_policies:
        return "manual"
    return min(
        (str(item.get("release_mode") or "manual") for item in project_policies),
        key=lambda mode: _RELEASE_MODE_RANK.get(mode, 1),
    )


def _build_delivery_contract(
    requirement: RequirementRow,
    target_path: str | None,
    project_policies: list[dict[str, Any]],
    execution_controls: dict[str, Any],
) -> dict[str, Any]:
    required_checks: list[str] = []
    for policy in project_policies:
        for check in policy.get("required_checks") or []:
            if check not in required_checks:
                required_checks.append(str(check))

    release_mode = _merge_release_mode(project_policies)
    requires_manual_approval = any(bool(policy.get("requires_manual_approval")) for policy in project_policies)
    capability_matrix = dict(execution_controls.get("capability_matrix") or {})
    interrupt_policy = dict(execution_controls.get("interrupt_policy") or {})
    branch_name = f"ops/req-{getattr(requirement, 'id', 'x')}-{_slugify_branch_fragment(requirement.title)[:40]}"
    base_branch = "main"
    root_target = target_path or (project_policies[0]["root_path"] if project_policies else None)

    rollback_hint = (
        f"If publish must be rolled back, revert the promoted change from `{base_branch}` and archive `{branch_name}`. "
        f"Until publish happens, keep review work isolated on `{branch_name}`."
    )
    if root_target:
        rollback_hint += f"\n\nPrimary repo: `{root_target}`"

    return {
        "branch_strategy": "requirement_branch",
        "branch_name": branch_name,
        "base_branch": base_branch,
        "review_surface": "delivery_state_artifact",
        "release_mode": release_mode,
        "requires_manual_approval": requires_manual_approval,
        "required_checks": required_checks,
        "required_capabilities": ["git_push", "publish"],
        "capability_matrix": capability_matrix,
        "interrupt_policy": interrupt_policy,
        "auto_publish_allowed": (
            release_mode == "auto"
            and not requires_manual_approval
            and not required_checks
            and bool(capability_matrix.get("git_push"))
            and bool(capability_matrix.get("publish"))
            and "publish" not in set(interrupt_policy.get("operator_confirmation_actions") or [])
        ),
        "managed_projects": [
            {
                "project_key": policy["project_key"],
                "display_name": policy["display_name"],
                "root_path": policy["root_path"],
                "release_mode": policy["release_mode"],
                "capability_matrix": policy.get("capability_matrix") or {},
                "interrupt_policy": policy.get("interrupt_policy") or {},
            }
            for policy in project_policies
        ],
        "rollback_hint_markdown": rollback_hint,
        "summary_markdown": (
            f"Ship through branch `{branch_name}`, validate before promotion, surface a review-ready bundle, "
            f"and only publish when release mode `{release_mode}` allows it. "
            f"Capability gate: git_push={'yes' if capability_matrix.get('git_push') else 'no'}, "
            f"publish={'yes' if capability_matrix.get('publish') else 'no'}."
        ),
    }


def _step_required_capabilities(step: dict[str, Any]) -> list[str]:
    step_type = str(step.get("step_type") or "")
    required = ["git_read"]
    if step_type in {"research", "synthesis", "review", "test", "implementation", "bugfix"}:
        required.append("shell_access")
    if step_type in {"implementation", "bugfix"}:
        required.append("git_write")
    ordered: list[str] = []
    for key in CAPABILITY_KEYS:
        if key in required and key not in ordered:
            ordered.append(key)
    return ordered


def _is_incident_recovery_requirement(requirement: RequirementRow | None) -> bool:
    if requirement is None:
        return False
    source = str(getattr(requirement, "source", "") or "").strip().lower()
    source_ref = str(getattr(requirement, "source_ref", "") or "").strip().lower()
    title = str(getattr(requirement, "title", "") or "").strip().lower()
    if source == "bugfix_circuit_breaker":
        return True
    if "incident:" in source_ref or "infra-incident" in source_ref:
        return True
    return "incident recovery" in title or title.startswith("infra incident:")


def _operator_confirmation_actions_for_step(
    *,
    step_type: str,
    required_capabilities: list[str],
    interrupt_policy: dict[str, Any],
    execution_profile: dict[str, Any] | None,
    requirement: RequirementRow | None,
) -> tuple[list[str], str]:
    configured_actions = {
        str(item).strip()
        for item in interrupt_policy.get("operator_confirmation_actions") or []
        if str(item).strip()
    }
    if not configured_actions:
        return [], "none"

    tier = _normalize_complexity_tier((execution_profile or {}).get("complexity_tier")) or "standard"
    incident_recovery = _is_incident_recovery_requirement(requirement)
    step_type = str(step_type or "").strip()

    if incident_recovery:
        return [name for name in required_capabilities if name in configured_actions], "incident_recovery"
    if tier == "max":
        return [name for name in required_capabilities if name in configured_actions], "max_tier"
    if step_type == "publish":
        return [name for name in required_capabilities if name in configured_actions], "publish"
    return [], "expensive_branches_only"


def _step_approval_policy(step: dict[str, Any], execution_controls: dict[str, Any], requirement: RequirementRow | None = None) -> dict[str, Any]:
    required_capabilities = _step_required_capabilities(step)
    capability_matrix = dict(execution_controls.get("capability_matrix") or {})
    interrupt_policy = dict(execution_controls.get("interrupt_policy") or {})
    denied = [name for name in required_capabilities if not bool(capability_matrix.get(name))]
    execution_profile = dict(step.get("execution_profile") or {})
    confirmation, approval_scope = _operator_confirmation_actions_for_step(
        step_type=str(step.get("step_type") or ""),
        required_capabilities=required_capabilities,
        interrupt_policy=interrupt_policy,
        execution_profile=execution_profile,
        requirement=requirement,
    )
    deny_reasons = [f"{name} disabled by project capability matrix" for name in denied]
    return {
        "required_capabilities": required_capabilities,
        "capability_matrix": capability_matrix,
        "interrupt_policy": interrupt_policy,
        "approval_scope": approval_scope,
        "requires_operator_confirmation": bool(confirmation),
        "operator_confirmation_actions": confirmation,
        "deny_execution": bool(denied),
        "deny_reasons": deny_reasons,
    }


def _context_policy_for_step(step_type: str) -> dict[str, Any]:
    step_type = str(step_type or "")
    base = {
        "max_prompt_chars": 12000,
        "compact_after_chars": 9000,
        "max_artifact_body_chars": 2200,
        "max_handoff_chars": 1200,
        "stale_after_minutes": 30,
        "stale_sensitive_artifact_types": [
            "requirement_snapshot",
            "research_report",
            "synthesis_report",
            "implementation_plan",
            "validation_plan",
            "delivery_contract",
        ],
        "block_on_stale_memory": True,
    }
    if step_type in {"review", "test", "closeout"}:
        base["max_prompt_chars"] = 10000
        base["compact_after_chars"] = 7500
        base["max_artifact_body_chars"] = 1800
    if step_type in {"implementation", "bugfix"}:
        base["max_prompt_chars"] = 14000
        base["compact_after_chars"] = 11000
        base["max_artifact_body_chars"] = 2600
    if step_type in {"research", "synthesis"}:
        base["max_prompt_chars"] = 13000
        base["compact_after_chars"] = 9500
        base["max_artifact_body_chars"] = 2400
    return base


def _latest_requirement_template_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    artifact = db.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "requirement_template",
    ).order_by(ArtifactRow.id.desc()).first()
    if artifact is None or not artifact.machine_readable_payload:
        return {}
    try:
        payload = json.loads(artifact.machine_readable_payload)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _template_acceptance_checks(template_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = template_payload.get("acceptance_checks") or []
    return [dict(item) for item in raw if isinstance(item, dict)]


def _merge_acceptance_checks(default_checks: list[dict[str, Any]], template_checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for check in default_checks + template_checks:
        check_key = str(check.get("check_key") or "").strip()
        if not check_key or check_key in seen:
            continue
        seen.add(check_key)
        merged.append(dict(check))
    return merged


def _apply_template_targets_to_steps(workflow_steps: list[dict[str, Any]], template_checks: list[dict[str, Any]]) -> None:
    if not template_checks:
        return
    by_key = {str(step.get("step_key") or ""): step for step in workflow_steps}
    for check in template_checks:
        check_key = str(check.get("check_key") or "").strip()
        if not check_key:
            continue
        step_key = str(check.get("validation_step_key") or "")
        if not step_key:
            step_key = "review" if str(check.get("check_type") or "") == "manual_review" else "test"
        step = by_key.get(step_key)
        if step is None:
            continue
        targets = list(step.get("validation_targets") or [])
        if any(str(item.get("check_key") or "") == check_key for item in targets if isinstance(item, dict)):
            continue
        targets.append({
            "check_key": check_key,
            "method": str(check.get("verification_type") or ("manual_review" if str(check.get("check_type") or "") == "manual_review" else "agent_validation")),
        })
        step["validation_targets"] = targets


# ---------------------------------------------------------------------------
# Public planner entry point
# ---------------------------------------------------------------------------

def build_planner_output(db: Session, requirement: RequirementRow) -> tuple[dict, WorkflowRoleAssignments]:
    description = f"{requirement.title}\n\n{requirement.description_markdown}"
    target_path = getattr(requirement, "target_project_path", None)
    project_policies = [project_policy_to_dict(row) for row in resolve_project_policies_for_target(db, target_path, require_active=False)]
    execution_controls = aggregate_execution_controls(project_policies)
    template_payload = _latest_requirement_template_payload(db, int(requirement.id))
    template_checks = _template_acceptance_checks(template_payload)
    acceptance_contract = acceptance_contract_for_requirement(requirement)
    routing_context = resolve_requirement_routing(
        db,
        title=str(requirement.title),
        description_markdown=str(requirement.description_markdown),
        target_project_path=target_path,
    )

    suggestion = suggest_task_execution(db=db, description=description)
    implementer_agent_id = suggestion.agent_id or _first_agent_id(db)
    researcher_agent_id = _pick_agent_id(db, exclude={implementer_agent_id}, preferred=["dev_rel", "seo_strategist", "growth_lead"])
    synthesizer_agent_id = _pick_agent_id(
        db,
        exclude={implementer_agent_id, researcher_agent_id},
        preferred=["growth_lead", "dev_rel", "launch_strategist"],
    )
    reviewer_agent_id = _pick_agent_id(db, exclude={implementer_agent_id}, preferred=["dev_rel", "growth_lead"])
    tester_agent_id = _pick_agent_id(
        db,
        exclude={implementer_agent_id, reviewer_agent_id, researcher_agent_id, synthesizer_agent_id},
        preferred=["cro_optimizer", "seo_strategist", "dev_rel"],
    )

    assignments = WorkflowRoleAssignments(
        researcher_agent_id=researcher_agent_id,
        synthesizer_agent_id=synthesizer_agent_id,
        implementer_agent_id=implementer_agent_id,
        reviewer_agent_id=reviewer_agent_id,
        tester_agent_id=tester_agent_id,
    )
    delivery_contract = _build_delivery_contract(requirement, target_path, project_policies, execution_controls)

    # Mode 1: try agent full-plan first
    planning_mode = "full_plan"
    agent_steps = _plan_with_agent(description, target_path)
    if agent_steps:
        impl_steps, impl_keys = _build_steps_from_agent_plan(
            requirement,
            agent_steps,
            target_path,
        )
        detected_phases_dict: dict[str, Any] = {
            "design": any(s.step_key == "design" or s.scope == "docs" for s in agent_steps),
            "frontend": any(s.scope == "frontend" for s in agent_steps),
            "backend": any(s.scope in {"backend", "infrastructure"} for s in agent_steps),
            "test_impl": any(s.scope == "test" for s in agent_steps),
            "agent_plan_scopes": {s.step_key: s.scope for s in agent_steps},
        }
    if not agent_steps:
        # Mode 2: fall back to 4-boolean phase detection
        planning_mode = "phase_detect"
        phases = _detect_phases_with_agent(description)
        impl_steps, impl_keys = _build_implementation_steps(requirement, phases, target_path)
        detected_phases_dict = {
            "design": phases.design,
            "frontend": phases.frontend,
            "backend": phases.backend,
            "test_impl": phases.test_impl,
        }

    # Introduce explicit research + synthesis before implementation begins.
    workflow_steps = _prepend_context_steps(impl_steps, requirement, target_path)
    target_paths = _split_target_paths(target_path)

    # The last implementation step key — review depends on it
    last_impl_key = impl_keys[-1] if impl_keys else "implementation"

    workflow_steps = workflow_steps + [
        {
            "step_key": "review",
            "step_type": "review",
            "title": "Review output",
            "assigned_role": "reviewer",
            "depends_on": [last_impl_key],
            "required_artifacts": [
                {"artifact_type": "step_output", "purpose": "review_context", "required": True},
            ],
            "file_scope": _review_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "review_report", "description": "Review findings and sign-off status."},
            ],
            "validation_targets": [
                {"check_key": "review_passed", "method": "manual_review"},
            ],
            "done_when_markdown": "Review report is created and the review acceptance check is passed.",
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
            **_build_execution_profile(
                step_type="review",
                target_paths=target_paths,
                expected_outputs=[
                    {"artifact_type": "review_report", "description": "Review findings and sign-off status."},
                ],
            ),
        },
        {
            "step_key": "test",
            "step_type": "test",
            "title": "Validate output",
            "assigned_role": "tester",
            "depends_on": ["review"],
            "required_artifacts": [
                {"artifact_type": "step_output", "purpose": "test_context", "required": True},
                {"artifact_type": "review_report", "purpose": "test_context", "required": True},
            ],
            "file_scope": _review_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "test_report", "description": "Validation report for the current workflow output."},
            ],
            "validation_targets": [
                {"check_key": "validation_passed", "method": "agent_validation"},
            ],
            "done_when_markdown": "Validation completes with a test report and all validation targets passed.",
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
            **_build_execution_profile(
                step_type="test",
                target_paths=target_paths,
                expected_outputs=[
                    {"artifact_type": "test_report", "description": "Validation report for the current workflow output."},
                ],
            ),
        },
        {
            "step_key": "closeout",
            "step_type": "closeout",
            "title": "Close requirement",
            "assigned_role": "tester",
            "depends_on": ["test"],
            "required_artifacts": [
                {"artifact_type": "test_report", "purpose": "test_context", "required": True},
            ],
            "file_scope": _review_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "validation_manifest", "description": "Final closeout evidence for the requirement."},
            ],
            "validation_targets": [
                {"check_key": "validation_passed", "method": "closeout_gate"},
            ],
            "done_when_markdown": "Closeout evidence is generated and the requirement is ready to be marked done.",
            "failure_policy": {"on_failure": "block", "max_retries": 0},
            **_build_execution_profile(
                step_type="closeout",
                target_paths=target_paths,
                expected_outputs=[
                    {"artifact_type": "validation_manifest", "description": "Final closeout evidence for the requirement."},
                ],
            ),
        },
    ]

    for step in workflow_steps:
        step["file_scope"] = apply_project_policies_to_scope(
            db,
            step.get("file_scope") or {},
            target_path,
            write=step.get("step_type") == "implementation",
        )
        step["execution_profile"] = _build_execution_profile(
            step_type=str(step.get("step_type") or ""),
            scope=str(step.get("scope") or ""),
            target_paths=target_paths,
            complexity_tier=step.get("complexity_tier"),
            budget_cap=step.get("budget_cap"),
            allow_escalation=step.get("allow_escalation"),
            escalation_rule=step.get("escalation_rule"),
            expected_outputs=step.get("expected_outputs"),
        )
        step["complexity_tier"] = step["execution_profile"]["complexity_tier"]
        step["budget_cap"] = step["execution_profile"]["budget_cap"]
        step["allow_escalation"] = step["execution_profile"]["allow_escalation"]
        step["escalation_rule"] = step["execution_profile"]["escalation_rule"]
        step["approval_policy"] = _step_approval_policy(step, execution_controls, requirement)
        step["context_policy"] = _context_policy_for_step(str(step.get("step_type") or ""))

    review_check = {
        "check_key": "review_passed",
        "description": "Review step confirms the implementation output satisfies the requirement intent.",
        "check_type": "manual_review",
        "owner_role": str(acceptance_contract.get("review_owner_role") or "reviewer"),
        "success_criteria_markdown": "Reviewer confirms the implementation output is coherent and aligned with the requirement.",
    }
    validation_check = {
        "check_key": "validation_passed",
        "description": "Validation step confirms the workflow output is ready to close.",
        "check_type": "content_assertion",
        "owner_role": str(acceptance_contract.get("acceptance_owner_role") or "tester"),
        "success_criteria_markdown": "Tester validates the produced artifacts and confirms all acceptance targets are satisfied.",
    }
    default_checks = [review_check, validation_check]
    acceptance_checks = _merge_acceptance_checks(default_checks, template_checks)
    _apply_template_targets_to_steps(workflow_steps, acceptance_checks)
    manual_checks = [
        {
            "check_key": str(check["check_key"]),
            "description": str(check["description"]),
            "owner_role": str(check.get("owner_role") or "reviewer"),
            "check_type": str(check.get("check_type") or "manual_review"),
            "verification_type": "manual",
            "method": "manual_review",
            "step_key": str(check.get("validation_step_key") or "review"),
            "step_type": "review",
            "blocking": True,
            "required_artifact_type": "review_report",
        }
        for check in acceptance_checks
        if str(check.get("check_type") or "") == "manual_review"
    ]
    automated_checks = [
        {
            "check_key": str(check["check_key"]),
            "description": str(check["description"]),
            "owner_role": str(check.get("owner_role") or "tester"),
            "check_type": str(check.get("check_type") or "content_assertion"),
            "verification_type": "automated",
            "method": "repo_file_changes" if str(check.get("check_type") or "") == "repo_file_changes" else "agent_validation",
            "step_key": str(check.get("validation_step_key") or "test"),
            "step_type": "test",
            "blocking": True,
            "required_artifact_type": "test_report",
            "required_target_path": str(check.get("required_target_path") or "") or None,
        }
        for check in acceptance_checks
        if str(check.get("check_type") or "") != "manual_review"
    ]

    planner_output = {
        "schema_version": "1.8",
        "goal_summary": requirement.title,
        "goal_summary_markdown": f"## Goal\n\n{requirement.title}\n\n{requirement.description_markdown}",
        "target_project_path": target_path,
        "delivery_expectation": {
            "planning_authority": "agent_decides_change_shape",
            "change_shape": "model_determined",
            "all_target_paths": _split_target_paths(target_path),
            "harness_constraints": [
                "project_scope_only",
                "capability_matrix",
                "interrupt_policy",
                "validation_governance",
            ],
        },
        "project_policies": project_policies,
        "execution_controls": execution_controls,
        "context_governance": {
            "summary_markdown": (
                "Every workflow step now carries an explicit context budget, deterministic compaction threshold, "
                "and stale-memory verification rule before dispatch."
            ),
            "default_limits": _context_policy_for_step("implementation"),
        },
        "model_routing": {
            "summary_markdown": (
                "Each workflow step now carries planner tier annotations: complexity_tier, budget_cap, "
                "allow_escalation, and escalation_rule. Runtime selection and automatic escalation are applied by later phases."
            ),
            "supported_tiers": ["mini", "standard", "max"],
        },
        "project_intelligence": {
            "routing_mode": routing_context.get("routing_mode"),
            "readiness_status": routing_context.get("readiness_status"),
            "automation_ready": routing_context.get("automation_ready"),
            "routed_project_keys": routing_context.get("routed_project_keys") or [],
            "summary_markdown": routing_context.get("summary") or "No managed project routing summary was generated.",
            "project_scorecards": routing_context.get("project_scorecards") or [],
        },
        "requirement_template": template_payload,
        "acceptance_contract": acceptance_contract,
        "detected_phases": detected_phases_dict,
        "acceptance_checks": acceptance_checks,
        "required_roles": ["researcher", "synthesizer", "implementer", "reviewer", "tester"],
        "known_risks_markdown": "- Requirement may need iterative bugfix if validation fails.\n- File scope is constrained by target_project_path and project policy.\n- Queue priority now considers project readiness, bug pressure, and delivery friction.\n- Research and synthesis must isolate uncertainty before implementation starts.",
        "open_questions_markdown": "- No open questions generated by smart planner.",
        "global_constraints_markdown": "- Keep changes minimal and traceable.\n- Persist all key outputs as artifacts.",
        "workflow_steps": workflow_steps,
        "delivery_contract": delivery_contract,
        "validation_plan": {
            "summary_markdown": (
                "Researcher explores current state, synthesizer compresses that into an execution plan, "
                "reviewer owns the manual review gate, tester owns automated validation and closeout, "
                "and implementer owns bugfix execution when any verification fails."
            ),
            "acceptance_owner_role": str(acceptance_contract.get("acceptance_owner_role") or "tester"),
            "review_owner_role": str(acceptance_contract.get("review_owner_role") or "reviewer"),
            "acceptance_mode": str(acceptance_contract.get("acceptance_mode") or "scheduled"),
            "acceptance_trigger": str(acceptance_contract.get("acceptance_trigger") or "implementation_completed"),
            "closeout_owner_role": str(acceptance_contract.get("acceptance_owner_role") or "tester"),
            "bugfix_owner_role": "implementer",
            "gates": [str(check.get("check_key") or "") for check in acceptance_checks if str(check.get("check_key") or "").strip()],
            "manual_checks": manual_checks,
            "automated_checks": automated_checks,
            "acceptance_dispatch": {
                "dispatcher_type": "scheduled_sweep",
                "workflow_step_types": list(acceptance_contract.get("workflow_step_types") or []),
                "required_evidence_artifact_types": list(acceptance_contract.get("required_evidence_artifact_types") or []),
            },
            "bugfix_loop": {
                "trigger_step_types": ["review", "test", "bugfix"],
                "reentry_step_type": "bugfix",
                "revalidation_step_types": ["review", "test"],
                "closeout_step_type": "closeout",
                "summary_markdown": "Any failed review/test check must produce a bug report, route into bugfix, and re-run review/test before closeout.",
            },
        },
        "extensions": {
            "planning_mode": planning_mode,
                "role_assignments": {
                    "researcher_agent_id": researcher_agent_id,
                    "synthesizer_agent_id": synthesizer_agent_id,
                    "implementer_agent_id": implementer_agent_id,
                    "reviewer_agent_id": reviewer_agent_id,
                    "tester_agent_id": tester_agent_id,
            }
        },
    }
    return planner_output, assignments


# ---------------------------------------------------------------------------
# Implementation step builder
# ---------------------------------------------------------------------------

def _build_implementation_steps(
    requirement: RequirementRow,
    phases: _DetectedPhases,
    target_path: str | None,
) -> tuple[list[dict], list[str]]:
    """Return a generic fallback implementation plan when model full-plan is unavailable."""
    project_note = f"\nTarget project: {target_path}" if target_path else ""
    target_paths = _split_target_paths(target_path)
    expected_outputs = [
        {"artifact_type": "step_output", "description": "Implementation result and execution output."},
    ]
    return [
        {
            "step_key": "implementation",
            "step_type": "implementation",
            "title": "Implement planned changes",
            "assigned_role": "implementer",
            "depends_on": [],
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _project_file_scope(target_path),
            "expected_outputs": expected_outputs,
            "validation_targets": [],
            "done_when_markdown": (
                "Apply the planned changes inside the configured target projects. "
                "The model may choose code, docs, tests, or mixed edits as long as they satisfy the requirement "
                "and stay within configured project boundaries."
                f"{project_note}"
            ),
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
            **_build_execution_profile(
                step_type="implementation",
                target_paths=target_paths,
                expected_outputs=expected_outputs,
            ),
        },
    ], ["implementation"]


# ---------------------------------------------------------------------------
# Agent picker helpers
# ---------------------------------------------------------------------------

def _first_agent_id(db: Session) -> str:
    rows = ensure_agents_loaded(db)
    agent = rows[0] if rows else None
    if not agent:
        raise ValueError("No agents are available.")
    return str(agent.id)


def _pick_agent_id(db: Session, exclude: set[str], preferred: list[str]) -> str:
    ensure_agents_loaded(db)
    for preferred_id in preferred:
        if preferred_id in exclude:
            continue
        agent = db.query(AgentRow).filter(AgentRow.id == preferred_id).first()
        if agent:
            return str(agent.id)

    fallback = db.query(AgentRow).order_by(AgentRow.id.asc()).all()
    for agent in fallback:
        if str(agent.id) not in exclude:
            return str(agent.id)
    return _first_agent_id(db)
