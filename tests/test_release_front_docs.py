import json

from server.database import DeploymentRecordRow
def test_front_docs_release_task_staging_deploy_creates_local_runner_record(
    synced_client, db_session
):
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "docs-front",
            "branch_name": "codex/staging-docs-front",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "ops-lead", "note": "ship front docs staging"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"] is not None
    assert payload["deployment_health_status"] == "checking"

    deployment = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    assert deployment.trigger_source == "local_deploy_runner"
    assert deployment.workflow_file == "local_deploy_runner"
    metadata = json.loads(deployment.metadata_json)
    assert metadata["deploy_strategy"] == "local_deploy_runner"
    assert metadata["service_key"] == "docs-front"
    assert metadata["deployScope"] == "docs-front"
    assert metadata["localRunnerCommand"][0:2] == ["bash", "scripts/local/deploy_synapse_staging.sh"]
