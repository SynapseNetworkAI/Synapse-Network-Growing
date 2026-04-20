from __future__ import annotations

import pytest

from server.database import OperatingManifestRow, ReleaseRecordRow, RequirementCandidateRow, RequirementRow, WorkflowRunRow
from server.services.workflows import declarative
from server.services.requirements.service import (
    cancel_requirement,
    delete_requirement,
    list_requirements,
    regenerate_requirement_assets,
    requirement_workflow_readiness,
    start_requirement_workflow,
    submit_requirement,
)


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
    assert payload["outcome_label"] == "Needs Human"
    assert payload["is_truly_completed"] is False
    assert payload["needs_human"] is True
    assert payload["simulated_delivery"] is True
    assert payload["requirement_title"] == "Repair Ops Dashboard failure"
    assert payload["pending_human_gate_count"] == 1
    assert payload["blackboard"]["verification"]["status"] == "passed"
    assert payload["evidence_complete"] is True
    assert payload["command_results"][0]["exit_code"] == 0
    assert payload["command_results"][0]["simulated"] is True
    assert any(output["state_key"] == "diagnose" for output in payload["agent_outputs"])
    assert "server/services/workflows/declarative.py" in payload["changed_files_summary"]["changed_files"]
    assert payload["blackboard"]["pr"]["created"] is True
    assert payload["blackboard"]["pr"]["url"] != "pending"
    assert payload["blackboard"]["pr"]["sync"]["status"] == "synced"
    assert "state_outputs" not in payload["blackboard"]
    assert "transition_history" not in payload["blackboard"]
    assert "artifacts" not in payload["blackboard"]
    assert payload["events"]
    assert payload["atom_invocations"]
    assert payload["human_gates"]
    assert payload["timeline"]
    assert any(item["kind"] == "state_transition" for item in payload["timeline"])
    assert any(item["kind"] == "atom_invocation" for item in payload["timeline"])
    assert any(item["kind"] == "artifact_created" for item in payload["timeline"])
    assert any(item["kind"] == "human_gate" for item in payload["timeline"])
    assert any(item["kind"] == "workflow_terminal" for item in payload["timeline"])
    assert all(item["artifact_type"] != "workflow_transition_event" for item in payload["artifacts"])

    events_response = synced_client.get(f"/api/workflows/runs/{payload['id']}/events")
    assert events_response.status_code == 200
    assert events_response.json()[-1]["to_state"] == "awaiting_operator"

    list_response = synced_client.get("/api/workflows/runs")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload[0]["id"] == payload["id"]
    assert list_payload[0]["pending_human_gate_count"] == 1
    assert list_payload[0]["last_atom"] == "open_self_repair_pr"
    assert list_payload[0]["completed_truthfully"] is False
    assert list_payload[0]["needs_human"] is True

    gated_response = synced_client.get("/api/workflows/runs?pending_human_gate=true")
    assert gated_response.status_code == 200
    assert any(item["id"] == payload["id"] for item in gated_response.json())


def test_workflow_operations_summary_archive_and_completed_tab(synced_client, db_session):
    requirement = _create_requirement(db_session)
    create_response = synced_client.post(
        "/api/workflows/runs",
        json={
            "requirement_id": int(requirement.id),
            "workflow_key": "gateway_reliability_repair",
            "initial_blackboard": {"trigger": {"gateway_drift_detected": True}},
            "run_immediately": True,
        },
    )
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["artifact_count"] >= 1
    assert payload["atom_count"] >= 1

    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        workflow_run_id=int(payload["id"]),
        status="release_ready",
        pr_url="https://github.com/example/repo/pull/1",
    )
    db_session.add(release)
    db_session.commit()

    summary_response = synced_client.get("/api/workflows/runs/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["completed"] >= 1
    assert summary["completed_today"] >= 1
    assert "pending_candidate_count" in summary

    completed_response = synced_client.get("/api/workflows/runs?tab=completed&page=1&page_size=20")
    assert completed_response.status_code == 200
    completed = completed_response.json()
    item = next(row for row in completed["items"] if row["id"] == payload["id"])
    assert item["pr_url"] == "https://github.com/example/repo/pull/1"
    assert item["artifact_count"] >= 1
    assert item["duration_ms"] is not None
    assert item["completed_truthfully"] is True
    assert item["needs_human"] is False

    archive_response = synced_client.post(
        f"/api/workflows/runs/{payload['id']}/archive",
        json={"archived_by": "tester", "reason": "done"},
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["archived_at"] is not None

    default_response = synced_client.get("/api/workflows/runs?tab=completed&page=1&page_size=20")
    assert all(row["id"] != payload["id"] for row in default_response.json()["items"])

    archived_response = synced_client.get("/api/workflows/runs?tab=archived&page=1&page_size=20")
    assert any(row["id"] == payload["id"] for row in archived_response.json()["items"])


def test_human_override_requires_business_confirmation_before_completed_tab(synced_client, db_session):
    requirement = RequirementRow(
        title="Manual copy tweak",
        description_markdown="Operator asked for a tiny copy fix and will manually review the result.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="ready",
        phase="ready",
        workflow_state="ready",
        assets_status="ready",
        acceptance_contract_json=(
            '{"acceptance_override": true, "manual_review_prompt": "帮我看看网页改对了没", '
            '"override_by": "operator", "override_reason": "small manual task", '
            '"markdown": "人工复核网页是否改对"}'
        ),
        execution_plan_json='{"summary_markdown": "use declarative workflow"}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    start_response = synced_client.post(
        f"/api/requirements/{int(requirement.id)}/workflow/start",
        json={"workflow_key": "gateway_reliability_repair", "run_immediately": True, "triggered_by": "operator"},
    )

    assert start_response.status_code == 201
    run_payload = start_response.json()
    assert run_payload["status"] == "succeeded"
    assert run_payload["acceptance_override"] is True
    assert run_payload["awaiting_business_confirmation"] is True
    assert run_payload["is_truly_completed"] is False
    assert run_payload["outcome_label"] == "Awaiting Business Confirmation"
    assert run_payload["manual_review_prompt"] == "帮我看看网页改对了没"

    completed_response = synced_client.get("/api/workflows/runs?tab=completed&page=1&page_size=20")
    assert completed_response.status_code == 200
    assert all(row["id"] != run_payload["id"] for row in completed_response.json()["items"])

    needs_human_response = synced_client.get("/api/workflows/runs?tab=needs_human&page=1&page_size=20")
    assert needs_human_response.status_code == 200
    assert any(row["id"] == run_payload["id"] and row["awaiting_business_confirmation"] for row in needs_human_response.json()["items"])

    confirm_response = synced_client.post(
        f"/api/workflows/runs/{run_payload['id']}/business-outcome/confirm",
        json={"operator": "tester", "note": "视觉结果正确"},
    )

    assert confirm_response.status_code == 200
    confirmed = confirm_response.json()
    assert confirmed["business_outcome_status"] == "confirmed"
    assert confirmed["business_outcome_confirmed_by"] == "tester"
    assert confirmed["business_outcome_note"] == "视觉结果正确"
    assert confirmed["awaiting_business_confirmation"] is False
    assert confirmed["is_truly_completed"] is True

    completed_after_confirm = synced_client.get("/api/workflows/runs?tab=completed&page=1&page_size=20")
    assert any(row["id"] == run_payload["id"] for row in completed_after_confirm.json()["items"])


def test_human_override_reject_and_followup_do_not_mutate_release_or_rollback(synced_client, db_session):
    requirement = RequirementRow(
        title="Manual review outcome rejected",
        description_markdown="Operator will reject the business result and request a follow-up.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="ready",
        phase="ready",
        workflow_state="ready",
        assets_status="ready",
        acceptance_contract_json='{"acceptance_override": true, "manual_review_prompt": "人工确认结果"}',
        execution_plan_json='{"summary_markdown": "use declarative workflow"}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)
    start_response = synced_client.post(
        f"/api/requirements/{int(requirement.id)}/workflow/start",
        json={"workflow_key": "gateway_reliability_repair", "run_immediately": True, "triggered_by": "operator"},
    )
    run_id = int(start_response.json()["id"])

    reject_response = synced_client.post(
        f"/api/workflows/runs/{run_id}/business-outcome/reject",
        json={"operator": "tester", "note": "结果不符合预期"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["business_outcome_status"] == "rejected"
    assert db_session.query(ReleaseRecordRow).count() == 0

    followup_response = synced_client.post(
        f"/api/workflows/runs/{run_id}/business-outcome/follow-up",
        json={"title": "Follow-up manual fix", "operator": "tester", "note": "需要二次修复"},
    )
    assert followup_response.status_code == 201
    followup_id = followup_response.json()["requirement_id"]
    followup = db_session.query(RequirementRow).filter(RequirementRow.id == followup_id).one()
    assert followup.title == "Follow-up manual fix"
    assert followup.active_workflow_run_id is None
    assert followup.linked_requirement_id == requirement.id


def test_pending_human_gate_run_is_not_completed_truthfully(synced_client, db_session):
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
    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["status"] == "awaiting_operator"
    assert payload["pending_human_gate_count"] == 1
    assert payload["is_truly_completed"] is False

    completed_response = synced_client.get("/api/workflows/runs?tab=completed&page=1&page_size=20")
    assert completed_response.status_code == 200
    assert all(row["id"] != payload["id"] for row in completed_response.json()["items"])

    needs_human_response = synced_client.get("/api/workflows/runs?tab=needs_human&page=1&page_size=20")
    assert needs_human_response.status_code == 200
    assert any(row["id"] == payload["id"] for row in needs_human_response.json()["items"])


def test_workflow_empty_state_summary_exposes_pending_candidates(synced_client, db_session):
    manifest = OperatingManifestRow(
        manifest_key="active",
        active_slot="global",
        version_name="Test",
        cycle_label="test",
        status="active",
        payload_json='{"goals": []}',
    )
    db_session.add(manifest)
    db_session.commit()
    candidate = RequirementCandidateRow(
        manifest_id=int(manifest.id),
        goal_key="community_support",
        candidate_fingerprint="forum::bug::1",
        title="Forum bug candidate",
        workflow_key="gateway_reliability_repair",
        status="pending",
    )
    db_session.add(candidate)
    db_session.commit()

    response = synced_client.get("/api/workflows/runs/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pending_candidate_count"] >= 1
    assert any(item["title"] == "Forum bug candidate" for item in payload["recent_candidates"])


def test_workflow_followup_endpoint_creates_linked_requirement(synced_client, db_session):
    requirement = _create_requirement(db_session)
    create_response = synced_client.post(
        "/api/workflows/runs",
        json={
            "requirement_id": int(requirement.id),
            "workflow_key": "gateway_reliability_repair",
            "initial_blackboard": {"trigger": {"gateway_drift_detected": True}},
            "run_immediately": True,
        },
    )
    payload = create_response.json()

    followup_response = synced_client.post(
        f"/api/workflows/runs/{payload['id']}/create-followup",
        json={"title": "Follow-up from workflow", "operator": "tester"},
    )

    assert followup_response.status_code == 201
    followup_id = followup_response.json()["requirement_id"]
    followup = db_session.query(RequirementRow).filter(RequirementRow.id == followup_id).one()
    assert followup.title == "Follow-up from workflow"
    assert followup.linked_requirement_id == requirement.id


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
    assert decided["resume_attempted"] is True
    assert decided["resume_status"] == "rejected"
    assert decided["human_gates"][0]["decision"] == "reject"


def test_human_gate_approve_completes_workflow_and_requirement(synced_client, db_session):
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
        json={"decision": "approve", "reviewer": "tester", "comment": "PR accepted"},
    )

    assert decision_response.status_code == 200
    decided = decision_response.json()
    assert decided["status"] == "succeeded"
    assert decided["resolution"] == "operator_approved"
    assert decided["resume_attempted"] is True
    assert decided["resume_status"] == "completed"
    assert decided["workflow_status_after_resume"] == "succeeded"
    assert decided["next_state"] == "done"
    assert decided["pending_human_gate_count"] == 0
    assert decided["outcome_label"] == "Completed"
    assert decided["is_truly_completed"] is True
    assert decided["human_gates"][0]["status"] == "decided"
    assert decided["human_gates"][0]["decision"] == "approve"
    assert any(event["event_type"] == "human_gate_decision" for event in decided["events"])

    db_session.refresh(requirement)
    assert requirement.status == "completed"
    assert requirement.workflow_state == "completed"
    assert requirement.completed_at is not None

    summary_response = synced_client.get("/api/workflows/runs/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["pending_gate_count"] == 0
    assert all(item["id"] != payload["id"] for item in summary["blocker_items"])


def test_cancelled_requirement_cannot_enter_workflow_or_human_gate(db_session):
    requirement = _create_requirement(db_session)

    detail = cancel_requirement(db_session, int(requirement.id))

    assert detail.state == "cancelled"
    assert detail.allowed_actions == ["view"]
    readiness = requirement_workflow_readiness(db_session, int(requirement.id))
    assert readiness.can_start_workflow is False
    assert readiness.blocking_reason == "requirement_cancelled"
    with pytest.raises(ValueError, match="Cancelled requirement cannot be submitted"):
        submit_requirement(db_session, int(requirement.id))
    with pytest.raises(ValueError, match="Cancelled requirement cannot start workflow"):
        start_requirement_workflow(db_session, int(requirement.id))
    with pytest.raises(ValueError, match="Cancelled requirement cannot regenerate workflow assets"):
        regenerate_requirement_assets(db_session, int(requirement.id))


def test_deleted_requirement_cannot_enter_workflow_or_human_gate(db_session):
    requirement = _create_requirement(db_session)

    detail = delete_requirement(db_session, int(requirement.id))

    assert detail.state == "deleted"
    assert detail.allowed_actions == ["view"]
    readiness = requirement_workflow_readiness(db_session, int(requirement.id))
    assert readiness.can_start_workflow is False
    assert readiness.blocking_reason == "requirement_deleted"
    with pytest.raises(ValueError, match="Deleted requirement cannot be submitted"):
        submit_requirement(db_session, int(requirement.id))
    with pytest.raises(ValueError, match="Deleted requirement cannot start workflow"):
        start_requirement_workflow(db_session, int(requirement.id))
    assert all(item.id != int(requirement.id) for item in list_requirements(db_session))
    assert any(item.id == int(requirement.id) for item in list_requirements(db_session, status="deleted"))


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
