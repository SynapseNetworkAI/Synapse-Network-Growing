import json
from datetime import datetime, timedelta, timezone

from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.services.releases import tasks as release_tasks_service


def _failed_wif_log() -> str:
    return "\n".join(
        [
            "deploy\tAuthenticate to Google Cloud\t2026-05-03T08:23:50Z ##[error]google-github-actions/auth failed with: failed to generate Google Cloud federated token",
            'deploy\tAuthenticate to Google Cloud\t{"error":"unauthorized_client","error_description":"The given credential is rejected by the attribute condition."}',
        ]
    )


def test_release_task_deployment_failed_run_records_actions_log_excerpt(
    monkeypatch, db_session
):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        external_run_id="25274187647",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc),
        metadata_json=json.dumps(
            {"deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network"}
        ),
    )
    db_session.add(record)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="docs-front",
        branch_name="main",
        environment="staging",
        status="deploying",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()
    monkeypatch.setattr(
        release_tasks_service,
        "_run_gh_text",
        lambda *args, **kwargs: ("ok", _failed_wif_log(), ""),
    )

    state = release_tasks_service._apply_github_run_to_deployment(
        db_session,
        record,
        run_id="25274187647",
        run_payload={
            "databaseId": 25274187647,
            "status": "completed",
            "conclusion": "failure",
            "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/25274187647",
            "headSha": "abc123",
        },
    )

    assert state == "failed"
    assert record.status == "failed"
    assert "unauthorized_client" in (record.notes or "")
    metadata = json.loads(record.metadata_json)
    assert metadata["githubFailureLogStatus"] == "ok"
    assert "attribute condition" in metadata["githubFailureLogExcerpt"]


def test_release_task_deployment_status_sync_enriches_recent_failed_run_logs(
    monkeypatch, db_session
):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="failed",
        external_run_id="25274187647",
        trigger_source="release_task",
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        finished_at=datetime.now(timezone.utc),
        metadata_json=json.dumps(
            {
                "deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network",
                "githubRunConclusion": "failure",
            }
        ),
    )
    db_session.add(record)
    db_session.commit()
    monkeypatch.setattr(
        release_tasks_service,
        "_run_gh_text",
        lambda *args, **kwargs: ("ok", _failed_wif_log(), ""),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(db_session)

    assert int(record.id) in result["enriched_failed_log_ids"]
    db_session.refresh(record)
    assert "attribute condition" in (record.notes or "")
    assert "githubFailureLogExcerpt" in json.loads(record.metadata_json)
