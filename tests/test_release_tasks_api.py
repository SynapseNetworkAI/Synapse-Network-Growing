from server.database import DeploymentRecordRow, ReleaseTaskRow, RequirementRow


def test_manual_release_task_create_list_and_complete(synced_client, db_session):
    response = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "project_display_name": "Synapse-Network-Growing",
            "branch_name": "codex/release-task-demo",
            "environment": "staging",
            "actor": "alice",
            "note": "manual staging smoke",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "manual"
    assert payload["status"] == "requested"
    assert payload["deployment_record_id"] is None
    assert payload["actor"] == "alice"
    assert payload["operator"] is None

    list_response = synced_client.get("/api/releases/tasks")
    assert list_response.status_code == 200
    assert [item["branch_name"] for item in list_response.json()] == ["codex/release-task-demo"]

    patch_response = synced_client.patch(
        f"/api/releases/tasks/{payload['id']}",
        json={"status": "completed", "operator": "ops-lead", "note": "deployed manually"},
    )

    assert patch_response.status_code == 200
    updated = patch_response.json()
    assert updated["status"] == "completed"
    assert updated["operator"] == "ops-lead"
    assert updated["note"] == "deployed manually"


def test_requirement_flow_release_task_keeps_requirement_and_null_deployment_anchor(synced_client, db_session):
    requirement = RequirementRow(
        title="Release candidate",
        description_markdown="A requirement-generated release task.",
        status="done",
        project_key="synapse-network-growing",
        project_display_name="Synapse-Network-Growing",
        target_project_path="/tmp/release-task",
        acceptance_contract_json='{"execution_acceptance_steps":[]}',
    )
    db_session.add(requirement)
    db_session.commit()
    db_session.refresh(requirement)

    response = synced_client.post(
        "/api/releases/tasks",
        json={
            "source_type": "requirement_flow",
            "requirement_id": int(requirement.id),
            "project_key": "synapse-network-growing",
            "branch_name": "ops/req-release-candidate",
            "environment": "production",
            "actor": "planner",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "requirement_flow"
    assert payload["requirement_id"] == int(requirement.id)
    assert payload["deployment_record_id"] is None
    assert payload["environment"] == "production"


def test_release_task_rejects_invalid_status_and_terminal_rewrite(synced_client, db_session):
    create_response = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/release-task-failure",
            "environment": "staging",
        },
    )
    task_id = create_response.json()["id"]

    invalid_response = synced_client.patch(
        f"/api/releases/tasks/{task_id}",
        json={"status": "requested", "operator": "ops-lead"},
    )
    assert invalid_response.status_code == 400

    failed_response = synced_client.patch(
        f"/api/releases/tasks/{task_id}",
        json={"status": "failed", "operator": "ops-lead", "note": "manual deploy failed"},
    )
    assert failed_response.status_code == 200
    assert failed_response.json()["status"] == "failed"

    rewrite_response = synced_client.patch(
        f"/api/releases/tasks/{task_id}",
        json={"status": "completed", "operator": "ops-lead"},
    )
    assert rewrite_response.status_code == 400
    assert "Terminal release task" in rewrite_response.json()["detail"]


def test_release_tasks_do_not_merge_deployment_records(synced_client, db_session):
    requirement = RequirementRow(
        title="Existing deployment",
        description_markdown="Deployment record should not appear in release task list.",
        status="done",
        project_key="synapse-network-growing",
        target_project_path="/tmp/release-task",
        acceptance_contract_json='{"execution_acceptance_steps":[]}',
    )
    db_session.add(requirement)
    db_session.flush()
    db_session.add(
        DeploymentRecordRow(
            requirement_id=int(requirement.id),
            project_key="synapse-network-growing",
            environment="staging",
            action="deploy",
            status="succeeded",
            branch_name="codex/deployment-only",
        )
    )
    db_session.add(
        ReleaseTaskRow(
            source_type="manual",
            project_key="synapse-network-growing",
            branch_name="codex/task-only",
            environment="staging",
            status="requested",
            actor="operator",
        )
    )
    db_session.commit()

    response = synced_client.get("/api/releases/tasks")

    assert response.status_code == 200
    branches = [item["branch_name"] for item in response.json()]
    assert branches == ["codex/task-only"]
    assert "codex/deployment-only" not in branches


def test_release_task_filters_and_validation_errors(synced_client, db_session):
    synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/filter-a",
            "environment": "staging",
        },
    )
    synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-provider",
            "branch_name": "codex/filter-b",
            "environment": "production",
        },
    )
    failed = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network-growing",
            "branch_name": "codex/filter-c",
            "environment": "staging",
        },
    ).json()
    synced_client.patch(f"/api/releases/tasks/{failed['id']}", json={"status": "failed", "operator": "ops"})

    filtered = synced_client.get(
        "/api/releases/tasks",
        params={
            "project_key": "synapse-network-provider",
            "environment": "production",
            "status": "requested",
            "source_type": "manual",
        },
    )
    assert filtered.status_code == 200
    assert [item["branch_name"] for item in filtered.json()] == ["codex/filter-b"]

    assert synced_client.post(
        "/api/releases/tasks",
        json={"source_type": "unknown", "project_key": "x", "branch_name": "b", "environment": "staging"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"project_key": "x", "branch_name": "b", "environment": "qa"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"branch_name": "b", "environment": "staging"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"project_key": "x", "environment": "staging"},
    ).status_code == 400
    assert synced_client.post(
        "/api/releases/tasks",
        json={"source_type": "requirement_flow", "requirement_id": 9999, "project_key": "x", "branch_name": "b", "environment": "staging"},
    ).status_code == 400


def test_release_task_update_unknown_id_returns_404(synced_client):
    response = synced_client.patch(
        "/api/releases/tasks/9999",
        json={"status": "completed", "operator": "ops"},
    )

    assert response.status_code == 404
