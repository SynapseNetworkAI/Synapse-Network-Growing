"""Tests for requirement-first workflow orchestration."""
from unittest.mock import MagicMock, patch

from server.database import RequirementRow, TaskRow, WorkflowStepRow
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
    assert "bug_report" in artifact_types
    assert "validation_manifest" in artifact_types

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
    assert replan_resp.json()["requirement"]["current_plan_version"] == 2