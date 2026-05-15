import json

from server import config
from server.database import DeploymentRecordRow
from server.database import ReleaseTaskRow
from server.services.releases import (
    production_tasks as release_production_tasks_service,
)
from server.services.releases.production_workflows import (
    production_workflow_file_for_service,
)


def test_release_task_production_deploy_requires_gate_and_dispatches_workflow(
    monkeypatch, synced_client, db_session
):
    calls = []
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("abc123prod", None),
    )
    monkeypatch.setattr(
        release_production_tasks_service,
        "_missing_required_production_deploy_secrets",
        lambda repo: ([], None),
    )
    monkeypatch.setattr(
        release_production_tasks_service,
        "_callback_url",
        lambda record_id: f"https://ops.example/api/deployments/{record_id}/report",
    )

    def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-production-frontends.yml"

    monkeypatch.setattr(
        release_production_tasks_service, "_dispatch_github_workflow", fake_dispatch
    )

    staging_record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        health_status="passed",
        branch_name="main",
        commit_sha="abc123prod",
        metadata_json=json.dumps(
            {"service_key": "docs-front", "deployScope": "docs-front"}
        ),
    )
    db_session.add(staging_record)
    db_session.commit()

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "docs-front",
            "branch_name": "main",
            "environment": "production",
        },
    ).json()

    missing_confirm = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy", json={}
    )
    assert missing_confirm.status_code == 400
    assert "DEPLOY_PRODUCTION" in missing_confirm.json()["detail"]

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={
            "actor": "ops-lead",
            "note": "pilot docs prod",
            "confirm_phrase": "DEPLOY_PRODUCTION",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"] is not None
    assert payload["deployment_workflow_file"] == "deploy-production-frontends.yml"
    assert payload["deployment_commit_sha"] == "abc123prod"
    assert calls[0]["repo_full_name"] == "SynapseNetworkAI/Synapse-Network"
    assert calls[0]["workflow_file"] == "deploy-production-frontends.yml"
    assert calls[0]["inputs"]["deploy_scope"] == "docs-front"
    assert calls[0]["inputs"]["source_ref"] == "main"
    assert calls[0]["inputs"]["commit_sha"] == "abc123prod"

    deployment = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    metadata = json.loads(deployment.metadata_json)
    assert metadata["gcpProject"] == "synapse-network-prod"
    assert metadata["sourceStagingDeploymentRecordId"] == int(staging_record.id)
    assert metadata["environmentIsolationVersion"] == "v1"


def test_production_workflow_resolver_uses_modular_defaults():
    assert (
        production_workflow_file_for_service(
            configured_workflow_file="deploy-production.yml",
            project_key="synapse-network",
            service_key="gateway",
        )
        == "deploy-production-gateway.yml"
    )
    assert (
        production_workflow_file_for_service(
            configured_workflow_file="deploy-production.yml",
            project_key="synapse-network",
            service_key="gateway-admin",
        )
        == "deploy-production-admin.yml"
    )
    assert (
        production_workflow_file_for_service(
            configured_workflow_file="deploy-production.yml",
            project_key="synapse-network",
            service_key="docs-front",
        )
        == "deploy-production-frontends.yml"
    )
    assert (
        production_workflow_file_for_service(
            configured_workflow_file="deploy-production.yml",
            project_key="synapse-network-provider",
            service_key="provider-service",
        )
        == "deploy-production-provider.yml"
    )
    assert (
        production_workflow_file_for_service(
            configured_workflow_file="custom-prod.yml",
            project_key="synapse-network",
            service_key="gateway",
        )
        == "custom-prod.yml"
    )


def test_release_task_production_deploy_blocks_without_matching_staging(
    monkeypatch, synced_client
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("missingstaging", None),
    )
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "production",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_PRODUCTION"},
    )

    assert response.status_code == 400
    assert "staging deployment" in response.json()["detail"]


def test_release_task_production_gate_uses_pinned_staging_commit(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("new-main-head", None),
    )
    staging_record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        health_status="passed",
        branch_name="main",
        commit_sha="staged-main-sha",
        metadata_json=json.dumps({"deployScope": "gateway"}),
    )
    db_session.add(staging_record)
    db_session.commit()
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        target_commit_sha="staged-main-sha",
        environment="production",
        status="requested",
    )

    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )

    assert gate.can_deploy_production
    assert gate.resolved_commit_sha == "staged-main-sha"
    assert gate.staging_deployment_record_id == int(staging_record.id)


def test_release_task_production_gate_recovers_legacy_unpinned_task_from_latest_staging(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("new-main-head", None),
    )
    db_session.add(
        DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="deploy",
            status="succeeded",
            health_status="passed",
            branch_name="main",
            metadata_json=json.dumps(
                {"serviceKey": "gateway", "commitSha": "legacy-staged-sha"}
            ),
        )
    )
    db_session.commit()
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="production",
        status="requested",
    )

    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )

    assert gate.can_deploy_production
    assert gate.resolved_commit_sha == "legacy-staged-sha"
    assert "passed staging" in gate.environment_gate_summary


def test_release_task_production_gate_blocks_invalid_inputs(monkeypatch, db_session):
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="docs-front",
        branch_name="codex/feature",
        environment="production",
        status="requested",
    )
    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )
    assert not gate.can_deploy_production
    assert "main" in gate.blocked_reason

    row.branch_name = "main"
    row.service_key = "unknown-service"
    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )
    assert "service_key must be one of" in gate.blocked_reason

    row.service_key = "docs-front"
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: (None, "main not found"),
    )
    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )
    assert gate.environment_gate_summary == "main not found"


def test_production_secret_and_branch_helpers(monkeypatch):
    monkeypatch.setattr(config, "E2E_MODE", True)
    assert release_production_tasks_service._missing_required_production_deploy_secrets(
        "owner/repo"
    ) == ([], None)
    assert release_production_tasks_service._github_branch_commit_sha(
        "owner/repo", "main"
    ) == (
        "e2e-commit-main",
        None,
    )
    assert release_production_tasks_service._github_branch_commit_sha(
        "owner/repo", "missing"
    ) == (
        None,
        "分支不存在，请重新选择有效远端分支",
    )

    monkeypatch.setattr(config, "E2E_MODE", False)
    monkeypatch.setattr(
        release_production_tasks_service,
        "_run_gh_json",
        lambda args, timeout=30: ("error", None, "gh unavailable"),
    )
    missing, error = (
        release_production_tasks_service._missing_required_production_deploy_secrets(
            "owner/repo"
        )
    )
    assert "PROD_GCP_PROJECT_ID" in missing
    assert error == "gh unavailable"

    monkeypatch.setattr(
        release_production_tasks_service,
        "_run_gh_json",
        lambda args, timeout=30: ("ok", {"not": "a list"}, None),
    )
    missing, error = (
        release_production_tasks_service._missing_required_production_deploy_secrets(
            "owner/repo"
        )
    )
    assert "PROD_GCP_REGION" in missing
    assert "not valid" in error

    monkeypatch.setattr(
        release_production_tasks_service,
        "_run_gh_json",
        lambda args, timeout=30: (
            "ok",
            [{"name": "PROD_GCP_PROJECT_ID"}, {"name": "PROD_GCP_REGION"}],
            None,
        ),
    )
    missing, error = (
        release_production_tasks_service._missing_required_production_deploy_secrets(
            "owner/repo"
        )
    )
    assert "PROD_GCP_DEPLOY_SERVICE_ACCOUNT" in missing
    assert error is None

    monkeypatch.setattr(
        release_production_tasks_service,
        "_run_gh_json",
        lambda args, timeout=30: ("ok", {"commit": {"sha": "sha-from-gh"}}, None),
    )
    assert release_production_tasks_service._github_branch_commit_sha(
        "owner/repo", "main"
    ) == (
        "sha-from-gh",
        None,
    )


def test_release_task_production_dispatch_failure_marks_task_failed(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("dispatchfailsha", None),
    )
    monkeypatch.setattr(
        release_production_tasks_service,
        "_missing_required_production_deploy_secrets",
        lambda repo: ([], None),
    )
    monkeypatch.setattr(
        release_production_tasks_service,
        "_dispatch_github_workflow",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("dispatch exploded")),
    )
    db_session.add(
        DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="deploy",
            status="succeeded",
            health_status="passed",
            branch_name="main",
            commit_sha="dispatchfailsha",
            metadata_json=json.dumps({"deployScope": "docs-front"}),
        )
    )
    db_session.commit()

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "docs-front",
            "branch_name": "main",
            "environment": "production",
        },
    ).json()
    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_PRODUCTION"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert "dispatch exploded" in payload["note"]
