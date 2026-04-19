"""Tests for /api/agents endpoints."""

import json
from datetime import datetime, timedelta, timezone

from server.database import HumanGateRequestRow, RequirementRow, WorkflowRunRow


def test_list_agents_auto_loads_roles(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 7
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


def test_list_agents_is_idempotent(client):
    client.get("/api/agents")
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    assert len(resp.json()) == 7


def test_list_agents_after_auto_load(synced_client):
    resp = synced_client.get("/api/agents")
    assert resp.status_code == 200
    assert len(resp.json()) == 7


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


def test_get_role_kpis_returns_capability_profiles_and_human_gate_metrics(synced_client, db_session):
    requirement = RequirementRow(
        title="Human-gated requirement",
        description_markdown="Detailed requirement ready for execution.",
        priority="normal",
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="awaiting_operator",
        status="awaiting_operator",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        HumanGateRequestRow(
            workflow_run_id=int(run.id),
            state_key="open_pr",
            gate_type="self_modification",
            risk_level="high",
            status="approved",
            reason="Self-repair PR requires review.",
            decided_by="reviewer",
            decision="approve",
            decided_at=datetime.now(timezone.utc) - timedelta(hours=1),
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
        )
    )
    db_session.commit()

    resp = synced_client.get("/api/agents/role-kpis")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["summary"]["role_count"] >= 1
    role = next(item for item in payload["roles"] if item["role_id"] == "dev_rel")
    assert role["task_count"] == 0
    assert role["completed_count"] == 0
    assert role["active_task_count"] == 0
    assert role["backlog_count"] == 0
    assert role["reopened_task_count"] == 0
    assert role["human_gate_dependency_count"] == 0
    assert role["average_token_cost"] == 0.0
    assert role["open_requirement_count"] == 0

    approval_role = next(item for item in payload["human_gate_roles"] if item["role_id"] == "reviewer")
    assert approval_role["assigned_count"] == 1
    assert approval_role["decided_count"] == 1
    assert approval_role["pending_count"] == 0
    assert approval_role["route_to_human_rate"] == 0.0
    assert approval_role["average_turnaround_hours"] == 3.0
