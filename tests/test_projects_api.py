from __future__ import annotations

from server.database import ProjectPolicyRow, RequirementRow


def test_projects_api_creates_project_with_linked_policy(synced_client, db_session):
    response = synced_client.post(
        "/api/projects",
        json={
            "project_key": "synapse-network-growing",
            "display_name": "Synapse-Network-Growing",
            "root_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
            "repo_full_name": "cliff-personal/Synapse-Network-Growing",
            "deploy_strategy": "github_actions",
            "deploy_repo_full_name": "cliff-personal/Synapse-Network-Growing",
            "deploy_trigger_enabled": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_key"] == "synapse-network-growing"
    assert payload["policy"] is not None
    assert payload["policy"]["project_id"] == payload["id"]

    policies = db_session.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_id == payload["id"]).all()
    assert len(policies) == 1


def test_requirement_creation_requires_project_and_resolves_override_path(synced_client, db_session):
    project = synced_client.post(
        "/api/projects",
        json={
            "project_key": "synapse-network-growing",
            "display_name": "Synapse-Network-Growing",
            "root_path": "/Users/cliff/workspace/agent/Synapse-Network-Growing",
            "repo_full_name": "cliff-personal/Synapse-Network-Growing",
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
    assert payload["project_key"] == "synapse-network-growing"
    assert payload["project_display_name"] == "Synapse-Network-Growing"
    assert payload["target_project_path"] == "/tmp/project-override"
    assert payload["target_project_path_override"] == "/tmp/project-override"

    stored = db_session.query(RequirementRow).filter(RequirementRow.id == payload["id"]).one()
    assert stored.project_id == project["id"]
    assert stored.project_key == "synapse-network-growing"
    assert stored.project_display_name == "Synapse-Network-Growing"
    assert stored.target_project_path == "/tmp/project-override"
