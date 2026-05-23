from server.database_deployments import DeploymentEventRow
from server.database import (
    DeploymentRecordRow,
    ProjectPolicyRow,
    ReleaseRecordRow,
    RequirementRow,
)
from server.schemas import ReleaseTaskPrGateOut
from server.services.delivery.deployment_events import record_deployment_event
from server.services.delivery import deployment_governance
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
    )


def _patch_deploy_preflight(monkeypatch, *, dispatch):
    monkeypatch.setattr(release_tasks_service, "_dispatch_github_workflow", dispatch)
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


def _create_release_task(synced_client, branch: str = "codex/deployment-events"):
    return synced_client.post(
        "/api/releases/tasks",
        json={
            "project_key": "synapse-network",
            "service_key": "gateway",
            "branch_name": branch,
            "environment": "staging",
        },
    ).json()


def _event_types(db_session, deployment_record_id: int) -> list[str]:
    rows = (
        db_session.query(DeploymentEventRow)
        .filter_by(deployment_record_id=deployment_record_id)
        .order_by(DeploymentEventRow.id.asc())
        .all()
    )
    return [str(row.event_type) for row in rows]


def _seed_requirement_release(
    db_session, *, commit_sha: str = "abc123"
) -> RequirementRow:
    root_path = "/tmp/synapse-deployment-events"
    policy = ProjectPolicyRow(
        project_key="synapse-deployment-events",
        display_name="Synapse Deployment Events",
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
        staging_workflow_file="deploy-staging.yml",
        production_workflow_file="deploy-production.yml",
    )
    requirement = RequirementRow(
        title="Deployment event release",
        description_markdown="Deploy with event evidence.",
        status="done",
        priority="normal",
        source="test",
        target_project_path=root_path,
        project_key="synapse-deployment-events",
        intake_metadata_json="{}",
    )
    db_session.add_all([policy, requirement])
    db_session.flush()
    db_session.add(
        ReleaseRecordRow(
            requirement_id=int(requirement.id),
            project_key="synapse-deployment-events",
            target_project_path=root_path,
            status="release_ready",
            delivery_state="merged",
            branch_name="main",
            actual_branch_name="main",
            commit_sha=commit_sha,
            pr_url="https://github.com/SynapseNetworkAI/Synapse-Network/pull/123",
            pr_number=123,
            metadata_json=(
                f'{{"head_branch":"main","latest_remote_sha":"{commit_sha}",'
                '"checks_status":"success","pr_merged":true}'
            ),
        )
    )
    db_session.commit()
    return requirement


def test_deploy_staging_writes_deployment_event_ledger(
    monkeypatch, synced_client, db_session
):
    _patch_deploy_preflight(
        monkeypatch,
        dispatch=lambda **kwargs: "https://github.com/actions/runs/123",
    )
    task = _create_release_task(synced_client)

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "ops-lead"},
    )

    assert response.status_code == 200
    record_id = int(response.json()["deployment_record_id"])
    events = synced_client.get(f"/api/deployments/{record_id}/events")
    assert events.status_code == 200
    assert [event["event_type"] for event in events.json()] == [
        "deployment_requested",
        "deployment_dispatched",
    ]
    assert _event_types(db_session, record_id) == [
        "deployment_requested",
        "deployment_dispatched",
    ]


def test_deploy_report_appends_deployment_reported_event(
    monkeypatch, synced_client, db_session
):
    _patch_deploy_preflight(
        monkeypatch,
        dispatch=lambda **kwargs: "https://github.com/actions/runs/124",
    )
    task = _create_release_task(synced_client, branch="codex/deployment-report-event")
    deployed = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging", json={}
    ).json()
    record_id = int(deployed["deployment_record_id"])

    report = synced_client.post(
        f"/api/deployments/{record_id}/report",
        json={
            "status": "succeeded",
            "health_status": "passed",
            "notes": "staging deploy succeeded",
        },
    )

    assert report.status_code == 200
    assert _event_types(db_session, record_id)[-1] == "deployment_reported"


def test_deploy_dispatch_failure_writes_failed_event(
    monkeypatch, synced_client, db_session
):
    def failing_dispatch(**kwargs):
        raise RuntimeError("GitHub workflow dispatch failed: missing workflow")

    _patch_deploy_preflight(monkeypatch, dispatch=failing_dispatch)
    task = _create_release_task(synced_client, branch="codex/deployment-failed-event")

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging", json={}
    )

    assert response.status_code == 200
    record_id = int(response.json()["deployment_record_id"])
    assert _event_types(db_session, record_id)[-1] == "deployment_dispatch_failed"


def test_requirement_staging_deploy_writes_deployment_events(
    monkeypatch, synced_client, db_session
):
    requirement = _seed_requirement_release(db_session)
    monkeypatch.setattr(
        deployment_governance,
        "_dispatch_github_workflow",
        lambda **kwargs: "https://github.com/actions/runs/300",
    )

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/staging",
        json={
            "actor": "operator",
            "source_ref_type": "branch",
            "source_ref": "main",
            "deploy_scope": "gateway",
        },
    )

    assert response.status_code == 200
    record_id = int(
        db_session.query(DeploymentRecordRow)
        .filter_by(requirement_id=int(requirement.id), environment="staging")
        .one()
        .id
    )
    assert _event_types(db_session, record_id) == [
        "deployment_requested",
        "deployment_dispatched",
    ]


def test_requirement_production_promote_writes_deployment_events(
    monkeypatch, synced_client, db_session
):
    requirement = _seed_requirement_release(db_session, commit_sha="prod123")
    staging = DeploymentRecordRow(
        requirement_id=int(requirement.id),
        project_key="synapse-deployment-events",
        environment="staging",
        action="deploy",
        status="succeeded",
        commit_sha="prod123",
        health_status="passed",
        metadata_json=(
            '{"smoke_evidence":{"api_health":"passed",'
            '"frontend_page":"passed","key_e2e":"passed"}}'
        ),
    )
    production = DeploymentRecordRow(
        project_key="synapse-deployment-events",
        environment="production",
        action="promote",
        status="succeeded",
        commit_sha="prev123",
        health_status="passed",
    )
    db_session.add_all([staging, production])
    db_session.flush()
    for event_type in (
        "deployment_requested",
        "deployment_dispatched",
        "deployment_reported",
    ):
        record_deployment_event(
            db_session,
            staging,
            event_type=event_type,
            actor="test",
            summary=f"staging {event_type}",
        )
    db_session.commit()
    monkeypatch.setattr(
        deployment_governance,
        "_dispatch_github_workflow",
        lambda **kwargs: "https://github.com/actions/runs/301",
    )

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/production",
        json={
            "actor": "operator",
            "source_ref_type": "commit",
            "source_ref": "prod123",
            "deploy_scope": "all",
        },
    )

    assert response.status_code == 200
    record_id = int(
        db_session.query(DeploymentRecordRow)
        .filter_by(requirement_id=int(requirement.id), environment="production")
        .one()
        .id
    )
    assert _event_types(db_session, record_id) == [
        "deployment_requested",
        "production_agent_review_started",
        "production_agent_review_passed",
        "production_dispatch_started",
        "deployment_dispatched",
    ]


def test_requirement_production_promote_blocks_without_staging_evidence(
    monkeypatch, synced_client, db_session
):
    requirement = _seed_requirement_release(db_session, commit_sha="missing-stage")
    monkeypatch.setattr(
        deployment_governance,
        "_dispatch_github_workflow",
        lambda **kwargs: "https://github.com/actions/runs/blocked",
    )

    response = synced_client.post(
        f"/api/releases/{requirement.id}/deploy/production",
        json={
            "actor": "agent-release-reviewer",
            "source_ref_type": "commit",
            "source_ref": "missing-stage",
            "deploy_scope": "all",
        },
    )

    assert response.status_code == 200
    record = (
        db_session.query(DeploymentRecordRow)
        .filter_by(requirement_id=int(requirement.id), environment="production")
        .one()
    )
    assert record.status == "agent_blocked"
    assert record.external_url is None
    assert "missing_same_commit_staging_success" in (record.notes or "")
    assert _event_types(db_session, int(record.id)) == [
        "deployment_requested",
        "production_agent_review_started",
        "production_agent_review_blocked",
    ]
