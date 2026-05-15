import json
from datetime import datetime, timedelta, timezone

from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.services.releases import tasks as release_tasks_service


def test_release_task_deployment_status_sync_prioritizes_active_records(
    monkeypatch, db_session
):
    old_terminal = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        external_run_id="10",
        trigger_source="release_task",
        updated_at=datetime.now(timezone.utc) - timedelta(days=1),
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    active = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        external_run_id="99",
        trigger_source="release_task",
        updated_at=datetime.now(timezone.utc),
        metadata_json=json.dumps({"deploy_repo_full_name": "example/repo"}),
    )
    db_session.add_all([old_terminal, active])
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="admin-front",
        branch_name="main",
        environment="staging",
        status="deploying",
        actor="operator",
        deployment_record_id=int(active.id),
    )
    db_session.add(task)
    db_session.commit()

    monkeypatch.setattr(
        release_tasks_service,
        "_github_actions_run_view",
        lambda *args, **kwargs: (
            {
                "databaseId": 99,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/example/repo/actions/runs/99",
                "headSha": "abc123",
            },
            None,
        ),
    )

    result = release_tasks_service.sync_release_task_deployment_statuses(
        db_session, max_records=1
    )

    assert result["processed_count"] == 1
    assert int(active.id) in result["succeeded_ids"]
    assert int(old_terminal.id) not in result["skipped_terminal_ids"]
    db_session.refresh(active)
    db_session.refresh(task)
    assert active.status == "succeeded"
    assert task.status == "completed"
