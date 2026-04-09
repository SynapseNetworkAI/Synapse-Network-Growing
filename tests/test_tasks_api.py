"""Tests for /api/tasks endpoints."""
from unittest.mock import patch, MagicMock

from server.config import ORCHESTRATION_BACKEND
from server.database import AgentRow
from server.services.task_runtime import TaskExecutionResult


def _runtime_result(
    *,
    text: str = "",
    error: str | None = None,
    execution_time_ms: int = 1,
    runtime_backend: str = "legacy",
    runtime_session_id: str | None = None,
    runtime_selected_agent: str | None = None,
    events=None,
):
    return TaskExecutionResult(
        text=text,
        files=[],
        error=error,
        execution_time_ms=execution_time_ms,
        runtime_backend=runtime_backend,
        runtime_session_id=runtime_session_id,
        runtime_selected_agent=runtime_selected_agent,
        events=events or [],
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
    assert len(resp.json()) == 2


def test_list_tasks_orders_newest_first(synced_client):
    first = synced_client.post("/api/tasks", json={"description": "older", "agent_id": "dev_rel"}).json()
    second = synced_client.post("/api/tasks", json={"description": "newer", "agent_id": "growth_lead"}).json()

    resp = synced_client.get("/api/tasks")

    assert resp.status_code == 200
    assert [task["id"] for task in resp.json()] == [second["id"], first["id"]]


def test_list_tasks_filter_by_status(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    resp = synced_client.get("/api/tasks?status=pending")
    assert len(resp.json()) == 1
    resp = synced_client.get("/api/tasks?status=completed")
    assert len(resp.json()) == 0


def test_list_tasks_filter_by_agent(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "growth_lead"})
    resp = synced_client.get("/api/tasks?agent_id=dev_rel")
    assert len(resp.json()) == 1
    assert resp.json()[0]["agent_id"] == "dev_rel"


def test_list_tasks_returns_derived_project_and_group(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    resp = synced_client.get("/api/tasks")
    assert resp.status_code == 200
    task = resp.json()[0]
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
    assert len(resp.json()) == 1
    assert resp.json()[0]["agent_id"] == "seo_strategist"


def test_list_tasks_filter_by_project(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    resp = synced_client.get("/api/tasks?project_id=Synapse-Network-Growing")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_tasks_only_anomalies(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    failed = synced_client.post("/api/tasks", json={
        "description": "t2", "agent_id": "seo_strategist", "skill_name": "seo-audit",
    }).json()
    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{failed['id']}/run")
    resp = synced_client.get("/api/tasks?only_anomalies=true")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "running"


def test_get_task(synced_client):
    create = synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    resp = synced_client.get(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id


def test_get_task_not_found(synced_client):
    resp = synced_client.get("/api/tasks/999")
    assert resp.status_code == 404


def test_run_task_no_approval(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "auto task",
        "agent_id": "dev_rel",
        "skill_name": "content-strategy",
    })
    task_id = create.json()["id"]
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
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
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
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
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")
    resp = synced_client.post(f"/api/tasks/{task_id}/run?skill=seo-audit")
    assert resp.status_code == 400


def test_task_logs(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "t", "agent_id": "dev_rel", "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")
    resp = synced_client.get(f"/api/tasks/{task_id}/logs")
    assert resp.status_code == 200
    logs = resp.json()
    event_types = [l["event_type"] for l in logs]
    assert "created" in event_types
    assert "started" in event_types


def test_retry_task_run_now_creates_new_running_task(synced_client):
    from server.services.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "retry me",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(error="boom")
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "seo-audit")

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/retry?mode=run_now")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["retry_of_task_id"] == task_id
    assert data["attempt_no"] == 2
    mock_dispatch.assert_called_once()


def test_retry_task_edit_first_creates_pending_task(synced_client):
    from server.services.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "retry me later",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
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
    from server.services.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "history me",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
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
    from server.services.task_runner import _run_task_sync

    created_ids = []
    for desc in ("retry one", "retry two"):
        created = synced_client.post("/api/tasks", json={
            "description": desc,
            "agent_id": "seo_strategist",
            "skill_name": "seo-audit",
        })
        task_id = created.json()["id"]
        created_ids.append(task_id)

        with patch("server.services.task_runner.dispatch"):
            synced_client.post(f"/api/tasks/{task_id}/run")

        persona = {"role": "seo_strategist", "display_name": "SEO", "goal": "", "body": ""}
        with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
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
    from server.services.task_runner import _run_task_sync
    from server.services.task_runtime import RuntimeEvent

    create = synced_client.post("/api/tasks", json={
        "description": "Use copilot runtime",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            text="# Copilot output",
            execution_time_ms=42,
            runtime_backend="copilot_sdk",
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
    assert task["runtime_session_id"] == "session-123"
    assert task["runtime_selected_agent"] == "editor"

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_submitted" in event_types
    assert "runtime_started" in event_types
    assert "subagent_selected" in event_types
