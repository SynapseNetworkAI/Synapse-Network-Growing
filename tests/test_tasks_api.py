"""Tests for /api/tasks endpoints."""


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


def test_list_tasks(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "growth_lead"})
    resp = synced_client.get("/api/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


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
    create = synced_client.post("/api/tasks", json={"description": "auto task", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    resp = synced_client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["output_content"] is not None
    assert data["completed_at"] is not None


def test_run_task_with_approval(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "publish tweet",
        "agent_id": "growth_lead",
        "requires_approval": True,
    })
    task_id = create.json()["id"]
    resp = synced_client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"

    # Verify approval was created
    approvals = synced_client.get("/api/approvals?status=pending").json()
    assert len(approvals) == 1
    assert approvals[0]["task_id"] == task_id


def test_run_task_already_running(synced_client):
    create = synced_client.post("/api/tasks", json={"description": "t", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    synced_client.post(f"/api/tasks/{task_id}/run")
    resp = synced_client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 400


def test_task_logs(synced_client):
    create = synced_client.post("/api/tasks", json={"description": "t", "agent_id": "dev_rel"})
    task_id = create.json()["id"]
    synced_client.post(f"/api/tasks/{task_id}/run")
    resp = synced_client.get(f"/api/tasks/{task_id}/logs")
    assert resp.status_code == 200
    logs = resp.json()
    event_types = [l["event_type"] for l in logs]
    assert "created" in event_types
    assert "started" in event_types
    assert "completed" in event_types


def test_agent_task_count_after_tasks(synced_client):
    synced_client.post("/api/tasks", json={"description": "t1", "agent_id": "dev_rel"})
    synced_client.post("/api/tasks", json={"description": "t2", "agent_id": "dev_rel"})
    create3 = synced_client.post("/api/tasks", json={"description": "t3", "agent_id": "dev_rel"})
    synced_client.post(f"/api/tasks/{create3.json()['id']}/run")

    agent = synced_client.get("/api/agents/dev_rel").json()
    assert agent["task_count"] == 3
    assert agent["completed_count"] == 1
