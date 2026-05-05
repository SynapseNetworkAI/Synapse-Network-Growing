import json
from datetime import timedelta

from server.database import DeploymentRecordRow, utcnow
from server.database_scheduled_jobs import ScheduledJobReleaseTaskRow
from server.services.releases.github_actions_logs import GitHubFailureLogResult
from server.services.releases import scheduled_jobs as scheduled_jobs_service
from server.services.releases import scheduled_job_tasks
from server.services.releases import scheduled_job_sync
from server.services.releases import scheduled_job_workflow


def test_scheduled_jobs_catalog_returns_gateway_and_admin_jobs(synced_client):
    response = synced_client.get("/api/releases/scheduled-jobs/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 7
    names = {item["job_name"] for item in payload}
    assert "synapse-staging-deposit-indexer" in names
    assert "synapse-staging-gateway-admin-db-migrate" in names
    assert sum(1 for item in payload if item["job_type"] == "periodic") == 5
    assert sum(1 for item in payload if item["job_type"] == "migration") == 2


def test_scheduled_jobs_records_returns_paginated_publish_records(
    synced_client, db_session
):
    gateway_record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="succeeded",
        health_status="passed",
        branch_name="main",
        workflow_file="deploy-staging-jobs.yml",
        external_run_id="123",
        external_url="https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123",
        actor="operator",
        trigger_source="scheduled_job_release",
        metadata_json=json.dumps(
            {
                "publishMode": "single_job",
                "jobFamily": "gateway",
                "jobName": "synapse-staging-deposit-indexer",
                "jobs": ["synapse-staging-deposit-indexer"],
                "sourceRef": "main",
            }
        ),
    )
    unrelated_record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        health_status="passed",
        actor="operator",
        trigger_source="release_task",
        metadata_json="{}",
    )
    db_session.add_all([gateway_record, unrelated_record])
    db_session.commit()

    response = synced_client.get(
        "/api/releases/scheduled-jobs/tasks",
        params={
            "job_name": "synapse-staging-deposit-indexer",
            "family": "gateway",
            "status": "completed",
            "limit": 10,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert payload["items"][0]["job_name"] == "synapse-staging-deposit-indexer"
    assert payload["items"][0]["family"] == "gateway"
    assert payload["items"][0]["status"] == "completed"
    assert payload["items"][0]["external_run_id"] == "123"


def test_scheduled_jobs_records_prioritize_unpublished_before_terminal(
    synced_client, db_session
):
    now = utcnow()
    for status, updated_at in [
        ("completed", now),
        ("failed", now - timedelta(minutes=1)),
        ("requested", now - timedelta(days=1)),
    ]:
        db_session.add(
            ScheduledJobReleaseTaskRow(
                project_key="synapse-network",
                job_name=f"synapse-staging-{status}-job",
                job_family="gateway",
                job_type="periodic",
                environment="staging",
                source_ref_type="branch",
                source_ref="main",
                status=status,
                health_status="pending",
                created_by="operator",
                updated_at=updated_at,
            )
        )
    db_session.commit()

    response = synced_client.get(
        "/api/releases/scheduled-jobs/tasks",
        params={"environment": "staging", "limit": 10},
    )

    assert response.status_code == 200
    statuses = [item["status"] for item in response.json()["items"][:3]]
    assert statuses == ["requested", "completed", "failed"]


def test_create_scheduled_job_task_does_not_dispatch(synced_client, db_session):
    response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "staging",
            "source_ref": "main",
            "actor": "operator",
            "run_smoke_jobs": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_name"] == "synapse-staging-deposit-indexer"
    assert payload["status"] == "requested"
    assert payload["health_status"] == "pending"
    assert payload["deployment_record_id"] is None
    assert db_session.query(DeploymentRecordRow).count() == 0


def test_publish_scheduled_job_task_dispatches_selected_job_only(
    monkeypatch, synced_client, db_session
):
    dispatches = []

    def fake_dispatch(*, repo_full_name, workflow_file, ref, inputs):
        dispatches.append(inputs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging-jobs.yml"

    monkeypatch.setattr(scheduled_job_tasks, "_dispatch_github_workflow", fake_dispatch)
    monkeypatch.setattr(
        scheduled_job_tasks,
        "_ensure_remote_workflow_accepts_inputs",
        lambda inputs: None,
    )

    create_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "staging",
            "source_ref": "main",
            "actor": "operator",
            "run_smoke_jobs": True,
        },
    )
    task_id = create_response.json()["id"]
    response = synced_client.post(
        f"/api/releases/scheduled-jobs/tasks/{task_id}/publish",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert payload["family"] == "gateway"
    assert payload["publish_mode"] == "single_job"
    assert payload["job_name"] == "synapse-staging-deposit-indexer"
    assert payload["jobs"] == ["synapse-staging-deposit-indexer"]
    assert dispatches[0]["job_family"] == "gateway"
    assert dispatches[0]["job_name"] == "synapse-staging-deposit-indexer"
    assert "environment" not in dispatches[0]
    assert dispatches[0]["source_ref"] == "main"
    record = db_session.get(DeploymentRecordRow, int(payload["deployment_record_id"]))
    assert record is not None
    metadata = json.loads(record.metadata_json)
    assert metadata["scheduledJobReleaseTaskId"] == task_id
    assert metadata["publishMode"] == "single_job"
    assert metadata["jobName"] == "synapse-staging-deposit-indexer"
    assert metadata["jobs"] == ["synapse-staging-deposit-indexer"]
    task = db_session.get(ScheduledJobReleaseTaskRow, task_id)
    assert task.status == "deploying"
    assert task.deployment_record_id == int(payload["deployment_record_id"])


def test_publish_scheduled_job_task_fails_when_remote_workflow_is_old(
    monkeypatch, synced_client, db_session
):
    dispatches = []

    def fake_dispatch(*, repo_full_name, workflow_file, ref, inputs):
        dispatches.append(inputs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging-jobs.yml"

    def fake_preflight(inputs):
        raise ValueError(
            "Scheduled jobs workflow on SynapseNetworkAI/Synapse-Network main does "
            "not accept input(s): job_name."
        )

    monkeypatch.setattr(scheduled_job_tasks, "_dispatch_github_workflow", fake_dispatch)
    monkeypatch.setattr(
        scheduled_job_tasks,
        "_ensure_remote_workflow_accepts_inputs",
        fake_preflight,
    )

    create_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "staging",
            "source_ref": "main",
            "actor": "operator",
        },
    )
    task_id = create_response.json()["id"]
    response = synced_client.post(
        f"/api/releases/scheduled-jobs/tasks/{task_id}/publish",
        json={"actor": "operator"},
    )

    assert response.status_code == 400
    assert "does not accept input" in response.json()["detail"]
    assert dispatches == []
    record = (
        db_session.query(DeploymentRecordRow)
        .order_by(DeploymentRecordRow.id.desc())
        .first()
    )
    assert record is not None
    assert record.trigger_source == "scheduled_job_release"
    assert record.status == "failed"
    assert "does not accept input" in (record.notes or "")
    task = db_session.get(ScheduledJobReleaseTaskRow, task_id)
    assert task.status == "failed"
    assert "does not accept input" in (task.failure_summary or "")


def test_workflow_dispatch_input_parser_extracts_allowed_inputs():
    workflow_yaml = """
name: Deploy Staging Cloud Run Jobs
on:
  workflow_dispatch:
    inputs:
      record_id:
        required: true
      job_name:
        required: false
      environment:
        required: false
permissions:
  contents: read
"""

    names = scheduled_job_workflow.workflow_dispatch_input_names(workflow_yaml)

    assert {"record_id", "job_name", "environment"} <= names
    assert "permissions" not in names


def test_scheduled_job_workflow_preflight_fail_closed(monkeypatch):
    monkeypatch.setattr(
        scheduled_job_workflow,
        "run_gh_text",
        lambda args, timeout=30: ("error", "", "gh offline"),
    )
    try:
        scheduled_job_workflow.ensure_scheduled_job_workflow_accepts_inputs(
            {"job_name": "synapse-staging-deposit-indexer"}
        )
    except ValueError as exc:
        assert "could not be verified" in str(exc)
    else:
        raise AssertionError("expected workflow schema verification failure")

    monkeypatch.setattr(
        scheduled_job_workflow,
        "run_gh_text",
        lambda args, timeout=30: (
            "ok",
            "on:\n  workflow_dispatch:\n    inputs:\n      record_id:\n",
            None,
        ),
    )
    try:
        scheduled_job_workflow.ensure_scheduled_job_workflow_accepts_inputs(
            {"record_id": "1", "job_name": "synapse-staging-deposit-indexer"}
        )
    except ValueError as exc:
        assert "does not accept input(s): job_name" in str(exc)
    else:
        raise AssertionError("expected unexpected workflow input failure")


def test_publish_single_migration_job_requires_confirmation(synced_client):
    response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-db-migrate",
            "environment": "staging",
            "source_ref": "main",
        },
    )

    assert response.status_code == 400
    assert "run_migrations confirmation" in response.json()["detail"]


def test_publish_scheduled_job_rejects_unknown_job_and_non_staging(synced_client):
    unknown_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={"job_name": "not-a-real-job", "environment": "staging"},
    )

    assert unknown_response.status_code == 400
    assert "Unknown scheduled job name" in unknown_response.json()["detail"]

    production_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={
            "job_name": "synapse-staging-deposit-indexer",
            "environment": "production",
        },
    )

    assert production_response.status_code == 400
    assert "environment must be staging" in production_response.json()["detail"]


def test_scheduled_jobs_status_projects_latest_manifest(synced_client, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="succeeded",
        health_status="passed",
        branch_name="main",
        workflow_file="deploy-staging-jobs.yml",
        external_url="https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/1",
        actor="operator",
        trigger_source="scheduled_job_release",
        notes="ok",
        metadata_json=(
            '{"jobFamily":"gateway","jobs":["synapse-staging-deposit-indexer"],'
            '"jobsManifest":{"updated":[{"family":"gateway","job":"synapse-staging-deposit-indexer",'
            '"effectiveImage":"us-central1-docker.pkg.dev/project/repo/gateway@sha256:abc"}]}}'
        ),
    )
    db_session.add(record)
    db_session.commit()

    response = synced_client.get("/api/releases/scheduled-jobs/status")

    assert response.status_code == 200
    deposit = next(
        item
        for item in response.json()["items"]
        if item["job_name"] == "synapse-staging-deposit-indexer"
    )
    assert deposit["publish_status"] == "published"
    assert deposit["health_status"] == "passed"
    assert deposit["effective_image"].endswith("@sha256:abc")


def test_scheduled_jobs_status_handles_empty_and_failed_records(
    synced_client, db_session
):
    empty_response = synced_client.get("/api/releases/scheduled-jobs/status")
    assert empty_response.status_code == 200
    empty_payload = empty_response.json()
    assert empty_payload["items"][0]["publish_status"] == "unknown"

    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="failed",
        health_status="failed",
        branch_name="main",
        workflow_file="deploy-staging-jobs.yml",
        external_url="https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/2",
        actor="operator",
        trigger_source="scheduled_job_release",
        notes="job publish failed",
        metadata_json='{"jobFamily":"gateway-admin","images":{"gateway-admin":"image@sha256:def"}}',
    )
    db_session.add(record)
    db_session.commit()

    response = synced_client.get("/api/releases/scheduled-jobs/status")

    assert response.status_code == 200
    migration = next(
        item
        for item in response.json()["items"]
        if item["job_name"] == "synapse-staging-gateway-admin-db-migrate"
    )
    assert migration["publish_status"] == "failed"
    assert migration["failure_summary"] == "job publish failed"
    assert migration["effective_image"] == "image@sha256:def"


def test_legacy_scheduled_jobs_publish_endpoint_is_disabled(synced_client):
    response = synced_client.post(
        "/api/releases/scheduled-jobs/publish",
        json={"job_name": "synapse-staging-deposit-indexer", "actor": "operator"},
    )

    assert response.status_code == 410
    assert "two-step" in response.json()["detail"]


def test_scheduled_jobs_task_publish_marks_dispatch_failure(monkeypatch, db_session):
    monkeypatch.setattr(
        scheduled_job_tasks,
        "_ensure_remote_workflow_accepts_inputs",
        lambda inputs: None,
    )
    monkeypatch.setattr(
        scheduled_job_tasks,
        "_dispatch_github_workflow",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("dispatch unavailable")),
    )
    task = scheduled_job_tasks.create_scheduled_job_release_task(
        db_session,
        scheduled_job_tasks.ScheduledCloudRunJobTaskCreateRequest(
            job_name="synapse-staging-deposit-indexer",
            actor="operator",
        ),
    )

    try:
        scheduled_job_tasks.publish_scheduled_job_release_task(
            db_session,
            task.id,
            scheduled_job_tasks.ScheduledCloudRunJobTaskPublishRequest(
                actor="operator"
            ),
        )
    except RuntimeError as exc:
        assert "dispatch unavailable" in str(exc)
    else:
        raise AssertionError("expected dispatch failure")

    record = (
        db_session.query(DeploymentRecordRow)
        .filter(DeploymentRecordRow.trigger_source == "scheduled_job_release")
        .one()
    )
    assert record.status == "failed"
    assert record.health_status == "failed"
    assert "dispatch unavailable" in str(record.notes)
    task_row = db_session.get(ScheduledJobReleaseTaskRow, int(task.id))
    assert task_row.status == "failed"


def test_scheduled_jobs_publish_includes_callback_inputs(monkeypatch, synced_client):
    dispatches = []

    monkeypatch.setattr(
        scheduled_jobs_service,
        "_callback_url",
        lambda record_id: f"https://callback/{record_id}",
    )
    monkeypatch.setattr(
        scheduled_jobs_service.config, "DEPLOY_WEBHOOK_TOKEN", "token-123"
    )

    def fake_dispatch(*, repo_full_name, workflow_file, ref, inputs):
        dispatches.append(inputs)
        return "https://github.com/SynapseNetworkAI/Synapse-Network/actions/workflows/deploy-staging-jobs.yml"

    monkeypatch.setattr(scheduled_job_tasks, "_dispatch_github_workflow", fake_dispatch)
    monkeypatch.setattr(
        scheduled_job_tasks,
        "_ensure_remote_workflow_accepts_inputs",
        lambda inputs: None,
    )

    create_response = synced_client.post(
        "/api/releases/scheduled-jobs/tasks",
        json={"job_name": "synapse-staging-deposit-indexer", "actor": "operator"},
    )
    response = synced_client.post(
        f"/api/releases/scheduled-jobs/tasks/{create_response.json()['id']}/publish",
        json={"actor": "operator"},
    )

    assert response.status_code == 200
    assert dispatches[0]["callback_url"].startswith("https://callback/")
    assert dispatches[0]["callback_token"] == "token-123"


def test_scheduled_job_helpers_are_fail_closed():
    assert scheduled_jobs_service._json_load(None) == {}
    assert scheduled_jobs_service._json_load({"ok": True}) == {"ok": True}
    assert scheduled_jobs_service._json_load(42) == {}
    assert scheduled_jobs_service._json_load("{") == {}
    assert (
        scheduled_jobs_service._run_id_from_url(
            "https://github.com/org/repo/actions/runs/123"
        )
        == "123"
    )
    assert scheduled_jobs_service._run_id_from_url("no-run") is None
    assert scheduled_jobs_service._parse_github_timestamp(None) is None
    assert scheduled_jobs_service._parse_github_timestamp("not-a-date") is None
    assert scheduled_jobs_service._as_aware_utc(None) is None


def test_scheduled_jobs_sync_reconciles_success(monkeypatch, synced_client, db_session):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="requested",
        health_status="checking",
        branch_name="main",
        workflow_file="deploy-staging-jobs.yml",
        external_run_id="123",
        external_url="https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123",
        actor="operator",
        trigger_source="scheduled_job_release",
        metadata_json='{"jobFamily":"gateway","jobs":["synapse-staging-deposit-indexer"]}',
    )
    db_session.add(record)
    db_session.commit()

    monkeypatch.setattr(
        scheduled_job_sync,
        "run_gh_json",
        lambda args, timeout=30: (
            "ok",
            {
                "databaseId": 123,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/123",
                "headSha": "abc123",
            },
            None,
        ),
    )

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["succeeded_ids"] == [int(record.id)]
    db_session.refresh(record)
    assert record.status == "succeeded"
    assert record.health_status == "passed"
    assert record.commit_sha == "abc123"


def test_scheduled_jobs_sync_handles_running_failure_error_and_pending(
    monkeypatch, synced_client, db_session
):
    records = []
    for run_id in ("201", "202", "203", "204"):
        record = DeploymentRecordRow(
            project_key="synapse-network",
            environment="staging",
            action="publish_cloud_run_jobs",
            status="requested",
            health_status="checking",
            branch_name="main",
            workflow_file="deploy-staging-jobs.yml",
            external_run_id=run_id if run_id != "204" else None,
            external_url=f"https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/{run_id}"
            if run_id != "204"
            else None,
            actor="operator",
            trigger_source="scheduled_job_release",
            metadata_json='{"jobFamily":"gateway","jobs":["synapse-staging-deposit-indexer"]}',
        )
        db_session.add(record)
        records.append(record)
    db_session.commit()

    def fake_run_gh_json(args, timeout=30):
        if args[:2] == ["run", "list"]:
            return "ok", [], None
        run_id = args[2]
        payloads = {
            "201": {
                "databaseId": 201,
                "status": "in_progress",
                "conclusion": "",
                "url": records[0].external_url,
            },
            "202": {
                "databaseId": 202,
                "status": "completed",
                "conclusion": "failure",
                "url": records[1].external_url,
            },
        }
        if run_id == "203":
            return "error", None, "gh unavailable"
        return "ok", payloads[run_id], None

    monkeypatch.setattr(scheduled_job_sync, "run_gh_json", fake_run_gh_json)
    monkeypatch.setattr(
        scheduled_job_sync,
        "github_failure_log_result",
        lambda *args, **kwargs: GitHubFailureLogResult(
            excerpt="failed step",
            metadata={"githubFailureLogStatus": "ok"},
            note="GitHub Actions scheduled jobs publish failure.\nfailed step",
        ),
    )

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    payload = response.json()
    assert int(records[0].id) in payload["running_ids"]
    assert int(records[1].id) in payload["failed_ids"]
    assert int(records[2].id) in payload["error_ids"]
    assert int(records[3].id) in payload["pending_ids"]
    db_session.refresh(records[1])
    assert "failed step" in str(records[1].notes)


def test_scheduled_jobs_sync_finds_recent_run_from_list(
    monkeypatch, synced_client, db_session
):
    record = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="publish_cloud_run_jobs",
        status="requested",
        health_status="checking",
        branch_name="main",
        workflow_file="deploy-staging-jobs.yml",
        actor="operator",
        trigger_source="scheduled_job_release",
        metadata_json='{"jobFamily":"gateway","jobs":["synapse-staging-deposit-indexer"],"sourceRef":"main"}',
    )
    db_session.add(record)
    db_session.commit()

    def fake_run_gh_json(args, timeout=30):
        if args[:2] == ["run", "list"]:
            return (
                "ok",
                [
                    {"databaseId": None, "createdAt": "bad-date", "headBranch": "main"},
                    {
                        "databaseId": 301,
                        "createdAt": "2999-01-01T00:00:00Z",
                        "headBranch": "other",
                    },
                    {
                        "databaseId": 302,
                        "createdAt": "2999-01-01T00:00:00Z",
                        "headBranch": "main",
                    },
                ],
                None,
            )
        return (
            "ok",
            {
                "databaseId": 302,
                "status": "completed",
                "conclusion": "success",
                "url": "https://github.com/SynapseNetworkAI/Synapse-Network/actions/runs/302",
            },
            None,
        )

    monkeypatch.setattr(scheduled_job_sync, "run_gh_json", fake_run_gh_json)

    response = synced_client.post("/api/releases/scheduled-jobs/sync")

    assert response.status_code == 200
    assert response.json()["succeeded_ids"] == [int(record.id)]
