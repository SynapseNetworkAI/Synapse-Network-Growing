import json
from datetime import datetime, timedelta, timezone

from server.database import HumanGateRequestRow, RecurringWorkflowRow, RecurringWorkflowRunRow, RequirementRow, WorkflowArtifactRow, WorkflowRunRow
from server.services.scheduling.recurring_workflows import (
    _ci_status_sweep,
    _next_run_at,
    list_recurring_workflow_runs,
    run_recurring_workflow,
    sync_recurring_workflows,
)
from server.services.scheduling.locks import acquire_scheduler_lock
from server.services.planning.scheduler import goal_planner_sweep_due


def test_recurring_workflow_dry_run_records_history(db_session):
    sync_recurring_workflows(db_session)

    result = run_recurring_workflow(
        db_session,
        workflow_key="bug_log_sweep",
        dry_run=True,
        triggered_by="operator",
    )

    assert result["status"] == "completed"
    assert result["run_id"] is not None
    rows = list_recurring_workflow_runs(db_session, "bug_log_sweep")
    assert len(rows) == 1
    assert rows[0].status == "succeeded"
    assert rows[0].dry_run is True
    assert rows[0].duration_ms >= 0


def test_recurring_workflow_failed_run_records_error(db_session):
    sync_recurring_workflows(db_session)

    try:
        run_recurring_workflow(db_session, workflow_key="unsupported_workflow", dry_run=False)
    except ValueError:
        pass

    assert db_session.query(RecurringWorkflowRunRow).count() == 0

    db_session.add(
        RecurringWorkflowRow(
            workflow_key="unsupported_workflow",
            display_name="Unsupported",
            description="Unsupported test workflow",
            status="active",
            trigger_type="scheduled",
            owner_role="tester",
            schedule_json='{"cadence":"interval","interval_minutes":5}',
            input_query_json="{}",
            output_action_json="{}",
            escalation_rule_json="{}",
            validation_signal_json="{}",
            is_builtin=False,
        )
    )
    db_session.commit()

    try:
        run_recurring_workflow(db_session, workflow_key="unsupported_workflow", dry_run=False)
    except ValueError as exc:
        assert "Unsupported recurring workflow" in str(exc)

    history = db_session.query(RecurringWorkflowRunRow).filter(RecurringWorkflowRunRow.workflow_key == "unsupported_workflow").one()
    assert history.status == "failed"
    assert "Unsupported recurring workflow" in str(history.error_excerpt)


def test_recurring_workflows_health_endpoint(synced_client):
    response = synced_client.get("/api/recurring-workflows/health")

    assert response.status_code == 200
    payload = response.json()
    assert "bug_log_scheduler" in payload
    assert "lock" in payload["bug_log_scheduler"]
    assert "notification_dispatcher" in payload
    assert payload["recurring_registry"]["total_count"] >= 7


def test_recurring_workflow_runs_endpoint(synced_client):
    run_response = synced_client.post("/api/recurring-workflows/bug_log_sweep/run", json={"dry_run": True})
    assert run_response.status_code == 200

    runs_response = synced_client.get("/api/recurring-workflows/bug_log_sweep/runs?limit=5")
    assert runs_response.status_code == 200
    runs = runs_response.json()
    assert runs
    assert runs[0]["workflow_key"] == "bug_log_sweep"
    assert runs[0]["dry_run"] is True


def test_goal_planner_sweep_due_after_daily_slot_without_prior_run():
    from datetime import datetime, timezone

    assert goal_planner_sweep_due(
        last_run_at=None,
        now=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
        local_time="09:00",
    )


def test_goal_planner_sweep_due_uses_operator_timezone():
    from datetime import datetime, timezone

    assert not goal_planner_sweep_due(
        last_run_at=None,
        now=datetime(2026, 4, 20, 0, 59, tzinfo=timezone.utc),
        local_time="09:00",
        timezone_name="Asia/Kuala_Lumpur",
    )
    assert goal_planner_sweep_due(
        last_run_at=None,
        now=datetime(2026, 4, 20, 1, 1, tzinfo=timezone.utc),
        local_time="09:00",
        timezone_name="Asia/Kuala_Lumpur",
    )
    assert not goal_planner_sweep_due(
        last_run_at=datetime(2026, 4, 20, 1, 1, tzinfo=timezone.utc),
        now=datetime(2026, 4, 20, 2, 0, tzinfo=timezone.utc),
        local_time="09:00",
        timezone_name="Asia/Kuala_Lumpur",
    )
    assert not goal_planner_sweep_due(
        last_run_at=datetime(2026, 4, 20, 9, 1, tzinfo=timezone.utc),
        now=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
        local_time="09:00",
    )


def test_recurring_daily_next_run_uses_operator_timezone(monkeypatch):
    monkeypatch.setattr("server.config.OPERATOR_TIMEZONE", "Asia/Kuala_Lumpur")
    row = RecurringWorkflowRow(
        workflow_key="goal_planner_sweep",
        display_name="Goal Planner Sweep",
        description="Daily planner",
        status="active",
        trigger_type="scheduled",
        owner_role="portfolio_planner",
        schedule_json='{"cadence":"daily","suggested_local_time":"09:00"}',
        input_query_json="{}",
        output_action_json="{}",
        escalation_rule_json="{}",
        validation_signal_json="{}",
    )

    next_run = _next_run_at(row, now=datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc))

    assert next_run == datetime(2026, 4, 22, 1, 0, tzinfo=timezone.utc)


def test_goal_planner_recurring_workflow_runs_real_planner_dry_run(db_session, monkeypatch):
    from server.services.planning.planner_agent import PlannerAgentCandidate

    monkeypatch.setattr(
        "server.services.planning.lifecycle.synthesize_candidate_for_goal",
        lambda **kwargs: PlannerAgentCandidate(
            title=f"Advance goal: {kwargs['goal'].title}",
            description_markdown="## Goal\nDry-run candidate",
            workflow_key=str(kwargs["goal"].workflow_key or "agent_self_repair"),
            priority="normal",
            risk_level="normal",
            confidence=0.7,
            rationale="Dry-run planner test.",
            acceptance_contract=kwargs.get("acceptance_contract") or {
                "execution_acceptance_steps": [
                    {
                        "step_key": "dry_run",
                        "title": "Dry-run evidence",
                        "expected_result": "Dry-run candidate has safe evidence.",
                        "required_commands": ["python -m pytest -q"],
                    }
                ]
            },
            metadata={"generated_by": "planner_agent_v1", "planner_repair_attempts": 0},
        ),
    )
    sync_recurring_workflows(db_session)

    result = run_recurring_workflow(db_session, workflow_key="goal_planner_sweep", dry_run=True)

    assert result["status"] == "completed"
    assert result["result"]["dry_run"] is True
    assert "routing_results" in result["result"]
    rows = list_recurring_workflow_runs(db_session, "goal_planner_sweep")
    assert rows


def test_bug_log_sweep_skips_when_scheduler_lock_is_held(db_session):
    sync_recurring_workflows(db_session)
    lock = acquire_scheduler_lock(
        db_session,
        lock_key="scheduler:bug_log_sweep",
        owner_id="test-owner",
        ttl_seconds=300,
        metadata={"test": True},
    )
    assert lock is not None

    result = run_recurring_workflow(db_session, workflow_key="bug_log_sweep", dry_run=True)

    assert result["status"] == "skipped_locked"
    rows = list_recurring_workflow_runs(db_session, "bug_log_sweep")
    assert len(rows) == 1
    assert rows[0].status == "skipped_locked"


def _create_awaiting_ci_run(db_session, tmp_path, *, exit_code: int | None = None, log_body: str = ""):
    requirement = RequirementRow(
        title="CI final regression",
        description_markdown="Run final regression before PR handoff.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
        status="in_progress",
    )
    db_session.add(requirement)
    db_session.flush()
    log_path = tmp_path / f"run-{requirement.id}.log"
    exit_code_path = tmp_path / f"run-{requirement.id}.exit_code"
    log_path.write_text(log_body, encoding="utf-8")
    if exit_code is not None:
        exit_code_path.write_text(f"{exit_code}\n", encoding="utf-8")
    blackboard = {
        "workflow_key": "agent_self_repair",
        "current_state": "awaiting_ci",
        "ci": {
            "status": "in_progress",
            "ci_backend": "local_marker",
            "ci_command": ["python", "-m", "pytest", "-q"],
            "ci_log_path": str(log_path),
            "ci_exit_code_path": str(exit_code_path),
            "ci_timeout_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        },
    }
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key="agent_self_repair",
        current_state="awaiting_ci",
        status="awaiting_ci",
        triggered_by="test",
        blackboard_json=json.dumps(blackboard),
    )
    db_session.add(run)
    db_session.flush()
    return run, log_path, exit_code_path


def test_ci_status_sweep_failed_ci_records_bounded_tail_and_human_gate(db_session, tmp_path):
    long_log = "\n".join(f"line {index}" for index in range(2000))
    run, _log_path, _exit_path = _create_awaiting_ci_run(db_session, tmp_path, exit_code=1, log_body=long_log)

    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["processed_count"] == 1
    db_session.refresh(run)
    assert run.current_state == "awaiting_operator"
    assert run.status == "awaiting_operator"
    assert run.resolution == "ci_failed_needs_human"
    artifact = db_session.query(WorkflowArtifactRow).filter(WorkflowArtifactRow.workflow_run_id == run.id).one()
    assert "line 1999" in artifact.human_readable_body
    assert "line 0" not in artifact.human_readable_body
    assert len(artifact.human_readable_body.encode("utf-8")) <= 8192
    gate = db_session.query(HumanGateRequestRow).filter(HumanGateRequestRow.workflow_run_id == run.id).one()
    assert gate.gate_type == "ci_final_regression_failed"


def test_ci_status_sweep_in_progress_does_not_read_log(db_session, tmp_path, monkeypatch):
    run, _log_path, _exit_path = _create_awaiting_ci_run(db_session, tmp_path, exit_code=None, log_body="still running")

    def fail_if_read(*args, **kwargs):
        raise AssertionError("in-progress CI must not read log tail")

    monkeypatch.setattr("server.services.scheduling.recurring_workflows._bounded_log_tail", fail_if_read)
    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["processed_count"] == 0
    db_session.refresh(run)
    assert run.current_state == "awaiting_ci"


def test_ci_status_sweep_recovers_stale_processing_lock(db_session, tmp_path):
    run, _log_path, _exit_path = _create_awaiting_ci_run(db_session, tmp_path, exit_code=None)
    run.current_state = "processing_ci_result"
    run.status = "awaiting_ci"
    run.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db_session.commit()

    result = _ci_status_sweep(db_session, runtime_cap_seconds=60, stale_lock_seconds=300)

    assert result["stale_processing_locks_recovered"] == 1
    db_session.refresh(run)
    assert run.current_state == "awaiting_ci"


def test_ci_status_sweep_runtime_cap_stops_before_next_workflow(db_session, tmp_path, monkeypatch):
    _create_awaiting_ci_run(db_session, tmp_path, exit_code=None)
    _create_awaiting_ci_run(db_session, tmp_path, exit_code=None)
    ticks = iter([0.0, 61.0])
    monkeypatch.setattr("server.services.scheduling.recurring_workflows.time.monotonic", lambda: next(ticks, 61.0))

    result = _ci_status_sweep(db_session, runtime_cap_seconds=60)

    assert result["sweep_runtime_cap_reached"] is True
    assert result["processed_count"] == 0
    assert result["remaining_count"] == 2


def test_ci_status_sweep_is_registered(db_session):
    rows = sync_recurring_workflows(db_session)

    assert any(row.workflow_key == "ci_status_sweep" for row in rows)
