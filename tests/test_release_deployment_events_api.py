from server.database import DeploymentEventRow, DeploymentRecordRow, ReleaseTaskRow
from server.services.releases.deployment_events import append_deployment_event


def _deployment_record(db_session, *, status="running") -> DeploymentRecordRow:
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status=status,
        health_status="checking",
        branch_name="main",
        actor="operator",
        trigger_source="local_deploy_runner",
        notes="local deploy running",
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_deployment_events_endpoint_returns_incremental_pages(
    synced_client, db_session
):
    record = _deployment_record(db_session)
    append_deployment_event(
        db_session,
        deployment_record_id=int(record.id),
        event_type="step_started",
        step_key="build",
        message="build started",
    )
    append_deployment_event(
        db_session,
        deployment_record_id=int(record.id),
        event_type="stderr",
        step_key="build",
        message="middle root cause: package install failed",
    )
    append_deployment_event(
        db_session,
        deployment_record_id=int(record.id),
        event_type="stdout",
        step_key="build",
        message="continuing cleanup output",
    )
    db_session.commit()

    first_page = synced_client.get(
        f"/api/releases/deployments/{int(record.id)}/events?after_sequence=0&limit=2"
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["has_more"] is True
    assert payload["next_sequence"] == 2
    assert [item["sequence"] for item in payload["items"]] == [1, 2]
    assert payload["items"][1]["message"] == "middle root cause: package install failed"

    next_page = synced_client.get(
        f"/api/releases/deployments/{int(record.id)}/events?after_sequence=2&limit=2"
    )
    assert next_page.status_code == 200
    assert next_page.json()["has_more"] is False
    assert [item["sequence"] for item in next_page.json()["items"]] == [3]


def test_deployment_events_endpoint_error_paths(synced_client, db_session):
    missing = synced_client.get("/api/releases/deployments/999999/events")
    assert missing.status_code == 404
    reset_missing = synced_client.post(
        "/api/releases/tasks/999999/reset-running",
        json={"confirm_phrase": "RESET_LOCAL_DEPLOY"},
    )
    assert reset_missing.status_code == 404

    record = _deployment_record(db_session, status="running")
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="deploying",
        actor="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    bad_confirm = synced_client.post(
        f"/api/releases/tasks/{int(task.id)}/reset-running",
        json={"confirm_phrase": "NOPE"},
    )
    assert bad_confirm.status_code == 400


def test_deployment_events_preserve_full_message_without_truncation(
    synced_client, db_session
):
    record = _deployment_record(db_session)
    long_message = (
        "prefix\n" + ("x" * 70000) + "\nroot cause in middle\n" + ("y" * 70000)
    )
    append_deployment_event(
        db_session,
        deployment_record_id=int(record.id),
        event_type="stderr",
        step_key="deploy",
        message=long_message,
    )
    db_session.commit()

    response = synced_client.get(f"/api/releases/deployments/{int(record.id)}/events")

    assert response.status_code == 200
    message = response.json()["items"][0]["message"]
    assert message == long_message
    assert "root cause in middle" in message


def test_reset_running_release_task_preserves_old_events_and_appends_reset(
    synced_client, db_session
):
    record = _deployment_record(db_session)
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="deploying",
        actor="operator",
        operator="operator",
        deployment_record_id=int(record.id),
    )
    db_session.add(task)
    append_deployment_event(
        db_session,
        deployment_record_id=int(record.id),
        event_type="stdout",
        step_key="build",
        message="first attempt output",
    )
    db_session.commit()
    db_session.refresh(task)

    response = synced_client.post(
        f"/api/releases/tasks/{int(task.id)}/reset-running",
        json={
            "confirm_phrase": "RESET_LOCAL_DEPLOY",
            "operator": "operator",
            "reason": "runner process was killed",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requested"
    assert payload["deployment_record_id"] is None
    db_session.refresh(record)
    assert record.status == "failed"
    assert record.health_status == "failed"
    events = (
        db_session.query(DeploymentEventRow)
        .filter(DeploymentEventRow.deployment_record_id == int(record.id))
        .order_by(DeploymentEventRow.sequence.asc())
        .all()
    )
    assert [event.event_type for event in events] == [
        "stdout",
        "local_deploy_force_reset",
    ]
    assert "runner process was killed" in events[-1].message
