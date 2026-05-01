from __future__ import annotations

from server.database import ProjectPolicyRow, ProjectRow, ReleaseRecordRow, RequirementRow


def test_default_projects_include_mcp_server_with_source_repo(synced_client):
    response = synced_client.get("/api/projects")

    assert response.status_code == 200
    projects = {item["project_key"]: item for item in response.json()}
    mcp = projects["synapse-network-mcp-server"]
    assert mcp["display_name"] == "Synapse-Network-MCP-Server"
    assert mcp["repo_full_name"] == "SynapseNetworkAI/Synapse-Network-MCP-Server"
    assert mcp["deploy_strategy"] == "disabled"


def test_projects_api_creates_project_with_linked_policy(synced_client, db_session):
    response = synced_client.post(
        "/api/projects",
        json={
            "project_key": "created-growing-shadow",
            "display_name": "Created Growing Shadow",
            "root_path": "/tmp/created-growing-shadow",
            "repo_full_name": "SynapseNetworkAI/Synapse-Network-Growing",
            "deploy_strategy": "github_actions",
            "deploy_repo_full_name": "SynapseNetworkAI/Synapse-Network-Growing",
            "deploy_trigger_enabled": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_key"] == "created-growing-shadow"
    assert payload["policy"] is not None
    assert payload["policy"]["project_id"] == payload["id"]

    policies = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_id == payload["id"]).all()
    assert len(policies) == 1


def test_projects_api_normalizes_github_repo_urls(synced_client):
    response = synced_client.post(
        "/api/projects",
        json={
            "project_key": "mcp-url-normalize",
            "display_name": "MCP URL Normalize",
            "root_path": "/tmp/mcp-url-normalize",
            "repo_full_name": "git@github.com:SynapseNetworkAI/Synapse-Network-MCP-Server.git",
            "deploy_repo_full_name": "https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server.git",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["repo_full_name"] == "SynapseNetworkAI/Synapse-Network-MCP-Server"
    assert payload["deploy_repo_full_name"] == "SynapseNetworkAI/Synapse-Network-MCP-Server"
    assert payload["policy"]["deploy_repo_full_name"] == "SynapseNetworkAI/Synapse-Network-MCP-Server"


def test_project_policy_deploy_repo_does_not_overwrite_source_repo(synced_client):
    created = synced_client.post(
        "/api/projects",
        json={
            "project_key": "split-source-deploy",
            "display_name": "Split Source Deploy",
            "root_path": "/tmp/split-source-deploy",
            "repo_full_name": "cliff-personal/source-repo",
            "deploy_repo_full_name": "cliff-personal/initial-deploy-repo",
        },
    ).json()

    update = synced_client.patch(
        f"/api/projects/{created['id']}/policy",
        json={
            "deploy_repo_full_name": "git@github.com:cliff-personal/final-deploy-repo.git",
        },
    )

    assert update.status_code == 200
    detail = synced_client.get(f"/api/projects/{created['id']}").json()
    assert detail["repo_full_name"] == "cliff-personal/source-repo"
    assert detail["deploy_repo_full_name"] == "cliff-personal/final-deploy-repo"
    assert detail["policy"]["deploy_repo_full_name"] == "cliff-personal/final-deploy-repo"


def test_requirement_creation_requires_project_and_resolves_override_path(synced_client, db_session):
    project = synced_client.post(
        "/api/projects",
        json={
            "project_key": "requirement-project",
            "display_name": "Requirement Project",
            "root_path": "/tmp/requirement-project",
            "repo_full_name": "SynapseNetworkAI/Synapse-Network-Growing",
        },
    ).json()

    missing_project = synced_client.post(
        "/api/requirements",
        json={
            "title": "Missing project should fail",
            "description_markdown": "Requirement must attach to a formal project.",
            "priority": "normal",
        },
    )
    assert missing_project.status_code == 400
    assert missing_project.json()["detail"] == "project_id is required"

    create_response = synced_client.post(
        "/api/requirements",
        json={
            "title": "Project-bound requirement",
            "description_markdown": "Bind requirement to project and use a path override for this run only.",
            "priority": "normal",
            "project_id": project["id"],
            "target_project_path_override": "/tmp/project-override",
        },
    )

    assert create_response.status_code == 201
    payload = create_response.json()["requirement"]
    assert payload["project_id"] == project["id"]
    assert payload["project_key"] == "requirement-project"
    assert payload["project_display_name"] == "Requirement Project"
    assert payload["target_project_path"] == "/tmp/project-override"
    assert payload["target_project_path_override"] == "/tmp/project-override"

    stored = db_session.query(RequirementRow).filter(RequirementRow.id == payload["id"]).one()
    assert stored.project_id == project["id"]
    assert stored.project_key == "requirement-project"
    assert stored.project_display_name == "Requirement Project"
    assert stored.target_project_path == "/tmp/project-override"


def test_projects_api_delete_marks_project_and_policy_deleted_and_hides_from_reads(synced_client, db_session):
    project = synced_client.post(
        "/api/projects",
        json={
            "project_key": "orphan-project",
            "display_name": "Orphan Project",
            "root_path": "/tmp/orphan-project",
        },
    ).json()

    delete_response = synced_client.delete(f"/api/projects/{project['id']}")

    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"

    stored_project = db_session.query(ProjectRow).filter(ProjectRow.id == project["id"]).one()
    stored_policy = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_id == project["id"]).one()
    assert stored_project.status == "deleted"
    assert stored_policy.status == "deleted"

    listing = synced_client.get("/api/projects")
    assert listing.status_code == 200
    assert all(item["id"] != project["id"] for item in listing.json())

    detail = synced_client.get(f"/api/projects/{project['id']}")
    assert detail.status_code == 404


def test_projects_api_delete_rejects_project_with_requirements(synced_client, db_session):
    project = synced_client.post(
        "/api/projects",
        json={
            "project_key": "project-with-req",
            "display_name": "Project With Requirement",
            "root_path": "/tmp/project-with-req",
        },
    ).json()

    create_requirement = synced_client.post(
        "/api/requirements",
        json={
            "title": "Requirement keeps project alive",
            "description_markdown": "This requirement should block project deletion.",
            "priority": "normal",
            "project_id": project["id"],
        },
    )
    assert create_requirement.status_code == 201

    delete_response = synced_client.delete(f"/api/projects/{project['id']}")

    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "Project cannot be deleted because requirements exist"


def test_projects_api_delete_rejects_project_with_releases(synced_client, db_session):
    project = synced_client.post(
        "/api/projects",
        json={
            "project_key": "project-with-release",
            "display_name": "Project With Release",
            "root_path": "/tmp/project-with-release",
        },
    ).json()

    backing_project = synced_client.post(
        "/api/projects",
        json={
            "project_key": "backing-project",
            "display_name": "Backing Project",
            "root_path": "/tmp/backing-project",
        },
    ).json()

    create_requirement = synced_client.post(
        "/api/requirements",
        json={
            "title": "Backing requirement",
            "description_markdown": "Requirement exists only to satisfy release foreign key.",
            "priority": "normal",
            "project_id": backing_project["id"],
        },
    )
    assert create_requirement.status_code == 201
    requirement_id = create_requirement.json()["requirement"]["id"]

    db_session.add(
        ReleaseRecordRow(
            requirement_id=requirement_id,
            project_id=project["id"],
            project_key=project["project_key"],
            project_display_name=project["display_name"],
            target_project_path=project["root_path"],
            branch_name="main",
            base_branch="main",
            notes="Release history blocks deletion.",
            pr_url=None,
            status="draft",
        )
    )
    db_session.commit()

    delete_response = synced_client.delete(f"/api/projects/{project['id']}")

    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "Project cannot be deleted because releases exist"
