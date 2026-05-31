import json

from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    run_recurring_workflow,
    sync_recurring_workflows,
)


def test_staging_environment_shutdown_recurring_workflow_is_registered_and_runnable(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)

    row = get_recurring_workflow(db_session, "staging_environment_shutdown_sweep")
    assert row.display_name == "Staging Environment Shutdown Sweep"
    assert json.loads(row.schedule_json)["suggested_local_time"] == "23:00"
    assert json.loads(row.input_query_json)["project"] == "fabled-archive-494108-k5"
    assert json.loads(row.output_action_json)["kind"] == "shutdown_staging_environment"

    calls: list[bool] = []

    def fake_shutdown_staging_environment(**kwargs):
        calls.append(bool(kwargs["dry_run"]))
        return {
            "dry_run": bool(kwargs["dry_run"]),
            "planned_count": 3 if kwargs["dry_run"] else 0,
            "succeeded_count": 0 if kwargs["dry_run"] else 3,
            "failed_count": 0,
            "actions": [],
        }

    monkeypatch.setattr(
        "server.services.scheduling.cleanup_workflows.shutdown_staging_environment",
        fake_shutdown_staging_environment,
    )

    dry_run = run_recurring_workflow(
        db_session, workflow_key="staging_environment_shutdown_sweep", dry_run=True
    )
    apply_run = run_recurring_workflow(
        db_session, workflow_key="staging_environment_shutdown_sweep", dry_run=False
    )

    assert calls == [True, False]
    assert dry_run["result"]["planned_count"] == 3
    assert apply_run["result"]["succeeded_count"] == 3
