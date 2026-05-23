import json

from server import config
from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.services.releases import (
    production_tasks as release_production_tasks_service,
)


def _staging_digest(service: str = "gateway") -> str:
    return (
        "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
        f"synapse-staging/{service}@sha256:" + ("a" * 64)
    )


def test_release_task_production_deploy_creates_local_runner_record(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("abc123prod", None),
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
            {
                "service_key": "gateway",
                "deployScope": "gateway",
                "imageDigest": _staging_digest("gateway"),
            }
        ),
    )
    db_session.add(staging_record)
    db_session.commit()

    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "production",
        },
    ).json()

    missing_confirm = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy", json={}
    )
    assert missing_confirm.status_code == 400
    assert "YES" in missing_confirm.json()["detail"]

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={
            "actor": "ops-lead",
            "note": "prod promote",
            "confirm_phrase": "YES",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"] is not None
    assert payload["deployment_workflow_file"] == "local_deploy_runner"

    deployment = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    assert deployment.trigger_source == "local_deploy_runner"
    assert deployment.workflow_file == "local_deploy_runner"
    metadata = json.loads(deployment.metadata_json)
    assert metadata["gcpProject"] == "synapse-network-prod"
    assert metadata["sourceStagingDeploymentRecordId"] == int(staging_record.id)
    assert metadata["environmentIsolationVersion"] == "v1"
    assert metadata["localDeployRunner"] is True
    assert metadata["deployScope"] == "gateway"
    assert metadata["stagingImageDigest"] == _staging_digest("gateway")


def test_production_frontend_gate_requires_staging_evidence(monkeypatch, db_session):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("front-direct-sha", None),
    )
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="docs-front",
        branch_name="main",
        environment="production",
        status="requested",
    )

    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )

    assert not gate.can_deploy_production
    assert gate.resolved_commit_sha == "front-direct-sha"
    assert gate.staging_deployment_record_id is None
    assert "No successful staging deployment" in gate.blocked_reason


def test_gateway_production_still_requires_staging_evidence(monkeypatch, db_session):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("gateway-main-sha", None),
    )
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

    assert not gate.can_deploy_production
    assert "No successful staging deployment" in gate.blocked_reason


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
        json={"confirm_phrase": "YES"},
    )

    assert response.status_code == 400
    assert "No successful staging deployment" in response.json()["detail"]


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
        metadata_json=json.dumps(
            {"deployScope": "gateway", "imageDigest": _staging_digest("gateway")}
        ),
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
    body = type("Body", (), {"confirm_phrase": "YES"})()

    try:
        release_production_tasks_service._production_task_row(
            db_session, int(row.id), body
        )
    except ValueError as exc:
        assert "Only requested or failed release tasks" in str(exc)
    else:
        raise AssertionError("Expected completed production task to be rejected")


def test_release_task_production_retry_creates_new_local_record(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("retryprodsha", None),
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
            metadata_json=json.dumps(
                {"deployScope": "gateway", "imageDigest": _staging_digest("gateway")}
            ),
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
        json={"confirm_phrase": "YES"},
    )
    assert first_response.status_code == 200
    first_payload = first_response.json()
    failed_record = db_session.get(
        DeploymentRecordRow, first_payload["deployment_record_id"]
    )
    failed_record.status = "failed"
    failed_record.health_status = "failed"
    failed_task = db_session.get(ReleaseTaskRow, task["id"])
    failed_task.status = "failed"
    db_session.commit()

    retry_response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "YES"},
    )

    assert retry_response.status_code == 200
    retry_payload = retry_response.json()
    assert retry_payload["status"] == "deploying"
    assert (
        retry_payload["deployment_record_id"] != first_payload["deployment_record_id"]
    )


def test_production_branch_helper(monkeypatch):
    monkeypatch.setattr(config, "E2E_MODE", True)
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


def test_production_local_branch_helper_errors(monkeypatch):
    monkeypatch.setattr(config, "E2E_MODE", False)
    monkeypatch.setitem(
        release_production_tasks_service.LOCAL_REPO_PATH_BY_PROJECT,
        "missing-project",
        "",
    )
    sha, error = release_production_tasks_service._local_branch_commit_sha(
        "unknown-project", "main"
    )
    assert sha is None
    assert "no registered repository" in error

    def raise_timeout(*_args, **_kwargs):
        raise release_production_tasks_service.subprocess.TimeoutExpired(
            cmd="git", timeout=10
        )

    monkeypatch.setitem(
        release_production_tasks_service.LOCAL_REPO_PATH_BY_PROJECT,
        "synapse-network",
        "/tmp/repo",
    )
    monkeypatch.setattr(
        release_production_tasks_service.subprocess, "run", raise_timeout
    )
    sha, error = release_production_tasks_service._local_branch_commit_sha(
        "synapse-network", "main"
    )
    assert sha is None
    assert "Unable to resolve" in error


def test_production_gate_blocks_stale_target_commit(monkeypatch, db_session):
    monkeypatch.setattr(
        release_production_tasks_service,
        "_github_branch_commit_sha",
        lambda repo, branch: ("current-main", None),
    )
    row = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        target_commit_sha="old-main",
        environment="production",
        status="requested",
    )

    gate = release_production_tasks_service.release_task_production_gate(
        db_session, row, "SynapseNetworkAI/Synapse-Network"
    )

    assert not gate.can_deploy_production
    assert "current origin/main" in gate.blocked_reason


def test_production_helpers_cover_missing_evidence_and_manifest_digest(db_session):
    gate = release_production_tasks_service.ReleaseTaskPrGateOut(
        can_deploy_production=False,
        resolved_commit_sha="abc",
        blocked_reason="blocked",
    )
    try:
        release_production_tasks_service._production_staging_evidence(db_session, gate)
    except ValueError as exc:
        assert "blocked" in str(exc)
    else:
        raise AssertionError("Expected blocked production evidence to raise")

    ready_gate = release_production_tasks_service.ReleaseTaskPrGateOut(
        can_deploy_production=True,
        resolved_commit_sha="abc",
        staging_deployment_record_id=999999,
    )
    try:
        release_production_tasks_service._production_staging_evidence(
            db_session, ready_gate
        )
    except ValueError as exc:
        assert "not found" in str(exc)
    else:
        raise AssertionError("Expected missing staging evidence to raise")

    no_record_gate = release_production_tasks_service.ReleaseTaskPrGateOut(
        can_deploy_production=True,
        resolved_commit_sha="abc",
    )
    assert (
        release_production_tasks_service._production_staging_evidence(
            db_session, no_record_gate
        )
        is None
    )
    assert release_production_tasks_service._staging_image_digest(None) is None

    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        health_status="passed",
        metadata_json=json.dumps(
            {"manifest": {"image_digest": "image@sha256:" + ("c" * 64)}}
        ),
    )
    assert release_production_tasks_service._staging_image_digest(record).endswith(
        "c" * 64
    )

    empty_record = DeploymentRecordRow(metadata_json=json.dumps({"manifest": {}}))
    assert release_production_tasks_service._staging_image_digest(empty_record) is None
