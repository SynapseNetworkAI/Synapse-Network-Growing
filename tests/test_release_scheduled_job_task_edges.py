import json
from datetime import timedelta

from server.database import DeploymentRecordRow, utcnow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.releases.github_actions_logs import GitHubFailureLogResult
from server.services.releases import scheduled_job_sync
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
    run_id: str | None = "555",
    started_at=None,
) -> DeploymentRecordRow:
    return DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status=status,
        health_status="checking",
        branch_name="main",
        workflow_file="deploy-staging-jobs.yml",
        external_run_id=run_id,
        external_url=f"https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/{run_id}"
        if run_id
        else None,
        actor="operator",
        trigger_source="scheduled_job_release",
        started_at=started_at,
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


def test_scheduled_jobs_sync_updates_parent_task_on_success(
    monkeypatch, synced_client, db_session
):
    task = _task_row()
    db_session.add(task)
    db_session.commit()
    record = _record_for_task(task)
    db_session.add(record)
    db_session.commit()

    monkeypatch.setattr(
        scheduled_job_sync,
        "run_gh_json",
        lambda args, timeout=30: (
            "ok",
            {
                "databaseId": 555,
                "status": "completed",
                "conclusion": "success",
                "url": record.external_url,
            },
            None,
        ),
    )

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.health_status == "passed"
    assert task.deployment_record_id == int(record.id)


def test_scheduled_jobs_sync_times_out_missing_run_and_updates_task(
    monkeypatch, synced_client, db_session
):
    task = _task_row()
    db_session.add(task)
    db_session.commit()
    record = _record_for_task(
        task,
        run_id=None,
        started_at=utcnow() - timedelta(minutes=16),
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(
        scheduled_job_sync,
        "run_gh_json",
        lambda args, timeout=30: ("ok", [], None),
    )

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    assert response.json()["failed_ids"] == [int(record.id)]
    db_session.refresh(task)
    assert task.status == "failed"
    assert "run id not found after 15m" in (task.failure_summary or "")


def test_scheduled_jobs_sync_keeps_terminal_task_terminal(
    monkeypatch, synced_client, db_session
):
    task = _task_row(status="completed")
    db_session.add(task)
    db_session.commit()
    record = _record_for_task(task, run_id="777")
    db_session.add(record)
    db_session.commit()

    monkeypatch.setattr(
        scheduled_job_sync,
        "run_gh_json",
        lambda args, timeout=30: (
            "ok",
            {
                "databaseId": 777,
                "status": "completed",
                "conclusion": "failure",
                "url": record.external_url,
            },
            None,
        ),
    )
    monkeypatch.setattr(
        scheduled_job_sync,
        "github_failure_log_result",
        lambda *args, **kwargs: GitHubFailureLogResult(
            excerpt="failed",
            metadata={},
            note="GitHub Actions scheduled jobs publish failure.",
        ),
    )

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
        workflow_file="deploy-staging-jobs.yml",
        external_run_id="888",
        external_url="https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/888",
        actor="operator",
        trigger_source="scheduled_job_release",
        notes="workflow failed",
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
    assert out.failure_summary == "workflow failed"
    assert out.external_run_id == "888"
