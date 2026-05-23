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
    assert "12:00" in row.schedule_json

    calls: list[bool] = []

    def fake_run_secret_manager_version_cleanup_workflow(*, dry_run):
        calls.append(bool(dry_run))
        return {
            "dry_run": bool(dry_run),
            "candidate_count": 2,
            "destroyed_count": 0 if dry_run else 2,
            "error_count": 0,
        }

    monkeypatch.setattr(
        "server.services.scheduling.cleanup_workflows.run_secret_manager_version_cleanup_workflow",
        fake_run_secret_manager_version_cleanup_workflow,
    )
    dry_run = run_recurring_workflow(
        db_session, workflow_key="secret_manager_version_cleanup_sweep", dry_run=True
    )
    apply_run = run_recurring_workflow(
        db_session, workflow_key="secret_manager_version_cleanup_sweep", dry_run=False
    )

    assert calls == [True, False]
    assert dry_run["result"]["candidate_count"] == 2
    assert apply_run["result"]["destroyed_count"] == 2
