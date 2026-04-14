"""Step-building helpers for workflow planning."""

from __future__ import annotations

from typing import Any

from server.database import RequirementRow
from server.services.workflows.planner_profiles import _build_execution_profile


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


def _base_file_scope() -> dict[str, list[str]]:
    """Always-included read/write scope for docs and shared assets."""

    return {
        "allowed_read_globs": ["roles/**", "docs/**", "campaigns/**", "demos/**", "README.md"],
        "allowed_write_globs": ["roles/**", "docs/**", "campaigns/**", "demos/**", "README.md"],
        "blocked_globs": [".git/**", "node_modules/**"],
    }


def _project_file_scope(target_project_path: str | None, *, write: bool = True) -> dict[str, list[str]]:
    """Extend the base scope with the target project path."""

    scope = _base_file_scope()
    if not target_project_path:
        return scope
    p = target_project_path.rstrip("/")
    scope["allowed_read_globs"].append(f"{p}/**")
    if write:
        scope["allowed_write_globs"].append(f"{p}/**")
    return scope


def _review_file_scope(target_project_path: str | None) -> dict[str, list[str]]:
    """Return read-mostly scope for review-like steps."""

    return _project_file_scope(target_project_path, write=False)


def _build_research_and_plan_steps(requirement: RequirementRow, target_path: str | None) -> list[dict[str, Any]]:
    """Build the fixed research and plan steps prepended by the harness."""

    project_note = f"\nTarget project: {target_path}" if target_path else ""
    target_paths = _split_target_paths(target_path)
    research_outputs = [
        {"artifact_type": "research_report", "description": "Research findings, constraints, existing code paths, and risks."},
    ]
    plan_outputs = [
        {"artifact_type": "plan_brief", "description": "Execution strategy, change plan, and validation outline."},
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
                {"artifact_type": "requirement_brief", "purpose": "bootstrap_context", "required": False},
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
            "step_key": "plan",
            "step_type": "plan",
            "title": "Plan implementation",
            "assigned_role": "synthesizer",
            "depends_on": ["research"],
            "required_artifacts": [
                {"artifact_type": "research_report", "purpose": "research_context", "required": True},
                {"artifact_type": "requirement_brief", "purpose": "bootstrap_context", "required": False},
            ],
            "file_scope": _review_file_scope(target_path),
            "expected_outputs": plan_outputs,
            "validation_targets": [],
            "done_when_markdown": (
                "Plan output turns research findings into a concrete execution plan with files, sequencing, and validation intent. "
                "Do not modify production code in this step."
                f"{project_note}"
            ),
            "failure_policy": {"on_failure": "requirement_revision", "max_retries": 0},
            **_build_execution_profile(
                step_type="plan",
                target_paths=target_paths,
                expected_outputs=plan_outputs,
            ),
        },
    ]


def _prepend_context_steps(workflow_steps: list[dict[str, Any]], requirement: RequirementRow, target_path: str | None) -> list[dict[str, Any]]:
    """Prepend research/plan steps and link orphan steps to the plan output."""

    context_steps = _build_research_and_plan_steps(requirement, target_path)
    for step in workflow_steps:
        key = str(step.get("step_key") or "")
        if key in {"research", "plan"}:
            continue
        depends_on = list(step.get("depends_on") or [])
        if not depends_on:
            step["depends_on"] = ["plan"]
    return context_steps + workflow_steps


def _scope_to_file_scope(scope: str, target_path: str | None) -> dict[str, list[str]]:
    """Map a planner scope label to a concrete file_scope contract."""

    if scope in ("infrastructure", "backend", "frontend", "test"):
        return _project_file_scope(target_path, write=True)
    return _base_file_scope()


__all__ = [
    "_base_file_scope",
    "_build_research_and_plan_steps",
    "_prepend_context_steps",
    "_project_file_scope",
    "_review_file_scope",
    "_scope_to_file_scope",
]
