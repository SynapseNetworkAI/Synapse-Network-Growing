"""Tests for /api/agents endpoints."""


def test_list_agents_empty(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sync_agents(client):
    resp = client.post("/api/agents/sync")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6
    ids = {a["id"] for a in data}
    assert "dev_rel" in ids
    assert "growth_lead" in ids
    assert "content_writer" in ids
    assert "seo_strategist" in ids
    assert "cro_optimizer" in ids
    assert "launch_strategist" in ids
    dev_rel = next(item for item in data if item["id"] == "dev_rel")
    assert dev_rel["role_contract"]["mission"]
    assert dev_rel["role_contract"]["acceptance_ownership"]


def test_sync_agents_idempotent(client):
    client.post("/api/agents/sync")
    resp = client.post("/api/agents/sync")
    assert resp.status_code == 200
    assert len(resp.json()) == 6


def test_list_agents_after_sync(synced_client):
    resp = synced_client.get("/api/agents")
    assert resp.status_code == 200
    assert len(resp.json()) == 6


def test_get_agent(synced_client):
    resp = synced_client.get("/api/agents/dev_rel")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "dev_rel"
    assert data["display_name"] == "DevRel Engineer"
    assert data["task_count"] == 0
    assert data["completed_count"] == 0
    assert data["role_contract"]["acceptance_ownership"]


def test_get_agent_not_found(client):
    resp = client.get("/api/agents/nonexistent")
    assert resp.status_code == 404
