from server.database import LocalCiEventRow, LocalCiRunRow
from server.services.local_runner.ci_runs import (
    append_local_ci_event,
    claim_local_ci_run,
    finish_local_ci_run,
)


def test_create_local_ci_run_and_incremental_events(
    synced_client, db_session, tmp_path
):
    response = synced_client.post(
        "/api/ci/runs",
        json={
            "repo_path": str(tmp_path),
            "branch_name": "main",
            "commit_sha": "abc123",
            "base_ref": "origin/main",
            "scope": "auto",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    run_id = response.json()["id"]
    run = db_session.get(LocalCiRunRow, run_id)
    append_local_ci_event(
        db_session,
        ci_run_id=run_id,
        event_type="stdout",
        step_key="ci",
        message="chunk one\n",
    )
    append_local_ci_event(
        db_session,
        ci_run_id=run_id,
        event_type="stderr",
        step_key="ci",
        message="root cause in middle\n",
    )
    db_session.commit()

    page = synced_client.get(f"/api/ci/runs/{run_id}/events?after_sequence=0&limit=1")

    assert run is not None
    assert page.status_code == 200
    assert page.json()["has_more"] is True
    assert page.json()["items"][0]["message"] == "chunk one\n"


def test_reset_local_ci_run_appends_reset_event(synced_client, db_session, tmp_path):
    run = LocalCiRunRow(
        repo_path=str(tmp_path),
        branch_name="main",
        commit_sha="abc123",
        base_ref="origin/main",
        scope="auto",
        status="failed",
        actor="operator",
        exit_code=1,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    response = synced_client.post(
        f"/api/ci/runs/{int(run.id)}/reset",
        json={
            "confirm_phrase": "RESET_LOCAL_CI",
            "actor": "operator",
            "reason": "retry after local env fix",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "requested"
    events = (
        db_session.query(LocalCiEventRow)
        .filter(LocalCiEventRow.ci_run_id == int(run.id))
        .all()
    )
    assert events
    assert events[0].event_type == "local_ci_force_reset"


def test_local_ci_run_list_get_claim_and_finish(synced_client, db_session, tmp_path):
    first = synced_client.post(
        "/api/ci/runs",
        json={
            "repo_path": str(tmp_path),
            "branch_name": "main",
            "commit_sha": "abc123",
            "scope": "auto",
        },
    ).json()
    synced_client.post(
        "/api/ci/runs",
        json={
            "repo_path": str(tmp_path / "other"),
            "branch_name": "feature",
            "commit_sha": "def456",
            "scope": "full",
        },
    )

    page = synced_client.get(f"/api/ci/runs?repo_path={tmp_path}&limit=500")
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert page.json()["limit"] == 100
    detail = synced_client.get(f"/api/ci/runs/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["commit_sha"] == "abc123"

    claimed = claim_local_ci_run(db_session, run_id=int(first["id"]))
    assert claimed is not None
    assert claimed.status == "running"
    finished = finish_local_ci_run(
        db_session, int(first["id"]), exit_code=0, summary=""
    )
    assert finished.status == "passed"
    assert finished.summary == "Local CI passed."
    assert claim_local_ci_run(db_session, run_id=999999) is None


def test_local_ci_api_error_paths(synced_client, db_session, tmp_path):
    invalid_scope = synced_client.post(
        "/api/ci/runs",
        json={
            "repo_path": str(tmp_path),
            "branch_name": "main",
            "commit_sha": "abc123",
            "scope": "surprise",
        },
    )
    assert invalid_scope.status_code == 400

    missing = synced_client.get("/api/ci/runs/999999")
    assert missing.status_code == 404
    missing_events = synced_client.get("/api/ci/runs/999999/events")
    assert missing_events.status_code == 404
    missing_reset = synced_client.post(
        "/api/ci/runs/999999/reset", json={"confirm_phrase": "RESET_LOCAL_CI"}
    )
    assert missing_reset.status_code == 404

    run = LocalCiRunRow(
        repo_path=str(tmp_path),
        branch_name="main",
        commit_sha="abc123",
        base_ref="origin/main",
        scope="auto",
        status="passed",
        actor="operator",
        exit_code=0,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    bad_confirm = synced_client.post(
        f"/api/ci/runs/{int(run.id)}/reset",
        json={"confirm_phrase": "WRONG"},
    )
    assert bad_confirm.status_code == 400
    cannot_reset = synced_client.post(
        f"/api/ci/runs/{int(run.id)}/reset",
        json={"confirm_phrase": "RESET_LOCAL_CI"},
    )
    assert cannot_reset.status_code == 400
