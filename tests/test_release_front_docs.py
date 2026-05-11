import json

from server.database import DeploymentRecordRow
from server.schemas import ReleaseTaskPrGateOut
from server.services.releases import tasks as release_tasks_service


def _successful_pr_gate() -> ReleaseTaskPrGateOut:
    return ReleaseTaskPrGateOut(
        branch_exists=True,
        pr_exists=True,
        pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/99",
        pr_number=99,
        pr_state="open",
        checks_status="success",
        checks_summary="3 checks passed",
        can_create_pr=False,
        can_deploy_staging=True,
        blocked_reason=None,
    )


def test_front_docs_release_task_staging_deploy_dispatches_synapse_workflow(
    monkeypatch, synced_client, db_session
):
    calls = []

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging-frontends.yml"

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

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "docs-front",
            "branch_name": "codex/staging-docs-front",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "ops-lead", "note": "ship front docs staging"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"] is not None
    assert payload["deployment_health_status"] == "checking"
    assert calls[0]["repo_full_name"] == "SynapseNetworkAI/Synapse-Network"
    assert calls[0]["workflow_file"] == "deploy-staging-frontends.yml"
    assert calls[0]["inputs"]["deploy_scope"] == "docs-front"
    assert calls[0]["inputs"]["source_ref"] == "codex/staging-docs-front"

    deployment = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    metadata = json.loads(deployment.metadata_json)
    assert metadata["deploy_strategy"] == "github_actions_gcp_cloudrun"
    assert metadata["service_key"] == "docs-front"
    assert metadata["deployScope"] == "docs-front"
