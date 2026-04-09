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

    def sync_dispatch(task_id: int, agent_persona: dict, skill_name: str):
        _run_task_sync(task_id, agent_persona, skill_name)
        return MagicMock(name=f"task-{task_id}")

    with patch("server.services.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
        "server.services.task_runner.dispatch", side_effect=sync_dispatch
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