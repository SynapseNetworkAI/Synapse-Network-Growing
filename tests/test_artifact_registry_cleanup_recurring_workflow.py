from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    run_recurring_workflow,
    sync_recurring_workflows,
)


def test_artifact_registry_cleanup_recurring_workflow_is_registered_and_runnable(
    db_session, monkeypatch
):
    sync_recurring_workflows(db_session)

    row = get_recurring_workflow(db_session, "artifact_registry_cleanup_sweep")
    assert row.display_name == "Artifact Registry Cleanup Sweep"
    assert "cleanup_artifact_registry_versions" in row.output_action_json

    calls: list[bool] = []

    def fake_cleanup_artifact_registry_versions(**kwargs):
        calls.append(bool(kwargs["dry_run"]))
        return {
            "dry_run": bool(kwargs["dry_run"]),
            "candidate_count": 4,
            "deleted_count": 0 if kwargs["dry_run"] else 4,
            "error_count": 0,
        }

    monkeypatch.setattr(
        "server.services.scheduling.cleanup_workflows.cleanup_artifact_registry_versions",
        fake_cleanup_artifact_registry_versions,
    )

    dry_run = run_recurring_workflow(
        db_session, workflow_key="artifact_registry_cleanup_sweep", dry_run=True
    )
    apply_run = run_recurring_workflow(
        db_session, workflow_key="artifact_registry_cleanup_sweep", dry_run=False
    )

    assert calls == [True, False]
    assert dry_run["result"]["candidate_count"] == 4
    assert apply_run["result"]["deleted_count"] == 4
