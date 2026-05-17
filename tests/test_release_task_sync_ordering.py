from datetime import datetime, timedelta, timezone

from server.database import DeploymentRecordRow
from server.services.releases import tasks as release_tasks_service


def test_release_task_deployment_status_sync_prioritizes_active_local_records(
    db_session,
):
    old_terminal = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        trigger_source="local_deploy_runner",
        updated_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    active = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        trigger_source="local_deploy_runner",
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add_all([old_terminal, active])
    db_session.commit()

    result = release_tasks_service.sync_release_task_deployment_statuses(
        db_session, max_records=1
    )

    assert result["processed_count"] == 1
    assert int(active.id) in result["running_ids"]
    assert int(old_terminal.id) not in result["succeeded_ids"]
