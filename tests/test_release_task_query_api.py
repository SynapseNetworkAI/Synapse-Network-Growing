from datetime import timedelta

from server.database import ReleaseTaskRow, utcnow
from server.schemas import ReleaseTaskPrGateOut
from server.services.releases import tasks as release_tasks_service


def test_release_task_query_returns_paginated_filtered_results(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda _row, _repo: ReleaseTaskPrGateOut(),
    )
    for index in range(3):
        db_session.add(
            ReleaseTaskRow(
                source_type="manual",
                project_key="synapse-network",
                service_key="gateway",
                branch_name=f"main-page-{index}",
                environment="staging",
                status="requested" if index < 2 else "failed",
                actor="operator",
                note=f"postgres pagination sample {index}",
            )
        )
    db_session.add(
        ReleaseTaskRow(
            source_type="manual",
            project_key="synapse-network-provider",
            service_key="provider-service",
            branch_name="main-provider",
            environment="staging",
            status="requested",
            actor="operator",
        )
    )
    db_session.commit()

    response = synced_client.get(
        "/api/releases/tasks/query",
        params={
            "project_key": "synapse-network",
            "status": "requested",
            "q": "pagination",
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["project_key"] == "synapse-network"
    assert payload["items"][0]["status"] == "requested"


def test_release_task_query_prioritizes_unpublished_before_terminal(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda _row, _repo: ReleaseTaskPrGateOut(),
    )
    now = utcnow()
    samples = [
        ("completed", now),
        ("failed", now - timedelta(minutes=1)),
        ("requested", now - timedelta(days=1)),
    ]
    for status, updated_at in samples:
        db_session.add(
            ReleaseTaskRow(
                source_type="manual",
                project_key="synapse-network",
                service_key=f"gateway-{status}",
                branch_name=f"main-{status}",
                environment="staging",
                status=status,
                actor="operator",
                updated_at=updated_at,
            )
        )
    db_session.commit()

    response = synced_client.get(
        "/api/releases/tasks/query",
        params={"project_key": "synapse-network", "limit": 10},
    )

    assert response.status_code == 200
    statuses = [item["status"] for item in response.json()["items"][:3]]
    assert statuses == ["requested", "completed", "failed"]
