from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from server.database import AgentRow, CodexSessionRow, RequirementRow, TaskLogRow, TaskRow, WorkflowRunRow, WorkflowStepRow, utcnow
from server.services.codex_cli import CodexAsyncExecResult, codex_runtime_paths, save_codex_state
from server.services.codex_cli_monitor import CodexCLITaskMonitor
from server.services.codex_session_registry import upsert_session_launch


def _seed_running_codex_task(db_session, tmp_path: Path) -> tuple[TaskRow, Path]:
    agent = AgentRow(id="dev_rel", display_name="DevRel", goal="Ship", group="content")
    db_session.add(agent)
    requirement = RequirementRow(
        title="Fix bug",
        description_markdown="Bug fix",
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
    output_dir = tmp_path / "roles" / "dev_rel" / "outputs" / "task-1"
    paths = codex_runtime_paths(output_dir)
    task = TaskRow(
        description="Target project path: " + str(tmp_path),
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
        step_key="research",
        step_type="research",
        title="Research",
        status="running",
        sequence_no=1,
        assigned_agent_id="dev_rel",
        compatibility_task_id=task.id,
    )
    db_session.add(step)
    db_session.commit()
    upsert_session_launch(
        db_session,
        role_key="dev_rel",
        project_root=str(tmp_path),
        requirement_id=requirement.id,
        workflow_run_id=run.id,
        task_id=task.id,
        thread_id=None,
        status="active",
        metadata={"cwd": str(tmp_path)},
    )
    db_session.commit()
    db_session.refresh(task)
    return task, output_dir


def test_codex_monitor_completes_task_and_updates_thread(db_session, tmp_path):
    task, output_dir = _seed_running_codex_task(db_session, tmp_path)
    paths = codex_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["metadata"].write_text(json.dumps({"cwd": str(tmp_path), "model": "gpt-5-codex"}), encoding="utf-8")
    paths["stdout"].write_text(
        "\n".join(
            [
                '{"type":"thread.started","thread_id":"thread-finish-1"}',
                '{"type":"item.completed","item":{"type":"agent_message","text":"done from codex"}}',
            ]
        ),
        encoding="utf-8",
    )
    save_codex_state(
        paths["state"],
        {
            "status": "completed",
            "exit_code": 0,
            "started_at": utcnow().isoformat(),
            "pid": 0,
        },
    )

    session_factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monitor = CodexCLITaskMonitor(project_root=tmp_path, session_factory=session_factory)
    monitor.sync_task(task.id)

    check_db = session_factory()
    try:
        refreshed = check_db.query(TaskRow).filter(TaskRow.id == task.id).first()
        assert refreshed is not None
        assert refreshed.status == "completed"
        assert refreshed.runtime_session_id == "thread-finish-1"
        assert "done from codex" in str(refreshed.output_content or "")
        session = check_db.query(CodexSessionRow).first()
        assert session is not None
        assert session.thread_id == "thread-finish-1"
        assert session.status == "completed"
    finally:
        check_db.close()


def test_codex_monitor_resumes_stalled_task(db_session, tmp_path):
    task, output_dir = _seed_running_codex_task(db_session, tmp_path)
    paths = codex_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["metadata"].write_text(
        json.dumps(
            {
                "cwd": str(tmp_path),
                "model": "gpt-5-codex",
                "add_dirs": [],
                "timeout_seconds": 900,
            }
        ),
        encoding="utf-8",
    )
    paths["prompt"].write_text("continue work", encoding="utf-8")
    paths["stdout"].write_text('{"type":"thread.started","thread_id":"thread-resume-1"}\n', encoding="utf-8")
    save_codex_state(
        paths["state"],
        {
            "status": "running",
            "pid": 999,
            "thread_id": "thread-resume-1",
            "started_at": "2026-04-12T00:00:00+00:00",
            "resume_count": 0,
        },
    )

    launched = CodexAsyncExecResult(
        command=["codex", "exec", "resume"],
        output_path=paths["output"],
        stdout_path=paths["stdout"],
        stderr_path=paths["stderr"],
        state_path=paths["state"],
        metadata_path=paths["metadata"],
        prompt_path=paths["prompt"],
        pid=1001,
        thread_id="thread-resume-1",
    )
    session_factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monitor = CodexCLITaskMonitor(project_root=tmp_path, session_factory=session_factory)
    old_mtime = 1
    for file_path in (paths["stdout"], paths["state"]):
        file_path.touch()
        os = __import__("os")
        os.utime(file_path, (old_mtime, old_mtime))

    with patch("server.services.codex_cli_monitor.pid_is_running", return_value=True), patch(
        "server.services.codex_cli_monitor.terminate_pid"
    ) as mock_terminate, patch(
        "server.services.codex_cli_monitor.start_codex_exec_async", return_value=launched
    ):
        monitor.sync_task(task.id)

    check_db = session_factory()
    try:
        refreshed = check_db.query(TaskRow).filter(TaskRow.id == task.id).first()
        assert refreshed is not None
        assert refreshed.status == "running"
        logs = check_db.query(TaskLogRow).filter(TaskLogRow.task_id == task.id).all()
        assert any(log.event_type == "runtime_resume_requested" for log in logs)
        session = check_db.query(CodexSessionRow).first()
        assert session is not None
        assert session.resume_count == 1
        assert session.thread_id == "thread-resume-1"
    finally:
        check_db.close()
    mock_terminate.assert_called_once()


def test_codex_monitor_resumes_unexpected_process_exit(db_session, tmp_path):
    task, output_dir = _seed_running_codex_task(db_session, tmp_path)
    paths = codex_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["metadata"].write_text(
        json.dumps(
            {
                "cwd": str(tmp_path),
                "model": "gpt-5-codex",
                "add_dirs": [],
                "timeout_seconds": 900,
                "resume_count": 0,
            }
        ),
        encoding="utf-8",
    )
    paths["prompt"].write_text("continue work", encoding="utf-8")
    paths["stdout"].write_text('{"type":"thread.started","thread_id":"thread-crash-1"}\n', encoding="utf-8")
    save_codex_state(
        paths["state"],
        {
            "status": "failed",
            "pid": 4321,
            "thread_id": "thread-crash-1",
            "started_at": utcnow().isoformat(),
            "resume_count": 0,
            "exit_code": -15,
        },
    )

    launched = CodexAsyncExecResult(
        command=["codex", "exec", "resume"],
        output_path=paths["output"],
        stdout_path=paths["stdout"],
        stderr_path=paths["stderr"],
        state_path=paths["state"],
        metadata_path=paths["metadata"],
        prompt_path=paths["prompt"],
        pid=5002,
        thread_id="thread-crash-1",
    )
    session_factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    monitor = CodexCLITaskMonitor(project_root=tmp_path, session_factory=session_factory)

    with patch("server.services.codex_cli_monitor.start_codex_exec_async", return_value=launched):
        monitor.sync_task(task.id)

    check_db = session_factory()
    try:
        refreshed = check_db.query(TaskRow).filter(TaskRow.id == task.id).first()
        assert refreshed is not None
        assert refreshed.status == "running"
        logs = check_db.query(TaskLogRow).filter(TaskLogRow.task_id == task.id).all()
        assert any(log.event_type == "runtime_resume_requested" for log in logs)
        session = check_db.query(CodexSessionRow).first()
        assert session is not None
        assert session.resume_count == 1
        assert session.thread_id == "thread-crash-1"
        state = json.loads(paths["state"].read_text(encoding="utf-8"))
        assert state["status"] == "running"
        assert state["resume_count"] == 1
    finally:
        check_db.close()
