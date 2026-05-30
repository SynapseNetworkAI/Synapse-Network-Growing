import json

from server.database import DeploymentRecordRow, ReleaseTaskRow


def _create_task(client, **overrides):
    payload = {
        "project_key": "synapse-network",
        "project_display_name": "Synapse-Network",
        "service_key": "gateway",
        "branch_name": "main",
        "environment": "staging",
    }
    payload.update(overrides)
    return client.post("/api/releases/tasks", json=payload)


def test_create_release_task_and_query_defaults_to_local_runner(synced_client):
    response = _create_task(synced_client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requested"
    assert payload["project_key"] == "synapse-network"
    assert payload["service_key"] == "gateway"

    query = synced_client.get("/api/releases/tasks/query", params={"limit": 10})
    assert query.status_code == 200
    items = query.json()["items"]
    assert items[0]["id"] == payload["id"]
    assert items[0]["deployment_record_id"] is None


def test_get_release_task_by_id_returns_detail(synced_client):
    task = _create_task(synced_client, service_key="docs-front").json()

    response = synced_client.get(f"/api/releases/tasks/{task['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task["id"]
    assert payload["service_key"] == "docs-front"
    assert payload["deployment_record_id"] is None


def test_get_release_task_by_id_handles_missing_task(synced_client):
    response = synced_client.get("/api/releases/tasks/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release task not found."


def test_agent_release_task_requires_local_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_DEPLOY_API_TOKEN", "")
    monkeypatch.delenv("OPS_AGENT_DEPLOY_API_TOKEN", raising=False)

    response = _create_task(synced_client, actor="codex/test-thread")

    assert response.status_code == 403
    assert "OPS_AGENT_DEPLOY_API_TOKEN" in response.json()["detail"]


def test_agent_release_task_accepts_matching_local_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_DEPLOY_API_TOKEN", "deploy-token")

    response = synced_client.post(
        "/api/releases/tasks",
        headers={"X-Growing-Agent-Deploy-Token": "deploy-token"},
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "staging",
            "actor": "codex/test-thread",
        },
    )

    assert response.status_code == 200
    assert response.json()["actor"] == "codex/test-thread"


def test_staging_deploy_creates_local_runner_record(synced_client, db_session):
    task = _create_task(synced_client).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "operator", "note": "staging via local runner"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"] is not None
    record = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    assert record.trigger_source == "local_deploy_runner"
    assert record.workflow_file == "local_deploy_runner"
    metadata = json.loads(record.metadata_json)
    assert metadata["localDeployRunner"] is True
    assert metadata["localRunnerCommand"][0:2] == [
        "bash",
        "scripts/local/deploy_synapse_staging.sh",
    ]
    assert metadata["deployScope"] == "gateway"


def test_agent_staging_deploy_requires_matching_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_DEPLOY_API_TOKEN", "deploy-token")
    task = _create_task(synced_client).json()

    blocked = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "codex/test-thread"},
    )
    allowed = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        headers={"X-Growing-Agent-Deploy-Token": "deploy-token"},
        json={"actor": "codex/test-thread"},
    )

    assert blocked.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["deployment_record_id"] is not None


def test_sync_deployment_statuses_only_summarizes_local_runner_records(
    synced_client, db_session
):
    running = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        health_status="checking",
        trigger_source="local_deploy_runner",
    )
    succeeded = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        health_status="passed",
        trigger_source="local_deploy_runner",
    )
    failed = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="failed",
        health_status="failed",
        trigger_source="local_deploy_runner",
    )
    db_session.add_all([running, succeeded, failed])
    db_session.commit()

    response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")

    assert response.status_code == 200
    payload = response.json()
    assert payload["local_runner_only"] is True
    assert set(payload["running_ids"]) == {int(running.id)}
    assert set(payload["succeeded_ids"]) == {int(succeeded.id)}
    assert set(payload["failed_ids"]) == {int(failed.id)}


def test_release_task_status_patch_is_local_state_only(synced_client, db_session):
    task = _create_task(synced_client).json()

    response = synced_client.patch(
        f"/api/releases/tasks/{task['id']}",
        json={"status": "failed", "operator": "operator", "note": "manual fail"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["note"] == "manual fail"
    row = db_session.get(ReleaseTaskRow, task["id"])
    assert row.status == "failed"


def test_release_task_rejects_unknown_service(synced_client):
    response = _create_task(synced_client, service_key="nope")

    assert response.status_code == 400
    assert "service_key must be one of" in response.json()["detail"]
