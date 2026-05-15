import json

from server import config
from server.database import DeploymentRecordRow
from server.database import ReleaseTaskRow
from server.services.releases import (
    production_dispatch as release_production_dispatch_service,
    production_tasks as release_production_tasks_service,
)
from server.services.releases.production_workflows import (
    production_workflow_file_for_service,
)


def test_release_task_production_deploy_queues_and_sync_dispatches_workflow(
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
        release_production_dispatch_service, "_dispatch_github_workflow", fake_dispatch
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
    assert payload["deployment_commit_sha"] is None
    assert calls == []

    deployment = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    metadata = json.loads(deployment.metadata_json)
    assert metadata["dispatchPending"] is True
    assert metadata["dispatchStatus"] == "pending"

    sync_response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")
    assert sync_response.status_code == 200
    assert payload["deployment_record_id"] in sync_response.json()["production_dispatch"]["dispatched_ids"]

    assert calls[0]["repo_full_name"] == "SynapseNetworkAI/Synapse-Network"
    assert calls[0]["workflow_file"] == "deploy-production-frontends.yml"
    assert calls[0]["inputs"]["deploy_scope"] == "docs-front"
    assert calls[0]["inputs"]["source_ref"] == "main"
    assert calls[0]["inputs"]["commit_sha"] == "abc123prod"

    db_session.refresh(deployment)
    metadata = json.loads(deployment.metadata_json)
    assert metadata["gcpProject"] == "synapse-network-prod"
    assert metadata["sourceStagingDeploymentRecordId"] == int(staging_record.id)
    assert metadata["environmentIsolationVersion"] == "v1"
    assert metadata["dispatchStatus"] == "dispatched"


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


def test_production_dispatch_inputs_match_modular_wrapper_contracts():
    row = ReleaseTaskRow(id=10)
    gateway_record = DeploymentRecordRow(id=20, workflow_file="deploy-production-gateway.yml")
    gateway_inputs = release_production_tasks_service._production_dispatch_inputs(
        row=row,
        record=gateway_record,
        commit_sha="abc",
        service_key="gateway",
        actor="operator",
    )
    assert "deploy_scope" not in gateway_inputs

    admin_record = DeploymentRecordRow(id=21, workflow_file="deploy-production-admin.yml")
    admin_inputs = release_production_tasks_service._production_dispatch_inputs(
        row=row,
        record=admin_record,
        commit_sha="abc",
        service_key="gateway-admin",
        actor="operator",
    )
    assert "deploy_scope" not in admin_inputs

    frontend_record = DeploymentRecordRow(
        id=22, workflow_file="deploy-production-frontends.yml"
    )
    frontend_inputs = release_production_tasks_service._production_dispatch_inputs(
        row=row,
        record=frontend_record,
        commit_sha="abc",
        service_key="docs-front",
        actor="operator",
    )
    assert frontend_inputs["deploy_scope"] == "docs-front"


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

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    sync_response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")
    assert sync_response.status_code == 200
    assert payload["deployment_record_id"] in sync_response.json()["production_dispatch"]["failed_ids"]


def test_release_task_production_gate_uses_pinned_staging_commit(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("staged-main-sha", None),
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
        lambda repo, branch: ("legacy-staged-sha", None),
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


def test_release_task_production_gate_blocks_stale_staging_commit(
    monkeypatch, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("current-main-sha", None),
    )
    db_session.add(
        DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="deploy",
            status="succeeded",
            health_status="passed",
            branch_name="main",
            commit_sha="old-staged-main-sha",
            metadata_json=json.dumps({"deployScope": "gateway"}),
        )
    )
    db_session.commit()
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        target_commit_sha="old-staged-main-sha",
        environment="production",
        status="requested",
    )

    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )

    assert not gate.can_deploy_production
    assert "current origin/main" in gate.blocked_reason


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


def test_production_task_row_rejects_non_deployable_status(db_session):
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="production",
        status="completed",
    )
    db_session.add(row)
    db_session.commit()
    body = type("Body", (), {"confirm_phrase": "DEPLOY_PRODUCTION"})()

    try:
        release_production_tasks_service._production_task_row(
            db_session, int(row.id), body
        )
    except ValueError as exc:
        assert "Only requested or failed release tasks" in str(exc)
    else:
        raise AssertionError("Expected completed production task to be rejected")


def test_failed_production_task_row_rejects_retry_after_successful_record(db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="production",
        action="deploy",
        status="succeeded",
        health_status="passed",
    )
    db_session.add(record)
    db_session.flush()
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="production",
        status="failed",
        deployment_record_id=int(record.id),
    )
    db_session.add(row)
    db_session.commit()
    body = type("Body", (), {"confirm_phrase": "DEPLOY_PRODUCTION"})()

    try:
        release_production_tasks_service._production_task_row(
            db_session, int(row.id), body
        )
    except ValueError as exc:
        assert "after a failed deployment record" in str(exc)
    else:
        raise AssertionError("Expected retry after successful record to be rejected")


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
        release_production_dispatch_service,
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
    assert payload["status"] == "deploying"

    sync_response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")
    assert sync_response.status_code == 200
    assert payload["deployment_record_id"] in sync_response.json()["production_dispatch"]["failed_ids"]
    updated = synced_client.get(f"/api/releases/tasks/{task['id']}/gate-status")
    assert updated.status_code == 200
    failed_task = db_session.get(ReleaseTaskRow, task["id"])
    assert failed_task.status == "failed"
    assert "dispatch exploded" in failed_task.note


def test_failed_production_release_task_can_retry_with_new_deployment_record(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("retryprodsha", None),
    )
    monkeypatch.setattr(
        release_production_tasks_service,
        "_missing_required_production_deploy_secrets",
        lambda repo: ([], None),
    )
    dispatch_calls: list[dict[str, object]] = []

    def fake_dispatch(**kwargs):
        dispatch_calls.append(kwargs)
        if len(dispatch_calls) == 1:
            raise RuntimeError("first dispatch failed")
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/9"

    monkeypatch.setattr(
        release_production_dispatch_service,
        "_dispatch_github_workflow",
        fake_dispatch,
    )
    db_session.add(
        DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="deploy",
            status="succeeded",
            health_status="passed",
            branch_name="main",
            commit_sha="retryprodsha",
            metadata_json=json.dumps({"deployScope": "gateway"}),
        )
    )
    db_session.commit()

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "production",
        },
    ).json()
    first_response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_PRODUCTION"},
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["status"] == "deploying"
    failed_record_id = first_payload["deployment_record_id"]
    sync_response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")
    assert sync_response.status_code == 200
    failed_task = db_session.get(ReleaseTaskRow, task["id"])
    assert failed_task.status == "failed"

    retry_response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_PRODUCTION"},
    )

    assert retry_response.status_code == 200
    retry_payload = retry_response.json()
    assert retry_payload["status"] == "deploying"
    assert retry_payload["deployment_record_id"] != failed_record_id
    retry_sync = synced_client.post("/api/releases/tasks/sync-deployment-statuses")
    assert retry_sync.status_code == 200
    assert len(dispatch_calls) == 2
    assert "deploy_scope" not in dispatch_calls[1]["inputs"]
