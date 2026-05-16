import json

import pytest

from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.schemas import ReleaseTaskPrGateOut
from server.services.delivery.deployment_governance import _json_dump
from server.services.releases import prebuilt_images as prebuilt_image_service
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
        can_deploy_staging=True,
    )


def _create_user_front_task(client):
    return client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "user-front",
            "branch_name": "main",
            "environment": "staging",
        },
    ).json()


def test_frontend_release_task_can_attach_prebuilt_image_and_deploy_digest(
    monkeypatch, synced_client, db_session
):
    calls = []
    digest = (
        "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
        "synapse-staging/user-front@sha256:" + ("a" * 64)
    )
    commit_sha = "b" * 40

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

    task = _create_user_front_task(synced_client)
    attach = synced_client.post(
        f"/api/releases/tasks/{task['id']}/attach-prebuilt-image",
        json={
            "service_key": "user-front",
            "image_digest": digest,
            "source_commit_sha": commit_sha,
            "build_evidence": {"tag": "staging-local-user-front"},
        },
    )

    assert attach.status_code == 200
    attached = attach.json()
    assert attached["target_commit_sha"] == commit_sha
    assert attached["task_metadata"]["prebuiltImageDigest"] == digest

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging", json={"actor": "ops-lead"}
    )

    assert response.status_code == 200
    assert calls[0]["workflow_file"] == "deploy-staging-frontends.yml"
    assert calls[0]["inputs"]["deploy_scope"] == "user-front"
    assert calls[0]["inputs"]["prebuilt_image_digest"] == digest
    assert calls[0]["inputs"]["source_ref_type"] == "commit"
    assert calls[0]["inputs"]["source_ref"] == commit_sha
    assert calls[0]["inputs"]["commit_sha"] == commit_sha

    deployment = db_session.get(
        DeploymentRecordRow, response.json()["deployment_record_id"]
    )
    metadata = json.loads(deployment.metadata_json)
    assert metadata["prebuiltImageDigest"] == digest
    assert metadata["imageSource"] == "prebuilt_digest"
    assert metadata["sourceCommitSha"] == commit_sha


def test_prebuilt_image_attach_defers_digest_identity_checks_to_actions(synced_client):
    task = _create_user_front_task(synced_client)
    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/attach-prebuilt-image",
        json={
            "service_key": "user-front",
            "image_digest": "not-even-a-digest",
            "source_commit_sha": "b" * 40,
        },
    )

    assert response.status_code == 200
    assert response.json()["task_metadata"]["prebuiltImageDigest"] == "not-even-a-digest"


def test_prebuilt_image_endpoint_rejects_missing_or_non_attachable_tasks(
    synced_client, db_session
):
    digest = (
        "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
        "synapse-staging/user-front@sha256:" + ("a" * 64)
    )
    body = {
        "service_key": "user-front",
        "image_digest": digest,
        "source_commit_sha": "b" * 40,
    }
    missing = synced_client.post(
        "/api/releases/tasks/999/attach-prebuilt-image", json=body
    )
    assert missing.status_code == 404

    completed = _create_user_front_task(synced_client)
    synced_client.patch(
        f"/api/releases/tasks/{completed['id']}",
        json={"status": "completed", "operator": "ops-lead"},
    )
    non_requested = synced_client.post(
        f"/api/releases/tasks/{completed['id']}/attach-prebuilt-image", json=body
    )
    assert non_requested.status_code == 400
    assert "Only requested" in non_requested.json()["detail"]

    deployment = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="requested",
        trigger_source="release_task",
    )
    db_session.add(deployment)
    db_session.flush()
    task = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="requested",
        deployment_record_id=int(deployment.id),
    )
    db_session.add(task)
    db_session.commit()
    deployed = synced_client.post(
        f"/api/releases/tasks/{int(task.id)}/attach-prebuilt-image", json=body
    )
    assert deployed.status_code == 400
    assert "already has a deployment" in deployed.json()["detail"]


def test_prebuilt_deploy_plan_handles_missing_and_corrupt_metadata(db_session):
    row = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="requested",
    )
    db_session.add(row)
    db_session.commit()

    assert not prebuilt_image_service.prebuilt_deploy_plan(
        row, service_key="user-front", workflow_file="deploy-staging-frontends.yml"
    ).enabled

    row.metadata_json = "{not-json"
    assert prebuilt_image_service.prebuilt_image_metadata(row) == {}

    row.metadata_json = json.dumps(["not", "a", "dict"])
    assert prebuilt_image_service.prebuilt_image_metadata(row) == {}


def test_prebuilt_deploy_plan_rejects_wrong_workflow(db_session):
    row = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="requested",
        metadata_json=_json_dump(
            {
                "prebuiltImageDigest": (
                    "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
                    "synapse-staging/user-front@sha256:" + ("a" * 64)
                ),
                "sourceCommitSha": "b" * 40,
                "imageSource": "ephemeral_worktree_local_build",
            }
        ),
    )
    db_session.add(row)
    db_session.commit()

    try:
        prebuilt_image_service.prebuilt_deploy_plan(
            row, service_key="user-front", workflow_file="deploy-staging-admin.yml"
        )
    except ValueError as exc:
        assert "staging frontend workflow" in str(exc)
    else:
        raise AssertionError("wrong workflow should fail closed")


def test_prebuilt_image_policy_rejects_invalid_scope_and_identity(db_session):
    base = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="requested",
        target_commit_sha="c" * 40,
    )
    db_session.add(base)
    db_session.commit()
    digest = (
        "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
        "synapse-staging/user-front@sha256:" + ("a" * 64)
    )

    cases = [
        (
            {
                "project_key": "synapse-network",
                "service_key": "user-front",
                "environment": "production",
            },
            "only allowed for staging",
        ),
        (
            {
                "project_key": "other",
                "service_key": "user-front",
                "environment": "staging",
            },
            "Synapse-Network frontend",
        ),
        (
            {
                "project_key": "synapse-network",
                "service_key": "gateway",
                "environment": "staging",
            },
            "admin-front/user-front/docs-front",
        ),
    ]
    for values, expected in cases:
        row = ReleaseTaskRow(
            source_type="manual",
            project_key=values["project_key"],
            service_key=values["service_key"],
            branch_name="main",
            environment=values["environment"],
            status="requested",
        )
        try:
            prebuilt_image_service.validate_prebuilt_image_for_task(
                row,
                service_key=values["service_key"],
                image_digest=digest,
                source_commit_sha="b" * 40,
                image_source="ephemeral_worktree_local_build",
            )
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"{expected} should fail closed")

    prebuilt_image_service.validate_prebuilt_image_for_task(
        base,
        service_key="user-front",
        image_digest="tag-only-or-wrong-registry",
        source_commit_sha="short",
        image_source="operator_supplied",
    )


def test_admin_front_can_attach_prebuilt_image_digest(synced_client):
    task = synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "admin-front",
            "branch_name": "main",
            "environment": "staging",
        },
    ).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/attach-prebuilt-image",
        json={
            "service_key": "admin-front",
            "image_digest": (
                "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
                "synapse-staging/admin-front@sha256:" + ("a" * 64)
            ),
            "source_commit_sha": "b" * 40,
        },
    )

    assert response.status_code == 200
    assert response.json()["task_metadata"]["buildService"] == "admin-front"


def test_prebuilt_image_attach_ignores_non_dict_evidence(db_session):
    row = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="requested",
    )
    db_session.add(row)
    db_session.commit()
    body = type(
        "Body",
        (),
        {
            "service_key": "user-front",
            "image_digest": (
                "us-central1-docker.pkg.dev/fabled-archive-494108-k5/"
                "synapse-staging/user-front@sha256:" + ("a" * 64)
            ),
            "source_commit_sha": "b" * 40,
            "image_source": "ephemeral_worktree_local_build",
            "build_evidence": "not-a-dict",
        },
    )()

    updated = prebuilt_image_service.attach_prebuilt_image_to_task(
        db_session, row, body
    )

    assert json.loads(updated.metadata_json)["buildEvidence"] == {}


def test_prebuilt_image_validation_rejects_empty_digest_or_commit(db_session):
    row = ReleaseTaskRow(
        source_type="manual",
        project_key="synapse-network",
        service_key="user-front",
        branch_name="main",
        environment="staging",
        status="requested",
    )
    db_session.add(row)
    db_session.commit()

    with pytest.raises(ValueError, match="prebuilt image digest is required"):
        prebuilt_image_service.validate_prebuilt_image_for_task(
            row,
            service_key="user-front",
            image_digest="",
            source_commit_sha="b" * 40,
            image_source="ephemeral_worktree_local_build",
        )

    with pytest.raises(ValueError, match="source_commit_sha is required"):
        prebuilt_image_service.validate_prebuilt_image_for_task(
            row,
            service_key="user-front",
            image_digest="not-even-a-digest",
            source_commit_sha="",
            image_source="ephemeral_worktree_local_build",
        )
