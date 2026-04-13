from __future__ import annotations

"""Tests for requirement-first workflow orchestration."""
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import server.services.project_intelligence as project_intelligence
import server.services.portfolio_scheduler as portfolio_scheduler
import server.services.workflow_orchestrator as workflow_orchestrator
from server.database import (
    ApprovalRequestRow,
    ArtifactRow,
    BugRecordRow,
    CompanyOperatingReviewRow,
    OptimizationSignalRow,
    ProjectOnboardingRow,
    ProjectPolicyRow,
    RequirementAcceptanceCheckRow,
    RequirementRow,
    StepInputBindingRow,
    TaskRow,
    WorkflowRunRow,
    WorkflowStepEventRow,
    WorkflowStepRow,
)
from server.services.workflow_orchestrator import MAX_BUGFIX_BRANCH_DEPTH
from server.services.task_runner import _run_task_sync
from server.services.task_runtime import RuntimeEvent, TaskExecutionResult


def _runtime_result(*, text: str = "", error: str | None = None, execution_time_ms: int = 5, events=None):
    return TaskExecutionResult(
        text=text,
        files=[],
        error=error,
        execution_time_ms=execution_time_ms,
        runtime_backend="legacy",
        events=events or [],
        deferred=False,
    )


def _deferred_runtime_result(*, session_id: str = "session-running-123", execution_time_ms: int = 5, events=None):
    return TaskExecutionResult(
        text="",
        files=[],
        error=None,
        execution_time_ms=execution_time_ms,
        runtime_backend="copilot_sdk",
        runtime_session_id=session_id,
        events=events or [],
        deferred=True,
    )


def _sync_dispatch(task_id: int, agent_persona: dict, skill_name: str):
    _run_task_sync(task_id, agent_persona, skill_name)
    return MagicMock(name=f"task-{task_id}")


def test_requirement_workflow_runs_bugfix_loop_to_completion(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Launch FAQ quality gate",
            "description_markdown": "Validate the launch FAQ flow and keep iterating until validation passes.",
            "priority": "high",
            "approval_contract": {
                "approval_mode": "waived",
            },
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    planned = plan_resp.json()
    assert planned["requirement"]["current_plan_version"] == 1
    planned_step_types = [step["step_type"] for step in planned["workflow_run"]["steps"]]
    assert planned_step_types[:2] == ["research", "synthesis"]
    assert planned_step_types[-3:] == ["review", "test", "closeout"]
    assert "implementation" in planned_step_types

    call_counts = {"test": 0}

    class FakeRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:research]" in task_description:
                return _runtime_result(text="Research report ready for synthesis.")
            if "[workflow_step:synthesis]" in task_description:
                return _runtime_result(text="Synthesis report ready for implementation.")
            if "[workflow_step:implementation]" in task_description:
                return _runtime_result(text="Implementation output ready for review.")
            if "[workflow_step:review]" in task_description:
                return _runtime_result(text="Review passed and output is coherent.")
            if "[workflow_step:test]" in task_description:
                call_counts["test"] += 1
                if call_counts["test"] == 1:
                    return _runtime_result(error="Validation failed: issue reproduced in end-to-end check.")
                return _runtime_result(text="Validation passed after bugfix.")
            if "[workflow_step:bugfix]" in task_description:
                return _runtime_result(text="Bugfix applied to resolve the failed validation.")
            return _runtime_result(text="noop")

    with patch("server.services.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200, start_resp.json()
    data = start_resp.json()
    assert data["requirement"]["status"] == "done"
    assert data["workflow_run"]["status"] == "completed"

    step_types = [step["step_type"] for step in data["workflow_run"]["steps"]]
    assert step_types[:3] == ["research", "synthesis", "implementation"]
    assert step_types.count("bugfix") == 1
    assert step_types.count("review") == 2
    assert step_types.count("test") == 2
    assert step_types[-1] == "closeout"

    failed_test_steps = [step for step in data["workflow_run"]["steps"] if step["step_type"] == "test" and step["status"] == "failed"]
    assert len(failed_test_steps) == 1
    bugfix_steps = [step for step in data["workflow_run"]["steps"] if step["step_type"] == "bugfix"]
    assert bugfix_steps[0]["branch_from_step_id"] == failed_test_steps[0]["id"]

    assert {check["check_key"]: check["status"] for check in data["acceptance_checks"]} == {
        "review_passed": "passed",
        "validation_passed": "passed",
    }

    artifact_types = [artifact["artifact_type"] for artifact in data["artifacts"]]
    assert "delivery_contract" in artifact_types
    assert "delivery_state" in artifact_types
    assert "review_surface" in artifact_types
    assert "validation_plan" in artifact_types
    assert "bug_report" in artifact_types
    assert "validation_manifest" in artifact_types
    bug_report = next(artifact for artifact in data["artifacts"] if artifact["artifact_type"] == "bug_report")
    bug_payload = json.loads(bug_report["machine_readable_payload"])
    assert bug_payload["step_type"] == "test"
    assert bug_payload["verification_type"] == "automated"
    assert bug_payload["bugfix_owner_role"] == "implementer"
    assert bug_payload["failed_checks"][0]["check_key"] == "validation_passed"

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    assert requirement.status == "done"

    tasks = db_session.query(TaskRow).order_by(TaskRow.id.asc()).all()
    assert len(tasks) >= 6
    assert sum(1 for task in tasks if task.status == "failed") == 1
    assert sum(1 for task in tasks if task.status == "completed") == len(tasks) - 1

    closeout = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "closeout",
    ).first()
    assert closeout is not None
    assert closeout.status == "completed"
    assert data["delivery_state"]["publish_status"] == "review_ready"
    assert data["delivery_state"]["branch_name"].startswith(f"ops/req-{requirement_id}-")


def test_legacy_runtime_budget_points_do_not_trip_bugfix_loop_budget_guardrail():
    from server.services.task_runtime import estimate_runtime_budget_points

    assert estimate_runtime_budget_points(
        tier="standard",
        runtime_backend="legacy",
        execution_time_ms=5,
        tokens_used=0,
    ) == 2


def test_incident_research_task_routes_to_engineering_agent(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Incident Recovery: runtime failure",
            "description_markdown": "Stabilize the runtime incident and close the failure path.",
            "priority": "high",
            "source": "workflow_incident",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Capture runtime incident record",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Scope: Only produce documentation and a precise implementation plan.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    research_step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "research",
    ).first()
    task, persona, skill_name = workflow_orchestrator._prepare_step_task(db_session, research_step)

    assert task.agent_id == "dev_rel"
    assert skill_name == "__direct_execution__"
    assert persona["display_name"] == "Engineering Executor"
    assert "## Step" in task.description
    assert "Cached Context Profile" not in task.description
    assert len(task.description) < 2600


def test_incident_implementation_task_rewrites_legacy_docs_only_scope(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Incident Recovery: runtime failure",
            "description_markdown": "Stabilize the runtime incident and close the failure path.",
            "priority": "high",
            "source": "workflow_incident",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Capture runtime incident record",
                        "scope": "docs",
                        "depends_on": [],
                        "done_when": "SCOPE: Only produce documentation (runbooks, architecture docs, ops guides). Do NOT write implementation code in this step.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    implementation_step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "implementation",
    ).first()
    task, persona, skill_name = workflow_orchestrator._prepare_step_task(db_session, implementation_step)

    assert task.agent_id == "dev_rel"
    assert implementation_step.assigned_agent_id == "dev_rel"
    assert skill_name == "__direct_execution__"
    assert persona["display_name"] == "Engineering Executor"
    assert "Only produce documentation" not in task.description
    assert "Do NOT write implementation code in this step." not in task.description
    assert "## Delta" in task.description
    assert len(task.description) < 1500


def test_requirement_plan_can_be_edited_and_rebound(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Editable plan contract",
            "description_markdown": "Create a requirement and update the plan markdown after planning.",
            "priority": "normal",
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement editable contract",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Editable implementation is ready.",
                    }
                ]
            }
        ),
        42,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    planned_detail = plan_resp.json()
    delivery_contract = next(item for item in planned_detail["artifacts"] if item["artifact_type"] == "delivery_contract")
    assert "push the branch for review" in delivery_contract["human_readable_body"]

    patch_resp = synced_client.patch(
        f"/api/requirements/{requirement_id}/plan",
        json={"human_readable_body": "# Edited Plan\n\nOnly do the minimum safe change."},
    )
    assert patch_resp.status_code == 200
    detail = patch_resp.json()
    latest_plan = [a for a in detail["artifacts"] if a["artifact_type"] == "implementation_plan"][-1]
    assert latest_plan["human_readable_body"].startswith("# Edited Plan")
    payload = json.loads(latest_plan["machine_readable_payload"])
    assert payload["edited_markdown"].startswith("# Edited Plan")

    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.requirement_id == requirement_id).first()
    assert workflow_run is not None
    latest_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.workflow_run_id == workflow_run.id,
        ArtifactRow.artifact_type == "implementation_plan",
    ).order_by(ArtifactRow.id.desc()).first()
    assert latest_artifact is not None
    bindings = db_session.query(StepInputBindingRow).filter(
        StepInputBindingRow.purpose == "implementation_context",
    ).all()
    assert any(binding.artifact_id == latest_artifact.id for binding in bindings)


def test_workflow_step_edit_updates_pending_task_description(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Editable workflow step",
            "description_markdown": "Allow editing pending steps and sync them to pending tasks.",
            "priority": "normal",
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement original title",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Original done when text.",
                    }
                ]
            }
        ),
        42,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "implementation",
    ).first()
    assert step is not None
    task = TaskRow(
        description="old description",
        agent_id=str(step.assigned_agent_id or "dev_rel"),
        status="pending",
        requires_approval=False,
        priority="normal",
        project_id="synapse-network-growing",
        agent_group="growth",
        skill_name="content-strategy",
    )
    db_session.add(task)
    db_session.flush()
    step.compatibility_task_id = task.id
    db_session.commit()

    patch_resp = synced_client.patch(
        f"/api/requirements/{requirement_id}/workflow-steps/{step.id}",
        json={
            "title": "Implement edited title",
            "done_when_markdown": "Edited done when contract.",
            "handoff_summary_markdown": "Carry the incident context forward.",
        },
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    patched_step = next(item for item in body["workflow_run"]["steps"] if item["id"] == step.id)
    assert patched_step["title"] == "Implement edited title"
    assert patched_step["done_when_markdown"] == "Edited done when contract."

    db_session.refresh(task)
    assert "Implement edited title" in str(task.description or "")
    assert "Edited done when contract." in str(task.description or "")


def test_running_or_completed_workflow_step_cannot_be_edited(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Immutable running workflow step",
            "description_markdown": "Running steps should not be editable.",
            "priority": "normal",
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement guarded step",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Guard against edits while running.",
                    }
                ]
            }
        ),
        42,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{requirement_id}/plan")

    step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "implementation",
    ).first()
    assert step is not None
    step.status = "running"
    db_session.commit()

    patch_resp = synced_client.patch(
        f"/api/requirements/{requirement_id}/workflow-steps/{step.id}",
        json={"title": "Should fail"},
    )
    assert patch_resp.status_code == 400
    assert "cannot be edited" in patch_resp.json()["detail"].lower()


def test_workflow_step_can_be_edited_before_task_exists(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Editable step before task dispatch",
            "description_markdown": "Planning should allow edits even before compatibility tasks exist.",
            "priority": "normal",
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "research",
                        "title": "Research original title",
                        "scope": "analysis",
                        "depends_on": [],
                        "done_when": "Original research contract.",
                    }
                ]
            }
        ),
        42,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "research",
    ).first()
    assert step is not None
    assert step.compatibility_task_id is None

    patch_resp = synced_client.patch(
        f"/api/requirements/{requirement_id}/workflow-steps/{step.id}",
        json={
            "title": "Research edited title",
            "done_when_markdown": "Edited research contract.",
        },
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    patched_step = next(item for item in body["workflow_run"]["steps"] if item["id"] == step.id)
    assert patched_step["title"] == "Research edited title"
    assert patched_step["done_when_markdown"] == "Edited research contract."


def test_requirement_acceptance_contract_roundtrips_and_dispatches(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Acceptance-owned requirement",
            "description_markdown": "Implement and then let the acceptance owner review it.",
            "acceptance_contract": {
                "acceptance_owner_role": "tester",
                "review_owner_role": "reviewer",
                "acceptance_mode": "scheduled",
                "acceptance_trigger": "implementation_completed",
                "workflow_step_types": ["review", "test", "closeout"],
                "required_evidence_artifact_types": ["project_change_summary", "validation_plan"],
            },
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]
    assert create_resp.json()["requirement"]["acceptance_contract"]["acceptance_owner_role"] == "tester"

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement changes",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation is complete.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    assert plan_resp.json()["requirement"]["acceptance_contract"]["acceptance_trigger"] == "implementation_completed"

    run_id = plan_resp.json()["workflow_run"]["id"]
    steps = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == run_id
    ).order_by(WorkflowStepRow.sequence_no.asc()).all()
    for step in steps:
        if step.step_type in {"research", "synthesis", "implementation"}:
            step.status = "completed"
        else:
            step.status = "pending"
    run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == run_id).first()
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    run.status = "running"
    requirement.status = "in_progress"
    db_session.commit()

    dispatch_resp = synced_client.post(
        "/api/requirements/acceptance/dispatch",
        json={"limit": 10, "auto_dispatch": False},
    )
    assert dispatch_resp.status_code == 200
    payload = dispatch_resp.json()
    assert payload["scanned"] >= 1
    candidate = next(item for item in payload["candidates"] if item["requirement_id"] == requirement_id)
    assert candidate["step_type"] == "review"
    assert candidate["acceptance_owner_role"] == "reviewer"
    assert "validation_plan" in candidate["required_evidence_artifact_types"]


def test_requirement_plan_auto_approves_low_risk_execution(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Auto approve simple requirement",
            "description_markdown": "A small single-project change should auto approve.",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]
    assert create_resp.json()["requirement"]["approval_status"] == "pending_approval"

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement small change",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation is complete.",
                        "complexity_tier": "standard",
                    }
                ]
            }
        ),
        111,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    payload = plan_resp.json()
    assert payload["requirement"]["approval_status"] == "approved"
    pending = db_session.query(ApprovalRequestRow).filter(
        ApprovalRequestRow.requirement_id == requirement_id,
        ApprovalRequestRow.approval_type == "requirement_execution_approval",
        ApprovalRequestRow.status == "pending",
    ).count()
    assert pending == 0


def test_requirement_serialization_includes_approval_router_and_recommendation(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Approval router summary",
            "description_markdown": "Implement a small single-project change with a clear description so the approval layer can auto-approve it.",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement change",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation is complete.",
                        "complexity_tier": "standard",
                    }
                ]
            }
        ),
        111,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")

    assert plan_resp.status_code == 200
    requirement = plan_resp.json()["requirement"]
    assert requirement["approval_source"] == "auto"
    assert requirement["approval_router"]["approval_source"] == "auto"
    assert requirement["approval_recommendation"]["action"] == "approve"


def test_requirement_serialization_routes_incomplete_work_to_agent_review(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Too short",
            "description_markdown": "Short.",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
            "approval_contract": {
                "approval_mode": "auto_or_human",
                "auto_approve": {"enabled": False},
                "agent_review": {"enabled": True, "approval_role": "reviewer"},
            },
        },
    )
    assert create_resp.status_code == 201
    payload = create_resp.json()["requirement"]
    assert payload["approval_status"] == "pending_approval"
    assert payload["approval_source"] == "agent"
    assert payload["approval_recommendation"]["action"] == "revise"


def test_requirement_approval_auto_triggers_planning(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Approval should auto-plan",
            "description_markdown": "Approval should trigger planning without a separate plan button.",
            "priority": "high",
            "approval_contract": {
                "approval_mode": "manual_required",
                "required_approver_roles": ["request_owner", "reviewer", "tester"],
                "fallback_reviewer": "operator",
            },
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement after approval",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation is complete.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        approve_resp = synced_client.post(
            f"/api/requirements/{requirement_id}/approval/decide",
            json={"action": "approve", "reviewer": "cto", "comment": "Proceed"},
        )
    assert approve_resp.status_code == 200
    payload = approve_resp.json()
    assert payload["requirement"]["approval_status"] == "approved"
    assert payload["requirement"]["status"] == "ready"
    assert payload["requirement"]["current_plan_version"] == 1
    assert payload["workflow_run"]["plan_version"] == 1


def test_requirement_approval_accepts_null_comment(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Approval null comment compatibility",
            "description_markdown": "Requirement approval should accept a null comment payload.",
            "approval_contract": {"approval_mode": "manual_required"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement small change",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation is complete.",
                        "complexity_tier": "standard",
                    }
                ]
            }
        ),
        111,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        approve_resp = synced_client.post(
            f"/api/requirements/{requirement_id}/approval/decide",
            json={"action": "approve", "reviewer": "cto", "comment": None},
        )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["requirement"]["approval_status"] == "approved"


def test_requirement_approval_sets_plan_failed_when_auto_planning_fails(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Approval can fail planning",
            "description_markdown": "Planner failure should surface as plan_failed after approval.",
            "approval_contract": {"approval_mode": "manual_required"},
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    with patch("server.services.workflow_orchestrator.build_planner_output", side_effect=RuntimeError("planner unavailable")):
        approve_resp = synced_client.post(
            f"/api/requirements/{requirement_id}/approval/decide",
            json={"action": "approve", "reviewer": "cto", "comment": "Try plan"},
        )
    assert approve_resp.status_code == 200
    payload = approve_resp.json()
    assert payload["requirement"]["approval_status"] == "approved"
    assert payload["requirement"]["status"] == "plan_failed"
    assert payload["requirement"]["current_plan_version"] == 0
    assert any(artifact["artifact_type"] == "planning_failure" for artifact in payload["artifacts"])


def test_requirement_start_blocks_until_requirement_approval_then_runs(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Manual approval requirement",
            "description_markdown": "This one should wait for approval before execution.",
            "priority": "high",
            "approval_contract": {
                "approval_mode": "manual_required",
                "required_approver_roles": ["request_owner", "reviewer", "tester"],
                "fallback_reviewer": "operator",
            },
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    blocked_start = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert blocked_start.status_code == 400
    assert "approved before automatic execution" in blocked_start.json()["detail"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement manual gate change",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation is complete.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        approve_resp = synced_client.post(
            f"/api/requirements/{requirement_id}/approval/decide",
            json={"action": "approve", "reviewer": "cto", "comment": "Looks good"},
        )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["requirement"]["approval_status"] == "approved"
    assert approve_resp.json()["requirement"]["current_plan_version"] == 1

    class FakeRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:research]" in task_description:
                return _runtime_result(text="research ok")
            if "[workflow_step:synthesis]" in task_description:
                return _runtime_result(text="synthesis ok")
            if "[workflow_step:implementation]" in task_description:
                return _runtime_result(text="implementation ok")
            if "[workflow_step:review]" in task_description:
                return _runtime_result(text="review ok")
            if "[workflow_step:test]" in task_description:
                return _runtime_result(text="test ok")
            return _runtime_result(text="closeout ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "done"


def test_requirement_reject_sets_rejected_approval_status(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Rejectable requirement",
            "description_markdown": "Need explicit approval.",
            "approval_contract": {"approval_mode": "manual_required"},
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps({"steps": [{"step_key": "implementation", "title": "Implement", "scope": "backend", "depends_on": [], "done_when": "Done."}]}),
        99,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{requirement_id}/plan")
    reject_resp = synced_client.post(
        f"/api/requirements/{requirement_id}/approval/decide",
        json={"action": "reject", "reviewer": "request_owner", "comment": "Needs refinement"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["requirement"]["approval_status"] == "rejected"
    assert reject_resp.json()["requirement"]["status"] == "blocked"


def test_scheduler_excludes_pending_requirement_approvals(synced_client, db_session):
    manual_required = synced_client.post(
        "/api/requirements",
        json={
            "title": "Pending approval backlog item",
            "description_markdown": "Should not be scheduled before requirement approval.",
            "approval_contract": {"approval_mode": "manual_required"},
        },
    )
    assert manual_required.status_code == 201
    approved = synced_client.post(
        "/api/requirements",
        json={
            "title": "Auto approved backlog item",
            "description_markdown": "Can be scheduled.",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )
    assert approved.status_code == 201

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps({"steps": [{"step_key": "implementation", "title": "Implement", "scope": "backend", "depends_on": [], "done_when": "Done."}]}),
        77,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{manual_required.json()['requirement']['id']}/plan")
        synced_client.post(f"/api/requirements/{approved.json()['requirement']['id']}/plan")

    scheduler_resp = synced_client.get("/api/requirements/scheduler")
    assert scheduler_resp.status_code == 200
    titles = [item["title"] for item in scheduler_resp.json()["decisions"]]
    assert "Auto approved backlog item" in titles
    assert "Pending approval backlog item" not in titles


def test_requirement_source_registry_lists_sources_and_counts(synced_client, db_session):
    db_session.add(
        RequirementRow(
            title="Manual backlog item",
            description_markdown="Operator-created requirement.",
            status="ready",
            priority="normal",
            source="manual",
            source_ref="manual:1",
            intake_metadata_json=json.dumps(
                {
                    "source_key": "manual",
                    "intake_reason": "operator_created_requirement",
                    "confidence": 1.0,
                }
            ),
        )
    )
    db_session.add(
        OptimizationSignalRow(
            dedupe_key="signal-1",
            signal_type="bug_report",
            source_kind="artifact",
            status="open",
            title="Repeated bug",
            summary="Repeated bug report",
            confidence=0.9,
        )
    )
    db_session.add(
        BugRecordRow(
            bug_key="manual_bug_report::synapse-network::fp_bug1",
            source_key="manual_bug_report",
            source_kind="manual_input",
            status="open",
            title="Gateway readiness failure",
            summary="Readiness endpoint returns 500.",
            severity="high",
            fingerprint="fp_bug1",
            project_key="synapse-network",
            project_root_path="/Users/cliff/workspace/agent/Synapse-Network",
            source_ref="bug:1",
            occurrence_count=3,
            evidence_json="[]",
            metadata_json="{}",
            scorecard_json=json.dumps({"total": 82.0, "priority": "high", "auto_intake_eligible": True}),
        )
    )
    db_session.add(
        CompanyOperatingReviewRow(
            cycle_label="2026-W15",
            title="Weekly review",
            summary_markdown="Weekly review summary",
            payload_json=json.dumps(
                {
                    "automation_candidates": [
                        {
                            "candidate_key": "automation:gate-1",
                            "title": "Automate publish gate",
                            "automation_type": "publish_automation",
                            "priority": "high",
                            "occurrence_count": 3,
                        }
                    ],
                    "next_cycle_requirement_bundle": [
                        {
                            "bundle_item_key": "bundle-1",
                            "title": "Bundle requirement",
                            "description_markdown": "Create from bundle",
                            "priority": "high",
                            "source_ref": "signal:bundle-1",
                        }
                    ]
                }
            ),
        )
    )
    db_session.commit()

    response = synced_client.get("/api/requirements/sources")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requirements"] == 1
    by_key = {item["source_key"]: item for item in data["sources"]}
    assert by_key["manual"]["requirement_count"] == 1
    assert by_key["optimization_signal"]["open_candidate_count"] == 1
    assert by_key["optimization_signal"]["intake_supported"] is True
    assert by_key["company_review_bundle"]["open_candidate_count"] == 1
    assert by_key["company_review_bundle"]["latest_review_id"] is not None
    assert by_key["automation_candidate"]["open_candidate_count"] == 1
    assert by_key["automation_candidate"]["intake_supported"] is True
    assert by_key["automation_candidate"]["latest_review_id"] is not None
    assert by_key["bug_intake"]["open_candidate_count"] == 1
    assert by_key["bug_intake"]["intake_supported"] is True


def test_requirement_source_intake_endpoint_aggregates_sources(synced_client):
    with patch("server.services.optimization_signals.refresh_optimization_signals"), patch(
        "server.services.optimization_signals.auto_intake_optimization_signals",
        return_value={
            "created": [{"signal_id": 7, "requirement_id": 71, "title": "From signal", "score": 88.0}],
            "skipped": ["signal #8 below threshold"],
        },
    ), patch(
        "server.services.company_review.refresh_company_operating_review",
        return_value=MagicMock(id=12),
    ), patch(
        "server.services.company_review.materialize_company_review_bundle",
        return_value=MagicMock(
            created_requirement_ids=[81],
            reused_requirement_ids=[82],
            skipped_bundle_item_keys=["bundle-3"],
            model_dump=lambda: {
                "review_id": 12,
                "created_requirement_ids": [81],
                "reused_requirement_ids": [82],
                "skipped_bundle_item_keys": ["bundle-3"],
                "items": [],
            },
        ),
    ), patch(
        "server.services.company_review.materialize_company_review_automation_candidates",
        return_value=MagicMock(
            created_requirement_ids=[91],
            reused_requirement_ids=[92],
            skipped_bundle_item_keys=["automation:gate-3"],
            model_dump=lambda: {
                "review_id": 12,
                "created_requirement_ids": [91],
                "reused_requirement_ids": [92],
                "skipped_bundle_item_keys": ["automation:gate-3"],
                "items": [],
            },
        ),
    ), patch(
        "server.services.requirement_sources.materialize_bug_backlog",
        return_value={
            "created_requirement_ids": [101],
            "reused_requirement_ids": [102],
            "skipped": ["bug #5 below threshold"],
            "items": [],
        },
    ):
        response = synced_client.post(
            "/api/requirements/intake",
            json={
                "source_key": "all",
                "refresh": True,
                "auto_start": False,
                "min_score": 70,
                "max_created": 2,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["executed_sources"] == ["optimization_signal", "company_review_bundle", "automation_candidate", "bug_intake"]
    assert data["created_requirement_ids"] == [71, 81, 91, 101]
    assert data["reused_requirement_ids"] == [82, 92, 102]
    assert "signal #8 below threshold" in data["skipped"]
    assert "bug #5 below threshold" in data["skipped"]
    by_source = {item["source_key"]: item for item in data["items"]}
    assert by_source["optimization_signal"]["created_requirement_ids"] == [71]
    assert by_source["company_review_bundle"]["created_requirement_ids"] == [81]
    assert by_source["automation_candidate"]["created_requirement_ids"] == [91]
    assert by_source["bug_intake"]["created_requirement_ids"] == [101]


def test_requirement_intake_metadata_roundtrips(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Requirement with intake metadata",
            "description_markdown": "Track why this requirement entered the pool.",
            "priority": "normal",
            "source": "manual",
            "source_ref": "manual:brief-1",
            "intake_metadata": {
                "intake_reason": "weekly_ops_review",
                "confidence": 0.93,
                "intake_mode": "operator",
            },
        },
    )
    assert create_resp.status_code == 201
    requirement = create_resp.json()["requirement"]
    assert requirement["intake_metadata"]["source_key"] == "manual"
    assert requirement["intake_metadata"]["intake_reason"] == "weekly_ops_review"
    assert requirement["intake_metadata"]["confidence"] == 0.93


def test_requirement_source_intake_materializes_automation_candidates_from_company_review(synced_client, db_session):
    db_session.add(
        CompanyOperatingReviewRow(
            cycle_label="2026-W16",
            title="Weekly review",
            summary_markdown="Weekly review summary",
            payload_json=json.dumps(
                {
                    "automation_candidates": [
                        {
                            "candidate_key": "automation:publish-gate",
                            "title": "Automate publish gate",
                            "gate_key": "publish_manual_gate::publish::synapse-network",
                            "project_key": "synapse-network",
                            "project_display_name": "Synapse-Network",
                            "automation_type": "publish_automation",
                            "priority": "high",
                            "rationale": "Reduce repeated publish approvals.",
                            "occurrence_count": 4,
                        }
                    ],
                    "operator_review_package": {
                        "title": "Operator Review Package",
                    },
                }
            ),
        )
    )
    db_session.commit()

    response = synced_client.post(
        "/api/requirements/intake",
        json={
            "source_key": "automation_candidate",
            "refresh": False,
            "auto_start": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["executed_sources"] == ["automation_candidate"]
    assert len(data["created_requirement_ids"]) == 1
    requirement_id = data["created_requirement_ids"][0]

    detail = synced_client.get(f"/api/requirements/{requirement_id}")
    assert detail.status_code == 200
    payload = detail.json()["requirement"]
    assert payload["source"] == "automation_candidate"
    assert payload["intake_metadata"]["source_key"] == "automation_candidate"
    assert payload["intake_metadata"]["trigger"] == "company_review_materialize_automation_candidate"


def test_requirement_source_intake_materializes_bug_backlog(synced_client, db_session):
    db_session.add(
        ProjectPolicyRow(
            project_key="synapse-network-bugtest",
            display_name="Synapse Network Bug Test",
            root_path="/Users/cliff/workspace/agent/Synapse-Network",
            status="active",
            allowed_write_globs_json='["**"]',
            forbidden_globs_json='[".git/**"]',
            required_checks_json="[]",
            release_mode="manual",
            requires_manual_approval=True,
        )
    )
    bug_row = BugRecordRow(
        bug_key="manual_bug_report::synapse-network-bugtest::fp_bugx",
        source_key="manual_bug_report",
        source_kind="manual_input",
        status="open",
        title="Gateway readiness 500",
        summary="Readiness endpoint returns 500 for healthy traffic.",
        severity="high",
        fingerprint="fp_bugx",
        project_key="synapse-network-bugtest",
        project_root_path="/Users/cliff/workspace/agent/Synapse-Network",
        source_ref="sentry:bugx",
        occurrence_count=4,
        evidence_json=json.dumps(
            [
                {
                    "source_ref": "sentry:bugx",
                    "environment": "prod",
                    "log_excerpt": "GET /readyz -> 500",
                }
            ]
        ),
        metadata_json=json.dumps({"component": "gateway"}),
        scorecard_json=json.dumps(
            {
                "total": 86.0,
                "priority": "high",
                "auto_intake_eligible": True,
                "blocker_flags": ["explicit_blocker"],
            }
        ),
    )
    db_session.add(bug_row)
    db_session.flush()
    bug_id = int(bug_row.id)
    db_session.commit()

    response = synced_client.post(
        "/api/requirements/intake",
        json={
            "source_key": "bug_intake",
            "refresh": False,
            "auto_start": False,
            "min_score": 60,
            "max_created": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["executed_sources"] == ["bug_intake"]
    assert len(data["created_requirement_ids"]) == 1
    requirement_id = data["created_requirement_ids"][0]

    detail = synced_client.get(f"/api/requirements/{requirement_id}")
    assert detail.status_code == 200
    payload = detail.json()["requirement"]
    assert payload["source"] == "bug_intake"
    assert payload["source_ref"] == f"bug-intake:{bug_id}"
    assert payload["intake_metadata"]["source_key"] == "bug_intake"
    assert payload["intake_metadata"]["trigger"] == "bug_backlog_materialize"
    assert payload["intake_metadata"]["scorecard_priority"] == "high"
    assert "explicit_blocker" in payload["intake_metadata"]["blocker_flags"]
    assert "/Users/cliff/workspace/agent/Synapse-Network" in str(payload["target_project_path"])
    assert payload["approval_contract"]["approval_mode"] == "manual_required"
    assert "operator" in payload["approval_contract"]["required_approver_roles"]
    assert payload["approval_status"] == "pending_approval"

    bug_row = db_session.query(BugRecordRow).filter(BugRecordRow.id == bug_id).first()
    assert bug_row.converted_requirement_id == requirement_id
    assert bug_row.status == "converted"


def test_requirement_source_intake_reuses_similar_active_bug_requirement(synced_client, db_session):
    existing = RequirementRow(
        title="Bug Fix: Runtime log error",
        description_markdown="Bug Intake: Runtime log error\n\nAUTOBUG-LIVE-VERIFY-########-#### gateway readiness live verification failure",
        status="pending_approval",
        priority="high",
        source="bug_intake",
        source_ref="bug-intake:1",
        current_plan_version=1,
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
        intake_metadata_json=json.dumps(
            {
                "source_key": "bug_intake",
                "bug_signature": "autobug-live-verify-########-#### gateway readiness live verification failure",
            }
        ),
    )
    db_session.add(existing)
    db_session.flush()

    bug_row = BugRecordRow(
        bug_key="runtime_log_error::synapse-network::fp-livecheck",
        source_key="runtime_log_error",
        source_kind="runtime_log",
        status="open",
        title="Runtime log error",
        summary="AUTOBUG-LIVE-VERIFY-20260412-1940 gateway readiness live verification failure",
        severity="high",
        fingerprint="fp-livecheck",
        project_key="synapse-network",
        project_root_path="/Users/cliff/workspace/agent/Synapse-Network",
        source_ref="log:ops-dashboard.log",
        occurrence_count=4,
        evidence_json=json.dumps(
            [
                {
                    "log_excerpt": "2026-04-12 20:33:42 [ERROR] ops-dashboard.livecheck: AUTOBUG-LIVE-VERIFY-20260412-1940 gateway readiness live verification failure",
                    "summary": "AUTOBUG-LIVE-VERIFY-20260412-1940 gateway readiness live verification failure",
                }
            ]
        ),
        metadata_json=json.dumps({}),
        scorecard_json=json.dumps(
            {
                "total": 79.0,
                "priority": "high",
                "auto_intake_eligible": True,
                "blocker_flags": [],
            }
        ),
    )
    db_session.add(bug_row)
    db_session.commit()

    response = synced_client.post(
        "/api/requirements/intake",
        json={"source_key": "bug_intake", "refresh": False, "auto_start": False, "min_score": 60, "max_created": 1},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["created_requirement_ids"] == []
    assert payload["reused_requirement_ids"] == [int(existing.id)]
    db_session.refresh(bug_row)
    assert bug_row.converted_requirement_id == existing.id
    assert bug_row.status == "converted"


def test_bug_intake_requirement_plan_includes_bug_validation_contract(synced_client, db_session):
    bug_row = BugRecordRow(
        bug_key="manual_bug_report::synapse-network-bugtest::fp_bugplan",
        source_key="manual_bug_report",
        source_kind="manual_input",
        status="open",
        title="Gateway readiness 500",
        summary="Readiness endpoint returns 500 for healthy traffic.",
        severity="high",
        fingerprint="fp_bugplan",
        project_key="synapse-network-growing",
        project_root_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        source_ref="sentry:bugplan",
        occurrence_count=2,
        evidence_json=json.dumps(
            [
                {
                    "source_ref": "sentry:bugplan",
                    "environment": "prod",
                    "log_excerpt": "GET /readyz -> 500",
                }
            ]
        ),
        metadata_json=json.dumps({"component": "ops-dashboard"}),
        scorecard_json=json.dumps(
            {
                "total": 78.0,
                "priority": "high",
                "auto_intake_eligible": True,
            }
        ),
    )
    db_session.add(bug_row)
    db_session.flush()
    bug_id = int(bug_row.id)
    db_session.commit()

    intake_resp = synced_client.post(
        "/api/requirements/intake",
        json={
            "source_key": "bug_intake",
            "refresh": False,
            "auto_start": False,
            "min_score": 60,
            "max_created": 1,
        },
    )
    assert intake_resp.status_code == 200
    requirement_id = intake_resp.json()["created_requirement_ids"][0]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement bug fix",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Bug fix is implemented.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")

    assert plan_resp.status_code == 200
    data = plan_resp.json()
    acceptance_keys = {item["check_key"] for item in data["acceptance_checks"]}
    assert {
        "root_cause_documented",
        "bug_evidence_bound",
        "fix_applied",
        "regression_guard_added",
        "bug_verification_passed",
    } <= acceptance_keys
    validation_artifact = next(
        artifact for artifact in data["artifacts"] if artifact["artifact_type"] == "validation_plan"
    )
    validation_payload = json.loads(validation_artifact["machine_readable_payload"])
    automated_keys = {item["check_key"] for item in validation_payload["automated_checks"]}
    assert {"fix_applied", "regression_guard_added", "bug_verification_passed"} <= automated_keys
    assert "bug-derived requirements" in validation_payload["summary_markdown"]
    assert data["requirement"]["source_ref"] == f"bug-intake:{bug_id}"


def test_cross_project_bug_backlog_materializes_multi_project_requirement(synced_client, db_session):
    db_session.add_all(
        [
            ProjectPolicyRow(
                project_key="synapse-network",
                display_name="Synapse Network",
                root_path="/Users/cliff/workspace/agent/Synapse-Network",
                status="active",
                allowed_write_globs_json='["**"]',
                forbidden_globs_json='[".git/**"]',
                required_checks_json="[]",
                release_mode="manual",
                requires_manual_approval=True,
            ),
            ProjectPolicyRow(
                project_key="synapse-network-provider",
                display_name="Synapse Network Provider",
                root_path="/Users/cliff/workspace/agent/Synapse-Network-Provider",
                status="active",
                allowed_write_globs_json='["**"]',
                forbidden_globs_json='[".git/**"]',
                required_checks_json="[]",
                release_mode="manual",
                requires_manual_approval=True,
            ),
        ]
    )
    bug_row = BugRecordRow(
        bug_key="workflow_incident::multi::fp-cross-project",
        source_key="workflow_incident",
        source_kind="signal",
        status="open",
        title="Provider auth desync",
        summary="Failure path crosses core product and provider runtime.",
        severity="high",
        fingerprint="fp-cross-project",
        project_key="synapse-network",
        project_root_path="/Users/cliff/workspace/agent/Synapse-Network",
        source_ref="incident:auth-desync",
        occurrence_count=4,
        evidence_json=json.dumps([{"log_excerpt": "provider auth mismatch"}]),
        metadata_json=json.dumps(
            {
                "affected_project_keys": ["synapse-network", "synapse-network-provider"],
                "affected_project_root_paths": [
                    "/Users/cliff/workspace/agent/Synapse-Network",
                    "/Users/cliff/workspace/agent/Synapse-Network-Provider",
                ],
            }
        ),
        scorecard_json=json.dumps(
            {
                "total": 88.0,
                "priority": "high",
                "auto_intake_eligible": True,
                "blocker_flags": ["workflow_incident"],
            }
        ),
    )
    db_session.add(bug_row)
    db_session.commit()

    response = synced_client.post(
        "/api/requirements/intake",
        json={"source_key": "bug_intake", "refresh": False, "auto_start": False, "min_score": 60, "max_created": 1},
    )
    assert response.status_code == 200
    requirement_id = response.json()["created_requirement_ids"][0]

    detail = synced_client.get(f"/api/requirements/{requirement_id}")
    assert detail.status_code == 200
    payload = detail.json()["requirement"]
    assert payload["target_project_path"].splitlines() == [
        "/Users/cliff/workspace/agent/Synapse-Network",
        "/Users/cliff/workspace/agent/Synapse-Network-Provider",
    ]
    assert payload["intake_metadata"]["cross_project_recovery"] is True
    assert payload["intake_metadata"]["affected_project_keys"] == [
        "synapse-network",
        "synapse-network-provider",
    ]
    assert payload["approval_contract"]["approval_mode"] == "manual_required"


def test_requirement_keeps_target_project_order_and_records_dynamic_project_change_summary(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Defect Reduction: Synapse-Network API regression",
            "description_markdown": "修复 Synapse-Network API 缺陷，并让模型自行决定需要改动哪些目标项目与验证方式。",
            "priority": "high",
            "approval_contract": {
                "approval_mode": "waived",
            },
            "target_project_path": (
                "/Users/cliff/workspace/agent/Synapse-Network-Growing\n"
                "/Users/cliff/workspace/agent/Synapse-Network"
            ),
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Apply planned changes",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Apply requirement changes across configured target projects.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    class FakeRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:research]" in task_description:
                assert "Target project path: /Users/cliff/workspace/agent/Synapse-Network-Growing" in task_description
                return _runtime_result(text="Research report ready.")
            if "[workflow_step:synthesis]" in task_description:
                return _runtime_result(text="Synthesis report ready.")
            if "[workflow_step:implementation]" in task_description:
                assert "Target project path: /Users/cliff/workspace/agent/Synapse-Network-Growing" in task_description
                return _runtime_result(text="Implemented API fix across configured target projects.")
            if "[workflow_step:review]" in task_description:
                return _runtime_result(text="Review passed.")
            if "[workflow_step:test]" in task_description:
                return _runtime_result(text="Validation passed with regression coverage.")
            return _runtime_result(text="noop")

    def _write_code_snapshot(_db, task, _requirement, step=None):
        if not task.output_path:
            task.output_path = f"/tmp/req-{requirement_id}-task-{task.id}/output.md"
        output_path = Path(str(task.output_path or ""))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        (output_path.parent / "file-changes.json").write_text(
            json.dumps(
                {
                    "changed_files": [
                        {
                            "filename": "server/routes/requirements.py",
                            "additions": 12,
                            "deletions": 1,
                            "patch": "@@\n+code\n",
                            "target_project_path": workflow_orchestrator.PRIMARY_GROWING_PROJECT,
                        },
                        {
                            "filename": "services/gateway/src/app.py",
                            "additions": 9,
                            "deletions": 0,
                            "patch": "@@\n+code\n",
                            "target_project_path": workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
                        }
                    ],
                    "target_project_path": workflow_orchestrator.PRIMARY_GROWING_PROJECT,
                    "changed_target_project_paths": [
                        workflow_orchestrator.PRIMARY_GROWING_PROJECT,
                        workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
                    ],
                    "project_snapshots": [
                        {
                            "target_project_path": workflow_orchestrator.PRIMARY_GROWING_PROJECT,
                            "changed_file_count": 1,
                            "changed_files": [
                                {
                                    "filename": "server/routes/requirements.py",
                                    "additions": 12,
                                    "deletions": 1,
                                    "patch": "@@\n+code\n",
                                    "target_project_path": workflow_orchestrator.PRIMARY_GROWING_PROJECT,
                                }
                            ],
                            "project_policy_summary": "Growing checks: pytest -q",
                        },
                        {
                            "target_project_path": workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
                            "changed_file_count": 1,
                            "changed_files": [
                                {
                                    "filename": "services/gateway/src/app.py",
                                    "additions": 9,
                                    "deletions": 0,
                                    "patch": "@@\n+code\n",
                                    "target_project_path": workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
                                }
                            ],
                            "project_policy_summary": "Synapse checks: npm test",
                        },
                    ],
                    "all_target_project_paths": [
                        workflow_orchestrator.PRIMARY_GROWING_PROJECT,
                        workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
                    ],
                        "source": "snapshot",
                        "baseline_captured_at": "2026-04-12T14:18:54Z",
                        "task_id": int(task.id),
                        "step_id": int(step.id) if step is not None else None,
                    },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    with patch("server.services.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ), patch(
        "server.services.workflow_orchestrator._snapshot_file_changes", side_effect=_write_code_snapshot
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["requirement"]["status"] == "done"
    assert data["requirement"]["target_project_path"].splitlines()[0] == workflow_orchestrator.PRIMARY_GROWING_PROJECT
    artifact_types = [artifact["artifact_type"] for artifact in data["artifacts"]]
    assert "project_change_summary" in artifact_types
    project_change_summary = next(
        artifact for artifact in reversed(data["artifacts"]) if artifact["artifact_type"] == "project_change_summary"
    )
    project_payload = json.loads(project_change_summary["machine_readable_payload"])
    assert project_payload["changed_target_project_paths"] == [
        workflow_orchestrator.PRIMARY_GROWING_PROJECT,
        workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
    ]
    dynamic_validation_plan = next(
        artifact for artifact in reversed(data["artifacts"]) if artifact["artifact_type"] == "validation_plan"
    )
    validation_payload = json.loads(dynamic_validation_plan["machine_readable_payload"])
    assert validation_payload["validation_mode"] == "dynamic_by_project_change_summary"
    assert [item["root_path"] for item in validation_payload["affected_projects"]] == [
        workflow_orchestrator.PRIMARY_GROWING_PROJECT,
        workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
    ]
    assert validation_payload["dynamic_required_checks"] == [
        "/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q",
        "cd dashboard && npm test",
        "cd dashboard && npm run build",
        "npm test",
        "pytest",
    ]
    dynamic_delivery_contract = next(
        artifact for artifact in reversed(data["artifacts"]) if artifact["artifact_type"] == "delivery_contract"
    )
    delivery_payload = json.loads(dynamic_delivery_contract["machine_readable_payload"])
    assert delivery_payload["required_checks"] == validation_payload["dynamic_required_checks"]
    assert [item["root_path"] for item in delivery_payload["affected_projects"]] == [
        workflow_orchestrator.PRIMARY_GROWING_PROJECT,
        workflow_orchestrator.PRIMARY_SYNAPSE_PROJECT,
    ]
    assert len(data["task_outputs"]) >= 1
    implementation_output = next(item for item in data["task_outputs"] if item["step_type"] == "implementation")
    assert implementation_output["output_files"]
    assert any(file["filename"] == "server/routes/requirements.py" for file in implementation_output["changed_files"])
    assert any(item["file_name"] == "server/routes/requirements.py" for item in data["merged_output_files"])
    assert data["delivery_state"]["required_checks"] == validation_payload["dynamic_required_checks"]
    latest_test_artifact = next(
        artifact for artifact in reversed(data["artifacts"]) if artifact["artifact_type"] == "test_report"
    )
    payload = json.loads(latest_test_artifact["machine_readable_payload"])
    assert payload["runtime_backend"] == "legacy"


def test_requirement_bugfix_loop_circuit_breaks_on_repeated_identical_errors(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Stop repeated session resume loop",
            "description_markdown": "Circuit break when the same bugfix error repeats.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    repeated_error = (
        "Request session.resume failed with message: "
        "Session not found: role-seo_strategist-1775919011484-1"
    )

    class FakeRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:research]" in task_description:
                return _runtime_result(text="Research output ready.")
            if "[workflow_step:synthesis]" in task_description:
                return _runtime_result(text="Synthesis output ready.")
            if "[workflow_step:review]" in task_description or "[workflow_step:test]" in task_description:
                return _runtime_result(text="not reached")
            if "[workflow_step:implementation]" in task_description or "[workflow_step:bugfix]" in task_description:
                return _runtime_result(error=repeated_error)
            return _runtime_result(text="noop")

    with patch("server.services.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["requirement"]["status"] == "needs_revision"
    assert data["workflow_run"]["status"] == "cancelled"
    assert any(item["incident_code"] == "bugfix_circuit_breaker" for item in data["incidents"])

    bugfix_steps = [step for step in data["workflow_run"]["steps"] if step["step_type"] == "bugfix"]
    assert len(bugfix_steps) == 2
    assert all(step["status"] == "failed" for step in bugfix_steps)

    breaker_artifact = next(
        artifact for artifact in data["artifacts"] if artifact["artifact_type"] == "bugfix_circuit_breaker"
    )
    breaker_payload = json.loads(breaker_artifact["machine_readable_payload"])
    assert "Repeated identical failure detected" in breaker_payload["reason"]
    assert breaker_payload["failed_step_id"] == bugfix_steps[-1]["id"]
    assert {item["kind"] for item in breaker_payload["followup_requirements"]} == {"operator_review", "infra_incident"}

    tasks = db_session.query(TaskRow).order_by(TaskRow.id.asc()).all()
    assert len(tasks) == 5
    assert sum(1 for task in tasks if task.status == "completed") == 2
    assert sum(1 for task in tasks if task.status == "failed") == 3
    followups = db_session.query(RequirementRow).filter(
        RequirementRow.source == "bugfix_circuit_breaker"
    ).order_by(RequirementRow.id.asc()).all()
    assert len(followups) == 2
    assert followups[0].title.startswith("Operator Review:")
    assert followups[1].title.startswith("Infra Incident:")
    assert "/Users/cliff/workspace/agent/Synapse-Network-Growing" in str(followups[1].target_project_path)


def test_requirement_bugfix_loop_circuit_breaks_on_depth_limit(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Stop deep bugfix chains",
            "description_markdown": "Circuit break when bugfix depth grows too large.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    error_messages = iter(
        [
            "Validation failed: branch alpha",
            "Validation failed: branch beta",
            "Validation failed: branch gamma",
            "Validation failed: branch delta",
            "Validation failed: branch epsilon",
            "Validation failed: branch zeta",
        ]
    )

    class FakeRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:research]" in task_description:
                return _runtime_result(text="Research report complete.")
            if "[workflow_step:synthesis]" in task_description:
                return _runtime_result(text="Synthesis report complete.")
            if "[workflow_step:implementation]" in task_description:
                return _runtime_result(text="Implementation complete.")
            if "[workflow_step:review]" in task_description:
                return _runtime_result(text="Review complete.")
            if "[workflow_step:bugfix]" in task_description:
                return _runtime_result(text="Bugfix applied.")
            if "[workflow_step:test]" in task_description:
                return _runtime_result(error=next(error_messages))
            return _runtime_result(text="noop")

    with patch("server.services.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["requirement"]["status"] == "needs_revision"
    assert data["workflow_run"]["status"] == "cancelled"

    bugfix_steps = [step for step in data["workflow_run"]["steps"] if step["step_type"] == "bugfix"]
    assert len(bugfix_steps) == MAX_BUGFIX_BRANCH_DEPTH

    breaker_artifact = next(
        artifact for artifact in data["artifacts"] if artifact["artifact_type"] == "bugfix_circuit_breaker"
    )
    breaker_payload = json.loads(breaker_artifact["machine_readable_payload"])
    assert "Bugfix loop depth exceeded" in breaker_payload["reason"]
    assert [item["kind"] for item in breaker_payload["followup_requirements"]] == ["operator_review"]

    followups = db_session.query(RequirementRow).filter(
        RequirementRow.source == "bugfix_circuit_breaker"
    ).order_by(RequirementRow.id.asc()).all()
    assert len(followups) == 1
    assert followups[0].title.startswith("Operator Review:")


def test_requirement_stays_blocked_until_dependencies_finish(synced_client):
    blocker_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Shared contract",
            "description_markdown": "Complete the shared contract before downstream work starts.",
            "priority": "high",
        },
    )
    assert blocker_resp.status_code == 201
    blocker_id = blocker_resp.json()["requirement"]["id"]

    dependent_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Downstream FAQ",
            "description_markdown": "Depends on the shared contract.",
            "priority": "normal",
            "depends_on_requirement_ids": [blocker_id],
        },
    )
    assert dependent_resp.status_code == 201
    dependent = dependent_resp.json()
    dependent_id = dependent["requirement"]["id"]
    assert dependent["requirement"]["status"] == "blocked"
    assert dependent["requirement"]["blocked_by_count"] == 1

    blocked_plan = synced_client.post(f"/api/requirements/{dependent_id}/plan")
    assert blocked_plan.status_code == 400
    assert blocked_plan.json()["detail"] == "Requirement is blocked by unfinished dependencies."

    synced_client.post(f"/api/requirements/{blocker_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{blocker_id}/start")

    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "done"

    refreshed = synced_client.get(f"/api/requirements/{dependent_id}")
    assert refreshed.status_code == 200
    assert refreshed.json()["requirement"]["status"] == "ready"
    assert refreshed.json()["requirement"]["blocked_by_count"] == 0

    unblocked_plan = synced_client.post(f"/api/requirements/{dependent_id}/plan")
    assert unblocked_plan.status_code == 200
    assert unblocked_plan.json()["requirement"]["current_plan_version"] == 1


def test_requirement_revision_reopens_and_replans_workflow(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Ambiguous FAQ requirement",
            "description_markdown": "Ship the FAQ flow.",
            "priority": "high",
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    class RevisionRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:implementation]" in task_description:
                return _runtime_result(text="Implementation draft ready.")
            if "[workflow_step:review]" in task_description:
                return _runtime_result(error="Requirement issue: needs revision because the acceptance criteria are ambiguous.")
            return _runtime_result(text="noop")

    with patch("server.services.task_runner.get_task_runtime", return_value=RevisionRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    started = start_resp.json()
    assert started["requirement"]["status"] == "paused"
    assert started["workflow_run"]["status"] == "paused"

    revise_resp = synced_client.post(
        f"/api/requirements/{requirement_id}/revise",
        json={
            "title": "Ambiguous FAQ requirement",
            "description_markdown": "Ship the FAQ flow with explicit pass/fail acceptance criteria.",
            "revision_note": "Clarified the acceptance criteria after review feedback.",
        },
    )
    assert revise_resp.status_code == 200
    revised = revise_resp.json()
    assert revised["requirement"]["status"] == "ready"
    assert revised["requirement"]["active_workflow_run_id"] is None
    assert any(artifact["artifact_type"] == "requirement_revision" for artifact in revised["artifacts"])

    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        replan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert replan_resp.status_code == 200


def test_start_after_revision_replaces_cancelled_workflow_run(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Restartable backend requirement",
            "description_markdown": "Ship a concrete backend fix with validation.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    first_run_id = plan_resp.json()["workflow_run"]["id"]

    class RevisionRuntime:
        def execute(self, *, task_description, **_kwargs):
            if "[workflow_step:review]" in task_description:
                return _runtime_result(error="Requirement issue: needs revision after first review.")
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=RevisionRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "paused"
    assert start_resp.json()["workflow_run"]["id"] == first_run_id

    revise_resp = synced_client.post(
        f"/api/requirements/{requirement_id}/revise",
        json={
            "title": "Restartable backend requirement",
            "description_markdown": "Ship a concrete backend fix with validation after revision.",
            "revision_note": "Clarified execution requirements and validation steps.",
        },
    )
    assert revise_resp.status_code == 200
    revised = revise_resp.json()
    assert revised["requirement"]["status"] == "ready"
    assert revised["requirement"]["current_plan_version"] == 0
    assert revised["requirement"]["active_workflow_run_id"] is None

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="completed")

    with patch("server.services.workflow_planner.get_provider", return_value=provider), patch(
        "server.services.workflow_orchestrator._execute_requirement_vcs_delivery",
        return_value=(
            {"status": "delivered", "blockers": [], "repositories": [], "remote_name": "origin"},
            None,
        ),
    ), patch(
        "server.services.workflow_orchestrator._sync_requirement_review_pr",
        return_value=(
            {"status": "draft", "blockers": [], "pr_url": "https://example.com/pr/1"},
            None,
        ),
    ), patch(
        "server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()
    ), patch("server.services.task_runner.dispatch", side_effect=_sync_dispatch):
        restart_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert restart_resp.status_code == 200
    payload = restart_resp.json()
    assert payload["requirement"]["status"] == "paused"
    assert payload["workflow_run"]["id"] != first_run_id
    assert payload["workflow_run"]["plan_version"] == 1


def test_start_requirement_auto_plans_unplanned_requirement(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Auto-plan on start",
            "description_markdown": "Start should create the plan before execution.",
            "priority": "high",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    payload = start_resp.json()
    assert payload["requirement"]["current_plan_version"] == 1
    assert payload["workflow_run"] is not None
    assert payload["workflow_run"]["plan_version"] == 1
    assert payload["requirement"]["status"] == "done"
    assert [step["step_type"] for step in payload["workflow_run"]["steps"]] == [
        "research",
        "synthesis",
        "implementation",
        "review",
        "test",
        "closeout",
    ]


def test_start_requirement_stays_ready_when_no_step_dispatch_happens(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Do not fake running state",
            "description_markdown": "Starting a requirement should not mark it in progress unless a step is actually dispatched.",
            "priority": "high",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    with patch("server.services.workflow_orchestrator._dispatch_next_step_for_requirement", return_value=None):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    payload = start_resp.json()
    assert payload["requirement"]["status"] == "ready"
    assert payload["workflow_run"]["status"] == "pending"
    assert all(step["status"] == "pending" for step in payload["workflow_run"]["steps"])


def test_paused_requirement_does_not_consume_project_capacity(synced_client, db_session):
    db_session.add(
        RequirementRow(
            title="Paused incident investigation",
            description_markdown="Paused work should not occupy a live project slot.",
            status="paused",
            priority="normal",
            source="manual",
            target_project_path="/Users/cliff/workspace/agent/Synapse-Network",
            current_plan_version=1,
        )
    )
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Start after paused requirement",
            "description_markdown": "A paused requirement should not block a new start in the same project.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    scheduler_resp = synced_client.get("/api/requirements/scheduler")
    assert scheduler_resp.status_code == 200
    network_state = next(
        item for item in scheduler_resp.json()["project_states"] if item["project_key"] == "synapse-network"
    )
    assert network_state["active_count"] == 0

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "done"


def test_patch_requirement_updates_fields(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Original title",
            "description_markdown": "Original description.",
            "priority": "normal",
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    patch_resp = synced_client.patch(
        f"/api/requirements/{requirement_id}",
        json={"title": "Updated title", "priority": "high"},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["requirement"]["title"] == "Updated title"
    assert patched["requirement"]["priority"] == "high"
    assert patched["requirement"]["description_markdown"] == "Original description."


def test_requirement_intake_auto_routes_to_matching_project(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Improve SDK onboarding",
            "description_markdown": "Update the Python SDK MCP integration flow and tighten developer integration docs.",
            "priority": "high",
        },
    )

    assert create_resp.status_code == 201
    payload = create_resp.json()
    assert payload["requirement"]["target_project_path"] == "/Users/cliff/workspace/agent/Synapse-Network-Sdk"
    assert payload["requirement"]["routing_context"]["routing_mode"] == "auto"
    assert payload["requirement"]["routing_context"]["routed_project_keys"] == ["synapse-network-sdk"]
    assert payload["requirement"]["routing_context"]["automation_ready"] is True
    route_artifact = next(artifact for artifact in payload["artifacts"] if artifact["artifact_type"] == "routing_decision")
    route_payload = json.loads(route_artifact["machine_readable_payload"])
    assert route_payload["routing_mode"] == "auto"
    assert route_payload["routed_project_keys"] == ["synapse-network-sdk"]


def test_queue_advance_prefers_automation_ready_projects(synced_client, db_session, tmp_path):
    ready_repo = tmp_path / "ready-repo"
    ready_repo.mkdir()
    unready_repo = tmp_path / "unready-repo"
    unready_repo.mkdir()

    ready_policy = ProjectPolicyRow(
        project_key="ready-repo",
        display_name="Ready Repo",
        root_path=str(ready_repo),
        status="active",
        allowed_write_globs_json='["**"]',
        forbidden_globs_json='[]',
        required_checks_json='[]',
        release_mode="manual",
        requires_manual_approval=True,
    )
    unready_policy = ProjectPolicyRow(
        project_key="unready-repo",
        display_name="Unready Repo",
        root_path=str(unready_repo),
        status="active",
        allowed_write_globs_json='["**"]',
        forbidden_globs_json='[]',
        required_checks_json='[]',
        release_mode="manual",
        requires_manual_approval=True,
    )
    db_session.add_all([ready_policy, unready_policy])
    db_session.flush()
    db_session.add_all([
        ProjectOnboardingRow(
            project_key="ready-repo",
            display_name="Ready Repo",
            root_path=str(ready_repo),
            docs_entrypoints_json='[]',
            validation_commands_json='["pytest -q"]',
            agents_memory_namespace="ready-repo",
            policy_id=ready_policy.id,
            readiness_status="ready",
            readiness_score=100,
            readiness_items_json='[]',
            missing_items_json='[]',
        ),
        ProjectOnboardingRow(
            project_key="unready-repo",
            display_name="Unready Repo",
            root_path=str(unready_repo),
            docs_entrypoints_json='[]',
            validation_commands_json='[]',
            agents_memory_namespace="unready-repo",
            policy_id=unready_policy.id,
            readiness_status="needs_setup",
            readiness_score=25,
            readiness_items_json='[]',
            missing_items_json='["Validation Commands"]',
        ),
    ])
    db_session.commit()

    blocked_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Highest priority but unready project",
            "description_markdown": "Target the unready project and improve automation.",
            "priority": "high",
            "target_project_path": str(unready_repo),
        },
    )
    ready_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Ready project follow-up",
            "description_markdown": "Target the ready project and improve automation.",
            "priority": "normal",
            "target_project_path": str(ready_repo),
        },
    )
    blocked_id = blocked_resp.json()["requirement"]["id"]
    ready_id = ready_resp.json()["requirement"]["id"]

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        queue_resp = synced_client.post("/api/requirements/queue/advance")

    assert queue_resp.status_code == 200
    assert queue_resp.json()["started"] == ready_id

    blocked_detail = synced_client.get(f"/api/requirements/{blocked_id}").json()
    assert blocked_detail["requirement"]["status"] == "ready"
    assert blocked_detail["requirement"]["routing_context"]["automation_ready"] is False


def test_scheduler_endpoint_exposes_project_capacity_and_decisions(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK scheduler candidate",
            "description_markdown": "Improve the SDK onboarding flow.",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    scheduler_resp = synced_client.get("/api/requirements/scheduler")

    assert scheduler_resp.status_code == 200
    payload = scheduler_resp.json()
    assert payload["global_capacity"] >= 1
    sdk_state = next(item for item in payload["project_states"] if item["project_key"] == "synapse-network-sdk")
    assert sdk_state["queued_count"] >= 1
    decision = next(item for item in payload["decisions"] if item.get("requirement_id") == requirement_id)
    assert decision["project_key"] == "synapse-network-sdk"
    assert decision["action"] in {"start", "delay"}
    assert decision["score"] >= decision["base_score"]


def test_scheduler_delays_requirement_when_project_budget_is_exhausted(synced_client, db_session):
    synced_client.get("/api/project-policies")
    sdk_policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == "synapse-network-sdk").first()
    assert sdk_policy is not None
    sdk_policy.portfolio_budget_points = 20
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK release bottleneck",
            "description_markdown": "High urgency release unblocker.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    db_session.add(
        ArtifactRow(
            requirement_id=requirement_id,
            artifact_type="requirement_template",
            content_summary="release bottleneck template",
            machine_readable_payload=json.dumps({"template_key": "release_bottleneck"}),
        )
    )
    db_session.commit()

    scheduler_resp = synced_client.get("/api/requirements/scheduler")
    assert scheduler_resp.status_code == 200
    decision = next(item for item in scheduler_resp.json()["decisions"] if item.get("requirement_id") == requirement_id)
    assert decision["action"] == "delay"
    assert "budget exhausted" in decision["reason"]


def test_queue_advance_can_start_multiple_projects_in_same_window(synced_client):
    sdk_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK quality gate",
            "description_markdown": "Improve SDK release validation.",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    memory_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Memory docs cleanup",
            "description_markdown": "Improve Agents-Memory documentation automation.",
            "target_project_path": "/Users/cliff/workspace/agent/Agents-Memory",
        },
    )
    sdk_id = sdk_resp.json()["requirement"]["id"]
    memory_id = memory_resp.json()["requirement"]["id"]

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result()

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        queue_resp = synced_client.post("/api/requirements/queue/advance")

    assert queue_resp.status_code == 200
    payload = queue_resp.json()
    assert sorted(payload["started_ids"]) == sorted([sdk_id, memory_id])

    sdk_detail = synced_client.get(f"/api/requirements/{sdk_id}").json()
    memory_detail = synced_client.get(f"/api/requirements/{memory_id}").json()
    assert sdk_detail["requirement"]["status"] == "in_progress"
    assert memory_detail["requirement"]["status"] == "in_progress"


def test_manual_scheduler_rebalance_preempts_lower_value_running_requirement(synced_client, db_session):
    synced_client.get("/api/project-policies")
    sdk_policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == "synapse-network-sdk").first()
    network_policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == "synapse-network").first()
    assert sdk_policy is not None and network_policy is not None
    sdk_policy.autonomy_mode = "execute_with_approval"
    sdk_policy.allow_rebalance = True
    sdk_policy.scheduler_weight = 2.2
    sdk_policy.portfolio_budget_points = 160
    network_policy.allow_preemption = False
    db_session.commit()

    running_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Low value maintenance",
            "description_markdown": "Routine maintenance task.",
            "priority": "low",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
        },
    )
    running_id = running_resp.json()["requirement"]["id"]
    synced_client.post(f"/api/requirements/{running_id}/plan")

    candidate_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK critical release blocker",
            "description_markdown": "Urgent SDK unblocker with high leverage.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )
    candidate_id = candidate_resp.json()["requirement"]["id"]
    db_session.add(
        ArtifactRow(
            requirement_id=candidate_id,
            artifact_type="requirement_template",
            content_summary="release bottleneck template",
            machine_readable_payload=json.dumps({"template_key": "release_bottleneck"}),
        )
    )
    db_session.commit()

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result()

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{running_id}/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "in_progress"

    with patch("server.services.portfolio_scheduler.MAX_GLOBAL_CAPACITY", 1), patch(
        "server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()
    ), patch("server.services.task_runner.dispatch", side_effect=_sync_dispatch):
        scheduler_resp = synced_client.get("/api/requirements/scheduler")
        rebalance_resp = synced_client.post("/api/requirements/scheduler/rebalance")

    assert scheduler_resp.status_code == 200
    decision = next(item for item in scheduler_resp.json()["decisions"] if item.get("requirement_id") == candidate_id)
    assert decision["action"] == "preempt_candidate"
    assert decision["approval_required"] is True

    assert rebalance_resp.status_code == 200
    rebalance_payload = rebalance_resp.json()
    assert running_id in rebalance_payload["preempted_ids"]
    assert candidate_id in rebalance_payload["started_ids"]
    assert candidate_id in rebalance_payload["rebalanced_ids"]

    running_detail = synced_client.get(f"/api/requirements/{running_id}").json()
    candidate_detail = synced_client.get(f"/api/requirements/{candidate_id}").json()
    assert running_detail["requirement"]["status"] == "paused"
    assert candidate_detail["requirement"]["status"] == "in_progress"


def test_patch_requirement_rejects_blank_title(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Temp", "description_markdown": "Desc."},
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    patch_resp = synced_client.patch(
        f"/api/requirements/{requirement_id}",
        json={"title": "   "},
    )
    assert patch_resp.status_code == 400


def test_close_requirement_requires_validation_contract(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Close me", "description_markdown": "Should close."},
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    close_resp = synced_client.post(f"/api/requirements/{requirement_id}/close")
    assert close_resp.status_code == 400
    assert "validation_plan artifact is missing" in close_resp.json()["detail"]


def test_close_requirement_requires_passing_checks_and_creates_manifest(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Close me safely", "description_markdown": "Only close after checks pass."},
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    blocked_close = synced_client.post(f"/api/requirements/{requirement_id}/close")
    assert blocked_close.status_code == 400
    assert "check `review_passed` is pending" in blocked_close.json()["detail"]

    checks = db_session.query(RequirementAcceptanceCheckRow).filter(
        RequirementAcceptanceCheckRow.requirement_id == requirement_id
    ).all()
    for check in checks:
        check.status = "passed"
    workflow_run = db_session.query(WorkflowRunRow).filter(
        WorkflowRunRow.requirement_id == requirement_id
    ).first()
    assert workflow_run is not None
    workflow_run.status = "cancelled"
    db_session.commit()

    close_resp = synced_client.post(f"/api/requirements/{requirement_id}/close")
    assert close_resp.status_code == 200
    closed = close_resp.json()
    assert closed["requirement"]["status"] == "done"
    assert closed["requirement"]["completed_at"] is not None
    assert any(artifact["artifact_type"] == "validation_manifest" for artifact in closed["artifacts"])
    assert any(artifact["artifact_type"] == "delivery_state" for artifact in closed["artifacts"])


def test_delivery_state_stops_at_review_ready_when_publish_disabled(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")
    project_policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.root_path == target_path).first()
    if project_policy is None:
        raise AssertionError("expected default project policy for target path")
    project_policy.release_mode = "disabled"
    project_policy.required_checks_json = "[]"
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Disabled publish gate",
            "description_markdown": "Finish the work but stop at review-ready because publish is disabled.",
            "target_project_path": target_path,
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    pr_payload = {
        "status": "synced",
        "pr_status": "draft",
        "pr_number": 77,
        "pr_url": "https://github.com/openai/synapse-network/pull/77",
        "head_branch": f"ops/req-{requirement_id}-disabled-publish-gate",
        "base_branch": "main",
        "latest_commit_sha": "abc123def456",
        "latest_remote_sha": "abc123def456",
        "blockers": [],
    }
    with patch("server.services.workflow_orchestrator._sync_requirement_review_pr", return_value=(pr_payload, None)), patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] == "done"
    assert detail["delivery_state"]["publish_status"] == "blocked"
    assert "publish disabled by project policy" in detail["delivery_state"]["publish_blockers"]

    publish_resp = synced_client.post(
        f"/api/requirements/{requirement_id}/publish",
        json={"completed_checks": [], "note": "try publish"},
    )
    assert publish_resp.status_code == 400
    assert publish_resp.json()["detail"] == "Publish is disabled by project policy."


def test_publish_endpoint_requires_confirmed_checks_then_promotes(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")

    project_policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.root_path == target_path).first()
    assert project_policy is not None
    project_policy.release_mode = "manual"
    project_policy.required_checks_json = json.dumps(["pytest -q", "npm run build"])
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Manual publish gate",
            "description_markdown": "Promote only after required checks are confirmed.",
            "target_project_path": target_path,
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    assert any(artifact["artifact_type"] == "delivery_contract" for artifact in plan_resp.json()["artifacts"])

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    pr_payload = {
        "status": "synced",
        "pr_status": "draft",
        "pr_number": 88,
        "pr_url": "https://github.com/openai/synapse-network/pull/88",
        "head_branch": f"ops/req-{requirement_id}-manual-publish-gate",
        "base_branch": "main",
        "latest_commit_sha": "abc123def456",
        "latest_remote_sha": "abc123def456",
        "blockers": [],
    }
    with patch("server.services.workflow_orchestrator._sync_requirement_review_pr", return_value=(pr_payload, None)), patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["delivery_state"]["publish_status"] == "review_ready"
    required_checks = sorted(detail["delivery_state"]["required_checks"])
    pending_checks = sorted(detail["delivery_state"]["pending_checks"])
    assert pending_checks == required_checks
    assert len(required_checks) >= 2

    blocked_publish = synced_client.post(
        f"/api/requirements/{requirement_id}/publish",
        json={"completed_checks": [required_checks[0]], "note": "not enough"},
    )
    assert blocked_publish.status_code == 400
    assert required_checks[1] in blocked_publish.json()["detail"]

    publish_resp = synced_client.post(
        f"/api/requirements/{requirement_id}/publish",
        json={"completed_checks": required_checks, "note": "ship it"},
    )
    assert publish_resp.status_code == 200


def test_closeout_blocks_when_delivery_vcs_fails(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network-Growing"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Delivery branch blocked",
            "description_markdown": "Validation passes but branch delivery fails.",
            "target_project_path": target_path,
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch(
        "server.services.workflow_orchestrator._execute_requirement_vcs_delivery",
        return_value=(
            {
                "status": "blocked",
                "branch_name": f"ops/req-{requirement_id}-delivery-branch-blocked",
                "base_branch": "main",
                "remote_name": "origin",
                "blockers": ["origin push rejected"],
                "repositories": [],
            },
            None,
        ),
    ), patch(
        "server.services.workflow_orchestrator._sync_requirement_review_pr",
        return_value=(
            {
                "status": "blocked",
                "pr_status": "missing",
                "blockers": ["review PR sync failed"],
            },
            None,
        ),
    ), patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] == "paused"
    assert detail["workflow_run"]["status"] == "paused"
    closeout = next(step for step in detail["workflow_run"]["steps"] if step["step_type"] == "closeout")
    assert closeout["status"] == "blocked"
    assert detail["delivery_state"]["review_status"] == "blocked"
    assert "origin push rejected" in detail["delivery_state"]["publish_blockers"]


def test_closeout_records_vcs_delivery_on_success(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network-Growing"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Delivery branch success",
            "description_markdown": "Validation passes and branch delivery succeeds.",
            "target_project_path": target_path,
            "approval_contract": {"approval_mode": "waived"},
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    vcs_payload = {
        "status": "delivered",
        "branch_name": f"ops/req-{requirement_id}-delivery-branch-success",
        "base_branch": "main",
        "remote_name": "origin",
        "blockers": [],
        "repositories": [
            {
                "repo_path": target_path,
                "status": "delivered",
                "branch_name": f"ops/req-{requirement_id}-delivery-branch-success",
                "base_branch": "main",
                "remote_name": "origin",
                "remote_url": "git@github.com:openai/synapse-network-growing.git",
                "commit_sha": "abc123def456",
                "remote_sha": "abc123def456",
                "committed": True,
                "pushed": True,
                "blockers": [],
            }
        ],
    }

    pr_payload = {
        "status": "synced",
        "pr_status": "draft",
        "pr_number": 91,
        "pr_url": "https://github.com/openai/synapse-network-growing/pull/91",
        "head_branch": f"ops/req-{requirement_id}-delivery-branch-success",
        "base_branch": "main",
        "latest_commit_sha": "abc123def456",
        "latest_remote_sha": "abc123def456",
        "blockers": [],
    }
    with patch(
        "server.services.workflow_orchestrator._execute_requirement_vcs_delivery",
        return_value=(vcs_payload, None),
    ), patch(
        "server.services.workflow_orchestrator._sync_requirement_review_pr",
        return_value=(pr_payload, None),
    ), patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] == "done"
    assert detail["delivery_state"]["review_status"] == "review_ready"
    assert detail["delivery_state"]["vcs_status"] == "delivered"
    assert detail["delivery_state"]["vcs_repositories"][0]["commit_sha"] == "abc123def456"
    assert detail["delivery_state"]["compare_url"] == (
        f"https://github.com/openai/synapse-network-growing/compare/main...ops/req-{requirement_id}-delivery-branch-success"
    )
    assert detail["delivery_state"]["pr_status"] == "draft"
    assert detail["delivery_state"]["pr_number"] == 91
    assert detail["delivery_state"]["pr_url"] == "https://github.com/openai/synapse-network-growing/pull/91"
    assert detail["delivery_state"]["pr_metadata"]["title"].startswith(f"ops(req-{requirement_id})")
    assert detail["delivery_state"]["promotion_checklist"][0]["key"] == "branch_delivery"
    review_surface = next(artifact for artifact in detail["artifacts"] if artifact["artifact_type"] == "review_surface")
    review_payload = json.loads(review_surface["machine_readable_payload"])
    assert review_payload["vcs_delivery"]["status"] == "delivered"
    assert review_payload["compare_url"] == detail["delivery_state"]["compare_url"]
    assert review_payload["pr_metadata"]["head_branch"] == f"ops/req-{requirement_id}-delivery-branch-success"
    assert review_payload["review_pr"]["pr_number"] == 91


def test_start_requirement_interrupts_when_capability_matrix_denies_shell_access(synced_client, db_session):
    target_path = "/tmp/restricted-capability-project"
    db_session.add(
        ProjectPolicyRow(
            project_key="restricted-capability-project",
            display_name="Restricted Capability Project",
            root_path=target_path,
            status="active",
            allowed_write_globs_json='["src/**"]',
            forbidden_globs_json='["secrets/**"]',
            required_checks_json="[]",
            release_mode="manual",
            requires_manual_approval=True,
            capability_matrix_json=json.dumps({
                "shell_access": False,
                "git_read": True,
                "git_write": True,
                "git_push": False,
                "network_access": False,
                "publish": False,
            }),
            interrupt_policy_json=json.dumps({
                "operator_confirmation_actions": ["publish"],
                "auto_pause_on_events": ["capability_denied"],
                "auto_abort_on_events": ["forbidden_write"],
            }),
        )
    )
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Restricted shell capability",
            "description_markdown": "Implement backend API changes in a restricted project.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] == "paused"
    assert detail["workflow_run"]["status"] == "paused"
    assert detail["workflow_run"]["steps"][0]["status"] == "blocked"
    assert any(item["incident_code"] == "capability_denied" for item in detail["incidents"])

    interrupt_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "capability_interrupt",
    ).first()
    assert interrupt_artifact is not None
    assert "shell_access disabled" in (interrupt_artifact.human_readable_body or "")
    stale_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "stale_memory_verification",
    ).first()
    assert stale_artifact is not None


def test_start_requirement_blocks_when_context_is_stale(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Stale context check",
            "description_markdown": "Implement a targeted backend change.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    stale_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "implementation_plan",
    ).first()
    assert stale_artifact is not None
    foreign_run = WorkflowRunRow(
        requirement_id=requirement_id,
        plan_version=99,
        status="completed",
        triggered_by="test",
    )
    db_session.add(foreign_run)
    db_session.flush()
    stale_artifact.workflow_run_id = foreign_run.id
    db_session.commit()

    start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] == "paused"
    assert detail["workflow_run"]["status"] == "paused"
    assert any(item["incident_code"] == "stale_memory_blocked" for item in detail["incidents"])

    stale_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "stale_memory_verification",
    ).order_by(ArtifactRow.id.desc()).first()
    assert stale_artifact is not None
    payload = json.loads(stale_artifact.machine_readable_payload or "{}")
    assert payload["verification_status"] == "stale"
    assert payload["stale_findings"]


def test_start_requirement_handles_mixed_datetime_freshness_checks(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Mixed datetime freshness guard",
            "description_markdown": "Re-run planning after a requirement update without crashing stale-memory checks.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == requirement.active_workflow_run_id).first()
    assert requirement is not None
    assert workflow_run is not None
    assert workflow_run.created_at is not None

    requirement.updated_at = workflow_run.created_at + timedelta(minutes=5)
    db_session.commit()

    start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] == "in_progress"
    assert detail["workflow_run"]["status"] in {"pending", "running"}


def test_start_requirement_allows_resume_when_snapshot_and_plan_are_old(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Resume with old planning artifacts",
            "description_markdown": "Ensure paused requirements do not fail stale-memory checks purely by age.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    artifacts = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type.in_(("requirement_snapshot", "implementation_plan")),
    ).all()
    assert artifacts
    old_time = utcnow() - timedelta(hours=2)
    for artifact in artifacts:
        artifact.created_at = old_time
    db_session.commit()

    start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["requirement"]["status"] != "blocked"
    assert not any(item["incident_code"] == "stale_memory_blocked" for item in detail["incidents"])


def test_implementation_context_omits_prior_synthesis_handoff(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Implementation should ignore stale synthesis blocker prose",
            "description_markdown": "Ensure implementation relies on structured plan instead of prior blocker handoff text.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == requirement.active_workflow_run_id).first()
    assert workflow_run is not None

    steps = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id
    ).order_by(WorkflowStepRow.sequence_no.asc()).all()
    synthesis_step = next(step for step in steps if step.step_type == "synthesis")
    implementation_step = next(step for step in steps if step.step_type == "implementation")
    synthesis_step.handoff_summary_markdown = (
        "**Summary:** Need more environment data before implementing.\n\n"
        "- **Blockers:** Waiting for runtime `/readiness` payload."
    )
    db_session.commit()

    snapshot = workflow_orchestrator._step_context_snapshot(db_session, implementation_step)
    prompt = str(snapshot["prompt"])
    assert "Prior Step: Synthesize plan" not in prompt
    assert "Need more environment data before implementing." not in prompt
    assert "Implementation Plan" in prompt


def test_implementation_context_includes_research_file_hints(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Implementation should receive research file hints",
            "description_markdown": "Ensure implementation prompt inherits the relevant file shortlist from research evidence.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == requirement.active_workflow_run_id).first()
    assert workflow_run is not None

    steps = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == workflow_run.id
    ).order_by(WorkflowStepRow.sequence_no.asc()).all()
    implementation_step = next(step for step in steps if step.step_type == "implementation")

    research_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "research_report",
    ).order_by(ArtifactRow.id.desc()).first()
    assert research_artifact is not None
    research_artifact.human_readable_body = (
        "Investigate `services/gateway/src/app.py:32-111` and "
        "`services/gateway/tests/unit/test_gateway_readiness_endpoint_unit.py:74-133` first."
    )
    db_session.commit()

    snapshot = workflow_orchestrator._step_context_snapshot(db_session, implementation_step)
    prompt = str(snapshot["prompt"])
    assert "Suggested File Scope" in prompt
    assert "services/gateway/src/app.py" in prompt
    assert "services/gateway/tests/unit/test_gateway_readiness_endpoint_unit.py" in prompt


def test_compact_task_description_preserves_requirement_goal_summary(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network-Growing"
    synced_client.get("/api/project-policies")

    create_resp = synced_client.post(
        "/api/requirements",
        json={
                "title": "Validate deterministic branch delivery on clean clone",
                "description_markdown": (
                    "Update only README.md in /Users/cliff/workspace/agent/Synapse-Network-Growing with a short note "
                    "explaining that each requirement uses a single long-lived branch, mutating steps "
                    "commit and push to that branch, and review-ready work syncs to one draft PR. "
                    "Keep the change tightly scoped to README only and prepare a review-ready bundle."
                ),
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == requirement.active_workflow_run_id).first()
    assert workflow_run is not None
    research_step = (
        db_session.query(WorkflowStepRow)
        .filter(WorkflowStepRow.workflow_run_id == workflow_run.id, WorkflowStepRow.step_type == "research")
        .first()
    )
    assert research_step is not None

    compact = workflow_orchestrator._step_task_description(db_session, research_step)
    assert "README.md" in compact
    assert "single long-lived branch" in compact
    assert "draft PR" in compact


def test_start_requirement_creates_context_compaction_artifact_for_large_prompt(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    synced_client.get("/api/project-policies")
    huge_description = "Large context block.\n" + ("x" * 16000)
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement large context requirement",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        42,
    )

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Large context compaction",
            "description_markdown": huge_description,
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    compaction_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "context_compaction",
    ).order_by(ArtifactRow.id.desc()).first()
    assert compaction_artifact is not None
    payload = json.loads(compaction_artifact.machine_readable_payload or "{}")
    assert payload["compacted"] is True
    assert payload["raw_chars"] > payload["final_chars"]
    prompt_cache_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "prompt_cache_profile",
    ).order_by(ArtifactRow.id.desc()).first()
    assert prompt_cache_artifact is not None
    cache_payload = json.loads(prompt_cache_artifact.machine_readable_payload or "{}")
    assert cache_payload["cache_applied"] is True
    assert cache_payload["cached_chars_saved"] > 0


def test_step_context_records_prompt_cache_dedupe_for_duplicate_bindings(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network-Growing"
    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement dedupe path",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Implementation output is produced and ready for review.",
                    }
                ]
            }
        ),
        42,
    )
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Prompt cache binding dedupe",
            "description_markdown": "Ensure duplicate context bindings are compacted before dispatch.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.workflow_run_id == requirement.active_workflow_run_id
    ).order_by(WorkflowStepRow.sequence_no.asc()).first()
    assert step is not None

    duplicate_a = workflow_orchestrator._create_artifact(
        db_session,
        requirement_id=requirement_id,
        workflow_run_id=step.workflow_run_id,
        artifact_type="routing_decision",
        content_summary="duplicate routing context",
        human_readable_body="Route this work to the managed project and keep within policy.",
        machine_readable_payload={"route": "managed-project", "reason": "duplicate"},
    )
    duplicate_b = workflow_orchestrator._create_artifact(
        db_session,
        requirement_id=requirement_id,
        workflow_run_id=step.workflow_run_id,
        artifact_type="routing_decision",
        content_summary="duplicate routing context",
        human_readable_body="Route this work to the managed project and keep within policy.",
        machine_readable_payload={"route": "managed-project", "reason": "duplicate"},
    )
    workflow_orchestrator._bind_artifact(db_session, step.id, duplicate_a.id, "routing_context", True)
    workflow_orchestrator._bind_artifact(db_session, step.id, duplicate_b.id, "routing_context", True)

    workflow_orchestrator._materialize_step_context(db_session, step)

    prompt_cache_artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.step_id == step.id,
        ArtifactRow.artifact_type == "prompt_cache_profile",
    ).order_by(ArtifactRow.id.desc()).first()
    assert prompt_cache_artifact is not None
    payload = json.loads(prompt_cache_artifact.machine_readable_payload or "{}")
    assert payload["cache_applied"] is True
    assert payload["total_binding_count"] > payload["unique_binding_count"]
    assert payload["deduped_binding_count"] >= 1


def test_research_context_skips_heavy_contract_bindings(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Research context stays lean",
            "description_markdown": "Investigate a bug without preloading implementation and delivery contracts.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    research_step = (
        db_session.query(WorkflowStepRow)
        .filter(
            WorkflowStepRow.workflow_run_id == requirement.active_workflow_run_id,
            WorkflowStepRow.step_type == "research",
        )
        .first()
    )
    assert research_step is not None

    snapshot = workflow_orchestrator._step_context_snapshot(db_session, research_step)
    prompt = snapshot["prompt"]
    assert "## Implementation Plan" not in prompt
    assert "## Delivery Contract" not in prompt
    assert "## Validation Contract" not in prompt
    assert "## Execution Guidance" in prompt
    assert "Limit exploration to the highest-signal files only" in prompt


def test_implementation_context_skips_delivery_and_validation_contracts(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Implementation context stays lean",
            "description_markdown": "Keep implementation focused on change execution rather than review contracts.",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    implementation_step = (
        db_session.query(WorkflowStepRow)
        .filter(
            WorkflowStepRow.workflow_run_id == requirement.active_workflow_run_id,
            WorkflowStepRow.step_type == "implementation",
        )
        .order_by(WorkflowStepRow.sequence_no.asc())
        .first()
    )
    assert implementation_step is not None

    snapshot = workflow_orchestrator._step_context_snapshot(db_session, implementation_step)
    prompt = snapshot["prompt"]
    assert "## Delivery Contract" not in prompt
    assert "## Validation Contract" not in prompt
    assert "## Execution Guidance" in prompt
    assert "Keep changes tightly scoped to the target project" in prompt


def test_bug_intake_steps_use_engineering_direct_execution_contract(synced_client, db_session):
    target_path = "/Users/cliff/workspace/agent/Synapse-Network"
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Bug Fix: Gateway readiness blocker",
            "description_markdown": "Investigate and fix the readiness blocker in the gateway.",
            "source": "bug_intake",
            "source_ref": "bug-intake:999",
            "target_project_path": target_path,
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "fix_gateway",
                        "title": "Fix gateway readiness handling",
                        "scope": "backend",
                        "depends_on": [],
                        "done_when": "Gateway readiness no longer reports the blocker when the service is healthy.",
                    }
                ]
            }
        ),
        123,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.id == requirement.active_workflow_run_id).first()
    assert workflow_run is not None

    synthesis_step = (
        db_session.query(WorkflowStepRow)
        .filter(
            WorkflowStepRow.workflow_run_id == workflow_run.id,
            WorkflowStepRow.step_type == "synthesis",
        )
        .first()
    )
    implementation_step = (
        db_session.query(WorkflowStepRow)
        .filter(
            WorkflowStepRow.workflow_run_id == workflow_run.id,
            WorkflowStepRow.step_type == "implementation",
        )
        .first()
    )
    assert synthesis_step is not None
    assert implementation_step is not None

    assert workflow_orchestrator._resolve_step_skill(db_session, synthesis_step) == "__direct_execution__"
    task, persona, skill_name = workflow_orchestrator._prepare_step_task(db_session, implementation_step)
    assert task.skill_name == "__direct_execution__"
    assert skill_name == "__direct_execution__"
    assert persona["display_name"] == "Engineering Executor"
    assert "engineering execution mode" in persona["body"].lower()


def test_standard_step_skips_operator_confirmation_on_start(synced_client, db_session):
    db_session.add(
        ProjectPolicyRow(
            project_key="standard-approval-policy",
            display_name="Standard Approval Policy",
            root_path="/standard-approval-policy",
            status="active",
            allowed_write_globs_json='["src/**"]',
            forbidden_globs_json='[]',
            required_checks_json='[]',
            release_mode="manual",
            requires_manual_approval=True,
            capability_matrix_json=json.dumps({
                "shell_access": True,
                "git_read": True,
                "git_write": True,
                "git_push": False,
                "network_access": False,
                "publish": False,
            }),
            interrupt_policy_json=json.dumps({
                "operator_confirmation_actions": ["shell_access", "git_write", "publish"],
                "auto_pause_on_events": ["operator_confirmation_required"],
                "auto_abort_on_events": ["forbidden_write"],
            }),
        )
    )
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Standard approval narrowing",
            "description_markdown": "单项目实现不应因为 shell/git_write 默认就进入人工审批。",
            "target_project_path": "/standard-approval-policy",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement change",
                        "scope": "backend",
                        "complexity_tier": "standard",
                        "depends_on": [],
                        "done_when": "Implementation output is ready for review.",
                    }
                ]
            }
        ),
        42,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    approval = db_session.query(workflow_orchestrator.ApprovalRequestRow).filter(
        workflow_orchestrator.ApprovalRequestRow.requirement_id == requirement_id,
        workflow_orchestrator.ApprovalRequestRow.approval_type == "step_operator_confirmation",
        workflow_orchestrator.ApprovalRequestRow.status == "pending",
    ).first()
    assert approval is None
    assert detail["requirement"]["status"] == "done"


def test_max_tier_step_still_requires_operator_confirmation_on_start(synced_client, db_session):
    for root_path, project_key in [("/max-approval/a", "max-approval-a"), ("/max-approval/b", "max-approval-b")]:
        db_session.add(
            ProjectPolicyRow(
                project_key=project_key,
                display_name=project_key,
                root_path=root_path,
                status="active",
                allowed_write_globs_json='["src/**"]',
                forbidden_globs_json='[]',
                required_checks_json='[]',
                release_mode="manual",
                requires_manual_approval=True,
                capability_matrix_json=json.dumps({
                    "shell_access": True,
                    "git_read": True,
                    "git_write": True,
                    "git_push": False,
                    "network_access": False,
                    "publish": False,
                }),
                interrupt_policy_json=json.dumps({
                    "operator_confirmation_actions": ["shell_access", "git_write", "publish"],
                    "auto_pause_on_events": ["operator_confirmation_required"],
                    "auto_abort_on_events": ["forbidden_write"],
                }),
            )
        )
    db_session.commit()

    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Cross-project max approval",
            "description_markdown": "跨项目实现仍应被视为昂贵分支。",
            "target_project_path": "/max-approval/a\n/max-approval/b",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    provider = MagicMock()
    provider.call.return_value = (
        json.dumps(
            {
                "steps": [
                    {
                        "step_key": "implementation",
                        "title": "Implement cross-project change",
                        "scope": "backend",
                        "complexity_tier": "max",
                        "depends_on": [],
                        "done_when": "Implementation output is ready for review.",
                    }
                ]
            }
        ),
        42,
    )
    with patch("server.services.workflow_planner.get_provider", return_value=provider):
        plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 200
    detail = start_resp.json()
    approval = db_session.query(workflow_orchestrator.ApprovalRequestRow).filter(
        workflow_orchestrator.ApprovalRequestRow.requirement_id == requirement_id,
        workflow_orchestrator.ApprovalRequestRow.approval_type == "step_operator_confirmation",
        workflow_orchestrator.ApprovalRequestRow.status == "pending",
    ).first()
    assert approval is not None
    assert detail["requirement"]["status"] == "paused"


def test_close_requirement_unblocks_dependents(synced_client, db_session):
    blocker = synced_client.post(
        "/api/requirements",
        json={"title": "Blocker", "description_markdown": "Blocks others."},
    ).json()
    blocker_id = blocker["requirement"]["id"]

    dependent = synced_client.post(
        "/api/requirements",
        json={
            "title": "Dependent",
            "description_markdown": "Depends on blocker.",
            "depends_on_requirement_ids": [blocker_id],
        },
    ).json()
    dependent_id = dependent["requirement"]["id"]
    assert dependent["requirement"]["status"] == "blocked"

    plan_resp = synced_client.post(f"/api/requirements/{blocker_id}/plan")
    assert plan_resp.status_code == 200

    checks = db_session.query(RequirementAcceptanceCheckRow).filter(
        RequirementAcceptanceCheckRow.requirement_id == blocker_id
    ).all()
    for check in checks:
        check.status = "passed"
    workflow_run = db_session.query(WorkflowRunRow).filter(
        WorkflowRunRow.requirement_id == blocker_id
    ).first()
    assert workflow_run is not None
    workflow_run.status = "cancelled"
    db_session.commit()

    close_resp = synced_client.post(f"/api/requirements/{blocker_id}/close")
    assert close_resp.status_code == 200

    refreshed = synced_client.get(f"/api/requirements/{dependent_id}").json()
    assert refreshed["requirement"]["status"] == "ready"
    assert refreshed["requirement"]["blocked_by_count"] == 0


def test_delete_requirement_soft_deletes_workflow_and_dependents(synced_client, db_session):
    blocker_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Delete blocker",
            "description_markdown": "Delete this requirement and cascade downstream.",
            "priority": "high",
        },
    )
    blocker_id = blocker_resp.json()["requirement"]["id"]

    dependent_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Delete dependent",
            "description_markdown": "Should be deleted together with the blocker.",
            "depends_on_requirement_ids": [blocker_id],
        },
    )
    dependent_id = dependent_resp.json()["requirement"]["id"]
    assert dependent_resp.json()["requirement"]["status"] == "blocked"

    synced_client.post(f"/api/requirements/{blocker_id}/plan")

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result()

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{blocker_id}/start")

    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "in_progress"

    delete_resp = synced_client.delete(f"/api/requirements/{blocker_id}")
    assert delete_resp.status_code == 200
    deleted = delete_resp.json()
    assert deleted["requirement"]["status"] == "deleted"
    assert deleted["workflow_run"]["status"] == "deleted"
    assert all(step["status"] == "deleted" for step in deleted["workflow_run"]["steps"])

    dependent = synced_client.get(f"/api/requirements/{dependent_id}").json()
    assert dependent["requirement"]["status"] == "deleted"

    blocker_row = db_session.query(RequirementRow).filter(RequirementRow.id == blocker_id).first()
    dependent_row = db_session.query(RequirementRow).filter(RequirementRow.id == dependent_id).first()
    assert blocker_row is not None and blocker_row.status == "deleted"
    assert dependent_row is not None and dependent_row.status == "deleted"

    tasks = db_session.query(TaskRow).order_by(TaskRow.id.asc()).all()
    assert len(tasks) >= 1
    assert all(task.status == "deleted" for task in tasks)

    steps = db_session.query(WorkflowStepRow).filter(WorkflowStepRow.requirement_id == blocker_id).all()
    assert len(steps) >= 1
    assert all(step.status == "deleted" for step in steps)

    advance_resp = synced_client.post("/api/requirements/queue/advance")
    assert advance_resp.status_code == 200
    assert advance_resp.json()["skipped"] == "no ready requirements"


def test_list_requirements_can_filter_deleted(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Delete me", "description_markdown": "Soft delete filter coverage."},
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    delete_resp = synced_client.delete(f"/api/requirements/{requirement_id}")
    assert delete_resp.status_code == 200

    filtered = synced_client.get("/api/requirements?status=deleted")
    assert filtered.status_code == 200
    payload = filtered.json()
    assert len(payload) == 1
    assert payload[0]["id"] == requirement_id
    assert payload[0]["status"] == "deleted"


def test_list_requirements_default_sorting_prioritizes_running_and_pushes_deleted_last(synced_client):
    running_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Running requirement", "description_markdown": "Keep this at the top.", "priority": "high"},
    )
    running_id = running_resp.json()["requirement"]["id"]

    archived_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Archived requirement", "description_markdown": "This should stay at the bottom."},
    )
    archived_id = archived_resp.json()["requirement"]["id"]

    ready_resp = synced_client.post(
        "/api/requirements",
        json={"title": "Ready requirement", "description_markdown": "This can stay in the middle."},
    )
    ready_id = ready_resp.json()["requirement"]["id"]

    synced_client.post(f"/api/requirements/{running_id}/plan")

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result()

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{running_id}/start")

    assert start_resp.status_code == 200
    assert start_resp.json()["requirement"]["status"] == "in_progress"

    delete_resp = synced_client.delete(f"/api/requirements/{archived_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["requirement"]["status"] == "deleted"

    listed_resp = synced_client.get("/api/requirements")
    assert listed_resp.status_code == 200
    listed = listed_resp.json()

    ids = [item["id"] for item in listed]
    assert ids[0] == running_id
    assert ids[-1] == archived_id
    assert ready_id in ids[1:-1]


def test_list_requirements_search_filters_by_title_source_and_project_path(synced_client):
    first = synced_client.post(
        "/api/requirements",
        json={
            "title": "Harness circuit breaker review",
            "description_markdown": "Investigate dead-loop incident and operator review follow-up.",
            "priority": "high",
            "source_ref": "bugfix-circuit-breaker:operator-review:40:29:2020",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    ).json()["requirement"]
    synced_client.post(
        "/api/requirements",
        json={
            "title": "SDK landing polish",
            "description_markdown": "Unrelated requirement.",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
        },
    )

    by_title = synced_client.get("/api/requirements", params={"search": "circuit breaker"})
    assert by_title.status_code == 200
    assert [item["id"] for item in by_title.json()] == [first["id"]]

    by_source_ref = synced_client.get("/api/requirements", params={"search": "operator-review:40"})
    assert by_source_ref.status_code == 200
    assert [item["id"] for item in by_source_ref.json()] == [first["id"]]

    by_project_path = synced_client.get("/api/requirements", params={"search": "Synapse-Network-Growing"})
    assert by_project_path.status_code == 200
    assert [item["id"] for item in by_project_path.json()] == [first["id"]]


def test_pause_requirement_stops_running_step_and_allows_restart(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Pause running requirement",
            "description_markdown": "Allow operators to pause and restart a running workflow.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result()

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    started = start_resp.json()
    assert started["requirement"]["status"] == "in_progress"
    running_steps = [step for step in started["workflow_run"]["steps"] if step["status"] == "running"]
    assert len(running_steps) == 1

    pause_resp = synced_client.post(f"/api/requirements/{requirement_id}/pause")
    assert pause_resp.status_code == 200
    paused = pause_resp.json()
    assert paused["requirement"]["status"] == "paused"
    assert paused["workflow_run"]["status"] == "paused"
    resumed_step = next(step for step in paused["workflow_run"]["steps"] if step["id"] == running_steps[0]["id"])
    assert resumed_step["status"] == "ready"
    assert resumed_step["compatibility_task_id"] is None

    tasks = db_session.query(TaskRow).order_by(TaskRow.id.asc()).all()
    assert tasks[-1].status == "cancelled"
    assert tasks[-1].last_error_message == "Paused by user"

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="done")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        restart_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert restart_resp.status_code == 200
    restarted = restart_resp.json()
    assert restarted["requirement"]["status"] == "done"
    assert restarted["workflow_run"]["status"] == "completed"

    refreshed_tasks = db_session.query(TaskRow).order_by(TaskRow.id.asc()).all()
    assert len(refreshed_tasks) >= 2
    assert refreshed_tasks[-1].status == "completed"

    lifecycle_artifacts = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement_id,
        ArtifactRow.artifact_type == "runtime_lifecycle",
    ).order_by(ArtifactRow.id.asc()).all()
    lifecycle_phases = [json.loads(artifact.machine_readable_payload)["phase"] for artifact in lifecycle_artifacts]
    assert "dispatch_requested" in lifecycle_phases
    assert "running" in lifecycle_phases
    assert "paused" in lifecycle_phases
    assert "completed" in lifecycle_phases


def test_start_requirement_records_runtime_telemetry_artifacts(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Runtime telemetry requirement",
            "description_markdown": "Capture runtime lifecycle and subagent telemetry.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result(
                session_id="runtime-session-123",
                events=[
                    RuntimeEvent(event_type="runtime_session_created", detail="session=runtime-session-123"),
                    RuntimeEvent(event_type="subagent_selected", detail="editor"),
                    RuntimeEvent(event_type="subagent_started", detail="editor"),
                ],
            )

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["requirement"]["status"] == "in_progress"

    lifecycle_artifact = sorted(
        [artifact for artifact in data["artifacts"] if artifact["artifact_type"] == "runtime_lifecycle"],
        key=lambda artifact: artifact["id"],
        reverse=True,
    )[0]
    lifecycle_payload = json.loads(lifecycle_artifact["machine_readable_payload"])
    assert lifecycle_payload["phase"] == "running"
    assert lifecycle_payload["runtime_backend"] == "copilot_sdk"
    assert lifecycle_payload["runtime_session_id"] == "runtime-session-123"

    telemetry_artifact = sorted(
        [artifact for artifact in data["artifacts"] if artifact["artifact_type"] == "runtime_telemetry"],
        key=lambda artifact: artifact["id"],
        reverse=True,
    )[0]
    telemetry_payload = json.loads(telemetry_artifact["machine_readable_payload"])
    assert telemetry_payload["runtime_event_cursor"] == 0
    assert telemetry_payload["event_counts"]["runtime_session_created"] == 1
    assert telemetry_payload["event_counts"]["subagent_started"] == 1
    assert telemetry_payload["subagent_counts"]["selected"] == 1
    assert telemetry_payload["subagent_counts"]["started"] == 1


def test_requirement_detail_includes_runtime_failure_incident(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Runtime failure test",
            "description_markdown": "Force a runtime failure and capture the runtime record.",
            "priority": "normal",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class FailureRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(error="simulated runtime failure")

    with patch("server.services.task_runner.get_task_runtime", return_value=FailureRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert any(item["incident_code"] == "runtime_failure" for item in detail["incidents"])
    incident_artifacts = [artifact for artifact in detail["artifacts"] if artifact["artifact_type"] == "incident_record"]
    assert incident_artifacts
    incident_payload = json.loads(incident_artifacts[-1]["machine_readable_payload"])
    assert incident_payload["incident_code"] == "runtime_failure"
    assert incident_payload["incident_family"] == "runtime_orchestration"
    assert incident_payload["recovery_status"] == "runtime_recovery_required"


def test_pause_requirement_handles_state_drift_without_running_step(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Pause drifted requirement",
            "description_markdown": "Pause should still work when the requirement status drifts.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class DeferredRuntime:
        def execute(self, **_kwargs):
            return _deferred_runtime_result()

    with patch("server.services.task_runner.get_task_runtime", return_value=DeferredRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        synced_client.post(f"/api/requirements/{requirement_id}/start")

    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    workflow_run = db_session.query(WorkflowRunRow).filter(WorkflowRunRow.requirement_id == requirement_id).first()
    step = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.status == "running",
    ).first()
    task = db_session.query(TaskRow).filter(TaskRow.id == step.compatibility_task_id).first()
    assert requirement is not None
    assert workflow_run is not None
    assert step is not None
    assert task is not None

    step.status = "ready"
    step.compatibility_task_id = None
    step.runtime_backend = ""
    step.runtime_session_id = None
    task.status = "cancelled"
    task.last_error_message = "reset for drift test"
    db_session.commit()

    pause_resp = synced_client.post(f"/api/requirements/{requirement_id}/pause")
    assert pause_resp.status_code == 200
    paused = pause_resp.json()
    assert paused["requirement"]["status"] == "paused"
    assert paused["workflow_run"]["status"] == "paused"


def test_create_requirement_normalizes_multi_project_target_path(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Cross-repo requirement",
            "description_markdown": "Needs Growing plus Synapse root.",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
        },
    )

    assert create_resp.status_code == 201
    requirement = create_resp.json()["requirement"]
    assert requirement["target_project_path"] == (
        "/Users/cliff/workspace/agent/Synapse-Network-Growing\n"
        "/Users/cliff/workspace/agent/Synapse-Network"
    )


def test_list_requirements_score_sorting(synced_client):
    synced_client.post(
        "/api/requirements",
        json={"title": "Low priority", "description_markdown": "L.", "priority": "low"},
    )
    synced_client.post(
        "/api/requirements",
        json={"title": "High priority", "description_markdown": "H.", "priority": "high"},
    )

    default_resp = synced_client.get("/api/requirements")
    assert default_resp.status_code == 200

    scored_resp = synced_client.get("/api/requirements?sort=score")
    assert scored_resp.status_code == 200
    scored = scored_resp.json()
    assert len(scored) >= 2
    assert scored[0]["title"] == "High priority"


def test_workflow_step_events_recorded(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Events test",
            "description_markdown": "Check events are recorded.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="done")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        synced_client.post(f"/api/requirements/{requirement_id}/start")

    events = db_session.query(WorkflowStepEventRow).all()
    assert len(events) > 0
    event_types = {e.event_type for e in events}
    assert "status_change" in event_types


def test_requirements_list_reuses_project_catalog_context(synced_client, monkeypatch):
    for idx in range(2):
        create_resp = synced_client.post(
            "/api/requirements",
            json={
                "title": f"Catalog reuse {idx}",
                "description_markdown": "Check score-sorted requirement listing.",
                "priority": "normal",
                "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
            },
        )
        assert create_resp.status_code == 201

    real_build_project_catalog = project_intelligence.build_project_catalog
    call_count = {"count": 0}

    def wrapped_build_project_catalog(db):
        call_count["count"] += 1
        return real_build_project_catalog(db)

    monkeypatch.setattr(project_intelligence, "build_project_catalog", wrapped_build_project_catalog)

    resp = synced_client.get("/api/requirements?sort=score")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
    assert call_count["count"] == 1


def test_requirement_scheduler_reuses_project_catalog_context(synced_client, monkeypatch):
    for idx in range(2):
        create_resp = synced_client.post(
            "/api/requirements",
            json={
                "title": f"Scheduler reuse {idx}",
                "description_markdown": "Check scheduler avoids rebuilding project catalog per requirement.",
                "priority": "normal",
                "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
            },
        )
        assert create_resp.status_code == 201

    real_build_project_catalog = project_intelligence.build_project_catalog
    call_count = {"count": 0}

    def wrapped_build_project_catalog(db):
        call_count["count"] += 1
        return real_build_project_catalog(db)

    monkeypatch.setattr(project_intelligence, "build_project_catalog", wrapped_build_project_catalog)
    monkeypatch.setattr(portfolio_scheduler, "build_project_catalog", wrapped_build_project_catalog)

    resp = synced_client.get("/api/requirements/scheduler")
    assert resp.status_code == 200
    assert call_count["count"] == 1


def test_requirement_detail_reconciles_active_workflow_run_to_live_run(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Workflow run repair",
            "description_markdown": "Prefer the workflow run that actually owns the running step.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None

    running_run = WorkflowRunRow(requirement_id=requirement_id, plan_version=1, status="running", triggered_by="user")
    pending_run = WorkflowRunRow(requirement_id=requirement_id, plan_version=1, status="pending", triggered_by="user")
    db_session.add_all([running_run, pending_run])
    db_session.flush()
    db_session.add(
        WorkflowStepRow(
            workflow_run_id=running_run.id,
            requirement_id=requirement_id,
            step_key="research",
            step_type="research",
            title="Research context",
            status="running",
            sequence_no=10,
            context_scope="project",
            done_when_markdown="done",
            file_scope_json="{}",
            validation_targets_json="[]",
            failure_policy_json="{}",
            approval_policy_json="{}",
            runtime_backend="codex_cli",
            retry_count=0,
            context_policy_json="{}",
            execution_profile_json="{}",
        )
    )
    requirement.current_plan_version = 1
    requirement.status = "in_progress"
    requirement.active_workflow_run_id = pending_run.id
    db_session.commit()

    resp = synced_client.get(f"/api/requirements/{requirement_id}")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["requirement"]["active_workflow_run_id"] == running_run.id
    assert payload["workflow_run"]["id"] == running_run.id
    assert payload["workflow_run"]["status"] == "running"


def test_runtime_escalation_promotes_ready_step_for_multi_project_large_change(db_session):
    requirement = RequirementRow(
        title="Escalate review after broad change",
        description_markdown="Validate a large multi-project implementation.",
        status="in_progress",
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="test")
    db_session.add(run)
    db_session.flush()
    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement.id,
        step_key="review",
        step_type="review",
        title="Review output",
        status="ready",
        sequence_no=20,
        context_scope="verification",
        done_when_markdown="done",
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        approval_policy_json="{}",
        execution_profile_json=json.dumps(
            {
                "complexity_tier": "standard",
                "budget_cap": {"max_runtime_seconds": 1800},
                "allow_escalation": True,
                "escalation_rule": {
                    "next_tier": "max",
                    "when": ["multi_project_change_detected", "changed_files_over_threshold"],
                    "changed_files_threshold": 8,
                },
            }
        ),
    )
    db_session.add(step)
    db_session.flush()
    db_session.add(
        ArtifactRow(
            requirement_id=requirement.id,
            workflow_run_id=run.id,
            step_id=step.id,
            artifact_type="project_change_summary",
            content_summary="changed projects",
            machine_readable_payload=json.dumps(
                {
                    "changed_projects": [
                        {"target_project_path": "/proj/a", "changed_file_count": 5},
                        {"target_project_path": "/proj/b", "changed_file_count": 6},
                    ]
                }
            ),
        )
    )
    db_session.commit()

    changed = workflow_orchestrator._maybe_escalate_ready_step(
        db_session,
        requirement=requirement,
        workflow_run=run,
        step=step,
    )
    db_session.commit()

    assert changed is True
    payload = json.loads(step.execution_profile_json)
    assert payload["complexity_tier"] == "max"
    artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement.id,
        ArtifactRow.artifact_type == "runtime_adaptation",
    ).order_by(ArtifactRow.id.desc()).first()
    assert artifact is not None
    adaptation = json.loads(artifact.machine_readable_payload)
    assert adaptation["adaptation_type"] == "escalation"
    assert adaptation["to_tier"] == "max"


def test_runtime_downgrade_reduces_closeout_to_mini_tier(db_session):
    requirement = RequirementRow(
        title="Downgrade closeout",
        description_markdown="Close the requirement with minimal cost.",
        status="in_progress",
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="test")
    db_session.add(run)
    db_session.flush()
    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement.id,
        step_key="closeout",
        step_type="closeout",
        title="Close requirement",
        status="ready",
        sequence_no=50,
        context_scope="verification",
        done_when_markdown="done",
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        approval_policy_json="{}",
        execution_profile_json=json.dumps(
            {
                "complexity_tier": "standard",
                "budget_cap": {"max_runtime_seconds": 1800},
                "allow_escalation": False,
                "expected_outputs": [{"artifact_type": "validation_manifest"}],
            }
        ),
    )
    db_session.add(step)
    db_session.commit()

    changed = workflow_orchestrator._maybe_downgrade_ready_step(
        db_session,
        requirement=requirement,
        workflow_run=run,
        step=step,
    )
    db_session.commit()

    assert changed is True
    payload = json.loads(step.execution_profile_json)
    assert payload["complexity_tier"] == "mini"
    artifact = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == requirement.id,
        ArtifactRow.artifact_type == "runtime_adaptation",
    ).order_by(ArtifactRow.id.desc()).first()
    assert artifact is not None
    adaptation = json.loads(artifact.machine_readable_payload)
    assert adaptation["adaptation_type"] == "downgrade"
    assert adaptation["to_tier"] == "mini"


def test_followup_bugfix_profile_escalates_after_second_failure(db_session):
    step = WorkflowStepRow(
        workflow_run_id=1,
        requirement_id=1,
        step_key="test",
        step_type="test",
        title="Validate output",
        status="failed",
        sequence_no=40,
        context_scope="verification",
        done_when_markdown="done",
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        approval_policy_json="{}",
        execution_profile_json=json.dumps(
            {
                "complexity_tier": "standard",
                "budget_cap": {"max_runtime_seconds": 1800},
                "allow_escalation": True,
                "escalation_rule": {
                    "next_tier": "max",
                    "when": ["step_failed_twice", "review_or_test_blocker"],
                    "changed_files_threshold": 8,
                },
                "failure_count": 1,
            }
        ),
        retry_count=1,
    )

    bugfix_profile = workflow_orchestrator._build_followup_execution_profile(
        step,
        step_type="bugfix",
        failure_count=2,
        error_text="validation blocker repeated",
        project_change_metrics={"changed_project_count": 1, "total_changed_files": 2},
    )
    review_profile = workflow_orchestrator._build_followup_execution_profile(
        step,
        step_type="review",
        failure_count=2,
        error_text="validation blocker repeated",
        project_change_metrics={"changed_project_count": 1, "total_changed_files": 2},
    )

    assert bugfix_profile["complexity_tier"] == "max"
    assert bugfix_profile["failure_count"] == 2
    assert review_profile["complexity_tier"] == "standard"


def test_budget_guardrail_pauses_requirement_and_creates_budget_review(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Budget guarded workflow",
            "description_markdown": "Stop and request operator review when runtime exceeds the configured budget.",
            "priority": "high",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None

    run = WorkflowRunRow(requirement_id=requirement_id, plan_version=1, status="running", triggered_by="test")
    db_session.add(run)
    db_session.flush()
    requirement.active_workflow_run_id = run.id
    requirement.current_plan_version = 1
    requirement.status = "in_progress"

    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement_id,
        step_key="implementation",
        step_type="implementation",
        title="Implement change",
        status="running",
        sequence_no=10,
        context_scope="step_private",
        done_when_markdown="done",
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        approval_policy_json="{}",
        execution_profile_json=json.dumps(
            {
                "complexity_tier": "standard",
                "budget_cap": {
                    "max_attempts": 3,
                    "max_runtime_seconds": 1,
                    "max_input_tokens": 4000,
                    "max_output_tokens": 4000,
                },
                "allow_escalation": True,
            }
        ),
    )
    db_session.add(step)
    db_session.flush()
    task = TaskRow(
        description="impl",
        agent_id="dev_rel",
        status="completed",
        project_id="Synapse-Network-Growing",
        agent_group="content",
        skill_name="content-strategy",
        runtime_backend="codex_cli",
        runtime_provider="codex",
        runtime_model="gpt-5-codex",
        output_content="completed",
        execution_time_ms=5000,
        tokens_used=12000,
        budget_cost_points=24,
        started_at=workflow_orchestrator.utcnow(),
        completed_at=workflow_orchestrator.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    step.compatibility_task_id = task.id
    db_session.commit()

    workflow_orchestrator.sync_workflow_for_task(task.id)
    db_session.expire_all()

    detail = synced_client.get(f"/api/requirements/{requirement_id}").json()
    assert detail["requirement"]["status"] == "paused"
    assert detail["workflow_run"]["status"] == "paused"
    artifact_types = [artifact["artifact_type"] for artifact in detail["artifacts"]]
    assert "budget_guardrail" in artifact_types
    assert "budget_usage_summary" in artifact_types
    pending_budget_review = db_session.query(workflow_orchestrator.ApprovalRequestRow).filter(
        workflow_orchestrator.ApprovalRequestRow.requirement_id == requirement_id,
        workflow_orchestrator.ApprovalRequestRow.approval_type == "budget_review",
        workflow_orchestrator.ApprovalRequestRow.status == "pending",
    ).first()
    assert pending_budget_review is not None


def test_scheduler_uses_budget_usage_summary_for_running_requirement(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Running budget usage",
            "description_markdown": "Ensure scheduler sees actual running budget usage.",
            "priority": "high",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    requirement = db_session.query(RequirementRow).filter(RequirementRow.id == requirement_id).first()
    assert requirement is not None
    requirement.status = "in_progress"
    run = WorkflowRunRow(requirement_id=requirement_id, plan_version=1, status="running", triggered_by="test")
    db_session.add(run)
    db_session.flush()
    requirement.active_workflow_run_id = run.id
    db_session.add(
        ArtifactRow(
            requirement_id=requirement_id,
            workflow_run_id=run.id,
            artifact_type="budget_usage_summary",
            content_summary="budget usage",
            machine_readable_payload=json.dumps({"spent_points": 77}),
        )
    )
    db_session.commit()

    scheduler_resp = synced_client.get("/api/requirements/scheduler")
    assert scheduler_resp.status_code == 200
    decision = next(item for item in scheduler_resp.json()["decisions"] if item.get("requirement_id") == requirement_id)
    assert decision["budget_cost"] == 77


def test_non_mutating_step_repo_changes_block_without_vcs_delivery(synced_client, db_session, tmp_path):
    requirement = RequirementRow(
        title="Research must not trigger branch delivery",
        description_markdown="Non-mutating steps should not commit or push tracked repo changes.",
        status="in_progress",
        approval_status="waived",
    )
    db_session.add(requirement)
    db_session.flush()
    run = WorkflowRunRow(requirement_id=requirement.id, plan_version=1, status="running", triggered_by="test")
    db_session.add(run)
    db_session.flush()
    requirement.active_workflow_run_id = run.id
    step = WorkflowStepRow(
        workflow_run_id=run.id,
        requirement_id=requirement.id,
        step_key="research",
        step_type="research",
        title="Research context",
        status="running",
        sequence_no=10,
        context_scope="project",
        done_when_markdown="Do not modify production code.",
        file_scope_json="{}",
        validation_targets_json="[]",
        failure_policy_json="{}",
        approval_policy_json="{}",
        runtime_backend="codex_cli",
        retry_count=0,
        context_policy_json="{}",
        execution_profile_json="{}",
    )
    db_session.add(step)
    db_session.flush()

    task_dir = tmp_path / "roles" / "dev_rel" / "outputs" / "task-1"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "output.md").write_text("research summary", encoding="utf-8")
    now = workflow_orchestrator.utcnow().isoformat()
    (task_dir / "file-changes.json").write_text(
        json.dumps(
            {
                "changed_files": [
                    {
                        "filename": "README.md",
                        "additions": 5,
                        "deletions": 0,
                        "patch": "@@\n+docs\n",
                        "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
                    }
                ],
                "changed_target_project_paths": ["/Users/cliff/workspace/agent/Synapse-Network-Growing"],
                "captured_at": now,
                "baseline_captured_at": now,
            }
        ),
        encoding="utf-8",
    )
    task = TaskRow(
        description="research",
        agent_id="dev_rel",
        status="completed",
        output_path=str(task_dir / "output.md"),
        output_content="research summary",
        runtime_backend="codex_cli",
        runtime_provider="codex",
        runtime_model="gpt-5-codex-mini",
        started_at=workflow_orchestrator.utcnow(),
        completed_at=workflow_orchestrator.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    step.compatibility_task_id = task.id
    db_session.commit()

    workflow_orchestrator.sync_workflow_for_task(task.id)
    db_session.expire_all()

    detail = synced_client.get(f"/api/requirements/{requirement.id}").json()
    assert detail["requirement"]["status"] == "paused"
    assert detail["workflow_run"]["status"] == "paused"
    artifact_types = [artifact["artifact_type"] for artifact in detail["artifacts"]]
    assert "policy_violation" in artifact_types
    assert "delivery_blocker" not in artifact_types
