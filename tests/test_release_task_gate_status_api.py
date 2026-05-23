from server.database import ReleaseTaskRow
from server.schemas import ReleaseTaskPrGateOut
from server.services.releases import gate_status as release_gate_status_service
from server.services.releases import tasks as release_tasks_service


def test_release_task_list_does_not_compute_live_pr_gate(
    monkeypatch, synced_client, db_session
):
    calls: list[int] = []

    def fake_gate(row, repo):
        calls.append(int(row.id))
        raise AssertionError("list endpoint must not refresh GitHub PR gate")

    monkeypatch.setattr(
        release_gate_status_service, "_release_task_pr_gate_for", fake_gate
    )
    for note in ("first", "second"):
        db_session.add(
            ReleaseTaskRow(
                source_type="manual",
                project_key="synapse-network",
                service_key="gateway",
                branch_name="codex/shared-release-branch",
                environment="staging",
                status="requested",
                actor="operator",
                note=note,
            )
        )
    db_session.commit()

    response = synced_client.get("/api/releases/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert calls == []
    assert {item["pr_gate"]["checks_status"] for item in payload} == {"unknown"}
    assert not any(item["pr_gate"]["can_deploy_staging"] for item in payload)


def test_release_task_gate_status_returns_live_pr_gate(
    monkeypatch, synced_client, db_session
):
    def fake_gate(row, repo):
        assert repo == "SynapseNetworkAI/Synapse-Network"
        return ReleaseTaskPrGateOut(
            branch_exists=True,
            pr_exists=True,
            pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/27",
            pr_number=27,
            pr_state="merged",
            checks_status="success",
            checks_summary="1 checks passed",
        )

    monkeypatch.setattr(
        release_gate_status_service, "_release_task_pr_gate_for", fake_gate
    )
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="staging",
        status="requested",
        actor="operator",
    )
    db_session.add(task)
    db_session.commit()

    response = synced_client.get(f"/api/releases/tasks/{int(task.id)}/gate-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["pr_number"] == 27
    assert payload["checks_status"] == "success"


def test_release_task_gate_status_handles_not_found(synced_client):
    response = synced_client.get("/api/releases/tasks/999/gate-status")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_release_task_gate_status_handles_unsupported_environment(
    synced_client, db_session
):
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="qa",
        status="requested",
        actor="operator",
    )
    db_session.add(task)
    db_session.commit()

    response = synced_client.get(f"/api/releases/tasks/{int(task.id)}/gate-status")

    assert response.status_code == 200
    assert "only available" in response.json()["blocked_reason"]


def test_release_task_gate_status_projects_production_gate(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_gate_status_service,
        "release_task_production_gate",
        lambda db, row, repo: ReleaseTaskPrGateOut(
            can_deploy_production=True,
            environment_gate_summary="prod gate ready",
        ),
    )
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="production",
        status="requested",
        actor="operator",
    )
    db_session.add(task)
    db_session.commit()

    response = synced_client.get(f"/api/releases/tasks/{int(task.id)}/gate-status")

    assert response.status_code == 200
    assert response.json()["can_deploy_production"] is True


def test_release_task_gate_status_returns_policy_error(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_gate_status_service,
        "_policy_for_project",
        lambda db, project_key: (_ for _ in ()).throw(ValueError("policy missing")),
    )
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="staging",
        status="requested",
        actor="operator",
    )
    db_session.add(task)
    db_session.commit()

    response = synced_client.get(f"/api/releases/tasks/{int(task.id)}/gate-status")

    assert response.status_code == 200
    assert response.json()["blocked_reason"] == "policy missing"


def test_release_task_query_does_not_compute_live_gate(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda row, repo: (_ for _ in ()).throw(
            AssertionError("query must not refresh GitHub PR gate")
        ),
    )
    db_session.add(
        ReleaseTaskRow(
            source_type="manual",
            project_key="synapse-network",
            service_key="gateway",
            branch_name="main",
            environment="staging",
            status="requested",
            actor="operator",
        )
    )
    db_session.commit()

    response = synced_client.get("/api/releases/tasks/query")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["pr_gate"]["checks_status"] == "unknown"
    assert payload["items"][0]["pr_gate"]["can_deploy_staging"] is False


def test_create_release_task_does_not_compute_live_gate(monkeypatch, synced_client):
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda row, repo: (_ for _ in ()).throw(
            AssertionError("create must not refresh GitHub PR gate")
        ),
    )

    response = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "staging",
            "actor": "operator",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requested"
    assert payload["pr_gate"]["checks_status"] == "unknown"
    assert payload["pr_gate"]["can_deploy_staging"] is False
