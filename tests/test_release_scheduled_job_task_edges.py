import json

from server.database import DeploymentRecordRow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.releases import scheduled_job_tasks


def _task_row(status: str = "deploying") -> ScheduledJobReleaseTaskRow:
    return ScheduledJobReleaseTaskRow(
        project_key="synapse-network",
        job_name="synapse-staging-deposit-indexer",
        job_family="gateway",
        job_type="periodic",
        environment="staging",
        source_ref_type="branch",
        source_ref="main",
        status=status,
        health_status="passed" if status == "completed" else "checking",
        created_by="operator",
    )


def _record_for_task(
    task: ScheduledJobReleaseTaskRow,
    *,
    status: str = "requested",
) -> DeploymentRecordRow:
    return DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status=status,
        health_status="checking",
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


def test_scheduled_job_task_detail_cancel_and_transition_guards(synced_client):
    create_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "staging",
            "source_ref": "main",
            "actor": "operator",
        },
    )
    task_id = create_response.json()["id"]

    detail_response = synced_client.get(f"/api/releases/scheduled-jobs/tasks/{task_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["job_name"] == "synapse-staging-deposit-indexer"

    cancel_response = synced_client.post(
        f"/api/releases/scheduled-jobs/tasks/{task_id}/cancel"
    )
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    publish_response = synced_client.post(
        f"/api/releases/scheduled-jobs/tasks/{task_id}/publish",
        json={"actor": "operator"},
    )
    assert publish_response.status_code == 400
    assert "Only requested or failed" in publish_response.json()["detail"]

    assert (
        synced_client.get("/api/releases/scheduled-jobs/tasks/404").status_code == 404
    )
    assert (
        synced_client.post("/api/releases/scheduled-jobs/tasks/404/cancel").status_code
        == 404
    )


def test_scheduled_jobs_sync_updates_parent_task_on_success(synced_client, db_session):
    task = _task_row()
    db_session.add(task)
    db_session.commit()
    record = _record_for_task(task, status="succeeded")
    db_session.add(record)
    db_session.commit()

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.health_status == "passed"
    assert task.deployment_record_id == int(record.id)


def test_scheduled_jobs_sync_marks_failed_local_record_on_task(
    synced_client, db_session
):
    task = _task_row()
    db_session.add(task)
    db_session.commit()
    record = _record_for_task(task, status="failed")
    record.notes = "local scheduled job publish failed"
    db_session.add(record)
    db_session.commit()

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    assert response.json()["failed_ids"] == [int(record.id)]
    db_session.refresh(task)
    assert task.status == "failed"
    assert "local scheduled job publish failed" in (task.failure_summary or "")


def test_scheduled_jobs_sync_keeps_terminal_task_terminal(synced_client, db_session):
    task = _task_row(status="completed")
    db_session.add(task)
    db_session.commit()
    record = _record_for_task(task, status="failed")
    db_session.add(record)
    db_session.commit()

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.health_status == "passed"


def test_scheduled_job_task_output_falls_back_to_deployment_record(db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="failed",
        health_status="failed",
        branch_name="main",
        workflow_file="local_scheduled_job_runner",
        actor="operator",
        trigger_source="local_deploy_runner",
        notes="local runner failed",
        metadata_json='{"jobFamily":"gateway","jobs":["synapse-staging-deposit-indexer"]}',
    )
    db_session.add(record)
    db_session.commit()
    task = _task_row(status="")
    task.health_status = ""
    task.deployment_record_id = int(record.id)
    db_session.add(task)
    db_session.commit()

    out = scheduled_job_tasks.get_scheduled_job_release_task(db_session, int(task.id))

    assert out.status == "failed"
    assert out.health_status == "failed"
    assert out.failure_summary == "local runner failed"
