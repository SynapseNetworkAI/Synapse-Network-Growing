from __future__ import annotations

from server.database import RequirementRow, WorkflowRunRow
from server.services.workflows import declarative
from server.services.requirements.service import submit_requirement


def _create_requirement(db_session) -> RequirementRow:
    requirement = RequirementRow(
        title="Repair Ops Dashboard failure",
        description_markdown="Detect, diagnose, patch, verify, and prepare PR for Ops Dashboard failure.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="ready",
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


def test_workflow_definition_detail_endpoint_returns_graph_shape(synced_client):
    response = synced_client.get("/api/workflows/definitions/agent_self_repair")

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow_key"] == "agent_self_repair"
    assert payload["initial_state"] == "detect_ops_failure"
    assert any(state["key"] == "verify" and state["transitions"] for state in payload["states"])


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
    assert payload["requirement_title"] == "Repair Ops Dashboard failure"
    assert payload["pending_human_gate_count"] == 1
    assert payload["blackboard"]["verification"]["status"] == "passed"
    assert payload["blackboard"]["pr"]["created"] is True
    assert payload["blackboard"]["pr"]["url"] != "pending"
    assert payload["blackboard"]["pr"]["sync"]["status"] == "synced"
    assert payload["events"]
    assert payload["atom_invocations"]
    assert payload["human_gates"]

    events_response = synced_client.get(f"/api/workflows/runs/{payload['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[-1]["to_state"] == "awaiting_operator"

    list_response = synced_client.get("/api/workflows/runs")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload[0]["id"] == payload["id"]
    assert list_payload[0]["pending_human_gate_count"] == 1
    assert list_payload[0]["last_atom"] == "open_self_repair_pr"

    gated_response = synced_client.get("/api/workflows/runs?pending_human_gate=true")
    assert gated_response.status_code == 200
    assert any(item["id"] == payload["id"] for item in gated_response.json())


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


def test_submit_requirement_creates_declarative_workflow_run(db_session):
    requirement = RequirementRow(
        title="Gateway 5xx reliability repair",
        description_markdown="Fix gateway reliability drift and prepare a PR.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        status="ready",
        phase="ready",
        workflow_state="ready",
        assets_status="ready",
        acceptance_contract_json='{"summary": "restore reliability"}',
        execution_plan_json='{"summary_markdown": "use declarative workflow"}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    submit_requirement(db_session, int(requirement.id))

    runs = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.requirement_id == requirement.id).all()
    assert len(runs) == 1
    assert runs[0].workflow_key == "gateway_reliability_repair"
    assert runs[0].current_state in {"done", "awaiting_operator"}


def test_submit_requirement_response_exposes_declarative_workflow_summary(db_session):
    requirement = RequirementRow(
        title="Repair Ops Dashboard self failure",
        description_markdown="Detect and repair an Ops Dashboard error with declarative workflow.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="ready",
        phase="ready",
        workflow_state="ready",
        assets_status="ready",
        acceptance_contract_json='{"summary": "repair ops"}',
        execution_plan_json='{"summary_markdown": "use agent_self_repair workflow"}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    detail = submit_requirement(db_session, int(requirement.id))

    assert detail.active_workflow_run_id is not None
    assert detail.active_workflow_run_summary is not None
    assert detail.active_workflow_run_summary.workflow_key == "agent_self_repair"
    assert detail.active_workflow_run_summary.pending_human_gate_count >= 0
    assert detail.requirement.active_workflow_run_id == detail.active_workflow_run_id


def test_requirement_workflow_readiness_and_manual_start_endpoint(synced_client, db_session):
    requirement = RequirementRow(
        title="Gateway timeout from bug intake",
        description_markdown="Bug intake saw 5xx gateway timeouts.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        status="planning",
        phase="planning",
        workflow_state="planning",
        source="bug_intake",
        source_ref="error-fingerprint:gateway-timeout",
        assets_status="pending",
        acceptance_contract_json='{"markdown": "## Done Criteria\\n- Gateway recovers", "done_criteria": ["Gateway recovers"]}',
        execution_plan_json="{}",
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    detail_response = synced_client.get(f"/api/requirements/{int(requirement.id)}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["workflow_readiness"]["blocking_reason"] == "acceptance_or_plan_pending"
    assert detail_payload["workflow_readiness"]["recommended_workflow_key"] == "gateway_reliability_repair"

    readiness_response = synced_client.get(f"/api/requirements/{int(requirement.id)}/workflow-readiness")
    assert readiness_response.status_code == 200
    assert readiness_response.json()["can_start_workflow"] is True

    start_response = synced_client.post(
        f"/api/requirements/{int(requirement.id)}/workflow/start",
        json={"workflow_key": "gateway_reliability_repair", "run_immediately": True, "triggered_by": "operator"},
    )
    assert start_response.status_code == 201
    run_payload = start_response.json()
    assert run_payload["workflow_key"] == "gateway_reliability_repair"
    assert run_payload["requirement_id"] == int(requirement.id)
    assert run_payload["blackboard"]["trigger"]["source_kind"] == "bug_intake"
    assert run_payload["blackboard"]["pr"]["created"] is True
    assert run_payload["blackboard"]["pr"]["url"] != "pending"

    db_session.refresh(requirement)
    assert requirement.active_workflow_run_id == run_payload["id"]

    requirement_response = synced_client.get(f"/api/requirements/{int(requirement.id)}")
    assert requirement_response.status_code == 200
    requirement_payload = requirement_response.json()
    assert requirement_payload["state"] == "completed"
    assert requirement_payload["requirement"]["state"] == "completed"
    assert "view_workflow" in requirement_payload["allowed_actions"]
    assert "submit" not in requirement_payload["allowed_actions"]


def test_gateway_pr_atom_calls_vcs_delivery_and_github_pr_sync(
    synced_client,
    db_session,
    monkeypatch,
):
    calls = {}

    def fake_vcs_delivery(*, requirement_id, requirement_title, delivery_contract, fallback_target_path=None):
        calls["vcs"] = {
            "requirement_id": requirement_id,
            "requirement_title": requirement_title,
            "delivery_contract": delivery_contract,
            "fallback_target_path": fallback_target_path,
        }
        branch_name = str(delivery_contract["branch_name"])
        return {
            "status": "delivered",
            "branch_name": branch_name,
            "base_branch": str(delivery_contract["base_branch"]),
            "remote_name": "origin",
            "blockers": [],
            "repositories": [
                {
                    "repo_path": fallback_target_path,
                    "status": "delivered",
                    "branch_name": branch_name,
                    "remote_url": "https://github.com/example/synapse-network.git",
                    "commit_sha": "abc123",
                    "remote_sha": "def456",
                    "committed": True,
                    "pushed": True,
                    "blockers": [],
                }
            ],
            "latest_commit_sha": "abc123",
            "latest_remote_sha": "def456",
            "last_pushed_at": "2026-04-18T00:00:00+00:00",
        }

    def fake_pr_sync(**kwargs):
        calls["pr"] = kwargs
        return {
            "status": "synced",
            "pr_status": "draft",
            "pr_number": 9,
            "pr_url": "https://github.com/example/synapse-network/pull/9",
            "branch_name": kwargs["branch_name"],
            "head_branch": kwargs["branch_name"],
            "base_branch": kwargs["base_branch"],
            "compare_url": kwargs["compare_url"],
            "blockers": [],
        }

    monkeypatch.setattr(declarative, "_workflow_pr_test_mode", lambda: False)
    monkeypatch.setattr(declarative, "execute_requirement_delivery_vcs", fake_vcs_delivery)
    monkeypatch.setattr(declarative, "sync_requirement_review_pr", fake_pr_sync)

    requirement = RequirementRow(
        title="Gateway reliability repair opens PR",
        description_markdown="Fix gateway reliability drift and open a real review PR.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        status="ready",
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    response = synced_client.post(
        "/api/workflows/runs",
        json={
            "requirement_id": int(requirement.id),
            "workflow_key": "gateway_reliability_repair",
            "triggered_by": "test",
            "initial_blackboard": {"trigger": {"gateway_drift_detected": True}},
            "run_immediately": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["blackboard"]["pr"]["created"] is True
    assert payload["blackboard"]["pr"]["url"] == "https://github.com/example/synapse-network/pull/9"
    assert calls["vcs"]["delivery_contract"]["push_required"] is True
    assert calls["vcs"]["delivery_contract"]["capability_matrix"]["git_push"] is True
    assert calls["vcs"]["fallback_target_path"] == "/Users/cliff/workspace/agent/Synapse-Network"
    assert calls["pr"]["vcs_payload"]["status"] == "delivered"
    assert calls["pr"]["compare_url"] == (
        "https://github.com/example/synapse-network/compare/"
        f"main...{calls['pr']['branch_name']}"
    )
    artifact_types = {item["artifact_type"] for item in payload["artifacts"]}
    assert {"workflow_vcs_delivery", "workflow_review_pr_sync"} <= artifact_types
