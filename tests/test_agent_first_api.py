from __future__ import annotations

import logging
from unittest.mock import patch

from server.database import ApprovalRequestRow, ExecutionNodeRow, ExecutionRunRow, NotificationDeliveryRow, ReleaseRecordRow, RequirementRow, TaskRow, ValidationRecordRow
from server.schemas import ValidationCheckResultOut
from server.services.workflows.agent_first import reset_execution_runtime_data


def _create_project(
    synced_client,
    *,
    project_key: str,
    display_name: str,
    root_path: str,
    repo_full_name: str | None = None,
    deploy_strategy: str = "disabled",
    deploy_repo_full_name: str | None = None,
    deploy_trigger_enabled: bool = False,
    git_push_enabled: bool = False,
):
    response = synced_client.post(
        "/api/projects",
        json={
            "project_key": project_key,
            "display_name": display_name,
            "root_path": root_path,
            "repo_full_name": repo_full_name,
            "deploy_strategy": deploy_strategy,
            "deploy_repo_full_name": deploy_repo_full_name,
            "deploy_trigger_enabled": deploy_trigger_enabled,
        },
    )
    assert response.status_code == 201
    project = response.json()
    if git_push_enabled:
        policy_response = synced_client.patch(
            f"/api/projects/{project['id']}/policy",
            json={
                "capability_matrix": {
                    "git_push": True,
                    "git_read": True,
                    "git_write": True,
                    "shell_access": True,
                    "network_access": False,
                    "publish": False,
                }
            },
        )
        assert policy_response.status_code == 200
    return project


def test_submit_low_risk_requirement_auto_approves_and_auto_starts_execution(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Simplify workspace summary copy",
            "description_markdown": "Update the workspace summary copy and keep the change minimal without touching unrelated projects or deployment gates.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )

    assert create_resp.status_code == 201
    assert "Simplify workspace summary copy" in create_resp.json()["requirement"]["acceptance_criteria_markdown"]
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


def test_requirement_submit_emits_structured_chain_logs(synced_client, caplog):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Emit chain logs for requirement submit",
            "description_markdown": "Verify the critical requirement to execution chain emits structured events.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), caplog.at_level(logging.INFO):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")

    assert submit_resp.status_code == 200
    text = caplog.text
    assert "requirement_submitted" in text
    assert "execution_run_created" in text
    assert "execution_run_started" in text
    assert f"'requirement_id': {requirement_id}" in text


def test_create_requirement_without_target_project_path_does_not_raise_policy_summary_error(synced_client):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Create requirement without explicit target path",
            "description_markdown": "Regression check for requirement detail serialization when no target project path is supplied.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )

    assert create_resp.status_code == 201
    payload = create_resp.json()
    assert payload["requirement"]["title"] == "Create requirement without explicit target path"
    assert payload["requirement"]["project_id"] == project["id"]
    assert payload["requirement"]["target_project_path"] == "/Users/cliff/workspace/agent/Synapse-Network-Growing"
    assert payload["requirement"]["acceptance_criteria_markdown"].strip()


def test_submit_high_risk_requirement_routes_to_manual_approval(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
        deploy_repo_full_name="cliff-personal/Synapse-Network",
        deploy_strategy="github_actions_ssh",
        deploy_trigger_enabled=True,
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Prepare production release rollout",
            "description_markdown": "Prepare a production release rollout with publish impact, release checklist, and production coordination evidence.",
            "acceptance_criteria_markdown": "- rollout plan captured\n- release risks documented",
            "priority": "high",
            "project_id": project["id"],
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
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    requirement = RequirementRow(
        title="Manual approval release prep",
        description_markdown="Production rollout change with publish impact and multi-stakeholder coordination.",
        status="blocked",
        approval_status="pending_approval",
        priority="high",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
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
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Reject execution until clarified",
        description_markdown="Need more detailed execution constraints.",
        status="blocked",
        approval_status="pending_approval",
        priority="high",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
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


def test_minimal_validate_prefers_execution_evidence_commands(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Validate using execution evidence",
        description_markdown="Backend bugfix with targeted validation evidence.",
        status="running",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()

    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="running",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add(run)
    db_session.flush()

    task = TaskRow(
        description="bugfix",
        agent_id="software_engineer",
        status="completed",
        priority="normal",
        output_content=(
            "Commands run:\n"
            "- `PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/pytest tests/test_agent_first_api.py tests/test_agent_match.py -q`\n"
            "- `curl -s -X POST http://localhost:9700/api/requirements ...`\n"
        ),
    )
    db_session.add(task)
    db_session.flush()

    db_session.add(
        ExecutionNodeRow(
            execution_run_id=int(run.id),
            requirement_id=int(requirement.id),
            node_key="execute",
            node_type="execute",
            title="Execute requirement",
            status="completed",
            sequence_no=1,
            task_id=int(task.id),
        )
    )
    db_session.commit()

    with patch("server.services.workflows.agent_first._run_check") as run_check:
        run_check.side_effect = lambda project_path, command: ValidationCheckResultOut(
            label=f"check:{command}",
            command=command,
            project_path=project_path,
            status="passed",
            output_excerpt=None,
        )
        resp = synced_client.post(f"/api/executions/{run.id}/validate")

    assert resp.status_code == 200
    payload = resp.json()
    commands = [item["command"] for item in payload["validation"]["checks"]]
    assert commands == ["PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/pytest tests/test_agent_first_api.py tests/test_agent_match.py -q"]
    assert payload["validation"]["status"] == "passed"
    assert payload["requirement"]["status"] == "delivery_ready"


def test_agent_first_release_flow_uses_validate_gate_and_open_pr(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="example/synapse-network",
        deploy_repo_full_name="example/synapse-network",
        deploy_strategy="github_actions_ssh",
        deploy_trigger_enabled=True,
        git_push_enabled=True,
    )
    requirement = RequirementRow(
        title="Promote validated change",
        description_markdown="Validated change ready for release.",
        status="delivery_ready",
        approval_status="waived",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
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


def test_create_execution_run_rejects_when_requirement_already_has_active_run(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Existing active execution",
        description_markdown="Do not create a second execution run while one is active.",
        status="ready",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        ExecutionRunRow(
            requirement_id=int(requirement.id),
            execution_mode="direct",
            complexity="simple",
            status="queued",
            validation_profile="minimal",
            delivery_intent="pr_required",
            approval_required=False,
            target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
        )
    )
    db_session.commit()

    resp = synced_client.post("/api/executions", json={"requirement_id": requirement.id})

    assert resp.status_code == 400
    assert "active execution run" in resp.json()["detail"]


def test_start_execution_rejects_finished_run(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Finished execution cannot restart",
        description_markdown="Completed runs should never start again.",
        status="delivery_ready",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="succeeded",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add(run)
    db_session.commit()

    resp = synced_client.post(f"/api/executions/{run.id}/start")

    assert resp.status_code == 400
    assert "Only queued or paused execution runs can start." == resp.json()["detail"]


def test_retry_execution_creates_new_run_and_keeps_old_run_failed(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Retry creates a new execution",
        description_markdown="Failed execution must stay failed; retry should create a new run.",
        status="blocked",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="failed",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add(run)
    db_session.commit()

    resp = synced_client.post(f"/api/executions/{run.id}/retry")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["execution"]["id"] != run.id
    db_session.refresh(run)
    assert run.status == "failed"
    assert db_session.query(ExecutionRunRow).filter(ExecutionRunRow.requirement_id == requirement.id).count() == 2


def test_validate_rejects_non_current_execution_run(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Old execution cannot validate",
        description_markdown="Only the latest execution chain can validate.",
        status="running",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()
    old_run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="validating",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    new_run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="queued",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add_all([old_run, new_run])
    db_session.flush()
    db_session.add(
        ExecutionNodeRow(
            execution_run_id=int(old_run.id),
            requirement_id=int(requirement.id),
            node_key="execute",
            node_type="execute",
            title="Execute requirement",
            status="completed",
            sequence_no=1,
        )
    )
    db_session.commit()

    resp = synced_client.post(f"/api/executions/{old_run.id}/validate")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Only the current execution run can be validated."


def test_reset_execution_runtime_data_clears_runtime_records_and_resets_requirements(db_session):
    ready_requirement = RequirementRow(
        title="Reset runtime state",
        description_markdown="Execution runtime data can be dropped.",
        status="done",
        approval_status="approved",
        priority="normal",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    blocked_requirement = RequirementRow(
        title="Pending approval survives as blocked",
        description_markdown="Keep manual approval status after cleanup.",
        status="running",
        approval_status="pending_approval",
        priority="high",
        source="manual",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
    )
    db_session.add_all([ready_requirement, blocked_requirement])
    db_session.flush()

    run = ExecutionRunRow(
        requirement_id=int(ready_requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="succeeded",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        ExecutionNodeRow(
            execution_run_id=int(run.id),
            requirement_id=int(ready_requirement.id),
            node_key="execute",
            node_type="execute",
            title="Execute requirement",
            status="completed",
            sequence_no=1,
        )
    )
    db_session.add(
        ValidationRecordRow(
            requirement_id=int(ready_requirement.id),
            execution_run_id=int(run.id),
            profile="minimal",
            status="passed",
            summary_markdown="Validation passed.",
            checks_json="[]",
        )
    )
    db_session.add(
        ReleaseRecordRow(
            requirement_id=int(ready_requirement.id),
            execution_run_id=int(run.id),
            status="pr_opened",
        )
    )
    db_session.commit()

    summary = reset_execution_runtime_data(db_session)

    assert summary["execution_runs_deleted"] == 1
    assert summary["execution_nodes_deleted"] == 1
    assert summary["validation_records_deleted"] == 1
    assert summary["release_records_deleted"] == 1
    assert db_session.query(ExecutionRunRow).count() == 0
    assert db_session.query(ExecutionNodeRow).count() == 0
    assert db_session.query(ValidationRecordRow).count() == 0
    assert db_session.query(ReleaseRecordRow).count() == 0

    db_session.refresh(ready_requirement)
    db_session.refresh(blocked_requirement)
    assert ready_requirement.status == "ready"
    assert blocked_requirement.status == "blocked"
