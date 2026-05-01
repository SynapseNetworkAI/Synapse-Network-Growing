import json

from server.database import DeploymentRecordRow, ProjectPolicyRow, ReleaseRecordRow, RequirementRow
from server.services.delivery.deployment_governance import mark_requirement_no_deploy


def _seed_release(db_session, *, commit_sha: str | None = None):
    root_path = "/tmp/synapse-branch-deploy"
    policy = ProjectPolicyRow(
        project_key="synapse-branch-deploy",
        display_name="Synapse Branch Deploy",
        root_path=root_path,
        status="active",
        allowed_write_globs_json='["**"]',
        forbidden_globs_json="[]",
        required_checks_json="[]",
        release_mode="manual",
        requires_manual_approval=True,
        deploy_repo_full_name="SynapseNetworkAI/Synapse-Network",
        deploy_strategy="github_actions_gcp_cloudrun",
        deploy_trigger_enabled=True,
        staging_host_label="cloud-run-staging",
        production_host_label="cloud-run-prod",
        staging_workflow_file="deploy-staging.yml",
        production_workflow_file="deploy-production.yml",
    )
    requirement = RequirementRow(
        title="Branch deploy release",
        description_markdown="Deploy a branch to staging.",
        status="done",
        priority="normal",
        source="test",
        target_project_path=root_path,
        project_key="synapse-branch-deploy",
        intake_metadata_json="{}",
    )
    db_session.add_all([policy, requirement])
    db_session.flush()
    release = ReleaseRecordRow(
        requirement_id=int(requirement.id),
        project_key="synapse-branch-deploy",
        target_project_path=root_path,
        status="release_ready",
        delivery_state="pr_open",
        branch_name="codex/branch-deploy-test",
        actual_branch_name="codex/branch-deploy-test",
        commit_sha=commit_sha,
        pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/123",
        pr_number=123,
        metadata_json=json.dumps(
            {
                "head_branch": "codex/branch-deploy-test",
                "latest_remote_sha": commit_sha,
            }
        ),
    )
    db_session.add(release)
    db_session.commit()
    return requirement


def test_staging_branch_deploy_freezes_source_ref_and_scope(synced_client, db_session, monkeypatch):
    requirement = _seed_release(db_session)
    dispatched = {}

    def fake_dispatch(**kwargs):
        dispatched.update(kwargs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging.yml"

    monkeypatch.setattr("server.services.delivery.deployment_governance._dispatch_github_workflow", fake_dispatch)

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={
            "actor": "operator",
            "source_ref_type": "branch",
            "source_ref": "codex/branch-deploy-test",
            "deploy_scope": "gateway",
        },
    )

    assert response.status_code == 200
    record = db_session.query(DeploymentRecordRow).one()
    metadata = json.loads(record.metadata_json)
    assert record.environment == "staging"
    assert record.action == "deploy"
    assert record.branch_name == "codex/branch-deploy-test"
    assert record.workflow_file == "deploy-staging.yml"
    assert metadata["sourceRefType"] == "branch"
    assert metadata["sourceRef"] == "codex/branch-deploy-test"
    assert metadata["deployScope"] == "gateway"
    assert metadata["host_label"] == "cloud-run-staging"
    assert dispatched["ref"] == "main"
    assert dispatched["inputs"]["source_ref_type"] == "branch"
    assert dispatched["inputs"]["source_ref"] == "codex/branch-deploy-test"
    assert dispatched["inputs"]["deploy_scope"] == "gateway"


def test_production_rejects_feature_branch_deploy(synced_client, db_session, monkeypatch):
    requirement = _seed_release(db_session, commit_sha="abc123")
    monkeypatch.setattr(
        "server.services.delivery.deployment_governance._dispatch_github_workflow",
        lambda **_: "should-not-dispatch",
    )

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/production",
        json={
            "actor": "operator",
            "source_ref_type": "branch",
            "source_ref": "codex/branch-deploy-test",
            "deploy_scope": "all",
        },
    )

    assert response.status_code == 400
    assert "Production deploy cannot target a feature branch" in response.json()["detail"]
    assert db_session.query(DeploymentRecordRow).count() == 0


def test_no_deploy_records_release_decision_and_metadata(synced_client, db_session):
    requirement = _seed_release(db_session, commit_sha="abc123")

    response = synced_client.post(
        f"/api/releases/{requirement.id}/no-deploy",
        json={
            "actor": "operator",
            "note": "docs-only change",
            "source_ref_type": "branch",
            "source_ref": "codex/docs-only",
            "deploy_scope": "auto",
        },
    )

    assert response.status_code == 200
    record = db_session.query(DeploymentRecordRow).one()
    metadata = json.loads(record.metadata_json)
    release = db_session.query(ReleaseRecordRow).one()
    assert record.action == "no_deploy"
    assert record.status == "no_deploy"
    assert record.branch_name == "codex/docs-only"
    assert metadata["sourceRefType"] == "branch"
    assert metadata["sourceRef"] == "codex/docs-only"
    assert metadata["resolvedCommitSha"] == "abc123"
    assert metadata["deployScope"] == []
    assert "requested scope=auto" in metadata["noDeployReason"]
    assert release.status == "no_deploy"
    assert release.delivery_state == "no_deploy"


def test_deployment_report_merges_release_manifest_metadata(synced_client, db_session, monkeypatch):
    requirement = _seed_release(db_session)
    monkeypatch.setattr(
        "server.services.delivery.deployment_governance._dispatch_github_workflow",
        lambda **_: "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging.yml",
    )
    deploy_response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={"actor": "operator", "source_ref_type": "branch", "deploy_scope": "user-front"},
    )
    assert deploy_response.status_code == 200
    record = db_session.query(DeploymentRecordRow).one()

    report_response = synced_client.post(
        f"/api/deployments/{record.id}/report",
        json={
            "status": "succeeded",
            "external_run_id": "123456",
            "external_url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123456",
            "health_status": "passed",
            "branch_name": "codex/branch-deploy-test",
            "commit_sha": "abc123",
            "notes": "staging smoke passed",
            "metadata": {
                "resolvedCommitSha": "abc123",
                "imageDigests": {"user-front": "us-central1-docker.pkg.dev/repo/user-front@sha256:abc"},
                "cloudRunRevisions": {"user-front": "synapse-user-front-0001"},
                "evidenceUri": "gs://synapse-staging-evidence/deployments/release.json",
            },
        },
    )

    assert report_response.status_code == 200
    payload = report_response.json()
    assert payload["status"] == "succeeded"
    assert payload["commit_sha"] == "abc123"
    assert payload["metadata"]["resolvedCommitSha"] == "abc123"
    assert payload["metadata"]["imageDigests"]["user-front"].endswith("@sha256:abc")
    assert payload["metadata"]["cloudRunRevisions"]["user-front"] == "synapse-user-front-0001"


def test_staging_commit_ref_resolves_commit_sha(synced_client, db_session, monkeypatch):
    requirement = _seed_release(db_session)
    monkeypatch.setattr(
        "server.services.delivery.deployment_governance._dispatch_github_workflow",
        lambda **_: "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging.yml",
    )

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={
            "actor": "operator",
            "source_ref_type": "commit",
            "source_ref": "abc123",
            "deploy_scope": "gateway-admin",
        },
    )

    assert response.status_code == 200
    record = db_session.query(DeploymentRecordRow).one()
    assert record.commit_sha == "abc123"
    assert record.branch_name == "abc123"


def test_deploy_rejects_invalid_source_ref_type_and_scope(synced_client, db_session):
    requirement = _seed_release(db_session)

    bad_ref = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={"actor": "operator", "source_ref_type": "floating", "deploy_scope": "gateway"},
    )
    bad_scope = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={"actor": "operator", "source_ref_type": "branch", "deploy_scope": "everything"},
    )

    assert bad_ref.status_code == 400
    assert "source_ref_type must be branch, tag, or commit" in bad_ref.json()["detail"]
    assert bad_scope.status_code == 400
    assert "deploy_scope must be auto" in bad_scope.json()["detail"]


def test_deploy_and_no_deploy_require_prepared_release(synced_client, db_session):
    root_path = "/tmp/synapse-no-release"
    db_session.add(
        ProjectPolicyRow(
            project_key="synapse-no-release",
            display_name="Synapse No Release",
            root_path=root_path,
            status="active",
            allowed_write_globs_json='["**"]',
            forbidden_globs_json="[]",
            required_checks_json="[]",
            deploy_repo_full_name="SynapseNetworkAI/Synapse-Network",
            deploy_strategy="github_actions_gcp_cloudrun",
            deploy_trigger_enabled=True,
        )
    )
    requirement = RequirementRow(
        title="No release yet",
        description_markdown="Release has not been prepared.",
        status="done",
        priority="normal",
        source="test",
        target_project_path=root_path,
        intake_metadata_json="{}",
    )
    db_session.add(requirement)
    db_session.commit()

    deploy_response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={"actor": "operator", "source_ref_type": "branch", "deploy_scope": "auto"},
    )
    no_deploy_response = synced_client.post(
        f"/api/releases/{requirement.id}/no-deploy",
        json={"actor": "operator", "source_ref_type": "branch", "deploy_scope": "auto"},
    )

    assert deploy_response.status_code == 400
    assert deploy_response.json()["detail"] == "Release must be prepared before deployment."
    assert no_deploy_response.status_code == 400
    assert no_deploy_response.json()["detail"] == "Release must be prepared before marking no-deploy."


def test_production_deploy_requires_release_commit(synced_client, db_session):
    requirement = _seed_release(db_session)

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/production",
        json={"actor": "operator", "source_ref_type": "commit", "source_ref": "abc123", "deploy_scope": "all"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Production deployment requires a resolved committed SHA."


def test_no_deploy_rejects_missing_requirement(db_session):
    try:
        mark_requirement_no_deploy(db_session, 404, actor="operator")
    except ValueError as exc:
        assert str(exc) == "Requirement not found."
    else:
        raise AssertionError("missing requirement should reject no-deploy")
