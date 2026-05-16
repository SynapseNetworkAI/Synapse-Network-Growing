from server.schemas import ReleaseTaskPrGateOut
from server.services.releases import tasks as release_tasks_service


def _successful_pr_gate() -> ReleaseTaskPrGateOut:
    return ReleaseTaskPrGateOut(
        branch_exists=True,
        pr_exists=True,
        pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/10",
        pr_number=10,
        pr_state="open",
        checks_status="success",
        checks_summary="3 checks passed",
        can_create_pr=False,
        can_deploy_staging=True,
        blocked_reason=None,
    )


def test_release_task_staging_deploy_routes_synapse_services_to_family_workflows(
    monkeypatch, synced_client
):
    calls = []

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return (
            "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/"
            f"{kwargs['workflow_file']}"
        )

    monkeypatch.setattr(
        release_tasks_service, "_dispatch_github_workflow", fake_dispatch
    )
    monkeypatch.setattr(
        release_tasks_service,
        "_callback_url",
        lambda record_id: f"https://ops.example/api/deployments/{record_id}/report",
    )
    monkeypatch.setattr(
        release_tasks_service,
        "_release_task_pr_gate_for",
        lambda row, repo: _successful_pr_gate(),
    )
    monkeypatch.setattr(
        release_tasks_service,
        "_missing_required_staging_deploy_secrets",
        lambda repo, **kwargs: ([], None),
    )

    cases = [
        ("gateway-admin", "deploy-staging-admin.yml"),
        ("admin-front", "deploy-staging-frontends.yml"),
        ("user-front", "deploy-staging-frontends.yml"),
        ("docs-front", "deploy-staging-frontends.yml"),
    ]
    for service_key, expected_workflow in cases:
        task = synced_client.post(
            "/api/releases/tasks",
            json={
                "project_key": "synapse-network",
                "project_display_name": "Synapse-Network",
                "service_key": service_key,
                "branch_name": "main",
                "environment": "staging",
            },
        ).json()
        response = synced_client.post(
            f"/api/releases/tasks/{task['id']}/deploy-staging",
            json={"actor": "ops-lead"},
        )
        assert response.status_code == 200
        assert calls[-1]["workflow_file"] == expected_workflow
        assert calls[-1]["inputs"]["deploy_scope"] == service_key
