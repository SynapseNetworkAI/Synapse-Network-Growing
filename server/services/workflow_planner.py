"""Agent-driven planner for requirement-first workflows.

Uses the Copilot SDK one-shot bridge to ask an LLM to analyse the
requirement and produce a full ordered step plan, then generates dynamic
file_scope based on target_project_path.

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
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import AgentRow, RequirementRow
from server.services.execution_resolver import suggest_task_execution

logger = logging.getLogger("ops-dashboard.workflow_planner")

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


def _plan_with_agent(text: str, target_path: str | None) -> list[_AgentStep] | None:
    """Pass the requirement directly to the agent; it decides the step plan."""
    try:
        from server.services.copilot_sdk_bridge import CopilotSDKBridge

        prompt = text[:4000]
        if target_path:
            prompt = f"Target project path: {target_path}\n\n{prompt}"

        bridge = CopilotSDKBridge(cwd=config.PROJECT_ROOT)
        payload = {
            "prompt": prompt,
            "model": config.COPILOT_SDK_MODEL,
            "sessionId": "planner-fullplan-oneshot",
            "cwd": str(config.PROJECT_ROOT),
        }
        result = bridge.run_session(payload, timeout=90)
        content = result.content.strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)

        raw_steps = data.get("steps", [])
        if not raw_steps or not isinstance(raw_steps, list):
            return None

        steps: list[_AgentStep] = []
        seen_keys: set[str] = set()
        for s in raw_steps:
            key = re.sub(r"[^a-z0-9_]", "_", str(s.get("step_key", "step")).lower())
            if key in seen_keys:
                key = f"{key}_{len(steps)}"
            seen_keys.add(key)
            steps.append(_AgentStep(
                step_key=key,
                title=str(s.get("title", key)),
                scope=str(s.get("scope", "backend")).lower(),
                depends_on=[str(d) for d in s.get("depends_on", []) if str(d) in seen_keys],
                done_when=str(s.get("done_when", "Step output is produced and ready for review.")),
            ))

        logger.info("Agent full-plan produced %d steps", len(steps))
        return steps if steps else None

    except Exception:
        logger.warning("Agent full-plan failed, will fall back to phase-detect mode", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Mode 2: Phase-detect (keyword fallback — no agent call)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WorkflowRoleAssignments:
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

    for step in agent_steps:
        scope_constraint = _SCOPE_CONSTRAINTS.get(step.scope, "")
        done_when = step.done_when
        if scope_constraint and "SCOPE:" not in done_when:
            done_when = f"{scope_constraint}\n\n{done_when}"
        done_when += project_note

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
            "file_scope": _scope_to_file_scope(step.scope, target_path),
            "expected_outputs": [
                {"artifact_type": "step_output", "description": f"{step.title} — implementation output."},
            ],
            "validation_targets": [],
            "done_when_markdown": done_when,
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
        })

    return result, keys


# ---------------------------------------------------------------------------
# Public planner entry point
# ---------------------------------------------------------------------------

def build_planner_output(db: Session, requirement: RequirementRow) -> tuple[dict, WorkflowRoleAssignments]:
    description = f"{requirement.title}\n\n{requirement.description_markdown}"
    target_path = getattr(requirement, "target_project_path", None)

    suggestion = suggest_task_execution(db=db, description=description)
    implementer_agent_id = suggestion.agent_id or _first_agent_id(db)
    reviewer_agent_id = _pick_agent_id(db, exclude={implementer_agent_id}, preferred=["dev_rel", "growth_lead"])
    tester_agent_id = _pick_agent_id(
        db,
        exclude={implementer_agent_id, reviewer_agent_id},
        preferred=["cro_optimizer", "seo_strategist", "dev_rel"],
    )

    assignments = WorkflowRoleAssignments(
        implementer_agent_id=implementer_agent_id,
        reviewer_agent_id=reviewer_agent_id,
        tester_agent_id=tester_agent_id,
    )

    # Mode 1: try agent full-plan first
    planning_mode = "full_plan"
    agent_steps = _plan_with_agent(description, target_path)
    if agent_steps:
        impl_steps, impl_keys = _build_steps_from_agent_plan(requirement, agent_steps, target_path)
        detected_phases_dict: dict[str, Any] = {
            s.step_key: s.scope for s in agent_steps
        }
    else:
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

    # The last implementation step key — review depends on it
    last_impl_key = impl_keys[-1] if impl_keys else "implementation"

    workflow_steps = impl_steps + [
        {
            "step_key": "review",
            "step_type": "review",
            "title": f"Review requirement output: {requirement.title}",
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
        },
        {
            "step_key": "test",
            "step_type": "test",
            "title": f"Validate requirement output: {requirement.title}",
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
        },
        {
            "step_key": "closeout",
            "step_type": "closeout",
            "title": f"Close requirement: {requirement.title}",
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
        },
    ]

    planner_output = {
        "schema_version": "1.2",
        "goal_summary": requirement.title,
        "goal_summary_markdown": f"## Goal\n\n{requirement.title}\n\n{requirement.description_markdown}",
        "target_project_path": target_path,
        "detected_phases": detected_phases_dict,
        "acceptance_checks": [
            {
                "check_key": "review_passed",
                "description": "Review step confirms the implementation output satisfies the requirement intent.",
                "check_type": "manual_review",
                "owner_role": "reviewer",
                "success_criteria_markdown": "Reviewer confirms the implementation output is coherent and aligned with the requirement.",
            },
            {
                "check_key": "validation_passed",
                "description": "Validation step confirms the workflow output is ready to close.",
                "check_type": "content_assertion",
                "owner_role": "tester",
                "success_criteria_markdown": "Tester validates the produced artifacts and confirms all acceptance targets are satisfied.",
            },
        ],
        "required_roles": ["implementer", "reviewer", "tester"],
        "known_risks_markdown": "- Requirement may need iterative bugfix if validation fails.\n- File scope dynamically generated from target_project_path.",
        "open_questions_markdown": "- No open questions generated by smart planner.",
        "global_constraints_markdown": "- Keep changes minimal and traceable.\n- Persist all key outputs as artifacts.",
        "workflow_steps": workflow_steps,
        "validation_plan": {
            "owner_role": "tester",
            "checks": ["review_passed", "validation_passed"],
            "summary_markdown": "Tester is responsible for the final validation and closeout recommendation.",
        },
        "extensions": {
            "planning_mode": planning_mode,
            "role_assignments": {
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
    """Return (step_dicts, ordered_step_keys) for implementation sub-phases."""
    title = requirement.title
    project_note = f"\nTarget project: {target_path}" if target_path else ""

    if not phases.has_sub_steps:
        # Fallback: single implementation step (backward compatible)
        return [
            {
                "step_key": "implementation",
                "step_type": "implementation",
                "title": f"Implement requirement: {title}",
                "assigned_role": "implementer",
                "depends_on": [],
                "required_artifacts": [
                    {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                    {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
                ],
                "file_scope": _project_file_scope(target_path),
                "expected_outputs": [
                    {"artifact_type": "step_output", "description": "Implementation result and execution output."},
                ],
                "validation_targets": [],
                "done_when_markdown": f"Implementation output is produced and ready for independent review.{project_note}",
                "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
            },
        ], ["implementation"]

    # Multi-phase implementation
    steps: list[dict] = []
    keys: list[str] = []
    prev_key: str | None = None

    if phases.design:
        key = "design"
        steps.append({
            "step_key": key,
            "step_type": "implementation",
            "title": f"Design architecture: {title}",
            "assigned_role": "implementer",
            "depends_on": [prev_key] if prev_key else [],
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _project_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "step_output", "description": "Architecture design document with technical decisions."},
            ],
            "validation_targets": [],
            "done_when_markdown": f"Architecture design document is produced with schema definitions, technology choices, and component boundaries. SCOPE: Only produce design documents — do NOT write implementation code in this step.{project_note}",
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
        })
        keys.append(key)
        prev_key = key

    if phases.frontend:
        key = "frontend_impl"
        steps.append({
            "step_key": key,
            "step_type": "implementation",
            "title": f"Frontend implementation: {title}",
            "assigned_role": "implementer",
            "depends_on": [prev_key] if prev_key else [],
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _project_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "step_output", "description": "Frontend code implementation."},
            ],
            "validation_targets": [],
            "done_when_markdown": f"Frontend code is implemented in the target project. Write actual source code files, not just documentation. SCOPE: Only implement frontend/client-side code (components, hooks, SDK, styles). Do NOT implement backend/API code in this step.{project_note}",
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
        })
        keys.append(key)
        prev_key = key

    if phases.backend:
        key = "backend_impl"
        steps.append({
            "step_key": key,
            "step_type": "implementation",
            "title": f"Backend implementation: {title}",
            "assigned_role": "implementer",
            "depends_on": [prev_key] if prev_key else [],
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _project_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "step_output", "description": "Backend/API code implementation."},
            ],
            "validation_targets": [],
            "done_when_markdown": f"Backend code is implemented in the target project. Write actual source code files, not just documentation. SCOPE: Only implement backend/API/server-side code (endpoints, services, middleware, database). Do NOT implement frontend code in this step.{project_note}",
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
        })
        keys.append(key)
        prev_key = key

    if phases.test_impl:
        key = "test_impl"
        steps.append({
            "step_key": key,
            "step_type": "implementation",
            "title": f"Test implementation: {title}",
            "assigned_role": "implementer",
            "depends_on": [prev_key] if prev_key else [],
            "required_artifacts": [
                {"artifact_type": "requirement_snapshot", "purpose": "primary_spec", "required": True},
                {"artifact_type": "implementation_plan", "purpose": "implementation_context", "required": True},
            ],
            "file_scope": _project_file_scope(target_path),
            "expected_outputs": [
                {"artifact_type": "step_output", "description": "Automated test code implementation."},
            ],
            "validation_targets": [],
            "done_when_markdown": f"Automated tests are implemented and can be executed in the target project. Focus on integration tests and end-to-end tests that validate frontend-backend interaction. Unit tests should already exist from prior implementation steps.{project_note}",
            "failure_policy": {"on_failure": "bugfix", "max_retries": 0},
        })
        keys.append(key)
        prev_key = key

    return steps, keys


# ---------------------------------------------------------------------------
# Agent picker helpers
# ---------------------------------------------------------------------------

def _first_agent_id(db: Session) -> str:
    agent = db.query(AgentRow).order_by(AgentRow.id.asc()).first()
    if not agent:
        raise ValueError("No agents are available. Sync agents first.")
    return str(agent.id)


def _pick_agent_id(db: Session, exclude: set[str], preferred: list[str]) -> str:
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
