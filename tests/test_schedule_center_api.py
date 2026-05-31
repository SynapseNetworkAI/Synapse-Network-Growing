def test_schedule_center_lists_builtins_and_templates(synced_client):
    schedules = synced_client.get("/api/schedules")
    templates = synced_client.get("/api/schedules/templates")

    assert schedules.status_code == 200
    keys = {item["workflow_key"] for item in schedules.json()}
    assert "artifact_registry_cleanup_sweep" in keys
    assert "secret_manager_version_cleanup_sweep" in keys
    assert "staging_environment_shutdown_sweep" in keys
    assert "growth_provider_source_sweep" in keys
    artifact = next(
        item
        for item in schedules.json()
        if item["workflow_key"] == "artifact_registry_cleanup_sweep"
    )
    assert artifact["category"] == "infra_cleanup"
    assert artifact["risk_level"] == "high"
    assert templates.status_code == 200
    template_keys = {item["template_key"] for item in templates.json()}
    assert "artifact_registry_cleanup" in template_keys
    assert "secret_manager_version_cleanup" in template_keys
    assert "staging_environment_shutdown" in template_keys


def test_schedule_center_rejects_builtin_delete_and_allows_disable(synced_client):
    delete_response = synced_client.delete("/api/schedules/bug_log_sweep")
    patch_response = synced_client.patch(
        "/api/schedules/bug_log_sweep", json={"status": "disabled"}
    )

    assert delete_response.status_code == 400
    assert "Built-in schedules cannot be deleted" in delete_response.json()["detail"]
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "disabled"


def test_schedule_center_custom_schedule_lifecycle(synced_client):
    create_response = synced_client.post(
        "/api/schedules",
        json={
            "template_key": "artifact_registry_cleanup",
            "workflow_key": "custom_artifact_cleanup_test",
            "display_name": "Custom Artifact Cleanup Test",
            "schedule": {"cadence": "daily", "suggested_local_time": "12:30"},
            "input_query": {"projects": ["demo"], "repository": "repo", "keep": 2},
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["workflow_key"] == "custom_artifact_cleanup_test"
    assert payload["deletable"] is True
    assert payload["handler_key"] == "cleanup_artifact_registry_versions"

    patch_response = synced_client.patch(
        "/api/schedules/custom_artifact_cleanup_test",
        json={"status": "paused", "display_name": "Paused Artifact Cleanup"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "paused"
    assert patch_response.json()["display_name"] == "Paused Artifact Cleanup"

    delete_response = synced_client.delete(
        "/api/schedules/custom_artifact_cleanup_test"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True


def test_schedule_center_rejects_unknown_template(synced_client):
    response = synced_client.post(
        "/api/schedules",
        json={"template_key": "shell", "workflow_key": "custom_shell"},
    )

    assert response.status_code == 400
    assert "Unknown schedule template" in response.json()["detail"]
