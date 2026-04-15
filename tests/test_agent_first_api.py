from __future__ import annotations

import base64
import json
import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

from server.database import AgentRow, ApprovalRequestRow, ApprovalRow, CodexSessionRow, ExecutionNodeRow, ExecutionRunRow, NotificationDeliveryRow, ReleaseRecordRow, RequirementAcceptanceCheckRow, RequirementAttachmentRow, RequirementRow, StepInputBindingRow, TaskLogRow, TaskRow, ValidationRecordRow, WorkflowRunRow, WorkflowStepDependencyRow, WorkflowStepEventRow, WorkflowStepRow, utcnow
from server.schemas import TaskExecutionSuggestion, ValidationCheckResultOut
from server.services.workflows.agent_first import reset_execution_runtime_data
from server.services.runtime.task_runner import _task_project_root


def _branch_ready_payload(branch_name: str) -> dict[str, object]:
    return {
        "status": "ready",
        "branch_name": branch_name,
        "base_branch": "main",
        "remote_name": "origin",
        "blockers": [],
        "repositories": [],
    }


def _init_git_repo(repo_path: Path) -> None:
    repo_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=repo_path, check=True, capture_output=True, text=True)
    (repo_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, check=True, capture_output=True, text=True)


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
    create_payload = create_resp.json()
    assert create_payload["requirement"]["assets_status"] == "ready"
    assert create_payload["assets_status"] == "ready"
    assert create_payload["acceptance_contract"]["done_criteria"]
    assert create_payload["acceptance_contract"]["verification_checks"]
    assert "Done Criteria" in create_payload["requirement"]["acceptance_criteria_markdown"]
    assert "Verification Focus" in create_payload["requirement"]["acceptance_criteria_markdown"]
    requirement_id = create_resp.json()["requirement"]["id"]

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-1-simplify-workspace-summary-copy"),
    ):
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
    assert payload["execution_plan"]["summary_markdown"]
    assert payload["execution_plan"]["steps"] == [
        {
            "step_key": "execute",
            "title": "Execute requirement",
            "step_type": "implementation",
            "scope": "implementation",
        }
    ]
    assert "Research context" not in payload["execution_plan"]["summary_markdown"]
    assert "Close requirement" not in payload["execution_plan"]["summary_markdown"]


def test_create_requirement_persists_attachments_and_detail_returns_them(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    response = synced_client.post(
        "/api/requirements",
        json={
            "title": "Attach screenshot to requirement",
            "description_markdown": "Use the screenshot as design and debugging context.",
            "priority": "normal",
            "project_id": project["id"],
            "attachments": [
                {
                    "file_name": "staging.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"fake-image").decode("ascii"),
                    "source": "clipboard",
                }
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["attachments"][0]["file_name"] == "staging.png"
    assert payload["attachments"][0]["attachment_kind"] == "image"
    assert payload["assets_status"] == "ready"
    requirement_id = int(payload["requirement"]["id"])

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    intake_metadata = json.loads(str(requirement.intake_metadata_json or "{}"))
    assert intake_metadata["attachment_count"] == 1
    assert any(str(item).endswith("context-manifest.md") for item in intake_metadata["attachment_context_files"])
    attachment = (
        db_session.query(RequirementAttachmentRow)
        .filter(RequirementAttachmentRow.requirement_id == requirement_id)
        .one()
    )
    assert attachment.file_name == "staging.png"


def test_submit_requirement_rejects_while_assets_are_pending(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Wait for generated assets",
            "description_markdown": "Submit should be blocked until assets are ready.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    requirement.assets_status = "pending"
    requirement.assets_error_message = None
    requirement.acceptance_contract_json = "{}"
    requirement.execution_plan_json = "{}"
    db_session.commit()

    submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")

    assert submit_resp.status_code == 400
    assert submit_resp.json()["detail"] == "验收标准与执行计划仍在生成中，请稍后再提交。"


def test_delete_requirement_only_allowed_before_execution_starts(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Delete before execution",
            "description_markdown": "Draft requirements can still be deleted.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])

    delete_resp = synced_client.post(f"/api/requirements/{requirement_id}/delete")

    assert delete_resp.status_code == 200
    assert delete_resp.json()["requirement"]["status"] == "deleted"


def test_delete_requirement_rejects_when_execution_history_exists(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    requirement = RequirementRow(
        title="Delete blocked after execution",
        description_markdown="Anything with execution history should not be deletable.",
        status="running",
        phase="executing",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        ExecutionRunRow(
            requirement_id=int(requirement.id),
            execution_mode="direct",
            complexity="simple",
            status="running",
            phase="executing",
            validation_profile="minimal",
            delivery_intent="pr_required",
            approval_required=False,
            target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
        )
    )
    db_session.commit()

    delete_resp = synced_client.post(f"/api/requirements/{int(requirement.id)}/delete")

    assert delete_resp.status_code == 400
    assert delete_resp.json()["detail"] == "Requirements with execution history cannot be deleted."


def test_requirement_list_reconciles_running_status_from_latest_execution(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "State reconcile from execution",
            "description_markdown": "Ensure requirement list derives running state from execution.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-state-reconcile"),
    ):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")
    assert submit_resp.status_code == 200
    execution_id = int(submit_resp.json()["latest_execution_id"])

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    run = db_session.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_id).one()
    task = db_session.query(TaskRow).filter(TaskRow.id == run.latest_task_id).one()
    requirement.status = "ready"
    requirement.phase = "branch_prepared"
    run.status = "running"
    run.phase = "executing"
    task.status = "running"
    db_session.commit()

    requirements_payload = synced_client.get("/api/requirements").json()
    execution_payload = synced_client.get("/api/executions").json()
    requirement_row = next(item for item in requirements_payload if int(item["id"]) == requirement_id)
    execution_row = next(item for item in execution_payload if int(item["id"]) == execution_id)

    assert requirement_row["status"] == "running"
    assert requirement_row["phase"] == "executing"
    assert execution_row["status"] == "running"
    assert execution_row["phase"] == "executing"


def test_start_execution_is_idempotent_when_already_running(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Idempotent start",
            "description_markdown": "Repeated start should not create duplicate work.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-idempotent-start"),
    ):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")
        assert submit_resp.status_code == 200
        execution_id = int(submit_resp.json()["latest_execution_id"])
        rerun_resp = synced_client.post(f"/api/executions/{execution_id}/resume")

    assert rerun_resp.status_code == 200
    payload = rerun_resp.json()
    assert payload["status"] == "noop"
    assert payload["reason"] == "already_running"
    assert payload["detail"]["execution"]["id"] == execution_id
    assert payload["detail"]["execution"]["status"] == "running"
    assert payload["detail"]["execution"]["phase"] == "executing"


def test_execution_detail_marks_running_codex_cli_session_as_recovering(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Recover running codex session",
            "description_markdown": "A running codex session should surface as recovering after reconcile.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-recovering"),
    ):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")
    execution_id = int(submit_resp.json()["latest_execution_id"])

    run = db_session.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_id).one()
    task = db_session.query(TaskRow).filter(TaskRow.id == run.latest_task_id).one()
    task.runtime_backend = "codex_cli"
    task.runtime_session_id = "thread-recover-1"
    db_session.add(
        CodexSessionRow(
            session_key="session-recover-1",
            role_key="software_engineer",
            project_root="/Users/cliff/workspace/agent/Synapse-Network",
            requirement_id=requirement_id,
            current_task_id=int(task.id),
            thread_id="thread-recover-1",
            status="active",
            resume_count=2,
            last_heartbeat_at=utcnow(),
        )
    )
    db_session.commit()

    detail = synced_client.get(f"/api/executions/{execution_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["execution"]["recovery_status"] == "recovering"
    assert payload["recovery_status"] == "recovering"
    assert payload["execution"]["resume_count"] == 2


def test_regenerate_requirement_assets_marks_pending_and_requeues_generation(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Retry asset generation",
            "description_markdown": "Regenerate acceptance and plan after a failed attempt.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    requirement.assets_status = "failed"
    requirement.assets_error_message = "planner crashed"
    db_session.commit()

    with patch("server.services.workflows.agent_first._enqueue_requirement_asset_generation", return_value=None):
        resp = synced_client.post(f"/api/requirements/{requirement_id}/regenerate-assets")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["assets_status"] == "pending"
    assert payload["assets_error_message"] is None


def test_start_execution_run_injects_attachment_context_files_into_task(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Use attachment context during execution",
            "description_markdown": "Please use the attached screenshot as implementation context.",
            "priority": "normal",
            "project_id": project["id"],
            "attachments": [
                {
                    "file_name": "ux.png",
                    "content_type": "image/png",
                    "content_base64": base64.b64encode(b"image").decode("ascii"),
                    "source": "upload",
                }
            ],
        },
    )
    requirement_id = int(create_resp.json()["requirement"]["id"])
    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-1-use-attachment-context-during-execution"),
    ):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")

    assert submit_resp.status_code == 200
    execution_id = int(submit_resp.json()["latest_execution_id"])
    task = db_session.query(TaskRow).filter(TaskRow.id == db_session.query(ExecutionRunRow).filter(ExecutionRunRow.id == execution_id).one().latest_task_id).one()
    context_files = json.loads(str(task.context_files or "[]"))
    assert any(str(item).endswith("context-manifest.md") for item in context_files)
    assert any("ux.png" in str(item) for item in context_files)


def test_requirement_attachment_endpoint_serves_persisted_file(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="cliff-personal/Synapse-Network",
    )
    response = synced_client.post(
        "/api/requirements",
        json={
            "title": "Serve attachment file",
            "description_markdown": "Need attachment download access.",
            "priority": "normal",
            "project_id": project["id"],
            "attachments": [
                {
                    "file_name": "context.txt",
                    "content_type": "text/plain",
                    "content_base64": base64.b64encode(b"context-body").decode("ascii"),
                    "source": "upload",
                }
            ],
        },
    )
    payload = response.json()
    requirement_id = int(payload["requirement"]["id"])
    attachment_id = int(payload["attachments"][0]["id"])

    file_response = synced_client.get(f"/api/requirements/{requirement_id}/attachments/{attachment_id}")

    assert file_response.status_code == 200
    assert file_response.text == "context-body"


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

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-1-emit-chain-logs-for-requirement-submit"),
    ), caplog.at_level(logging.INFO):
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


def test_agent_first_execution_uses_single_execute_node_even_for_multi_target_requirement(synced_client, db_session):
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
            "title": "Cross-project rollout plan",
            "description_markdown": "Coordinate a rollout touching two target paths and keep the delivery evidence unified.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).one()
    requirement.target_project_path = "/Users/cliff/workspace/agent/Synapse-Network-Growing\n/Users/cliff/workspace/agent/Synapse-Network"
    db_session.commit()

    with patch("server.services.workflows.agent_first.dispatch", return_value=None):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")

    assert submit_resp.status_code == 200
    submit_payload = submit_resp.json()
    assert submit_payload["approval"]["approval_decision"] == "pending_manual_approval"
    assert submit_payload["approval"]["execution_run_id"] is None

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-1-cross-project-rollout-plan"),
    ):
        approve_resp = synced_client.post(
            f"/api/requirements/{requirement_id}/approve",
            json={"action": "approve", "reviewer": "cto", "comment": "Approved for execution"},
        )

    assert approve_resp.status_code == 200
    execution = db_session.query(ExecutionRunRow).filter(ExecutionRunRow.requirement_id == requirement_id).one()
    nodes = (
        db_session.query(ExecutionNodeRow)
        .filter(ExecutionNodeRow.execution_run_id == execution.id)
        .order_by(ExecutionNodeRow.sequence_no.asc())
        .all()
    )
    assert execution.execution_mode == "direct"
    assert [node.node_key for node in nodes] == ["execute"]


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

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value=_branch_ready_payload("ops/req-1-manual-approval-release-prep"),
    ):
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
        acceptance_contract_json=json.dumps(
            {
                "done_criteria": ["Targeted validation evidence is captured."],
                "verification_checks": [
                    {"label": "Repo-wide pytest", "command": "pytest", "kind": "command"},
                    {"label": "Repo-wide npm", "command": "npm test", "kind": "command"},
                    {"label": "Review execution evidence", "kind": "evidence"},
                ],
                "delivery_expectation": "Prepare a PR-ready branch when implementation succeeds.",
                "markdown": "### Verification Checks\n- Repo-wide pytest (`pytest`)\n- Repo-wide npm (`npm test`)\n- Review execution evidence",
            },
            ensure_ascii=False,
        ),
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
    assert commands == [
        "PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/pytest tests/test_agent_first_api.py tests/test_agent_match.py -q",
        None,
    ]
    assert payload["validation"]["status"] == "passed"
    assert payload["validation"]["verification_agent_id"] == "verification_agent"
    assert payload["validation"]["verification_agent_label"] == "Verification Agent"
    assert payload["validation"]["suggested_next_action"] == "release_ready"
    assert payload["validation"]["verification_plan"]["mode"] == "command_checks"
    assert payload["verification_plan"]["mode"] == "command_checks"
    assert payload["verification_result"]["verification_agent_id"] == "verification_agent"
    assert payload["requirement"]["status"] == "delivery_ready"


def test_submit_blocks_execution_start_when_branch_preparation_is_blocked(synced_client, db_session):
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
            "title": "Blocked by dirty worktree",
            "description_markdown": "This requirement should stop before execution when the target repo is dirty.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    with patch("server.services.workflows.agent_first.dispatch", return_value=None), patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value={
            "status": "blocked",
            "branch_name": "ops/req-1-blocked-by-dirty-worktree",
            "base_branch": "main",
            "remote_name": "origin",
            "blockers": ["dirty worktree on `main` blocks automatic execution branch preparation"],
            "repositories": [],
        },
    ):
        submit_resp = synced_client.post(f"/api/requirements/{requirement_id}/submit")

    assert submit_resp.status_code == 200
    payload = submit_resp.json()
    assert payload["approval"]["auto_started"] is False
    assert payload["approval"]["pending_execution_start"] is True
    assert payload["approval"]["execution_run_id"] is not None
    assert payload["latest_release"]["status"] == "release_blocked"
    execution = db_session.query(ExecutionRunRow).filter(ExecutionRunRow.requirement_id == requirement_id).one()
    assert execution.status == "queued"
    detail_resp = synced_client.get(f"/api/executions/{int(execution.id)}")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["queue_reason"].startswith("启动失败：")
    assert detail_payload["blocking_reason_code"] == "branch_preparation_blocked"
    assert "dirty worktree" in detail_payload["blocking_reason_message"]


def test_branch_preparation_blocker_restarts_same_execution_after_workspace_is_clean(synced_client, db_session, tmp_path):
    repo_path = tmp_path / "dirty-repo"
    _init_git_repo(repo_path)
    (repo_path / "README.md").write_text("dirty\n", encoding="utf-8")
    project = _create_project(
        synced_client,
        project_key="dirty-repo",
        display_name="Dirty Repo",
        root_path=str(repo_path),
        repo_full_name="example/dirty-repo",
    )
    requirement = RequirementRow(
        title="Restart current execution after cleaning workspace",
        description_markdown="Dirty worktree should block start until the repo is clean.",
        status="ready",
        phase="branch_prepared",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path=str(repo_path),
    )
    db_session.add(requirement)
    db_session.flush()
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="blocked",
        phase="blocked",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json=json.dumps([str(repo_path)]),
    )
    db_session.add(run)
    db_session.flush()
    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=int(run.id),
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path=str(repo_path),
        status="release_blocked",
        branch_name="ops/req-1-restart-current-execution",
        base_branch="main",
        notes=f"{repo_path}: dirty worktree on `main` blocks automatic execution branch preparation",
    )
    db_session.add(release)
    db_session.add(
        ExecutionNodeRow(
            execution_run_id=int(run.id),
            requirement_id=int(requirement.id),
            node_key="execute",
            node_type="execute",
            title="Execute requirement",
            status="queued",
            sequence_no=1,
        )
    )
    db_session.commit()

    detail_resp = synced_client.get(f"/api/executions/{run.id}")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["allowed_actions"] == ["start", "view", "view_requirement"]
    assert detail_payload["blocking_reason_code"] == "branch_preparation_blocked"
    assert detail_payload["recovery_mode"] == "restart_current"
    assert detail_payload["workspace_blocker"]["repo_path"] == str(repo_path)
    assert detail_payload["workspace_blocker"]["dirty_file_count"] >= 1
    assert "README.md" in "\n".join(detail_payload["workspace_blocker"]["dirty_files_preview"])

    with patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value={
            "status": "blocked",
            "branch_name": "ops/req-1-restart-current-execution",
            "base_branch": "main",
            "remote_name": "origin",
            "blockers": [f"{repo_path}: dirty worktree on `main` blocks automatic execution branch preparation"],
            "repositories": [],
        },
    ):
        blocked_start_resp = synced_client.post(f"/api/executions/{run.id}/start")

    assert blocked_start_resp.status_code == 200
    blocked_start_payload = blocked_start_resp.json()
    assert blocked_start_payload["status"] == "blocked"
    assert blocked_start_payload["execution_id"] == run.id
    assert blocked_start_payload["detail"]["execution"]["id"] == run.id

    subprocess.run(["git", "checkout", "--", "README.md"], cwd=repo_path, check=True, capture_output=True, text=True)

    with patch("server.services.workflows.agent_first.prepare_requirement_delivery_branch", return_value=_branch_ready_payload("ops/req-1-restart-current-execution")), patch(
        "server.services.workflows.agent_first.suggest_task_execution",
        return_value=TaskExecutionSuggestion(
            agent_id="software_engineer",
            skill_name="__direct_execution__",
            confidence=0.99,
            reason="test",
        ),
    ), patch("server.services.workflows.agent_first._load_full_persona", return_value="# persona"), patch(
        "server.services.workflows.agent_first.dispatch",
        return_value=None,
    ):
        start_resp = synced_client.post(f"/api/executions/{run.id}/start")

    assert start_resp.status_code == 200
    start_payload = start_resp.json()
    assert start_payload["status"] == "applied"
    assert start_payload["execution_id"] == run.id
    assert start_payload["replacement_execution_id"] is None
    assert start_payload["detail"]["execution"]["id"] == run.id
    assert start_payload["detail"]["execution"]["status"] == "running"


def test_verification_blocked_current_execution_exposes_retry_not_start(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="example/synapse-network",
    )
    requirement = RequirementRow(
        title="Verification failure requires new run",
        description_markdown="Verification should require retry, not restart current execution.",
        status="blocked",
        phase="needs_revision",
        approval_status="approved",
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
        status="blocked",
        phase="blocked",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()
    validation = ValidationRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=int(run.id),
        profile="minimal",
        status="needs_revision",
        summary_markdown="Verification found unfinished work.",
        suggested_next_action="retry_execution",
        resolution_path="retry_execution",
        resolution_reason="A new implementation attempt is required.",
    )
    db_session.add(validation)
    db_session.commit()

    detail_resp = synced_client.get(f"/api/executions/{run.id}")
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["recovery_mode"] == "retry_new_run"
    assert "retry" in detail_payload["allowed_actions"]
    assert "start" not in detail_payload["allowed_actions"]

    start_resp = synced_client.post(f"/api/executions/{run.id}/start")
    assert start_resp.status_code == 200
    start_payload = start_resp.json()
    assert start_payload["status"] == "invalid_action"
    assert start_payload["reason"] == "verification_needs_revision"


def test_validation_pass_auto_opens_pr(synced_client, db_session):
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
        title="Auto open PR after verification",
        description_markdown="Verified change should immediately publish a review branch and PR.",
        status="running",
        approval_status="waived",
        priority="normal",
        source="manual",
        project_id=int(project["id"]),
        project_key=str(project["project_key"]),
        project_display_name=str(project["display_name"]),
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        acceptance_contract_json=json.dumps(
            {
                "done_criteria": ["PR is ready after verification."],
                "verification_checks": [],
                "delivery_expectation": "Open a PR when verification passes.",
                "markdown": "### Done Criteria\n- PR is ready after verification.",
            }
        ),
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
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()
    task = TaskRow(
        description="implement",
        agent_id="software_engineer",
        status="completed",
        priority="normal",
        output_content="Commands run:\n- `pytest tests/test_logging_utils.py -q`\n",
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
    db_session.add(
        ReleaseRecordRow(
            requirement_id=int(requirement.id),
            execution_run_id=int(run.id),
            project_id=int(project["id"]),
            project_key=str(project["project_key"]),
            project_display_name=str(project["display_name"]),
            target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
            status="branch_prepared",
            branch_name="ops/req-1-auto-open-pr-after-verification",
            base_branch="main",
        )
    )
    db_session.commit()

    with patch(
        "server.services.workflows.agent_first.execute_requirement_delivery_vcs",
        return_value={
            "branch_name": "ops/req-1-auto-open-pr-after-verification",
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
            "compare_url": "https://github.com/example/synapse-network/compare/main...ops/req-1-auto-open-pr-after-verification",
            "pr_url": "https://github.com/example/synapse-network/pull/11",
            "pr_number": 11,
        },
    ), patch(
        "server.services.workflows.agent_first.verify_with_agent",
        return_value={
            "verification_plan": {
                "mode": "command_checks",
                "summary": "Replay the targeted pytest command captured by the execution agent.",
                "checks": ["pytest tests/test_logging_utils.py -q"],
                "evidence_expectations": ["Changed files should map to the requirement scope."],
                "why_no_verification": None,
            },
            "status": "passed",
            "summary": "Verification passed.",
            "checks_run": ["pytest tests/test_logging_utils.py -q"],
            "evidence_used": ["changed_files:1", "raw_output:commands"],
            "reasoning": "Execution evidence matches the requirement and is ready for PR.",
            "suggested_next_action": "release_ready",
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        },
    ):
        resp = synced_client.post(f"/api/executions/{run.id}/validate")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["verification_result"]["status"] == "passed"
    assert payload["verification_plan"]["mode"] == "command_checks"
    assert payload["delivery_summary"]["status"] == "pr_opened"
    assert payload["delivery_summary"]["pr_number"] == 11
    assert payload["delivery_summary"]["pr_url"] == "https://github.com/example/synapse-network/pull/11"
    db_session.refresh(requirement)
    assert requirement.status == "done"


def test_validation_defaults_to_retry_execution_resolution_path(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="example/synapse-network",
    )
    requirement = RequirementRow(
        title="Retry within current requirement",
        description_markdown="A scoped docs fix should retry in place when verification still wants revisions.",
        status="running",
        phase="executing",
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
        status="running",
        phase="executing",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()
    task = TaskRow(
        description="implement",
        agent_id="software_engineer",
        status="completed",
        priority="normal",
        output_content="Adjusted the docs validation script in the current repo.",
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

    with patch(
        "server.services.workflows.agent_first.verify_with_agent",
        return_value={
            "verification_plan": {
                "mode": "evidence_review",
                "summary": "Review the updated script and raw execution output.",
                "checks": [],
                "evidence_expectations": ["Current repo docs checks should pass after a retry."],
                "why_no_verification": None,
            },
            "status": "needs_revision",
            "summary": "The fix is still incomplete but remains in the same requirement scope.",
            "checks_run": [],
            "evidence_used": ["changed_files:1"],
            "reasoning": "The remaining work is still in the same project and scope.",
            "suggested_next_action": "retry_execution",
            "resolution_recommendation": "retry_execution",
            "resolution_confidence": 0.91,
            "resolution_reason": "The remaining gap is still inside the original requirement scope.",
            "followup_requirement_payload": {},
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        },
    ):
        resp = synced_client.post(f"/api/executions/{run.id}/validate")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["verification_result"]["resolution_path"] == "retry_execution"
    assert payload["verification_result"]["followup_requirement_id"] is None
    db_session.refresh(requirement)
    assert requirement.status == "needs_revision"
    assert requirement.followup_requirement_id is None


def test_validation_creates_followup_requirement_when_scope_drift_is_explicit(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="example/synapse-network",
    )
    requirement = RequirementRow(
        title="Current requirement hit a platform gate issue",
        description_markdown="The original task was scoped to one service, but verification found a wider docs gate issue.",
        status="running",
        phase="executing",
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
        status="running",
        phase="executing",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()
    task = TaskRow(
        description="implement",
        agent_id="software_engineer",
        status="completed",
        priority="normal",
        output_content="Service change completed, but the docs metadata gate is still failing globally.",
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

    with patch(
        "server.services.workflows.agent_first.verify_with_agent",
        return_value={
            "verification_plan": {
                "mode": "evidence_review",
                "summary": "Review the failing metadata gate evidence.",
                "checks": [],
                "evidence_expectations": ["The follow-up should fix the global docs gate."],
                "why_no_verification": None,
            },
            "status": "needs_revision",
            "summary": "The original service fix is done, but a broader docs metadata gate issue remains.",
            "checks_run": [],
            "evidence_used": ["raw_output:120 chars"],
            "reasoning": "The remaining work is broader than the original service-scoped requirement.",
            "suggested_next_action": "retry_execution",
            "resolution_recommendation": "create_followup_requirement",
            "resolution_confidence": 0.93,
            "resolution_reason": "The remaining fix is out of scope and should become a dedicated follow-up requirement.",
            "followup_requirement_payload": {
                "title": "修复 docs metadata gate 错误",
                "description_markdown": "Fix the broader docs metadata gate exposed during verification.",
                "priority": "high",
                "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network/docs-metadata",
                "scope_assessment": "out_of_scope",
                "ownership_change_required": False,
            },
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        },
    ):
        resp = synced_client.post(f"/api/executions/{run.id}/validate")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["verification_result"]["resolution_path"] == "create_followup_requirement"
    followup_requirement_id = payload["verification_result"]["followup_requirement_id"]
    assert followup_requirement_id is not None
    followup = db_session.query(RequirementRow).filter(RequirementRow.id == followup_requirement_id).one()
    assert followup.source == "verification_followup"
    assert followup.linked_requirement_id == requirement.id
    assert followup.origin_execution_run_id == run.id
    db_session.refresh(requirement)
    assert requirement.followup_requirement_id == followup_requirement_id
    assert requirement.resolution_path == "create_followup_requirement"


def test_validation_routes_followup_to_human_for_high_risk_requirement(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network",
        display_name="Synapse-Network",
        root_path="/Users/cliff/workspace/agent/Synapse-Network",
        repo_full_name="example/synapse-network",
    )
    requirement = RequirementRow(
        title="High risk requirement keeps human in the loop",
        description_markdown="High risk work should not auto-create follow-up requirements.",
        status="running",
        phase="executing",
        approval_status="approved",
        priority="high",
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
        status="running",
        phase="executing",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=True,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network"]',
    )
    db_session.add(run)
    db_session.flush()
    task = TaskRow(
        description="implement",
        agent_id="software_engineer",
        status="completed",
        priority="high",
        output_content="High risk fix exposed broader ownership changes.",
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

    with patch(
        "server.services.workflows.agent_first.verify_with_agent",
        return_value={
            "verification_plan": {
                "mode": "evidence_review",
                "summary": "Human should evaluate the broader ownership change.",
                "checks": [],
                "evidence_expectations": ["A human should confirm the scope expansion."],
                "why_no_verification": None,
            },
            "status": "needs_revision",
            "summary": "The remaining work is broader and high risk.",
            "checks_run": [],
            "evidence_used": ["raw_output:60 chars"],
            "reasoning": "The fix crosses ownership boundaries in a high-risk requirement.",
            "suggested_next_action": "retry_execution",
            "resolution_recommendation": "create_followup_requirement",
            "resolution_confidence": 0.94,
            "resolution_reason": "High-risk ownership changes should be reviewed by a human before branching further.",
            "followup_requirement_payload": {
                "title": "follow-up",
                "description_markdown": "follow-up",
                "scope_assessment": "out_of_scope",
                "ownership_change_required": True,
            },
            "verification_agent_id": "verification_agent",
            "verification_agent_label": "Verification Agent",
        },
    ):
        resp = synced_client.post(f"/api/executions/{run.id}/validate")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["verification_result"]["resolution_path"] == "route_to_human"
    assert payload["verification_result"]["followup_requirement_id"] is None


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

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "invalid_action"
    assert payload["reason"] == "not_startable"
    assert "cannot be started" in payload["message"]


def test_retry_execution_creates_new_run_and_auto_starts_replacement(synced_client, db_session):
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

    with patch("server.services.workflows.agent_first.prepare_requirement_delivery_branch", return_value=_branch_ready_payload("ops/req-1-retry-creates-a-new-execution")), patch(
        "server.services.workflows.agent_first.suggest_task_execution",
        return_value=TaskExecutionSuggestion(
            agent_id="software_engineer",
            skill_name="__direct_execution__",
            confidence=0.99,
            reason="test",
        ),
    ), patch("server.services.workflows.agent_first._load_full_persona", return_value="# persona"), patch(
        "server.services.workflows.agent_first.dispatch",
        return_value=None,
    ):
        resp = synced_client.post(f"/api/executions/{run.id}/retry")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["execution"]["id"] != run.id
    assert payload["execution"]["status"] == "running"
    db_session.refresh(run)
    assert run.status == "failed"
    assert db_session.query(ExecutionRunRow).filter(ExecutionRunRow.requirement_id == requirement.id).count() == 2
    historical_resp = synced_client.get(f"/api/executions/{int(run.id)}")
    assert historical_resp.status_code == 200
    assert historical_resp.json()["is_current_execution"] is False
    assert historical_resp.json()["allowed_actions"] == ["view", "view_requirement"]


def test_retry_execution_reports_queue_reason_when_auto_start_is_blocked(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Retry blocked by dirty worktree",
        description_markdown="Retry should explain why the replacement run cannot start.",
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
        status="blocked",
        phase="blocked",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add(run)
    db_session.commit()

    with patch(
        "server.services.workflows.agent_first.prepare_requirement_delivery_branch",
        return_value={
            "status": "blocked",
            "branch_name": "ops/req-1-retry-blocked",
            "base_branch": "main",
            "remote_name": "origin",
            "blockers": ["dirty worktree on `main` blocks automatic execution branch preparation"],
            "repositories": [],
        },
    ):
        resp = synced_client.post(f"/api/executions/{run.id}/retry")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["execution"]["id"] != run.id
    assert payload["execution"]["status"] == "queued"
    assert payload["queue_reason"].startswith("启动失败：")
    assert payload["blocking_reason_code"] == "branch_preparation_blocked"
    assert "dirty worktree" in payload["blocking_reason_message"]


def test_retry_execution_rejects_when_retry_budget_is_exhausted(synced_client, db_session):
    project = _create_project(
        synced_client,
        project_key="synapse-network-growing",
        display_name="Synapse-Network-Growing",
        root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        repo_full_name="cliff-personal/Synapse-Network-Growing",
    )
    requirement = RequirementRow(
        title="Retry limit is one",
        description_markdown="A requirement should not burn tokens by retrying forever.",
        status="blocked",
        phase="blocked",
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
    original_run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="failed",
        phase="blocked",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    retry_run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="blocked",
        phase="blocked",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        target_projects_json='["/Users/cliff/workspace/agent/Synapse-Network-Growing"]',
    )
    db_session.add_all([original_run, retry_run])
    db_session.commit()

    resp = synced_client.post(f"/api/executions/{retry_run.id}/retry")

    assert resp.status_code == 400
    assert "Execution retry limit reached (1)." in resp.json()["detail"]
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
    workflow_run = WorkflowRunRow(
        requirement_id=int(ready_requirement.id),
        plan_version=1,
        status="running",
        triggered_by="system",
    )
    db_session.add(workflow_run)
    db_session.flush()
    db_session.add(AgentRow(id="backend", display_name="Backend Agent", goal="Execute backend tasks"))
    db_session.flush()
    task = TaskRow(
        description="Implement reset runtime cleanup",
        agent_id="backend",
        status="completed",
        project_id="synapse-network-growing",
        runtime_backend="codex_cli",
        runtime_provider="openai",
        runtime_model="gpt-5.4",
    )
    db_session.add(task)
    db_session.flush()
    ready_requirement.active_workflow_run_id = int(workflow_run.id)
    db_session.add(
        ExecutionNodeRow(
            execution_run_id=int(run.id),
            requirement_id=int(ready_requirement.id),
            node_key="execute",
            node_type="execute",
            title="Execute requirement",
            status="completed",
            sequence_no=1,
            task_id=int(task.id),
        )
    )
    workflow_step = WorkflowStepRow(
        workflow_run_id=int(workflow_run.id),
        requirement_id=int(ready_requirement.id),
        step_key="execute",
        step_type="execute",
        title="Execute requirement",
        status="completed",
        sequence_no=1,
        compatibility_task_id=int(task.id),
    )
    db_session.add(workflow_step)
    db_session.flush()
    db_session.add(
        WorkflowStepDependencyRow(
            step_id=int(workflow_step.id),
            depends_on_step_id=int(workflow_step.id),
            dependency_kind="self",
        )
    )
    db_session.add(
        RequirementAcceptanceCheckRow(
            requirement_id=int(ready_requirement.id),
            check_key="verify-logs",
            description="Verify runtime logs are emitted.",
            check_type="command",
            owner_role="validator",
            status="passed",
            verified_by_step_id=int(workflow_step.id),
        )
    )
    db_session.add(
        ApprovalRow(
            task_id=int(task.id),
            status="approved",
            reviewer="operator",
        )
    )
    db_session.add(
        TaskLogRow(
            task_id=int(task.id),
            event_type="completed",
            detail="Task finished.",
        )
    )
    db_session.add(
        CodexSessionRow(
            session_key="sess-reset",
            role_key="backend",
            project_root="/Users/cliff/workspace/agent/Synapse-Network-Growing",
            requirement_id=int(ready_requirement.id),
            workflow_run_id=int(workflow_run.id),
            current_task_id=int(task.id),
            status="active",
            metadata_json="{}",
        )
    )
    db_session.add(
        ApprovalRequestRow(
            requirement_id=int(ready_requirement.id),
            workflow_run_id=int(workflow_run.id),
            step_id=int(workflow_step.id),
            approval_type="manual_gate",
            status="pending",
        )
    )
    db_session.add(
        WorkflowStepEventRow(
            step_id=int(workflow_step.id),
            event_type="step_started",
            detail="Started executing step.",
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
    assert summary["tasks_deleted"] == 1
    assert summary["task_logs_deleted"] == 1
    assert summary["approvals_deleted"] == 1
    assert summary["workflow_runs_deleted"] == 1
    assert summary["workflow_steps_deleted"] == 1
    assert summary["workflow_step_dependencies_deleted"] == 1
    assert summary["workflow_step_events_deleted"] == 1
    assert summary["acceptance_checks_deleted"] == 1
    assert summary["approval_requests_deleted"] == 1
    assert summary["codex_sessions_deleted"] == 1
    assert db_session.query(ExecutionRunRow).count() == 0
    assert db_session.query(ExecutionNodeRow).count() == 0
    assert db_session.query(ValidationRecordRow).count() == 0
    assert db_session.query(ReleaseRecordRow).count() == 0
    assert db_session.query(TaskRow).count() == 0
    assert db_session.query(TaskLogRow).count() == 0
    assert db_session.query(ApprovalRow).count() == 0
    assert db_session.query(WorkflowRunRow).count() == 0
    assert db_session.query(WorkflowStepRow).count() == 0
    assert db_session.query(WorkflowStepDependencyRow).count() == 0
    assert db_session.query(WorkflowStepEventRow).count() == 0
    assert db_session.query(RequirementAcceptanceCheckRow).count() == 0
    assert db_session.query(ApprovalRequestRow).count() == 0
    assert db_session.query(CodexSessionRow).count() == 0

    db_session.refresh(ready_requirement)
    db_session.refresh(blocked_requirement)
    assert ready_requirement.status == "ready"
    assert ready_requirement.active_workflow_run_id is None
    assert blocked_requirement.status == "blocked"


def _seed_execution_observability_fixture(db_session, tmp_path: Path) -> tuple[RequirementRow, ExecutionRunRow]:
    target_root = tmp_path / "target-project"
    target_root.mkdir(parents=True, exist_ok=True)
    changed_file = target_root / "src" / "feature.py"
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("print('after')\n", encoding="utf-8")

    output_dir = tmp_path / "task-output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "output.md"
    output_path.write_text("execution summary", encoding="utf-8")
    (output_dir / "file-changes.json").write_text(
        json.dumps(
            {
                "changed_files": [
                    {
                        "filename": "src/feature.py",
                        "additions": 3,
                        "deletions": 1,
                        "patch": "@@ -1 +1 @@\n-print('before')\n+print('after')\n",
                        "target_project_path": str(target_root),
                    }
                ],
                "target_project_path": str(target_root),
                "source": "snapshot",
                "captured_at": "2026-04-14T00:00:00Z",
                "baseline_captured_at": "2026-04-14T00:00:00Z",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    agent = AgentRow(
        id="execution_observability_agent",
        display_name="Software Engineer",
        goal="Implement and validate engineering changes.",
        group="engineering",
        skills='["execution"]',
    )
    requirement = RequirementRow(
        title="Execution observability fixture",
        description_markdown="Render runtime observability fields.",
        status="running",
        approval_status="approved",
        priority="normal",
        source="manual",
        project_key="synapse-network-growing",
        project_display_name="Synapse-Network-Growing",
        target_project_path=str(target_root),
        acceptance_contract_json=json.dumps(
            {
                "done_criteria": ["Runtime metrics are visible for the current execution run."],
                "verification_checks": [{"label": "Review execution detail runtime evidence", "kind": "evidence"}],
                "scope_constraints": ["Keep the change scoped to the execution detail surface."],
                "delivery_expectation": "Prepare a PR-ready branch when implementation is complete.",
                "markdown": "### Done Criteria\n- Runtime metrics are visible for the current execution run.",
            },
            ensure_ascii=False,
        ),
        execution_plan_json=json.dumps(
            {
                "planning_mode": "full_plan",
                "goal_summary": "Execution observability fixture",
                "summary_markdown": "## Goal\n\nExecution observability fixture\n\n## Planned Steps\n\n1. Add observability fields\n   - Done when: execution detail shows metrics, files, validation, and raw output.",
                "steps": [
                    {
                        "step_key": "add_observability_fields",
                        "title": "Add observability fields",
                        "step_type": "implementation",
                        "done_when": "execution detail shows metrics, files, validation, and raw output.",
                    }
                ],
                "planned_checks": ["Review execution detail output."],
                "risks": ["Avoid regressing execution detail loading."],
                "delivery_intent": "pr_required",
            },
            ensure_ascii=False,
        ),
    )
    db_session.add_all([agent, requirement])
    db_session.flush()

    started_at = utcnow()
    completed_at = utcnow()
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="running",
        validation_profile="minimal",
        delivery_intent="pr_required",
        approval_required=False,
        planner_summary="Direct execution fixture.",
        plan_snapshot_json=requirement.execution_plan_json,
        target_projects_json=json.dumps([str(target_root)]),
        started_at=started_at,
    )
    db_session.add(run)
    db_session.flush()

    task = TaskRow(
        description="Execute requirement",
        agent_id=agent.id,
        status="completed",
        runtime_backend="codex_cli",
        runtime_provider="openai",
        runtime_model="gpt-5.4",
        output_path=str(output_path),
        output_content="## Result\n\nApplied the requested change.\n\nCommands run:\n- `pytest tests/test_agent_first_api.py -q`",
        execution_time_ms=42000,
        tokens_used=321,
        project_id="synapse-network-growing",
        started_at=started_at,
        completed_at=completed_at,
    )
    db_session.add(task)
    db_session.flush()

    run.latest_task_id = int(task.id)
    node = ExecutionNodeRow(
        execution_run_id=int(run.id),
        requirement_id=int(requirement.id),
        node_key="execute",
        node_type="execute",
        title="Execute requirement",
        status="completed",
        sequence_no=1,
        task_id=int(task.id),
        runtime_backend="codex_cli",
        runtime_provider="openai",
        runtime_model="gpt-5.4",
        summary_markdown="Applied the requested change.",
        started_at=started_at,
        completed_at=completed_at,
    )
    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        execution_run_id=int(run.id),
        status="ready",
        branch_name="feature/execution-observability",
        compare_url="https://github.com/example/repo/compare/main...feature/execution-observability",
    )
    db_session.add_all([node, release])
    db_session.commit()
    return requirement, run


def test_execution_detail_exposes_runtime_observability_fields(synced_client, db_session, tmp_path):
    requirement, run = _seed_execution_observability_fixture(db_session, tmp_path)

    response = synced_client.get(f"/api/executions/{run.id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution"]["requirement_id"] == int(requirement.id)
    assert payload["execution"]["tokens_used_total"] == 321
    assert payload["execution"]["runtime_backend"] == "codex_cli"
    assert payload["execution"]["runtime_provider"] == "openai"
    assert payload["execution"]["runtime_model"] == "gpt-5.4"
    assert payload["execution"]["agent_id"] == "execution_observability_agent"
    assert payload["execution"]["agent_label"] == "Software Engineer"
    assert payload["execution"]["current_branch"] == "feature/execution-observability"
    assert payload["execution"]["elapsed_ms"] is not None
    assert payload["runtime_summary"]["tokens_used_total"] == 321
    assert payload["nodes"][0]["tokens_used"] == 321
    assert payload["nodes"][0]["agent_label"] == "Software Engineer"
    assert payload["changed_files"][0]["path"] == "src/feature.py"
    assert payload["changed_files"][0]["preview_available"] is True
    assert any(event["event"] == "run_created" for event in payload["activity_stream"])
    assert payload["delivery_summary"]["branch_name"] == "feature/execution-observability"
    assert payload["plan_summary"]["summary_markdown"]
    assert "Applied the requested change." in payload["raw_task_output"]
    assert payload["raw_task_output_truncated"] is False


def test_execution_file_preview_endpoint_returns_diff_and_current_content(synced_client, db_session, tmp_path):
    _, run = _seed_execution_observability_fixture(db_session, tmp_path)

    response = synced_client.get(f"/api/executions/{run.id}/files/src/feature.py")

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == "src/feature.py"
    assert "print('before')" in payload["diff_patch"]
    assert "print('after')" in payload["current_content"]
    assert payload["truncated"] is False


def test_direct_execution_task_uses_requirement_target_project_path(db_session):
    agent = AgentRow(
        id="software_engineer",
        display_name="Software Engineer",
        goal="Implement code changes safely.",
        group="engineering",
    )
    requirement = RequirementRow(
        title="Implement logging plan in target repo",
        description_markdown="Apply the requested logging changes in the target repository.",
        status="running",
        approval_status="approved",
        source="manual",
        priority="normal",
        project_key="synapse-network",
        project_display_name="Synapse-Network",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        acceptance_contract_json='{"markdown":"- verify logging output"}',
    )
    db_session.add_all([agent, requirement])
    db_session.flush()

    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="direct",
        complexity="simple",
        status="running",
        validation_profile="minimal",
        delivery_intent="pr_required",
    )
    db_session.add(run)
    db_session.flush()

    task = TaskRow(
        description="Execute requirement",
        agent_id=str(agent.id),
        status="running",
        priority="normal",
        runtime_backend="codex_cli",
    )
    db_session.add(task)
    db_session.flush()

    node = ExecutionNodeRow(
        execution_run_id=int(run.id),
        requirement_id=int(requirement.id),
        node_key="execute",
        node_type="execute",
        title="Execute requirement",
        status="running",
        sequence_no=1,
        task_id=int(task.id),
    )
    db_session.add(node)
    db_session.commit()
    db_session.refresh(task)

    assert _task_project_root(task) == "/Users/cliff/workspace/agent/Synapse-Network"
