from __future__ import annotations

from server.database import ExecutionRunRow, RequirementRow, WorkflowRunRow
from server.services.workflows.agent_first import submit_requirement


def _create_requirement(db_session) -> RequirementRow:
    requirement = RequirementRow(
        title="Repair Ops Dashboard failure",
        description_markdown="Detect, diagnose, patch, verify, and prepare PR for Ops Dashboard failure.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="approved",
        approval_status="approved",
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)
    return requirement


def test_workflow_definitions_endpoint_lists_builtin_workflows(synced_client):
    response = synced_client.get("/api/workflows/definitions")

    assert response.status_code == 200
    workflow_keys = {item["workflow_key"] for item in response.json()}
    assert {"agent_self_repair", "gateway_reliability_repair"}.issubset(workflow_keys)


def test_create_workflow_run_endpoint_executes_agent_self_repair(synced_client, db_session):
    requirement = _create_requirement(db_session)

    response = synced_client.post(
        "/api/workflows/runs",
        json={
            "requirement_id": int(requirement.id),
            "workflow_key": "agent_self_repair",
            "triggered_by": "test",
            "initial_blackboard": {
                "trigger": {
                    "source": "test",
                    "ops_failure_detected": True,
                    "force_first_verification_failure": True,
                }
            },
            "run_immediately": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["workflow_key"] == "agent_self_repair"
    assert payload["status"] == "awaiting_operator"
    assert payload["current_state"] == "awaiting_operator"
    assert payload["blackboard"]["verification"]["status"] == "passed"
    assert payload["events"]
    assert payload["atom_invocations"]
    assert payload["human_gates"]

    events_response = synced_client.get(f"/api/workflows/runs/{payload['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[-1]["to_state"] == "awaiting_operator"


def test_human_gate_decision_endpoint_updates_workflow_run(synced_client, db_session):
    requirement = _create_requirement(db_session)
    create_response = synced_client.post(
        "/api/workflows/runs",
        json={
            "requirement_id": int(requirement.id),
            "workflow_key": "agent_self_repair",
            "initial_blackboard": {"trigger": {"ops_failure_detected": True}},
            "run_immediately": True,
        },
    )
    payload = create_response.json()
    gate_id = int(payload["human_gates"][0]["id"])

    decision_response = synced_client.post(
        f"/api/workflows/runs/{payload['id']}/human-gates/{gate_id}/decide",
        json={"decision": "reject", "reviewer": "tester", "comment": "not safe"},
    )

    assert decision_response.status_code == 200
    decided = decision_response.json()
    assert decided["status"] == "failed"
    assert decided["resolution"] == "operator_rejected"
    assert decided["human_gates"][0]["decision"] == "reject"


def test_submit_requirement_creates_declarative_workflow_run_not_legacy_execution(db_session):
    requirement = RequirementRow(
        title="Gateway 5xx reliability repair",
        description_markdown="Fix gateway reliability drift and prepare a PR.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        status="ready",
        phase="ready",
        workflow_state="ready",
        assets_status="ready",
        approval_status="waived",
        acceptance_contract_json='{"summary": "restore reliability"}',
        execution_plan_json='{"summary_markdown": "use declarative workflow"}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    submit_requirement(db_session, int(requirement.id))

    runs = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.requirement_id == requirement.id).all()
    legacy_executions = db_session.query(ExecutionRunRow).filter(ExecutionRunRow.requirement_id == requirement.id).all()
    assert len(runs) == 1
    assert runs[0].workflow_key == "gateway_reliability_repair"
    assert runs[0].current_state in {"done", "awaiting_operator"}
    assert legacy_executions == []
