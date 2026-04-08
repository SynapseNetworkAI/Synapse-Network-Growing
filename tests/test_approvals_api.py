"""Tests for /api/approvals endpoints."""


def _create_approval_task(client):
    """Helper: create a task with requires_approval and run it."""
    create = client.post("/api/tasks", json={
        "description": "publish content",
        "agent_id": "growth_lead",
        "requires_approval": True,
    })
    task_id = create.json()["id"]
    client.post(f"/api/tasks/{task_id}/run")
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
    create2 = synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "dev_rel"})
    synced_client.post(f"/api/tasks/{create2.json()['id']}/run")
    create3 = synced_client.post("/api/tasks", json={
        "description": "t3", "agent_id": "growth_lead", "requires_approval": True,
    })
    synced_client.post(f"/api/tasks/{create3.json()['id']}/run")

    resp = synced_client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent_count"] == 6
    assert data["task_total"] == 3
    assert data["task_pending"] == 1
    assert data["task_completed"] == 1
    assert data["approval_pending"] == 1
