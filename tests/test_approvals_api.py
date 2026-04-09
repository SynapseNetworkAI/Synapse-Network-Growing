"""Tests for /api/approvals endpoints."""
from unittest.mock import patch, MagicMock

from server.services.task_runner import _run_task_sync


def _create_approval_task(client):
    """Helper: create a task with requires_approval, run via task_runner directly."""
    create = client.post("/api/tasks", json={
        "description": "publish content",
        "agent_id": "growth_lead",
        "requires_approval": True,
        "skill_name": "social-content",
    })
    task_id = create.json()["id"]

    # Set status to running via API (mocked dispatch)
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        client.post(f"/api/tasks/{task_id}/run")

    # Run the task_runner synchronously with mocked engine
    mock_result = MagicMock()
    mock_result.text = "[Mock output] publish content"
    mock_result.files = []
    mock_result.error = None
    mock_result.execution_time_ms = 100

    persona = {"role": "growth_lead", "display_name": "GL", "goal": "", "body": ""}
    with patch("server.services.task_runner._engine") as mock_engine:
        mock_engine.execute.return_value = mock_result
        _run_task_sync(task_id, persona, "social-content")

    return task_id


def test_list_approvals_empty(synced_client):
    resp = synced_client.get("/api/approvals")
    assert resp.status_code == 200
    assert resp.json() == []


def test_approval_created_on_run(synced_client):
    _create_approval_task(synced_client)
    resp = synced_client.get("/api/approvals?status=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_approve_task(synced_client):
    task_id = _create_approval_task(synced_client)
    approvals = synced_client.get("/api/approvals?status=pending").json()
    approval_id = approvals[0]["id"]

    resp = synced_client.post(f"/api/approvals/{approval_id}/decide", json={
        "action": "approve",
        "comment": "LGTM",
        "reviewer": "cto",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
    assert data["reviewer"] == "cto"
    assert data["comment"] == "LGTM"

    # Task should now be completed
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "completed"


def test_reject_task(synced_client):
    task_id = _create_approval_task(synced_client)
    approvals = synced_client.get("/api/approvals?status=pending").json()
    approval_id = approvals[0]["id"]

    resp = synced_client.post(f"/api/approvals/{approval_id}/decide", json={
        "action": "reject",
        "comment": "Needs rework",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "rejected"


def test_cannot_decide_twice(synced_client):
    _create_approval_task(synced_client)
    approvals = synced_client.get("/api/approvals?status=pending").json()
    approval_id = approvals[0]["id"]
    synced_client.post(f"/api/approvals/{approval_id}/decide", json={"action": "approve"})
    resp = synced_client.post(f"/api/approvals/{approval_id}/decide", json={"action": "reject"})
    assert resp.status_code == 400


def test_invalid_action(synced_client):
    _create_approval_task(synced_client)
    approvals = synced_client.get("/api/approvals?status=pending").json()
    approval_id = approvals[0]["id"]
    resp = synced_client.post(f"/api/approvals/{approval_id}/decide", json={"action": "maybe"})
    assert resp.status_code == 400


def test_approval_not_found(synced_client):
    resp = synced_client.post("/api/approvals/999/decide", json={"action": "approve"})
    assert resp.status_code == 404


def test_dashboard_stats(synced_client):
    # Create tasks in various states
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})

    # Run t2 (no approval) — goes to running, then complete via runner
    create2 = synced_client.post("/api/tasks", json={
        "description": "t2", "agent_id": "dev_rel", "skill_name": "seo-audit",
    })
    task2_id = create2.json()["id"]
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task2_id}/run")

    # Complete t2 via task_runner
    mock_result = MagicMock()
    mock_result.text = "done"
    mock_result.files = []
    mock_result.error = None
    mock_result.execution_time_ms = 50
    with patch("server.services.task_runner._engine") as mock_engine:
        mock_engine.execute.return_value = mock_result
        _run_task_sync(task2_id, {"role": "dev_rel", "display_name": "DR", "goal": "", "body": ""}, "seo-audit")

    # Run t3 (with approval)
    create3 = synced_client.post("/api/tasks", json={
        "description": "t3", "agent_id": "growth_lead",
        "requires_approval": True, "skill_name": "social-content",
    })
    task3_id = create3.json()["id"]
    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task3_id}/run")

    mock_result2 = MagicMock()
    mock_result2.text = "tweet"
    mock_result2.files = []
    mock_result2.error = None
    mock_result2.execution_time_ms = 50
    with patch("server.services.task_runner._engine") as mock_engine:
        mock_engine.execute.return_value = mock_result2
        _run_task_sync(task3_id, {"role": "growth_lead", "display_name": "GL", "goal": "", "body": ""}, "social-content")

    resp = synced_client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_count"] == 6
    assert data["task_total"] == 3
    assert data["task_pending"] == 1
    assert data["task_completed"] == 1
    assert data["approval_pending"] == 1
