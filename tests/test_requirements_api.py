from __future__ import annotations

"""Tests for requirement-first workflow orchestration."""
import json
from unittest.mock import MagicMock, patch

from server.database import (
    ProjectPolicyRow,
    RequirementAcceptanceCheckRow,
    RequirementRow,
    TaskRow,
    WorkflowRunRow,
    WorkflowStepEventRow,
    WorkflowStepRow,
)
from server.services.task_runner import _run_task_sync
from server.services.task_runtime import TaskExecutionResult


def _runtime_result(*, text: str = "", error: str | None = None, execution_time_ms: int = 5):
    return TaskExecutionResult(
        text=text,
        files=[],
        error=error,
        execution_time_ms=execution_time_ms,
        runtime_backend="legacy",
        events=[],
        deferred=False,
    )


def _deferred_runtime_result(*, session_id: str = "session-running-123", execution_time_ms: int = 5):
    return TaskExecutionResult(
        text="",
        files=[],
        error=None,
        execution_time_ms=execution_time_ms,
        runtime_backend="copilot_sdk",
        runtime_session_id=session_id,
        events=[],
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
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    planned = plan_resp.json()
    assert planned["requirement"]["current_plan_version"] == 1
    assert [step["step_type"] for step in planned["workflow_run"]["steps"]] == [
        "implementation",
        "review",
        "test",
        "closeout",
    ]

    call_counts = {"test": 0}

    class FakeRuntime:
        def execute(self, *, task_description, **_kwargs):
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

    assert start_resp.status_code == 200
    data = start_resp.json()
    assert data["requirement"]["status"] == "done"
    assert data["workflow_run"]["status"] == "completed"

    step_types = [step["step_type"] for step in data["workflow_run"]["steps"]]
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
    assert len(tasks) == 6
    assert sum(1 for task in tasks if task.status == "failed") == 1
    assert sum(1 for task in tasks if task.status == "completed") == 5

    closeout = db_session.query(WorkflowStepRow).filter(
        WorkflowStepRow.requirement_id == requirement_id,
        WorkflowStepRow.step_type == "closeout",
    ).first()
    assert closeout is not None
    assert closeout.status == "completed"
    assert data["delivery_state"]["publish_status"] == "review_ready"
    assert data["delivery_state"]["branch_name"].startswith(f"ops/req-{requirement_id}-")


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
        },
    )
    assert create_resp.status_code == 201
    requirement_id = create_resp.json()["requirement"]["id"]

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
    assert started["requirement"]["status"] == "needs_revision"
    assert started["workflow_run"]["status"] == "cancelled"
    assert any(artifact["artifact_type"] == "requirement_revision" for artifact in started["artifacts"])

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

    replan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert replan_resp.status_code == 200


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
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    synced_client.post(f"/api/requirements/{requirement_id}/plan")

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
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
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]
    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200
    assert any(artifact["artifact_type"] == "delivery_contract" for artifact in plan_resp.json()["artifacts"])

    class SuccessRuntime:
        def execute(self, **_kwargs):
            return _runtime_result(text="ok")

    with patch("server.services.task_runner.get_task_runtime", return_value=SuccessRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=_sync_dispatch
    ):
        start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")

    assert start_resp.status_code == 200
    detail = start_resp.json()
    assert detail["delivery_state"]["publish_status"] == "review_ready"
    assert sorted(detail["delivery_state"]["pending_checks"]) == ["npm run build", "pytest -q"]

    blocked_publish = synced_client.post(
        f"/api/requirements/{requirement_id}/publish",
        json={"completed_checks": ["pytest -q"], "note": "not enough"},
    )
    assert blocked_publish.status_code == 400
    assert "npm run build" in blocked_publish.json()["detail"]

    publish_resp = synced_client.post(
        f"/api/requirements/{requirement_id}/publish",
        json={"completed_checks": ["pytest -q", "npm run build"], "note": "ship it"},
    )
    assert publish_resp.status_code == 200
    published = publish_resp.json()
    assert published["delivery_state"]["publish_status"] == "published"
    assert published["delivery_state"]["pending_checks"] == []
    assert sorted(published["delivery_state"]["confirmed_checks"]) == ["npm run build", "pytest -q"]
    assert any(artifact["artifact_type"] == "publish_record" for artifact in published["artifacts"])


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
