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


def test_schedule_center_custom_secret_apply_is_scoped_and_observable(
    synced_client, db_session, monkeypatch
):
    calls: list[dict[str, object]] = []

    def fake_cleanup_secret_manager_versions(**kwargs):
        calls.append(dict(kwargs))
        return {
            "dry_run": bool(kwargs["dry_run"]),
            "project_count": 1,
            "secret_count": 1,
            "version_count": 5,
            "kept_count": 3,
            "candidate_count": 2,
            "destroyed_count": 0 if kwargs["dry_run"] else 2,
            "skipped_count": 0,
            "error_count": 0,
            "projects": [
                {
                    "project": "fabled-archive-494108-k5",
                    "secret_count": 1,
                    "candidates": [
                        {"secret": "schedule-e2e-cleanup-test", "version": "2"},
                        {"secret": "schedule-e2e-cleanup-test", "version": "1"},
                    ],
                    "errors": [],
                    "skipped": [],
                }
            ],
        }

    monkeypatch.setattr(
        "server.services.scheduling.cleanup_workflows.cleanup_secret_manager_versions",
        fake_cleanup_secret_manager_versions,
    )

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
    assert create.json()["is_builtin"] is False

    dry_run = synced_client.post(
        "/api/schedules/custom_secret_cleanup_e2e/run", json={"dry_run": True}
    )
    apply = synced_client.post(
        "/api/schedules/custom_secret_cleanup_e2e/run", json={"dry_run": False}
    )

    assert dry_run.status_code == 200
    assert apply.status_code == 200
    assert calls == [
        {
            "projects": ["fabled-archive-494108-k5"],
            "secret_ids": ["schedule-e2e-cleanup-test"],
            "keep": 3,
            "dry_run": True,
        },
        {
            "projects": ["fabled-archive-494108-k5"],
            "secret_ids": ["schedule-e2e-cleanup-test"],
            "keep": 3,
            "dry_run": False,
        },
    ]

    history = synced_client.get("/api/schedules/custom_secret_cleanup_e2e/runs")
    assert history.status_code == 200
    assert [item["dry_run"] for item in history.json()[:2]] == [False, True]
    assert history.json()[0]["result"]["destroyed_count"] == 2

    row = _db_workflow(db_session, "custom_secret_cleanup_e2e")
    assert row is not None
    assert row.is_builtin is False
    assert json.loads(row.input_query_json)["secret_ids"] == [
        "schedule-e2e-cleanup-test"
    ]

    delete = synced_client.delete("/api/schedules/custom_secret_cleanup_e2e")
    assert delete.status_code == 200
    assert _db_workflow(db_session, "custom_secret_cleanup_e2e") is None
