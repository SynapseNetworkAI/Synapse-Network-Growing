from server.database import RecurringWorkflowRow, RecurringWorkflowRunRow
from server.services.scheduling.recurring_workflows import (
    list_recurring_workflow_runs,
    run_recurring_workflow,
    sync_recurring_workflows,
)
from server.services.scheduling.locks import acquire_scheduler_lock


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
