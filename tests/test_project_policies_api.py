from server.database import ProjectPolicyRow


def test_project_policies_list_includes_default_managed_projects(synced_client):
    resp = synced_client.get("/api/project-policies")

    assert resp.status_code == 200
    payload = resp.json()
    project_keys = {item["project_key"] for item in payload}
    assert "synapse-network" in project_keys
    assert "synapse-network-growing" in project_keys
    assert "agents-memory" in project_keys


def test_project_policy_can_be_updated(synced_client):
    list_resp = synced_client.get("/api/project-policies")
    policy = next(item for item in list_resp.json() if item["project_key"] == "synapse-network")

    patch_resp = synced_client.patch(
        f"/api/project-policies/{policy['id']}",
        json={
            "release_mode": "disabled",
            "required_checks": ["pytest -q", "npm test"],
            "notes": "Tightened during validation.",
        },
    )

    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["release_mode"] == "disabled"
    assert updated["required_checks"] == ["pytest -q", "npm test"]
    assert updated["notes"] == "Tightened during validation."


def test_project_policy_can_be_created(synced_client):
    create_resp = synced_client.post(
        "/api/project-policies",
        json={
            "project_key": "sandbox-app",
            "display_name": "Sandbox App",
            "root_path": "/tmp/sandbox-app",
            "allowed_write_globs": ["src/**"],
            "forbidden_globs": ["secrets/**"],
            "required_checks": ["pytest -q"],
            "release_mode": "manual",
            "requires_manual_approval": True,
            "notes": "Temporary sandbox policy.",
        },
    )

    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["project_key"] == "sandbox-app"
    assert created["allowed_write_globs"] == ["src/**"]
    assert created["forbidden_globs"] == ["secrets/**"]


def test_planning_requires_registered_project_policy(synced_client):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Unknown target project",
            "description_markdown": "Implement code in an unmanaged project.",
            "target_project_path": "/tmp/unknown-project",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")

    assert plan_resp.status_code == 400
    assert "No project policy registered" in plan_resp.json()["detail"]


def test_start_requirement_revalidates_active_project_policy(synced_client, db_session):
    create_resp = synced_client.post(
        "/api/requirements",
        json={
            "title": "Managed target project",
            "description_markdown": "Implement code in the managed product repo.",
            "target_project_path": "/Users/cliff/workspace/agent/Synapse-Network",
        },
    )
    requirement_id = create_resp.json()["requirement"]["id"]

    plan_resp = synced_client.post(f"/api/requirements/{requirement_id}/plan")
    assert plan_resp.status_code == 200

    policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == "synapse-network").first()
    assert policy is not None
    policy.status = "disabled"
    db_session.commit()

    start_resp = synced_client.post(f"/api/requirements/{requirement_id}/start")
    assert start_resp.status_code == 400
    assert "not active" in start_resp.json()["detail"]
