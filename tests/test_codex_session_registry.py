from __future__ import annotations

import json
from pathlib import Path

from server.database import AgentRow, CodexSessionRow, RequirementRow, TaskRow, WorkflowRunRow, WorkflowStepRow
from server.services.codex_cli import codex_runtime_paths
from server.services.codex_session_registry import (
    build_session_key,
    find_reusable_session,
    update_session_state,
    upsert_session_launch,
    validate_codex_session_registry,
)


def _ensure_agent(db_session) -> AgentRow:
    agent = db_session.query(AgentRow).filter(AgentRow.id == "dev_rel").first()
    if agent:
        return agent
    agent = AgentRow(id="dev_rel", display_name="DevRel", goal="Ship", group="content")
    db_session.add(agent)
    db_session.flush()
    return agent


def _seed_codex_session(
    db_session,
    tmp_path: Path,
    *,
    suffix: str,
    thread_id: str,
    status: str = "active",
    metadata_override: dict | None = None,
    create_state_file: bool = True,
) -> tuple[TaskRow, Path]:
    _ensure_agent(db_session)
    requirement = RequirementRow(
        title=f"Requirement {suffix}",
        description_markdown="Fix issue",
        status="in_progress",
        priority="high",
        source="manual",
        approval_status="approved",
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="system")
    db_session.add(run)
    db_session.flush()

    project_root = (tmp_path / f"project-{suffix}").resolve()
    project_root.mkdir(parents=True, exist_ok=True)
    output_dir = (tmp_path / f"outputs-{suffix}").resolve()
    paths = codex_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if create_state_file:
        paths["state"].write_text(json.dumps({"status": "running", "pid": 4321, "thread_id": thread_id}), encoding="utf-8")
    for key in ("stdout", "stderr", "prompt", "output"):
        paths[key].write_text("", encoding="utf-8")

    task = TaskRow(
        description=f"Target project path: {project_root}",
        agent_id="dev_rel",
        status="running",
        runtime_backend="codex_cli",
        runtime_provider="codex",
        runtime_model="gpt-5-codex",
        output_path=str(paths["output"]),
    )
    db_session.add(task)
    db_session.flush()

    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement.id,
        step_key=f"step-{suffix}",
        step_type="implementation",
        title="Implementation",
        status="running",
        sequence_no=1,
        assigned_agent_id="dev_rel",
        compatibility_task_id=task.id,
    )
    db_session.add(step)

    metadata = {
        "cwd": str(project_root),
        "model": "gpt-5-codex",
        "add_dirs": [],
        "timeout_seconds": 900,
        "pid": 4321,
        "state_path": str(paths["state"]),
        "stdout_path": str(paths["stdout"]),
        "stderr_path": str(paths["stderr"]),
        "prompt_path": str(paths["prompt"]),
        "session_key": build_session_key(role_key="dev_rel", project_root=str(project_root), requirement_id=requirement.id),
        "thread_id": thread_id,
        "last_task_id": task.id,
        "json_event_count": 1,
        "resume_count": 0,
    }
    if metadata_override:
        metadata.update(metadata_override)

    upsert_session_launch(
        db_session,
        role_key="dev_rel",
        project_root=str(project_root),
        requirement_id=requirement.id,
        workflow_run_id=run.id,
        task_id=task.id,
        thread_id=thread_id,
        status=status,
        resume_count=int(metadata.get("resume_count") or 0),
        metadata=metadata,
    )
    db_session.commit()
    return task, project_root


def test_validate_codex_session_registry_reports_mismatches(db_session, tmp_path):
    healthy_task, _ = _seed_codex_session(db_session, tmp_path, suffix="healthy", thread_id="thread-ok")
    bad_task, _ = _seed_codex_session(
        db_session,
        tmp_path,
        suffix="bad",
        thread_id="thread-registry",
        metadata_override={
            "last_task_id": 9999,
            "thread_id": "thread-from-metadata",
        },
        create_state_file=False,
    )

    report = validate_codex_session_registry(db_session, project_root=tmp_path)
    session_map = {entry["current_task_id"]: entry for entry in report["sessions"]}
    assert not session_map[healthy_task.id]["issues"]
    bad_codes = {issue["code"] for issue in session_map[bad_task.id]["issues"]}
    assert "metadata_last_task_mismatch" in bad_codes
    assert "metadata_thread_mismatch" in bad_codes
    assert "state_path_missing" in bad_codes or "state_path_untracked" in bad_codes
    assert report["summary"]["total_sessions"] == 2
    assert report["summary"]["sessions_with_issues"] == 1


def test_codex_monitor_validate_registry_exposes_report(db_session, tmp_path):
    from sqlalchemy.orm import sessionmaker

    _seed_codex_session(db_session, tmp_path, suffix="monitor", thread_id="thread-monitor")
    session_factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)

    from server.services.codex_cli_monitor import CodexCLITaskMonitor

    monitor = CodexCLITaskMonitor(project_root=tmp_path, session_factory=session_factory)
    report = monitor.validate_registry()
    assert report["summary"]["total_sessions"] == 1
    assert report["sessions"][0]["issues"] == []


def test_find_reusable_session_rotates_when_usage_threshold_is_exceeded(db_session, tmp_path):
    task, project_root = _seed_codex_session(
        db_session,
        tmp_path,
        suffix="rotate",
        thread_id="thread-rotate",
        status="completed",
        metadata_override={
            "usage": {
                "input_tokens": 1_700_000,
                "cached_input_tokens": 1_200_000,
                "output_tokens": 1000,
            },
            "usage_totals": {
                "input_tokens": 1_700_000,
                "cached_input_tokens": 1_200_000,
                "output_tokens": 1000,
            },
            "cumulative_turn_count": 9,
        },
    )

    row = find_reusable_session(
        db_session,
        role_key="dev_rel",
        project_root=str(project_root),
        requirement_id=task.workflow_steps[0].requirement_id,
    )

    assert row is None
    rotated = db_session.query(CodexSessionRow).filter(CodexSessionRow.current_task_id == task.id).first()
    assert rotated is not None
    assert rotated.status == "rotated"
    metadata = json.loads(rotated.metadata_json)
    assert "rotated_reason" in metadata


def test_update_session_state_accumulates_usage_once_per_completed_task(db_session, tmp_path):
    task, project_root = _seed_codex_session(
        db_session,
        tmp_path,
        suffix="usage",
        thread_id="thread-usage",
        status="active",
    )
    requirement_id = task.workflow_steps[0].requirement_id

    update_session_state(
        db_session,
        role_key="dev_rel",
        project_root=str(project_root),
        requirement_id=requirement_id,
        current_task_id=task.id,
        status="completed",
        metadata_patch={
            "last_task_id": task.id,
            "usage": {"input_tokens": 100, "cached_input_tokens": 70, "output_tokens": 5},
            "turn_count": 2,
        },
    )
    update_session_state(
        db_session,
        role_key="dev_rel",
        project_root=str(project_root),
        requirement_id=requirement_id,
        current_task_id=task.id,
        status="completed",
        metadata_patch={
            "last_task_id": task.id,
            "usage": {"input_tokens": 100, "cached_input_tokens": 70, "output_tokens": 5},
            "turn_count": 2,
        },
    )
    db_session.commit()

    session = db_session.query(CodexSessionRow).filter(CodexSessionRow.current_task_id == task.id).first()
    assert session is not None
    payload = json.loads(session.metadata_json)
    assert payload["usage_totals"] == {
        "input_tokens": 100,
        "cached_input_tokens": 70,
        "output_tokens": 5,
    }
    assert payload["cumulative_turn_count"] == 2
