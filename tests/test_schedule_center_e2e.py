import json

from server.database import RecurringWorkflowRow, RecurringWorkflowRunRow


def _db_workflow(db_session, workflow_key: str) -> RecurringWorkflowRow | None:
    return (
        db_session.query(RecurringWorkflowRow)
        .filter(RecurringWorkflowRow.workflow_key == workflow_key)
        .first()
    )


def _latest_run(db_session, workflow_key: str) -> RecurringWorkflowRunRow | None:
    return (
        db_session.query(RecurringWorkflowRunRow)
        .filter(RecurringWorkflowRunRow.workflow_key == workflow_key)
        .order_by(RecurringWorkflowRunRow.id.desc())
        .first()
    )


def test_schedule_center_api_run_history_and_db_evidence(
    synced_client, db_session, monkeypatch
):
    calls: list[dict[str, object]] = []

    def fake_cleanup_artifact_registry_versions(**kwargs):
        calls.append(dict(kwargs))
        return {
            "dry_run": bool(kwargs["dry_run"]),
            "project_count": 1,
            "image_count": 5,
            "kept_count": 3,
            "candidate_count": 2,
            "deleted_count": 0 if kwargs["dry_run"] else 2,
            "skipped_count": 0,
            "error_count": 0,
            "projects": [
                {
                    "project": "demo",
                    "repository": "schedule-e2e",
                    "kept": [{"image": "demo/repo/app@sha256:3"}],
                    "candidates": [{"image": "demo/repo/app@sha256:1"}],
                    "skipped": [],
                    "errors": [],
                }
            ],
        }

    monkeypatch.setattr(
        "server.services.scheduling.cleanup_workflows.cleanup_artifact_registry_versions",
        fake_cleanup_artifact_registry_versions,
    )

    schedules = synced_client.get("/api/schedules")
    assert schedules.status_code == 200
    keys = {item["workflow_key"] for item in schedules.json()}
    assert "artifact_registry_cleanup_sweep" in keys
    assert "secret_manager_version_cleanup_sweep" in keys
    assert "staging_environment_shutdown_sweep" in keys

    workflow = _db_workflow(db_session, "artifact_registry_cleanup_sweep")
    assert workflow is not None
    assert json.loads(workflow.output_action_json)["kind"] == (
        "cleanup_artifact_registry_versions"
    )

    run = synced_client.post(
        "/api/schedules/artifact_registry_cleanup_sweep/run",
        json={"dry_run": True},
    )
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert run.json()["result"]["deleted_count"] == 0
    assert calls[-1]["dry_run"] is True

    history = synced_client.get("/api/schedules/artifact_registry_cleanup_sweep/runs")
    assert history.status_code == 200
    assert history.json()[0]["dry_run"] is True
    assert history.json()[0]["result"]["projects"][0]["candidates"]

    db_run = _latest_run(db_session, "artifact_registry_cleanup_sweep")
    assert db_run is not None
    assert db_run.status == "succeeded"
    assert db_run.dry_run is True
    assert db_run.error_excerpt in {None, ""}
    result = json.loads(db_run.result_json)
    assert result["candidate_count"] == 2
    assert result["deleted_count"] == 0


def test_schedule_center_secret_manager_template_is_enabled(synced_client):
    create = synced_client.post(
        "/api/schedules",
        json={
            "template_key": "secret_manager_version_cleanup",
            "workflow_key": "custom_secret_cleanup_e2e",
            "display_name": "Custom Secret Cleanup E2E",
            "input_query": {
                "projects": ["fabled-archive-494108-k5"],
                "secret_ids": ["schedule-e2e-cleanup-test"],
                "keep": 3,
            },
        },
    )
    assert create.status_code == 200
    assert create.json()["handler_key"] == "destroy_old_secret_manager_versions"
