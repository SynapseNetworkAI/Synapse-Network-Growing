import json

from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    run_recurring_workflow,
    sync_recurring_workflows,
)


def test_secret_manager_cleanup_recurring_workflow_is_registered_and_runnable(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)

    row = get_recurring_workflow(db_session, "secret_manager_version_cleanup_sweep")
    assert row.display_name == "Secret Manager Version Cleanup Sweep"
    assert json.loads(row.schedule_json)["interval_minutes"] == 30
    assert json.loads(row.input_query_json)["keep"] == 2
    assert "destroy_old_secret_manager_versions" in row.output_action_json

    calls: list[bool] = []

    def fake_cleanup_secret_manager_versions(**kwargs):
        calls.append(bool(kwargs["dry_run"]))
        return {
            "dry_run": bool(kwargs["dry_run"]),
            "candidate_count": 4,
            "destroyed_count": 0 if kwargs["dry_run"] else 4,
            "error_count": 0,
        }

    monkeypatch.setattr(
        "server.services.scheduling.cleanup_workflows.cleanup_secret_manager_versions",
        fake_cleanup_secret_manager_versions,
    )

    dry_run = run_recurring_workflow(
        db_session, workflow_key="secret_manager_version_cleanup_sweep", dry_run=True
    )
    apply_run = run_recurring_workflow(
        db_session, workflow_key="secret_manager_version_cleanup_sweep", dry_run=False
    )

    assert calls == [True, False]
    assert dry_run["result"]["candidate_count"] == 4
    assert dry_run["result"]["destroyed_count"] == 0
    assert apply_run["result"]["destroyed_count"] == 4
