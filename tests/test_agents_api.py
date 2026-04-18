"""Tests for /api/agents endpoints."""

import json
from datetime import datetime, timedelta, timezone

from server.database import ApprovalRequestRow, ArtifactRow, RequirementRow, TaskRow, WorkflowRunRow, WorkflowStepRow


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


def test_get_role_kpis_returns_execution_and_approval_metrics(synced_client, db_session):
    requirement = RequirementRow(
        title="Approval-routed requirement",
        description_markdown="Detailed requirement ready for execution.",
        priority="normal",
        approval_status="pending_approval",
        approval_contract_json=json.dumps({"approval_mode": "auto_or_human"}),
    )
    db_session.add(requirement)
    db_session.flush()

    db_session.add_all(
        [
            TaskRow(
                description="Completed task",
                agent_id="dev_rel",
                status="completed",
                tokens_used=1200,
                budget_cost_points=12,
            ),
            TaskRow(
                description="Running task",
                agent_id="dev_rel",
                status="running",
                requires_approval=True,
            ),
            TaskRow(
                description="Retry task",
                agent_id="dev_rel",
                status="completed",
                attempt_no=2,
                retry_of_task_id=1,
                tokens_used=800,
                budget_cost_points=8,
            ),
        ]
    )
    db_session.flush()
    tasks = db_session.query(TaskRow).order_by(TaskRow.id.asc()).all()
    workflow_run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running")
    db_session.add(workflow_run)
    db_session.flush()
    db_session.add_all(
        [
            WorkflowStepRow(
                workflow_run_id=workflow_run.id,
                requirement_id=requirement.id,
                step_key="implementation",
                step_type="implementation",
                title="Implementation",
                status="completed",
                sequence_no=1,
                assigned_agent_id="dev_rel",
                compatibility_task_id=tasks[0].id,
            ),
            WorkflowStepRow(
                workflow_run_id=workflow_run.id,
                requirement_id=requirement.id,
                step_key="review",
                step_type="review",
                title="Review",
                status="running",
                sequence_no=2,
                assigned_agent_id="dev_rel",
                compatibility_task_id=tasks[1].id,
            ),
            WorkflowStepRow(
                workflow_run_id=workflow_run.id,
                requirement_id=requirement.id,
                step_key="retry",
                step_type="implementation",
                title="Retry",
                status="completed",
                sequence_no=3,
                assigned_agent_id="dev_rel",
                compatibility_task_id=tasks[2].id,
            ),
        ]
    )

    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            artifact_type="requirement_approval_state",
            content_summary="Requirement approval state",
            machine_readable_payload=json.dumps(
                {
                    "approval_recommendation": {
                        "action": "approve",
                        "role": "reviewer",
                        "confidence": 0.91,
                        "reason": "low risk",
                    }
                }
            ),
        )
    )
    db_session.add(
        ApprovalRequestRow(
            requirement_id=requirement.id,
            approval_type="requirement_execution_approval",
            reviewer="reviewer",
            status="approved",
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
            decided_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    )
    db_session.commit()

    resp = synced_client.get("/api/agents/role-kpis")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["summary"]["role_count"] >= 1
    role = next(item for item in payload["roles"] if item["role_id"] == "dev_rel")
    assert role["task_count"] == 3
    assert role["completed_count"] == 2
    assert role["active_task_count"] == 1
    assert role["backlog_count"] == 1
    assert role["reopened_task_count"] == 1
    assert role["approval_dependency_count"] == 1
    assert role["average_token_cost"] == 1000.0
    assert role["open_requirement_count"] >= 1

    approval_role = next(item for item in payload["approval_roles"] if item["role_id"] == "reviewer")
    assert approval_role["assigned_count"] == 1
    assert approval_role["decided_count"] == 1
    assert approval_role["pending_count"] == 0
    assert approval_role["approve_recommendation_count"] == 1
    assert approval_role["route_to_human_rate"] == 0.0
    assert approval_role["average_turnaround_hours"] == 3.0
