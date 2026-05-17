import json

from server.database import DeploymentEventRow, DeploymentRecordRow, ReleaseTaskRow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.delivery.deployment_governance import _json_dump
import pytest

from server.services.local_runner.deploy_runs import (
    _apply_manifest,
    _load_manifest,
    claim_local_deployment,
    finish_local_deployment,
)
from server.services.releases import local_deploy_tasks


def test_release_task_deploy_can_queue_local_runner_record(
    monkeypatch, synced_client, db_session
):
    created = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "user-front",
            "branch_name": "main",
            "environment": "staging",
            "actor": "operator",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{created['id']}/deploy-staging",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"]
    record = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    assert record.trigger_source == "local_deploy_runner"
    assert record.status == "requested"
    metadata = json.loads(record.metadata_json)
    assert metadata["localDeployRunner"] is True
    assert metadata["localRunnerCommand"][:4] == [
        "bash",
        "scripts/local/deploy_synapse_staging.sh",
        "--service",
        "user-front",
    ]
    assert metadata["localRunnerCommand"][4:6] == ["--ref", "main"]


def test_release_task_local_recipe_passes_frontend_prebuilt_digest(
    monkeypatch, synced_client, db_session
):
    digest = (
        "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
        "synapse-staging/user-front@sha256:" + ("a" * 64)
    )
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "user-front",
            "branch_name": "main",
            "environment": "staging",
            "actor": "operator",
        },
    ).json()
    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/attach-prebuilt-image",
        json={
            "service_key": "user-front",
            "image_digest": digest,
            "source_commit_sha": "b" * 40,
        },
    )
    assert response.status_code == 200

    deployed = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "operator"},
    )

    assert deployed.status_code == 200
    record = db_session.get(
        DeploymentRecordRow, deployed.json()["deployment_record_id"]
    )
    metadata = json.loads(record.metadata_json)
    assert metadata["prebuiltImageDigest"] == digest
    assert metadata["localRunnerCommand"][-2:] == [
        "--prebuilt-image-digest",
        digest,
    ]


def test_release_task_local_recipe_supports_gateway(
    monkeypatch, synced_client, db_session
):
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "staging",
            "actor": "operator",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    record = db_session.get(
        DeploymentRecordRow, response.json()["deployment_record_id"]
    )
    metadata = json.loads(record.metadata_json)
    assert metadata["localRunnerCommand"][:4] == [
        "bash",
        "scripts/local/deploy_synapse_staging.sh",
        "--service",
        "gateway",
    ]


def test_release_task_local_recipe_supports_gateway_admin(
    monkeypatch, synced_client, db_session
):
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "gateway-admin",
            "branch_name": "main",
            "environment": "staging",
            "actor": "operator",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    record = db_session.get(
        DeploymentRecordRow, response.json()["deployment_record_id"]
    )
    metadata = json.loads(record.metadata_json)
    assert metadata["localRunnerCommand"][:4] == [
        "bash",
        "scripts/local/deploy_synapse_staging.sh",
        "--service",
        "gateway-admin",
    ]


def test_local_deploy_runner_claims_record_and_preserves_logs(db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        health_status="checking",
        branch_name="main",
        actor="operator",
        trigger_source="local_deploy_runner",
        metadata_json=_json_dump({"release_task_id": 0}),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    claimed = claim_local_deployment(db_session, deployment_record_id=int(record.id))

    assert claimed is not None
    assert claimed.status == "running"
    events = (
        db_session.query(DeploymentEventRow)
        .filter(DeploymentEventRow.deployment_record_id == int(record.id))
        .all()
    )
    assert events
    assert events[0].event_type == "runner_status"


def test_local_deploy_runner_finish_updates_linked_task_and_metadata(db_session):
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="deploying",
        actor="operator",
    )
    db_session.add(task)
    db_session.flush()
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        health_status="checking",
        branch_name="main",
        actor="operator",
        trigger_source="local_deploy_runner",
        metadata_json=_json_dump({"release_task_id": int(task.id)}),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    finished = finish_local_deployment(
        db_session, int(record.id), exit_code=0, summary=""
    )

    assert finished.status == "succeeded"
    assert finished.health_status == "passed"
    assert json.loads(finished.metadata_json)["localDeployExitCode"] == 0
    db_session.refresh(task)
    assert task.status == "completed"
    assert task.note == "Local deploy succeeded."


def test_local_deploy_runner_finish_failure_and_missing_record(db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        health_status="checking",
        branch_name="main",
        actor="operator",
        trigger_source="local_deploy_runner",
        metadata_json=_json_dump({}),
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)

    finished = finish_local_deployment(
        db_session, int(record.id), exit_code=7, summary=None
    )

    assert finished.status == "failed"
    assert finished.health_status == "failed"
    assert finished.notes == "Local deploy failed."
    with pytest.raises(ValueError):
        finish_local_deployment(db_session, 999999, exit_code=1)


def test_local_deploy_runner_finish_updates_scheduled_job_task(db_session):
    task = ScheduledJobReleaseTaskRow(
        project_key="synapse-network",
        job_name="synapse-staging-deposit-indexer",
        job_family="gateway",
        job_type="periodic",
        environment="staging",
        source_ref="main",
        status="deploying",
        health_status="checking",
        created_by="operator",
    )
    db_session.add(task)
    db_session.flush()
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="running",
        health_status="checking",
        branch_name="main",
        actor="operator",
        trigger_source="local_deploy_runner",
        metadata_json=_json_dump({"scheduledJobReleaseTaskId": int(task.id)}),
    )
    db_session.add(record)
    db_session.commit()

    finished = finish_local_deployment(
        db_session, int(record.id), exit_code=4, summary="job failed"
    )

    assert finished.status == "failed"
    db_session.refresh(task)
    assert task.status == "failed"
    assert task.health_status == "failed"
    assert task.failure_summary == "job failed"
    assert task.deployment_record_id == int(record.id)


def test_local_deploy_runner_applies_manifest_and_ignores_bad_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    missing = DeploymentRecordRow(
        metadata_json=_json_dump({"localManifestPath": "missing.json"})
    )
    assert _load_manifest(missing) == {}

    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{bad", encoding="utf-8")
    bad = DeploymentRecordRow(
        metadata_json=_json_dump({"localManifestPath": str(bad_path)})
    )
    assert _load_manifest(bad) == {}

    list_path = tmp_path / "list.json"
    list_path.write_text("[]", encoding="utf-8")
    list_record = DeploymentRecordRow(
        metadata_json=_json_dump({"localManifestPath": str(list_path)})
    )
    assert _load_manifest(list_record) == {}

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "imageDigest": "image@sha256:" + ("a" * 64),
                "commitSha": "abc123",
                "serviceUrl": "https://example.test",
                "cloud_run_service": "svc",
                "revision": "rev-1",
                "smoke_status": "passed",
            }
        ),
        encoding="utf-8",
    )
    record = DeploymentRecordRow(
        metadata_json=_json_dump({"localManifestPath": "manifest.json"})
    )

    loaded = _load_manifest(record)
    _apply_manifest(record, loaded)

    metadata = json.loads(record.metadata_json)
    assert record.commit_sha == "abc123"
    assert record.external_url == "https://example.test"
    assert metadata["imageDigest"].endswith("a" * 64)
    assert metadata["cloudRunRevision"] == "rev-1"


def test_local_deploy_task_command_edges():
    staging = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="not-real",
        branch_name="main",
        environment="staging",
        status="requested",
    )
    assert (
        "local_runner_recipe_missing"
        in pytest.raises(
            ValueError,
            local_deploy_tasks._validate_local_recipe_scope,
            "synapse-network",
            "staging",
            "not-real",
        ).value.args[0]
    )
    unsupported = local_deploy_tasks._synapse_network_staging_command(
        staging, service_key="not-real"
    )
    assert unsupported[:2] == ["bash", "-lc"]

    provider = ReleaseTaskRow(
        project_key="synapse-network-provider",
        service_key="provider-service",
        branch_name="main",
        environment="staging",
        status="requested",
    )
    assert local_deploy_tasks._synapse_provider_staging_command(
        provider, service_key="provider-service"
    )[:4] == [
        "bash",
        "scripts/local/deploy_synapse_provider_staging.sh",
        "--ref",
        "main",
    ]

    prod = ReleaseTaskRow(
        project_key="synapse-network",
        service_key="gateway",
        branch_name="main",
        environment="production",
        status="requested",
    )
    assert "staging_digest_missing" in " ".join(
        local_deploy_tasks._production_promote_command(prod, service_key="gateway")
    )
    assert local_deploy_tasks._production_promote_digest(
        prod, {"promoteImageDigest": "image@sha256:" + ("b" * 64)}
    ).endswith("b" * 64)
