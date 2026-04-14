from __future__ import annotations

from unittest.mock import patch

from server.database import ApprovalRequestRow, ExecutionRunRow, NotificationDeliveryRow, RequirementRow, TaskRow, ValidationRecordRow


def test_submit_low_risk_requirement_auto_approves_and_auto_starts_execution(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Simplify workspace summary copy",
            "description_markdown": "Update the workspace summary copy and keep the change minimal without touching unrelated projects or deployment gates.",
            "acceptance_criteria_markdown": "- Copy updated\n- No unrelated edits",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )

    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")

    assert submit_resp.status_code == 200
    payload = submit_resp.json()
    assert payload["requirement"]["status"] == "running"
    assert payload["requirement"]["approval_status"] == "approved"
    assert payload["approval"]["approval_decision"] == "approved"
    assert payload["approval"]["approval_source"] == "agent_auto_approved"
    assert payload["approval"]["auto_started"] is True
    assert payload["approval"]["execution_run_id"] is not None
    assert payload["latest_execution_id"] == payload["approval"]["execution_run_id"]

    execution = db_session.query(ExecutionRunRow).filter(ExecutionRunRow.requirement_id == requirement_id).one()
    assert execution.execution_mode == "direct"
    assert execution.status == "running"
    assert db_session.query(TaskRow).filter(TaskRow.id == execution.latest_task_id).one().status == "running"


def test_submit_high_risk_requirement_routes_to_manual_approval(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Prepare production release rollout",
            "description_markdown": "Prepare a production release rollout with publish impact, release checklist, and production coordination evidence.",
            "acceptance_criteria_markdown": "- rollout plan captured\n- release risks documented",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")
    assert submit_resp.status_code == 200
    payload = submit_resp.json()
    assert payload["requirement"]["status"] == "blocked"
    assert payload["requirement"]["approval_status"] == "pending_approval"
    assert payload["approval"]["approval_decision"] == "pending_manual_approval"
    assert payload["approval"]["approval_source"] == "manual_required"
    assert payload["approval"]["auto_started"] is False
    assert payload["approval"]["execution_run_id"] is None

    pending = (
        db_session.query(ApprovalRequestRow)
        .filter(ApprovalRequestRow.requirement_id == requirement_id, ApprovalRequestRow.status == "pending")
        .one()
    )
    assert pending.approval_type == "requirement_execution_approval"


def test_manual_approval_auto_starts_execution(synced_client, db_session):
    requirement = RequirementRow(
        title="Manual approval release prep",
        description_markdown="Production rollout change with publish impact and multi-stakeholder coordination.",
        status="blocked",
        approval_status="pending_approval",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        acceptance_contract_json='{"markdown":"- rollout approved"}',
        approval_requested_at=None,
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        ApprovalRequestRow(
            requirement_id=int(requirement.id),
            workflow_run_id=None,
            step_id=None,
            approval_type="requirement_execution_approval",
            status="pending",
            reviewer="operator",
            comment="Need manual approval",
        )
    )
    db_session.commit()

    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
        approve_resp = synced_client.post(
            f"/api/requirements/{requirement.id}/approve",
            json={"action": "approve", "reviewer": "cto", "comment": "Approved"},
        )

    assert approve_resp.status_code == 200
    payload = approve_resp.json()
    assert payload["requirement"]["status"] == "running"
    assert payload["requirement"]["approval_status"] == "approved"
    assert payload["approval"]["auto_started"] is True
    assert payload["approval"]["execution_run_id"] is not None

    pending = (
        db_session.query(ApprovalRequestRow)
        .filter(ApprovalRequestRow.requirement_id == requirement.id)
        .order_by(ApprovalRequestRow.id.desc())
        .first()
    )
    assert pending is not None
    assert pending.status == "approved"
    assert pending.reviewer == "cto"


def test_manual_reject_marks_requirement_needs_revision(synced_client, db_session):
    requirement = RequirementRow(
        title="Reject execution until clarified",
        description_markdown="Need more detailed execution constraints.",
        status="blocked",
        approval_status="pending_approval",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        acceptance_contract_json='{"markdown":"- clarified"}',
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        ApprovalRequestRow(
            requirement_id=int(requirement.id),
            workflow_run_id=None,
            step_id=None,
            approval_type="requirement_execution_approval",
            status="pending",
            reviewer="operator",
            comment="Need review",
        )
    )
    db_session.commit()

    reject_resp = synced_client.post(
        f"/api/requirements/{requirement.id}/reject",
        json={"action": "reject", "reviewer": "cto", "comment": "Clarify scope first"},
    )
    assert reject_resp.status_code == 200
    payload = reject_resp.json()
    assert payload["requirement"]["status"] == "needs_revision"
    assert payload["requirement"]["approval_status"] == "rejected"
    assert payload["approval"]["approval_decision"] == "rejected"


def test_agent_first_release_flow_uses_validate_gate_and_open_pr(synced_client, db_session):
    requirement = RequirementRow(
        title="Promote validated change",
        description_markdown="Validated change ready for release.",
        status="delivery_ready",
        approval_status="waived",
        priority="normal",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
    )
    db_session.add(requirement)
    db_session.flush()

    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="succeeded",
        validation_profile="release_candidate",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()

    db_session.add(
        ValidationRecordRow(
            requirement_id=int(requirement.id),
            execution_run_id=int(run.id),
            profile="release_candidate",
            status="passed",
            summary_markdown="Validation passed.",
            checks_json="[]",
        )
    )
    db_session.commit()

    candidates = synced_client.get("/api/releases/candidates")
    assert candidates.status_code == 200
    payload = candidates.json()
    candidate = next(item for item in payload if item["requirement"]["id"] == requirement.id)
    assert candidate["validation"]["status"] == "passed"

    with patch(
        "server.services.workflows.agent_first.execute_requirement_delivery_vcs",
        return_value={
            "branch_name": "ops/req-1-promote-validated-change",
            "base_branch": "main",
            "blockers": [],
            "repositories": [
                {
                    "remote_url": "https://github.com/example/synapse-network.git",
                    "commit_sha": "abc123",
                    "remote_sha": "abc123",
                }
            ],
        },
    ), patch(
        "server.services.workflows.agent_first.sync_requirement_review_pr",
        return_value={
            "compare_url": "https://github.com/example/synapse-network/compare/main...ops/req-1-promote-validated-change",
            "pr_url": "https://github.com/example/synapse-network/pull/7",
            "pr_number": 7,
        },
    ):
        prepare_resp = synced_client.post(
            f"/api/releases/{requirement.id}/prepare",
            json={"actor": "operator", "note": "prepare"},
        )
        assert prepare_resp.status_code == 200
        assert prepare_resp.json()["release"]["status"] == "branch_prepared"

        open_pr_resp = synced_client.post(
            f"/api/releases/{requirement.id}/open-pr",
            json={"actor": "operator", "note": "open pr"},
        )
        assert open_pr_resp.status_code == 200
        release = open_pr_resp.json()["release"]
        assert release["status"] == "pr_opened"
        assert release["pr_number"] == 7
        assert release["commit_sha"] == "abc123"
        delivery = (
            db_session.query(NotificationDeliveryRow)
            .filter(NotificationDeliveryRow.channel == "release", NotificationDeliveryRow.event_type == "pr_opened")
            .order_by(NotificationDeliveryRow.id.desc())
            .first()
        )
        assert delivery is not None
