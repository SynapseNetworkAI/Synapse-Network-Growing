import json

from server.database import DeploymentRecordRow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow


def test_scheduled_jobs_catalog_returns_gateway_and_admin_jobs(synced_client):
    response = synced_client.get("/api/releases/scheduled-jobs/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 7
    names = {item["job_name"] for item in payload}
    assert "synapse-staging-deposit-indexer" in names
    assert "synapse-staging-gateway-admin-db-migrate" in names
    assert sum(1 for item in payload if item["job_type"] == "periodic") == 5
    assert sum(1 for item in payload if item["job_type"] == "migration") == 2


def test_create_scheduled_job_task_does_not_publish(synced_client, db_session):
    response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "staging",
            "source_ref": "main",
            "actor": "operator",
            "run_smoke_jobs": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_name"] == "synapse-staging-deposit-indexer"
    assert payload["status"] == "requested"
    assert payload["health_status"] == "pending"
    assert payload["deployment_record_id"] is None
    assert db_session.query(DeploymentRecordRow).count() == 0


def test_publish_scheduled_job_task_creates_local_runner_record(
    synced_client, db_session
):
    create_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "staging",
            "source_ref": "main",
            "actor": "operator",
            "run_smoke_jobs": True,
        },
    )
    task_id = create_response.json()["id"]
    response = synced_client.post(
        f"/api/releases/scheduled-jobs/tasks/{task_id}/publish",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert payload["family"] == "gateway"
    assert payload["publish_mode"] == "single_job"
    assert payload["job_name"] == "synapse-staging-deposit-indexer"
    assert payload["jobs"] == ["synapse-staging-deposit-indexer"]

    record = db_session.get(DeploymentRecordRow, int(payload["deployment_record_id"]))
    assert record is not None
    assert record.trigger_source == "local_deploy_runner"
    assert record.workflow_file == "local_scheduled_job_runner"
    metadata = json.loads(record.metadata_json)
    assert metadata["scheduledJobReleaseTaskId"] == task_id
    assert metadata["publishMode"] == "single_job"
    assert metadata["jobName"] == "synapse-staging-deposit-indexer"
    assert metadata["jobs"] == ["synapse-staging-deposit-indexer"]
    assert metadata["localRunnerCommand"][0:2] == ["bash", "scripts/local/deploy_synapse_scheduled_job.sh"]

    task = db_session.get(ScheduledJobReleaseTaskRow, task_id)
    assert task.status == "deploying"
    assert task.deployment_record_id == int(payload["deployment_record_id"])


def test_publish_single_migration_job_requires_confirmation(synced_client):
    response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-db-migrate",
            "environment": "staging",
            "source_ref": "main",
        },
    )

    assert response.status_code == 400
    assert "run_migrations confirmation" in response.json()["detail"]


def test_publish_scheduled_job_rejects_unknown_job_and_non_staging(synced_client):
    unknown_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={"job_name": "not-a-real-job", "environment": "staging"},
    )

    assert unknown_response.status_code == 400
    assert "Unknown scheduled job name" in unknown_response.json()["detail"]

    production_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "production",
        },
    )

    assert production_response.status_code == 400
    assert "environment must be staging" in production_response.json()["detail"]


def test_scheduled_jobs_records_returns_paginated_publish_records(
    synced_client, db_session
):
    task = ScheduledJobReleaseTaskRow(
        project_key="synapse-network",
        job_name="synapse-staging-deposit-indexer",
        job_family="gateway",
        job_type="periodic",
        environment="staging",
        source_ref_type="branch",
        source_ref="main",
        status="completed",
        health_status="passed",
        created_by="operator",
    )
    db_session.add(task)
    db_session.commit()

    response = synced_client.get(
        "/api/releases/scheduled-jobs/tasks",
        params={
            "job_name": "synapse-staging-deposit-indexer",
            "family": "gateway",
            "status": "completed",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert payload["items"][0]["job_name"] == "synapse-staging-deposit-indexer"
    assert payload["items"][0]["family"] == "gateway"
    assert payload["items"][0]["status"] == "completed"


def test_scheduled_jobs_sync_reconciles_local_runner_success(
    synced_client, db_session
):
    task = ScheduledJobReleaseTaskRow(
        project_key="synapse-network",
        job_name="synapse-staging-deposit-indexer",
        job_family="gateway",
        job_type="periodic",
        environment="staging",
        source_ref_type="branch",
        source_ref="main",
        status="deploying",
        health_status="checking",
        created_by="operator",
    )
    db_session.add(task)
    db_session.commit()
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="succeeded",
        health_status="passed",
        branch_name="main",
        workflow_file="local_scheduled_job_runner",
        actor="operator",
        trigger_source="local_deploy_runner",
        metadata_json=json.dumps(
            {
                "scheduledJobReleaseTaskId": int(task.id),
                "jobFamily": "gateway",
                "jobs": ["synapse-staging-deposit-indexer"],
            }
        ),
    )
    db_session.add(record)
    db_session.commit()

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["succeeded_ids"] == [int(record.id)]
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.health_status == "passed"
