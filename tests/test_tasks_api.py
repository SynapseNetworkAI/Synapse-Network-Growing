from __future__ import annotations

"""Tests for /api/tasks endpoints."""
import json
import subprocess
from unittest.mock import patch, MagicMock
from typing import Any, cast
from pathlib import Path
from sqlalchemy.orm import sessionmaker

from server.config import ORCHESTRATION_BACKEND
from server.database import AgentRow, ArtifactRow, RequirementRow, TaskRow, WorkflowRunRow, WorkflowStepRow
from server.services.runtime.copilot_sdk_state import seconds_since_timestamp
from server.services.runtime.task_runtime import TaskExecutionResult
from server.services.workflows.orchestrator import capture_task_file_change_baseline, _snapshot_file_changes


def _runtime_result(
    *,
    text: str = "",
    error: str | None = None,
    execution_time_ms: int = 1,
    runtime_backend: str = "legacy",
    runtime_provider: str = "",
    runtime_session_id: str | None = None,
    runtime_selected_agent: str | None = None,
    events=None,
    deferred: bool = False,
    files=None,
    model: str = "",
    tokens_used: int = 0,
):
    return TaskExecutionResult(
        text=text,
        files=files or [],
        error=error,
        execution_time_ms=execution_time_ms,
        model=model,
        tokens_used=tokens_used,
        runtime_backend=runtime_backend,
        runtime_provider=runtime_provider,
        runtime_session_id=runtime_session_id,
        runtime_selected_agent=runtime_selected_agent,
        events=events or [],
        deferred=deferred,
    )


def test_create_task(synced_client):
    resp = synced_client.post("/api/tasks", json={
        "description": "Write MCP tutorial",
        "agent_id": "dev_rel",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["description"] == "Write MCP tutorial"
    assert data["agent_id"] == "dev_rel"
    assert data["status"] == "pending"
    assert data["requires_approval"] is False
    assert data["priority"] == "normal"


def test_create_task_invalid_agent(synced_client):
    resp = synced_client.post("/api/tasks", json={
        "description": "bad task",
        "agent_id": "nonexistent",
    })
    assert resp.status_code == 400


def test_create_task_invalid_priority(synced_client):
    resp = synced_client.post("/api/tasks", json={
        "description": "bad priority",
        "agent_id": "dev_rel",
        "priority": "ultra",
    })
    assert resp.status_code == 400


def test_seconds_since_timestamp_accepts_naive_iso_datetime():
    age = seconds_since_timestamp("2026-04-11T22:57:25.123456")
    assert age is not None
    assert age >= 0


def test_suggest_execution_returns_best_agent_and_skill(synced_client):
    resp = synced_client.post("/api/tasks/suggest-execution", json={
        "description": "Create a detailed analytics tracking plan with UTM taxonomy, event tracking, and attribution setup",
    })

    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_id"] == "cro_optimizer"
    assert data["skill_name"] == "analytics-tracking"
    assert data["requires_confirmation"] is False


def test_create_task_auto_selects_agent_and_skill(synced_client):
    resp = synced_client.post("/api/tasks", json={
        "description": "Create a detailed analytics tracking plan with UTM taxonomy, event tracking, and attribution setup",
        "confirm_auto_selection": True,
    })

    assert resp.status_code == 201
    data = resp.json()
    assert data["agent_id"] == "cro_optimizer"
    assert data["skill_name"] == "analytics-tracking"
    assert data["status"] == "pending"


def test_create_task_requires_confirmation_for_low_confidence_auto_selection(synced_client):
    resp = synced_client.post("/api/tasks", json={
        "description": "Help me with something important later",
    })

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "suggestion" in detail
    assert detail["suggestion"]["requires_confirmation"] is True


def test_list_tasks(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "growth_lead"})
    resp = synced_client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2


def test_list_tasks_orders_newest_first(synced_client):
    first = synced_client.post("/api/tasks", json={"description": "older", "agent_id": "dev_rel"}).json()
    second = synced_client.post("/api/tasks", json={"description": "newer", "agent_id": "growth_lead"}).json()

    resp = synced_client.get("/api/tasks")

    assert resp.status_code == 200
    assert [task["id"] for task in resp.json()["items"]] == [second["id"], first["id"]]


def test_list_tasks_filter_by_status(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    resp = synced_client.get("/api/tasks?status=pending")
    assert len(resp.json()["items"]) == 1
    resp = synced_client.get("/api/tasks?status=completed")
    assert len(resp.json()["items"]) == 0


def test_list_tasks_filter_by_agent(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "growth_lead"})
    resp = synced_client.get("/api/tasks?agent_id=dev_rel")
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["agent_id"] == "dev_rel"


def test_list_tasks_returns_derived_project_and_group(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    resp = synced_client.get("/api/tasks")
    assert resp.status_code == 200
    task = resp.json()["items"][0]
    assert task["project_id"] == "Synapse-Network-Growing"
    assert task["project_label"] == "Synapse-Network-Growing"
    assert task["agent_group"] == "content"


def test_task_project_and_group_are_persisted_snapshot(synced_client, db_session):
    create = synced_client.post("/api/tasks", json={"description": "persist me", "agent_id": "dev_rel"})
    task_id = create.json()["id"]

    agent = db_session.query(AgentRow).filter(AgentRow.id == "dev_rel").first()
    agent.group = "optimization"
    db_session.commit()

    resp = synced_client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_group"] == "content"
    assert data["project_id"] == "Synapse-Network-Growing"


def test_list_tasks_filter_by_agent_group(synced_client):
    synced_client.post("/api/tasks", json={"description": "seo", "agent_id": "seo_strategist"})
    synced_client.post("/api/tasks", json={"description": "content", "agent_id": "content_writer"})
    resp = synced_client.get("/api/tasks?agent_group=optimization")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["agent_id"] == "seo_strategist"


def test_list_tasks_filter_by_project(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    resp = synced_client.get("/api/tasks?project_id=Synapse-Network-Growing")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


def test_list_tasks_only_anomalies(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    failed = synced_client.post("/api/tasks", json={
        "description": "t2", "agent_id": "seo_strategist", "skill_name": "seo-audit",
    }).json()
    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{failed['id']}/run")
    resp = synced_client.get("/api/tasks?only_anomalies=true")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    assert resp.json()["items"][0]["status"] == "running"


def test_get_task(synced_client):
    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    resp = synced_client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id


def test_get_task_not_found(synced_client):
    resp = synced_client.get("/api/tasks/999")
    assert resp.status_code == 404


def test_get_task_output_file_returns_preview(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    output_dir = tmp_path / "task-outputs"
    output_dir.mkdir()
    output_file = output_dir / "output.md"
    output_file.write_text("# Result\n\nhello", encoding="utf-8")

    row = db_session.query(TaskRow).filter(TaskRow.id == task_id).first()
    row.output_path = str(output_file)
    db_session.commit()

    resp = synced_client.get(f"/api/tasks/{task_id}/output-files/output.md")
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_name"] == "output.md"
    assert "hello" in data["content"]
    assert data["content_type"] == "text/markdown"


def test_get_task_output_file_filters_codex_stderr_noise(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    output_dir = tmp_path / "task-outputs"
    output_dir.mkdir()
    stderr_file = output_dir / "codex.stderr.log"
    stderr_file.write_text(
        "\n".join(
            [
                "WARN codex_protocol::openai_models: Model personality requested but model_messages is missing",
                "WARN codex_core::plugins::manifest: ignoring interface.defaultPrompt: prompt must be at most 128 characters",
                "Traceback (most recent call last):",
                "RuntimeError: gateway failure",
            ]
        ),
        encoding="utf-8",
    )

    row = db_session.query(TaskRow).filter(TaskRow.id == task_id).first()
    row.output_path = str(output_dir / "output.md")
    db_session.commit()

    resp = synced_client.get(f"/api/tasks/{task_id}/output-files/codex.stderr.log")
    assert resp.status_code == 200
    data = resp.json()
    assert "gateway failure" in data["content"]
    assert "defaultPrompt" not in data["content"]
    assert "model_messages is missing" not in data["content"]


def test_get_task_file_changes_requires_snapshot(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    output_dir = tmp_path / "task-outputs"
    output_dir.mkdir()
    row = db_session.query(TaskRow).filter(TaskRow.id == task_id).first()
    row.output_path = str(output_dir / "output.md")
    db_session.commit()

    resp = synced_client.get(f"/api/tasks/{task_id}/file-changes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed_files"] == []
    assert data["source"] == "snapshot"
    assert "not available yet" in data["error"]


def test_get_task_file_changes_hides_legacy_snapshot_diff(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    output_dir = tmp_path / "task-outputs"
    output_dir.mkdir()
    (output_dir / "file-changes.json").write_text(
        json.dumps(
            {
                "changed_files": [
                    {
                        "filename": "dashboard/src/App.tsx",
                        "additions": 65,
                        "deletions": 14,
                        "patch": "@@",
                    }
                ],
                "source": "snapshot",
                "captured_at": "2026-04-12T14:18:54Z",
            }
        ),
        encoding="utf-8",
    )
    row = db_session.query(TaskRow).filter(TaskRow.id == task_id).first()
    row.output_path = str(output_dir / "output.md")
    db_session.commit()

    resp = synced_client.get(f"/api/tasks/{task_id}/file-changes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["changed_files"] == []
    assert data["legacy_snapshot"] is True
    assert "before task-scoped diff baselines" in data["change_warning"]


def test_task_file_changes_include_dirty_file_when_content_hash_changes(synced_client, db_session, tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True, capture_output=True, text=True)
    tracked_file = repo_dir / "tracked.txt"
    tracked_file.write_text("line1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=repo_dir, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True, capture_output=True, text=True)

    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    output_dir = tmp_path / "task-outputs"
    output_dir.mkdir()
    row = db_session.query(TaskRow).filter(TaskRow.id == task_id).first()
    row.output_path = str(output_dir / "output.md")

    requirement = RequirementRow(
        title="Dirty file hash test",
        description_markdown="Bug fix",
        status="in_progress",
        priority="high",
        source="manual",
        approval_status="approved",
        target_project_path=str(repo_dir),
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="system")
    db_session.add(run)
    db_session.flush()
    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement.id,
        step_key="implementation",
        step_type="implementation",
        title="Implementation",
        status="running",
        sequence_no=1,
        assigned_agent_id="dev_rel",
        compatibility_task_id=task_id,
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(row)

    tracked_file.write_text("line1\npre-task dirty\n", encoding="utf-8")
    capture_task_file_change_baseline(db_session, row, requirement=requirement, step=step)
    tracked_file.write_text("line1\npre-task dirty\ntask change\n", encoding="utf-8")

    _snapshot_file_changes(db_session, row, requirement, step=step)

    resp = synced_client.get(f"/api/tasks/{task_id}/file-changes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["legacy_snapshot"] is False
    assert any(item["filename"] == "tracked.txt" for item in data["changed_files"])


def test_run_task_no_approval(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "auto task",
        "agent_id": "dev_rel",
        "skill_name": "content-strategy",
    })
    task_id = create.json()["id"]
    with patch("server.services.runtime.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["skill_name"] == "content-strategy"
    assert data["runtime_backend"] == ORCHESTRATION_BACKEND


def test_run_task_with_approval(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "publish tweet",
        "agent_id": "growth_lead",
        "requires_approval": True,
        "skill_name": "social-content",
    })
    task_id = create.json()["id"]
    with patch("server.services.runtime.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["runtime_backend"] == ORCHESTRATION_BACKEND


def test_run_task_already_running(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "t", "agent_id": "dev_rel", "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]
    with patch("server.services.runtime.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")
    resp = synced_client.post(f"/api/tasks/{task_id}/run?skill=seo-audit")
    assert resp.status_code == 400


def test_task_logs(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "t", "agent_id": "dev_rel", "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]
    with patch("server.services.runtime.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")
    resp = synced_client.get(f"/api/tasks/{task_id}/logs")
    assert resp.status_code == 200
    logs = resp.json()
    event_types = [l["event_type"] for l in logs]
    assert "created" in event_types
    assert "started" in event_types


def test_retry_task_run_now_creates_new_running_task(synced_client):
    from server.services.runtime.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "retry me",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
    with patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(error="boom")
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "seo-audit")

    with patch("server.services.runtime.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/retry?mode=run_now")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["retry_of_task_id"] == task_id
    assert data["attempt_no"] == 2
    mock_dispatch.assert_called_once()


def test_retry_task_edit_first_creates_pending_task(synced_client):
    from server.services.runtime.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "retry me later",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
    with patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(error="boom")
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "seo-audit")

    resp = synced_client.post(f"/api/tasks/{task_id}/retry?mode=edit_first")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["retry_of_task_id"] == task_id
    assert data["attempt_no"] == 2


def test_get_task_history_returns_retry_chain(synced_client):
    from server.services.runtime.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "history me",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
    with patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(error="boom")
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "seo-audit")

    retried = synced_client.post(f"/api/tasks/{task_id}/retry?mode=edit_first").json()
    history = synced_client.get(f"/api/tasks/{retried['id']}/history")

    assert history.status_code == 200
    data = history.json()
    assert [item["attempt_no"] for item in data] == [1, 2]
    assert data[0]["task_id"] == task_id
    assert data[1]["retry_of_task_id"] == task_id
    assert data[1]["project_id"] == "Synapse-Network-Growing"


def test_bulk_retry_creates_new_retry_tasks(synced_client):
    from server.services.runtime.task_runner import _run_task_sync

    created_ids = []
    for desc in ("retry one", "retry two"):
        created = synced_client.post("/api/tasks", json={
            "description": desc,
            "agent_id": "seo_strategist",
            "skill_name": "seo-audit",
        })
        task_id = created.json()["id"]
        created_ids.append(task_id)

        with patch("server.services.runtime.task_runner.dispatch"):
            synced_client.post(f"/api/tasks/{task_id}/run")

        persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
        with patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
            mock_runtime = MagicMock()
            mock_runtime.execute.return_value = _runtime_result(error="boom")
            mock_runtime_factory.return_value = mock_runtime
            _run_task_sync(task_id, persona, "seo-audit")

    resp = synced_client.post("/api/tasks/bulk-retry", json={"task_ids": created_ids, "mode": "edit_first"})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["retry_of_task_id"] for item in data] == created_ids
    assert [item["attempt_no"] for item in data] == [2, 2]
    assert all(item["status"] == "pending" for item in data)


def test_bulk_retry_rejects_non_retryable_tasks(synced_client):
    create = synced_client.post("/api/tasks", json={"description": "not failed", "agent_id": "dev_rel"})
    task_id = create.json()["id"]

    resp = synced_client.post("/api/tasks/bulk-retry", json={"task_ids": [task_id], "mode": "run_now"})
    assert resp.status_code == 400


def test_retry_task_invalid_status(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "not failed yet",
        "agent_id": "dev_rel",
    })
    task_id = create.json()["id"]
    resp = synced_client.post(f"/api/tasks/{task_id}/retry?mode=run_now")
    assert resp.status_code == 400


def test_agent_task_count_after_tasks(synced_client):
    """Task count increments; run_task now goes async so completed_count only updates after runner finishes."""
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t3", "agent_id": "dev_rel"})

    agent = synced_client.get("/api/agents/dev_rel").json()
    assert agent["task_count"] == 3


def test_task_runner_persists_runtime_metadata_and_events(synced_client):
    from server.services.runtime.task_runner import _run_task_sync
    from server.services.runtime.task_runtime import RuntimeEvent

    create = synced_client.post("/api/tasks", json={
        "description": "Use copilot runtime",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    with patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            text="# Copilot output",
            execution_time_ms=42,
            runtime_backend="copilot_sdk",
            runtime_provider="copilot",
            model="gpt-4o",
            runtime_session_id="session-123",
            runtime_selected_agent="editor",
            events=[
                RuntimeEvent(event_type="runtime_started", detail="backend=copilot_sdk"),
                RuntimeEvent(event_type="subagent_selected", detail="editor"),
            ],
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "content_writer", "display_name": "Writer", "goal": "", "body": ""}, "copywriting")

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "completed"
    assert task["runtime_backend"] == "copilot_sdk"
    assert task["runtime_provider"] == "copilot"
    assert task["runtime_model"] == "gpt-4o"
    assert task["tokens_used"] == 0
    assert task["budget_cost_points"] >= 16
    assert task["runtime_session_id"] == "session-123"
    assert task["runtime_selected_agent"] == "editor"

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_submitted" in event_types
    assert "runtime_selection" in event_types
    assert "runtime_started" in event_types
    assert "subagent_selected" in event_types


def test_task_runner_uses_execution_profile_runtime_selection(synced_client, db_session):
    from server.services.runtime.task_runner import _run_task_sync, PROJECT_ROOT

    create = synced_client.post("/api/tasks", json={
        "description": "Route this mini task",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    task = db_session.query(TaskRow).filter(TaskRow.id == task_id).first()
    assert task is not None
    requirement = RequirementRow(title="Tier routing", description_markdown="Route runtime by execution profile.")
    db_session.add(requirement)
    db_session.flush()
    workflow_run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="user")
    db_session.add(workflow_run)
    db_session.flush()
    db_session.add(
        WorkflowStepRow(
            workflow_run_id=workflow_run.id,
            requirement_id=requirement.id,
            step_key="research",
            step_type="research",
            title="Research context",
            status="running",
            sequence_no=10,
            compatibility_task_id=task_id,
            done_when_markdown="done",
            context_scope="step_private",
            context_policy_json="{}",
            execution_profile_json='{"complexity_tier":"mini","budget_cap":{"max_runtime_seconds":600},"allow_escalation":true,"escalation_rule":{"next_tier":"standard"}}',
            file_scope_json="{}",
            validation_targets_json="[]",
            failure_policy_json="{}",
            approval_policy_json="{}",
        )
    )
    db_session.commit()

    with patch("server.services.runtime.task_runner.resolve_runtime_selection") as mock_selection, patch(
        "server.services.runtime.task_runner.get_task_runtime"
    ) as mock_runtime_factory:
        mock_selection.return_value.backend = "openai_responses"
        mock_selection.return_value.provider = "openai"
        mock_selection.return_value.model = "gpt-5-mini"
        mock_selection.return_value.complexity_tier = "mini"
        mock_selection.return_value.reason = "tier=mini"
        mock_selection.return_value.timeout_seconds = 600
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            text="done",
            execution_time_ms=9,
            runtime_backend="openai_responses",
            runtime_provider="openai",
            model="gpt-5-mini",
            tokens_used=9000,
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "content_writer", "display_name": "Writer", "goal": "", "body": ""}, "copywriting")

    mock_runtime_factory.assert_called_with(PROJECT_ROOT, backend="openai_responses")
    selection_arg = mock_runtime.execute.call_args.kwargs["runtime_selection"]
    assert selection_arg.model == "gpt-5-mini"
    assert selection_arg.complexity_tier == "mini"

    payload = synced_client.get(f"/api/tasks/{task_id}").json()
    assert payload["runtime_backend"] == "openai_responses"
    assert payload["runtime_provider"] == "openai"
    assert payload["runtime_model"] == "gpt-5-mini"
    assert payload["tokens_used"] == 9000
    assert payload["budget_cost_points"] >= 8


def test_task_runner_uses_deterministic_delivery_executor_for_validation_clone_research(synced_client, db_session, tmp_path):
    from server.services.runtime.task_runner import _run_task_sync

    repo_root = tmp_path / "validation-repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "README.md").write_text("# Validation Clone\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    create = synced_client.post("/api/tasks", json={
        "description": "Run deterministic research",
        "agent_id": "dev_rel",
        "skill_name": "__direct_execution__",
    })
    task_id = create.json()["id"]

    requirement = RequirementRow(
        title="Validate unattended auto-start branch delivery on validation clone",
        description_markdown=(
            "Use a requirement branch, commit, push, draft PR, compare URL, and write `docs/auto-validation/req-test.md` "
            "inside the validation clone."
        ),
        target_project_path=str(repo_root / "sng-delivery-validation"),
    )
    db_session.add(requirement)
    db_session.flush()
    workflow_run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="user")
    db_session.add(workflow_run)
    db_session.flush()
    db_session.add(
        WorkflowStepRow(
            workflow_run_id=workflow_run.id,
            requirement_id=requirement.id,
            step_key="research",
            step_type="research",
            title="Research preflight",
            status="running",
            sequence_no=10,
            assigned_agent_id="dev_rel",
            compatibility_task_id=task_id,
            done_when_markdown="done",
            context_scope="step_private",
            context_policy_json="{}",
            execution_profile_json='{"complexity_tier":"mini","budget_cap":{"max_runtime_seconds":600}}',
            file_scope_json="{}",
            validation_targets_json="[]",
            failure_policy_json="{}",
            approval_policy_json="{}",
        )
    )
    db_session.commit()

    # align target path with validation clone marker
    requirement.target_project_path = str(repo_root / "sng-delivery-validation")
    Path(requirement.target_project_path).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=requirement.target_project_path, check=True, capture_output=True, text=True)
    (Path(requirement.target_project_path) / "README.md").write_text("# Validation Clone\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=requirement.target_project_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=requirement.target_project_path, check=True, capture_output=True, text=True)
    db_session.commit()

    with patch("server.services.workflows.orchestrator.sync_workflow_for_task"), patch(
        "server.services.runtime.task_runner.PROJECT_ROOT", tmp_path
    ), patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        _run_task_sync(task_id, {"role": "dev_rel", "display_name": "DevRel", "goal": "", "body": ""}, "__direct_execution__")

    mock_runtime_factory.assert_not_called()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "completed"
    assert "Branch Delivery Preflight" in task["output_content"]


def test_task_runner_uses_deterministic_delivery_executor_for_validation_clone_implementation(synced_client, db_session, tmp_path):
    from server.services.runtime.task_runner import _run_task_sync

    repo_root = tmp_path / "sng-delivery-validation"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "README.md").write_text("# Validation Clone\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    create = synced_client.post("/api/tasks", json={
        "description": "Run deterministic implementation",
        "agent_id": "dev_rel",
        "skill_name": "__direct_execution__",
    })
    task_id = create.json()["id"]

    requirement = RequirementRow(
        title="Validate unattended auto-start branch delivery on validation clone",
        description_markdown=(
            "Use a requirement branch, commit, push, draft PR, compare URL, and write `docs/auto-validation/req-test.md` "
            "inside the validation clone."
        ),
        target_project_path=str(repo_root),
    )
    db_session.add(requirement)
    db_session.flush()
    workflow_run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="user")
    db_session.add(workflow_run)
    db_session.flush()
    db_session.add(
        WorkflowStepRow(
            workflow_run_id=workflow_run.id,
            requirement_id=requirement.id,
            step_key="implementation",
            step_type="implementation",
            title="Write delivery note",
            status="running",
            sequence_no=20,
            assigned_agent_id="dev_rel",
            compatibility_task_id=task_id,
            done_when_markdown="done",
            context_scope="step_private",
            context_policy_json="{}",
            execution_profile_json='{"complexity_tier":"mini","budget_cap":{"max_runtime_seconds":600}}',
            file_scope_json="{}",
            validation_targets_json="[]",
            failure_policy_json="{}",
            approval_policy_json="{}",
        )
    )
    db_session.commit()

    with patch("server.services.workflows.orchestrator.sync_workflow_for_task"), patch(
        "server.services.runtime.task_runner.PROJECT_ROOT", tmp_path
    ), patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        _run_task_sync(task_id, {"role": "dev_rel", "display_name": "DevRel", "goal": "", "body": ""}, "__direct_execution__")

    mock_runtime_factory.assert_not_called()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "completed"
    target_file = repo_root / "docs/auto-validation/req-test.md"
    assert target_file.exists()
    assert "requirement_branch" in target_file.read_text(encoding="utf-8")


def test_task_runner_prepares_requirement_branch_before_mutating_runtime_execution(synced_client, db_session, tmp_path):
    from server.services.runtime.task_runner import _run_task_sync

    repo_root = tmp_path / "sng-delivery-validation-next"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "README.md").write_text("# Validation Clone\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "checkout", "-b", "ops/req-old"], cwd=repo_root, check=True, capture_output=True, text=True)

    create = synced_client.post("/api/tasks", json={
        "description": "Run mutating implementation",
        "agent_id": "dev_rel",
        "skill_name": "__direct_execution__",
    })
    task_id = create.json()["id"]

    requirement = RequirementRow(
        title="Bug Fix: timeout constant",
        description_markdown="Increase the timeout constant in `dashboard/src/api.ts` and validate the behavior.",
        source="bug_intake",
        source_ref="bug-intake:test",
        target_project_path=str(repo_root),
    )
    db_session.add(requirement)
    db_session.flush()
    workflow_run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="user")
    db_session.add(workflow_run)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            workflow_run_id=workflow_run.id,
            artifact_type="delivery_contract",
            content_summary="delivery contract",
            human_readable_body="delivery contract",
            machine_readable_payload=json.dumps(
                {
                    "branch_strategy": "requirement_branch",
                    "branch_name": "ops/req-test-timeout",
                    "base_branch": "main",
                    "remote_name": "origin",
                    "capability_matrix": {"git_write": True, "git_push": False},
                    "managed_projects": [{"root_path": str(repo_root)}],
                }
            ),
        )
    )
    db_session.add(
        WorkflowStepRow(
            workflow_run_id=workflow_run.id,
            requirement_id=requirement.id,
            step_key="implementation",
            step_type="implementation",
            title="Bump timeout",
            status="running",
            sequence_no=20,
            assigned_agent_id="dev_rel",
            compatibility_task_id=task_id,
            done_when_markdown="done",
            context_scope="step_private",
            context_policy_json="{}",
            execution_profile_json='{"complexity_tier":"mini","budget_cap":{"max_runtime_seconds":600}}',
            file_scope_json="{}",
            validation_targets_json="[]",
            failure_policy_json="{}",
            approval_policy_json="{}",
        )
    )
    db_session.commit()

    with patch("server.services.workflows.orchestrator.sync_workflow_for_task"), patch(
        "server.services.runtime.task_runner.PROJECT_ROOT", tmp_path
    ), patch("server.services.runtime.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            text="implemented",
            execution_time_ms=25,
            runtime_backend="openai_responses",
            runtime_provider="openai",
            model="gpt-5-mini",
            tokens_used=120,
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "dev_rel", "display_name": "DevRel", "goal": "", "body": ""}, "__direct_execution__")

    assert (
        subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == "ops/req-test-timeout"
    )
    payload = synced_client.get(f"/api/tasks/{task_id}").json()
    assert payload["status"] == "completed"
    assert any(log["event_type"] == "delivery_branch_prepared" for log in synced_client.get(f"/api/tasks/{task_id}/logs").json())


def test_deterministic_delivery_review_and_test_use_review_surface_metadata(db_session, tmp_path):
    from server.services.runtime.task_runner import _deterministic_delivery_validation_result

    repo_root = tmp_path / "sng-delivery-validation"
    repo_root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_root, check=True, capture_output=True, text=True)
    (repo_root / "README.md").write_text("# Validation Clone\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_root, check=True, capture_output=True, text=True)

    requirement = RequirementRow(
        title="Validate unattended auto-start branch delivery on validation clone",
        description_markdown="Create `docs/auto-validation/req-test.md`, commit, push, draft PR, compare URL on validation clone.",
        target_project_path=str(repo_root),
    )
    db_session.add(
        AgentRow(
            id="dev_rel",
            display_name="DevRel",
            goal="",
            group="growth",
            persona_path="roles/dev_rel/prompts/persona.md",
            skills="[]",
        )
    )
    db_session.add(requirement)
    db_session.flush()
    workflow_run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="user")
    db_session.add(workflow_run)
    db_session.flush()
    task = TaskRow(description="deterministic review", agent_id="dev_rel", skill_name="__direct_execution__", status="running")
    db_session.add(task)
    db_session.flush()
    step = WorkflowStepRow(
        workflow_run_id=workflow_run.id,
        requirement_id=requirement.id,
        step_key="review",
        step_type="review",
        title="Review output",
        status="running",
        sequence_no=40,
        assigned_agent_id="dev_rel",
        compatibility_task_id=task.id,
        done_when_markdown="done",
        context_scope="step_private",
        context_policy_json="{}",
        execution_profile_json='{"complexity_tier":"mini"}',
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        approval_policy_json="{}",
    )
    db_session.add(step)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            workflow_run_id=workflow_run.id,
            artifact_type="delivery_contract",
            content_summary="delivery contract",
            human_readable_body="delivery contract",
            machine_readable_payload=json.dumps({
                "branch_name": "ops/req-test",
                "base_branch": "main",
            }),
        )
    )
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            workflow_run_id=workflow_run.id,
            artifact_type="review_pr_sync",
            content_summary="review pr",
            human_readable_body="review pr",
            machine_readable_payload=json.dumps({
                "compare_url": "https://example.test/compare",
                "pr_url": "https://example.test/pr/1",
                "latest_remote_sha": "abc123",
            }),
        )
    )
    db_session.commit()

    target_file = repo_root / "docs/auto-validation/req-test.md"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("hello\n", encoding="utf-8")

    review_result = _deterministic_delivery_validation_result(db_session, task, tmp_path / "out-review", "review")
    assert "https://example.test/compare" in review_result.text
    assert "https://example.test/pr/1" in review_result.text

    step.step_type = "test"
    step.step_key = "test"
    db_session.commit()
    test_result = _deterministic_delivery_validation_result(db_session, task, tmp_path / "out-test", "test")
    assert "abc123" in test_result.text


def test_task_runner_leaves_deferred_copilot_task_running(synced_client, tmp_path):
    from server.services.runtime.task_runner import _run_task_sync
    from server.services.runtime.task_runtime import RuntimeEvent

    create = synced_client.post("/api/tasks", json={
        "description": "Detach copilot runtime",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    predicted_output = tmp_path / "roles" / "content_writer" / "outputs" / f"task-{task_id}" / "output.md"
    with patch("server.services.runtime.task_runner.PROJECT_ROOT", tmp_path), patch(
        "server.services.runtime.task_runner.get_task_runtime"
    ) as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            execution_time_ms=7,
            runtime_backend="copilot_sdk",
            runtime_session_id="session-async-123",
            events=[RuntimeEvent(event_type="runtime_started", detail="backend=copilot_sdk")],
            deferred=True,
            files=[predicted_output],
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "content_writer", "display_name": "Writer", "goal": "", "body": ""}, "copywriting")

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "running"
    assert task["runtime_session_id"] == "session-async-123"
    assert task["output_path"] == str(predicted_output)

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_detached" in event_types


def test_copilot_monitor_completes_detached_task(synced_client, db_session, tmp_path):
    import json

    from server.services.runtime.copilot_sdk_monitor import CopilotSDKTaskMonitor
    from server.services.runtime.copilot_sdk_state import copilot_runtime_paths, task_output_dir
    from server.services.runtime.task_runner import _run_task_sync
    from server.services.runtime.task_runtime import RuntimeEvent

    create = synced_client.post("/api/tasks", json={
        "description": "Complete detached copilot runtime",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    predicted_output = task_output_dir(tmp_path, "content_writer", task_id) / "output.md"
    with patch("server.services.runtime.task_runner.PROJECT_ROOT", tmp_path), patch(
        "server.services.runtime.task_runner.get_task_runtime"
    ) as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            execution_time_ms=7,
            runtime_backend="copilot_sdk",
            runtime_session_id="session-async-456",
            events=[RuntimeEvent(event_type="runtime_started", detail="backend=copilot_sdk")],
            deferred=True,
            files=[predicted_output],
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "content_writer", "display_name": "Writer", "goal": "", "body": ""}, "copywriting")

    output_dir = task_output_dir(tmp_path, "content_writer", task_id)
    paths = copilot_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["output"].write_text("# Detached output\nFinished asynchronously", encoding="utf-8")
    paths["state"].write_text(json.dumps({
        "sessionId": "session-async-456",
        "status": "completed",
        "selectedAgent": "editor",
        "executionTimeMs": 314,
        "lastSeq": 2,
        "heartbeatAt": "2026-04-09T00:00:00+00:00",
    }), encoding="utf-8")
    paths["events"].write_text(
        "\n".join([
            json.dumps({"seq": 1, "type": "session.created", "detail": "session-async-456"}),
            json.dumps({"seq": 2, "type": "subagent.selected", "detail": "editor"}),
        ]),
        encoding="utf-8",
    )

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = CopilotSDKTaskMonitor(project_root=tmp_path, session_factory=session_factory)
    monitor.poll_once()

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "completed"
    assert task["runtime_selected_agent"] == "editor"
    assert task["execution_time_ms"] == 314
    assert "Detached output" in task["output_content"]

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_session_created" in event_types
    assert "subagent_selected" in event_types
    assert "completed" in event_types


def test_copilot_monitor_resumes_stale_task(synced_client, db_session, tmp_path):
    import json

    from server.services.runtime.copilot_sdk_monitor import CopilotSDKTaskMonitor
    from server.services.runtime.copilot_sdk_state import copilot_runtime_paths, task_output_dir

    create = synced_client.post("/api/tasks", json={
        "description": "Resume stale task",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).runtime_backend = "copilot_sdk"
    cast(Any, row).runtime_session_id = "session-stale-789"
    cast(Any, row).runtime_selected_agent = "editor"
    db_session.commit()

    output_dir = task_output_dir(tmp_path, "content_writer", task_id)
    paths = copilot_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["state"].write_text(json.dumps({
        "sessionId": "session-stale-789",
        "status": "running",
        "selectedAgent": "editor",
        "lastEventType": "assistant.message",
        "heartbeatAt": "2000-01-01T00:00:00+00:00",
    }), encoding="utf-8")

    bridge = MagicMock()
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = CopilotSDKTaskMonitor(
        project_root=tmp_path,
        session_factory=session_factory,
        bridge=bridge,
        stale_after_sec=1,
    )
    monitor.poll_once()

    bridge.resume_session.assert_called_once()
    resumed_payload = bridge.resume_session.call_args.args[0]
    assert resumed_payload["action"] == "resume"
    assert resumed_payload["sessionId"] == "session-stale-789"
    assert resumed_payload["assumeAlreadyIdle"] is True


def test_copilot_monitor_clears_role_sessions_on_session_not_found(synced_client, db_session, tmp_path):
    import json

    from server.services.runtime.copilot_sdk_monitor import CopilotSDKTaskMonitor
    from server.services.runtime.copilot_sdk_state import copilot_runtime_paths, task_output_dir

    create = synced_client.post("/api/tasks", json={
        "description": "Fail detached task",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).runtime_backend = "copilot_sdk"
    cast(Any, row).runtime_session_id = "role-seo_strategist-1775919011484-1"
    db_session.commit()

    output_dir = task_output_dir(tmp_path, "content_writer", task_id)
    paths = copilot_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["state"].write_text(json.dumps({
        "sessionId": "role-seo_strategist-1775919011484-1",
        "status": "failed",
        "error": (
            "Request session.resume failed with message: "
            "Session not found: role-seo_strategist-1775919011484-1"
        ),
    }), encoding="utf-8")

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    runtime = MagicMock()
    monitor = CopilotSDKTaskMonitor(project_root=tmp_path, session_factory=session_factory)
    with patch("server.services.runtime.copilot_sdk_monitor.get_copilot_sdk_runtime", return_value=runtime):
        monitor.poll_once()

    runtime.clear_role_sessions.assert_called_once()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "failed"


def test_copilot_monitor_alerts_and_pauses_on_authorization_error(synced_client, db_session, tmp_path):
    import json

    from server.services.runtime.copilot_sdk_monitor import CopilotSDKTaskMonitor
    from server.services.runtime.copilot_sdk_state import copilot_runtime_paths, task_output_dir

    create = synced_client.post("/api/tasks", json={
        "description": "Authorization guarded task",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).runtime_backend = "copilot_sdk"
    cast(Any, row).runtime_session_id = "role-content_writer-authorization-1"
    db_session.commit()

    output_dir = task_output_dir(tmp_path, "content_writer", task_id)
    paths = copilot_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["state"].write_text(json.dumps({
        "sessionId": "role-content_writer-authorization-1",
        "status": "failed",
        "error": (
            "You are not authorized to use this Copilot feature, "
            "it requires an enterprise or organization policy to be enabled."
        ),
    }), encoding="utf-8")

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = CopilotSDKTaskMonitor(project_root=tmp_path, session_factory=session_factory)
    with patch("server.services.runtime.copilot_sdk_monitor.send_lark_text_alert", return_value=(True, "ok")) as mock_alert:
        monitor.poll_once()

    mock_alert.assert_called_once()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "cancelled"
    assert "not authorized to use this copilot feature" in str(task["last_error_message"]).lower()

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_auth_alert" in event_types
    assert "paused" in event_types


def test_copilot_monitor_tolerates_state_file_with_trailing_brace(synced_client, db_session, tmp_path):
    from server.services.runtime.copilot_sdk_monitor import CopilotSDKTaskMonitor
    from server.services.runtime.copilot_sdk_state import copilot_runtime_paths, task_output_dir

    create = synced_client.post("/api/tasks", json={
        "description": "Authorization guarded task with malformed state file",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.runtime.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).runtime_backend = "copilot_sdk"
    cast(Any, row).runtime_session_id = "role-content_writer-authorization-2"
    db_session.commit()

    output_dir = task_output_dir(tmp_path, "content_writer", task_id)
    paths = copilot_runtime_paths(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths["state"].write_text(
        (
            '{\n'
            '  "sessionId": "role-content_writer-authorization-2",\n'
            '  "status": "failed",\n'
            '  "error": "You are not authorized to use this Copilot feature, it requires an enterprise or organization policy to be enabled."\n'
            '}}\n'
        ),
        encoding="utf-8",
    )

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = CopilotSDKTaskMonitor(project_root=tmp_path, session_factory=session_factory)
    with patch("server.services.runtime.copilot_sdk_monitor.send_lark_text_alert", return_value=(True, "ok")) as mock_alert:
        monitor.poll_once()

    mock_alert.assert_called_once()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "cancelled"
