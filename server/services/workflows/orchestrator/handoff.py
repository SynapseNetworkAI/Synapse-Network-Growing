"""Workflow-orchestrator handoff helpers and compact step packet rendering."""

from __future__ import annotations

from typing import Any

from server.database import TaskRow, WorkflowStepRow


def _truncate_text(value: str, limit: int) -> str:
    """Clamp long handoff strings while preserving a readable suffix."""

    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _populate_handoff_summary(step: WorkflowStepRow, task: TaskRow) -> None:
    """Persist a concise task-output summary onto the workflow step row."""

    output = (task.output_content or "").strip()
    if not output:
        return
    summary_lines = output.split("\n")[:10]
    step.handoff_summary_markdown = "\n".join(summary_lines)


def _compact_task_description_from_snapshot(step: WorkflowStepRow, snapshot: dict[str, Any]) -> str:
    """Reduce a verbose context snapshot into a short Markdown execution packet."""

    sections = list(snapshot.get("sections") or [])
    binding_summaries = list(snapshot.get("binding_summaries") or [])
    context_parts: list[str] = []
    constraint_parts: list[str] = []
    delta_parts: list[str] = []
    done_when = ""
    step_goal = ""

    for section in sections:
        kind = str(section.get("kind") or "").strip()
        title = str(section.get("title") or "").strip()
        body = str(section.get("body") or "").strip()
        if not body:
            continue
        if kind == "base" and not step_goal:
            lines = [line.strip() for line in body.splitlines() if line.strip()]
            headline = lines[:5]
            goal_text = "\n".join(headline).strip()
            if len(lines) > 5:
                remaining = " ".join(lines[5:]).strip()
                if remaining:
                    goal_text = f"{goal_text}\n{remaining}".strip()
            step_goal = _truncate_text(goal_text, 520)
            continue
        if kind == "done_when" and not done_when:
            done_when = _truncate_text(body, 280)
            continue
        if kind in {"project", "file_hints"}:
            context_parts.append(f"### {title}\n{_truncate_text(body, 220)}")
            continue
        if kind in {"capability", "guidance"}:
            constraint_parts.append(f"### {title}\n{_truncate_text(body, 180)}")
            continue
        if kind == "handoff":
            delta_parts.append(f"### {title}\n{_truncate_text(body, 160)}")

    if binding_summaries:
        bound_inputs = []
        for item in binding_summaries[:3]:
            if str(item.get("artifact_type") or "").strip() == "requirement_snapshot":
                continue
            title = str(item.get("title") or item.get("artifact_type") or "artifact").strip()
            artifact_type = str(item.get("artifact_type") or "").strip()
            bound_inputs.append(f"- {title} ({artifact_type})")
        if bound_inputs:
            delta_parts.append("### Bound Inputs\n" + "\n".join(bound_inputs))

    parts = [
        "## Step",
        step_goal or f"[workflow_step:{step.step_type}] {step.title}",
    ]
    if done_when:
        parts.extend(["", "## Done When", done_when])
    if context_parts:
        parts.extend(["", "## Context", "\n\n".join(context_parts[:2])])
    if constraint_parts:
        parts.extend(["", "## Constraints", "\n\n".join(constraint_parts[:2])])
    if delta_parts:
        parts.extend(["", "## Delta", "\n\n".join(delta_parts[:2])])
    return _truncate_text("\n".join(parts).strip(), 1400)


def _materialize_step_context(*args: Any, **kwargs: Any) -> Any:
    """Resolve step-context materialization via the artifacts submodule lazily."""

    from server.services.workflows.orchestrator.artifacts import _materialize_step_context as _impl

    return _impl(*args, **kwargs)


__all__ = [
    "_populate_handoff_summary",
    "_materialize_step_context",
    "_compact_task_description_from_snapshot",
]
