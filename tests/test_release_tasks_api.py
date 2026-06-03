import json
import subprocess

from server.database import DeploymentRecordRow, ReleaseTaskRow
from server.services.releases import mcp_remote_tasks, mcp_server_runner
from server.services.releases.mcp_server_models import McpServerReleaseRow


def _create_task(client, **overrides):
    payload = {
        "project_key": "synapse-network",
        "project_display_name": "Synapse-Network",
        "service_key": "gateway",
        "branch_name": "main",
        "environment": "staging",
    }
    payload.update(overrides)
    return client.post("/api/releases/tasks", json=payload)


def _create_ready_mcp_release(client, db_session, repo_path=None):
    created = client.post(
        "/api/releases/mcp-servers",
        json={"package_version": "0.1.0", "release_notes": "Remote MCP prod."},
    )
    assert created.status_code == 201
    row = db_session.get(McpServerReleaseRow, created.json()["id"])
    if repo_path is not None:
        _write_mcp_repo(repo_path, "0.1.0")
        row.server.local_repo_path = str(repo_path)
    row.status = "ready_to_publish"
    db_session.commit()
    return created.json()["id"]


def _write_mcp_repo(path, version: str):
    path.mkdir()
    (path / "package.json").write_text(
        json.dumps(
            {
                "name": "@synapse-network-ai/mcp-server",
                "version": version,
                "mcpName": "io.github.synapsenetworkai/synapse-network-mcp-server",
            }
        ),
        encoding="utf-8",
    )
    (path / "server.json").write_text(
        json.dumps(
            {
                "name": "io.github.synapsenetworkai/synapse-network-mcp-server",
                "version": version,
                "packages": [{"registryType": "npm"}],
            }
        ),
        encoding="utf-8",
    )


def test_create_release_task_and_query_defaults_to_local_runner(synced_client):
    response = _create_task(synced_client)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "requested"
    assert payload["project_key"] == "synapse-network"
    assert payload["service_key"] == "gateway"

    query = synced_client.get("/api/releases/tasks/query", params={"limit": 10})
    assert query.status_code == 200
    items = query.json()["items"]
    assert items[0]["id"] == payload["id"]
    assert items[0]["deployment_record_id"] is None


def test_get_release_task_by_id_returns_detail(synced_client):
    task = _create_task(synced_client, service_key="docs-front").json()

    response = synced_client.get(f"/api/releases/tasks/{task['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task["id"]
    assert payload["service_key"] == "docs-front"
    assert payload["deployment_record_id"] is None


def test_get_release_task_by_id_handles_missing_task(synced_client):
    response = synced_client.get("/api/releases/tasks/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Release task not found."


def test_agent_release_task_requires_local_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_DEPLOY_API_TOKEN", "")
    monkeypatch.delenv("OPS_AGENT_DEPLOY_API_TOKEN", raising=False)

    response = _create_task(synced_client, actor="codex/test-thread")

    assert response.status_code == 403
    assert "OPS_AGENT_DEPLOY_API_TOKEN" in response.json()["detail"]


def test_agent_release_task_accepts_matching_local_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_DEPLOY_API_TOKEN", "deploy-token")

    response = synced_client.post(
        "/api/releases/tasks",
        headers={"X-Growing-Agent-Deploy-Token": "deploy-token"},
        json={
            "project_key": "synapse-network",
            "project_display_name": "Synapse-Network",
            "service_key": "gateway",
            "branch_name": "main",
            "environment": "staging",
            "actor": "codex/test-thread",
        },
    )

    assert response.status_code == 200
    assert response.json()["actor"] == "codex/test-thread"


def test_mcp_remote_prod_task_is_prod_only_and_binds_release(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)

    blocked = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="staging",
        branch_name="main",
        mcp_server_release_id=release_id,
    )
    assert blocked.status_code == 400
    assert "production-only" in blocked.json()["detail"]

    response = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "mcp_remote_gcloud"
    assert payload["deployment_record_id"] is None
    assert payload["task_metadata"]["mcpServerReleaseId"] == release_id
    assert (
        payload["task_metadata"]["remoteEndpointUrl"]
        == "https://mcp.synapse-network.ai/mcp"
    )
    assert db_session.get(McpServerReleaseRow, release_id).status == "remote_prod_ready"


def test_mcp_remote_prod_task_rejects_invalid_create_shape(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)

    cases = [
        ({"project_key": "synapse-network"}, "project_key=synapse-network-mcp-server"),
        ({"service_key": "gateway"}, "service_key=remote-mcp"),
        ({"branch_name": "feature"}, "only allows branch main"),
        ({"mcp_server_release_id": 0}, "mcp_server_release_id is required"),
        ({"mcp_server_release_id": 999999}, "MCP server release not found"),
    ]
    for overrides, detail in cases:
        payload = {
            "source_type": "mcp_remote_gcloud",
            "project_key": "synapse-network-mcp-server",
            "project_display_name": "Synapse-Network-MCP-Server",
            "service_key": "remote-mcp",
            "environment": "production",
            "branch_name": "main",
            "mcp_server_release_id": release_id,
        }
        payload.update(overrides)
        response = _create_task(
            synced_client,
            **payload,
        )
        assert response.status_code == 400
        assert detail in response.json()["detail"]

    planned = synced_client.post(
        "/api/releases/mcp-servers",
        json={"package_version": "0.1.0", "release_notes": "Not ready."},
    ).json()
    planned_row = db_session.get(McpServerReleaseRow, planned["id"])
    planned_row.status = "planned"
    db_session.commit()
    response = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=planned["id"],
    )
    assert response.status_code == 400
    assert "must pass readiness" in response.json()["detail"]


def test_mcp_remote_gate_blocks_malformed_metadata_and_commit_drift(
    monkeypatch, synced_client, db_session
):
    release_id = _create_ready_mcp_release(synced_client, db_session)
    row = ReleaseTaskRow(
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        branch_name="main",
        environment="production",
        status="requested",
        metadata_json="{broken",
    )
    db_session.add(row)
    db_session.commit()

    gate = mcp_remote_tasks.gate_status(db_session, row)
    assert gate.can_deploy_production is False
    assert "mcp_server_release_id is missing" in gate.blocked_reason

    row.metadata_json = json.dumps(
        {"mcpServerReleaseId": release_id, "targetCommitSha": "old-main"}
    )
    db_session.commit()
    monkeypatch.setattr(mcp_remote_tasks, "_mcp_main_commit_sha", lambda: "new-main")

    gate = mcp_remote_tasks.gate_status(db_session, row)
    assert gate.can_deploy_production is False
    assert "target commit is no longer current main" in gate.blocked_reason

    row.environment = "staging"
    db_session.commit()
    gate = mcp_remote_tasks.gate_status(db_session, row)
    assert "production-only" in gate.blocked_reason

    row.environment = "production"
    row.branch_name = "feature"
    db_session.commit()
    gate = mcp_remote_tasks.gate_status(db_session, row)
    assert "only allows branch main" in gate.blocked_reason

    row.branch_name = "main"
    row.metadata_json = json.dumps({"mcpServerReleaseId": 999999})
    db_session.commit()
    gate = mcp_remote_tasks.gate_status(db_session, row)
    assert "release not found" in gate.blocked_reason

    row.metadata_json = json.dumps({"mcpServerReleaseId": release_id})
    db_session.commit()
    monkeypatch.setattr(mcp_remote_tasks, "_mcp_main_commit_sha", lambda: None)
    gate = mcp_remote_tasks.gate_status(db_session, row)
    assert "Unable to resolve current MCP main commit sha" in gate.blocked_reason


def test_mcp_remote_prod_task_requires_resolvable_target_commit(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: None,
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)

    response = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    )

    assert response.status_code == 400
    assert "Unable to resolve MCP main commit sha" in response.json()["detail"]


def test_mcp_remote_prod_gate_and_deploy_do_not_create_deployment_record(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)
    task = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    ).json()

    gate = synced_client.get(f"/api/releases/tasks/{task['id']}/gate-status")
    assert gate.status_code == 200
    assert gate.json()["can_deploy_production"] is True
    assert "No staging version" in gate.json()["environment_gate_summary"]

    bad = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "YES"},
    )
    assert bad.status_code == 400
    assert "DEPLOY_MCP_REMOTE_PROD" in bad.json()["detail"]

    deployed = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_MCP_REMOTE_PROD", "actor": "operator"},
    )
    assert deployed.status_code == 200
    assert deployed.json()["status"] == "deploying"
    assert deployed.json()["deployment_record_id"] is None
    assert (
        db_session.get(McpServerReleaseRow, release_id).status
        == "remote_prod_deploying"
    )

    redeploy = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_MCP_REMOTE_PROD", "actor": "operator"},
    )
    assert redeploy.status_code == 400
    assert "Only requested or failed" in redeploy.json()["detail"]


def test_mcp_remote_failed_release_can_create_retry_task(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "retry123mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)
    release = db_session.get(McpServerReleaseRow, release_id)
    release.status = "failed"
    release.failure_summary = "domain mapping failed"
    db_session.commit()

    response = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
        target_commit_sha="retry123mcp",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_commit_sha"] == "retry123mcp"
    assert payload["deployment_record_id"] is None
    release = db_session.get(McpServerReleaseRow, release_id)
    assert release.status == "remote_prod_ready"


def test_mcp_remote_failed_openai_smoke_retry_resumes_openai_only(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "retry-openai-mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)
    release = db_session.get(McpServerReleaseRow, release_id)
    release.status = "failed"
    release.failure_summary = "getaddrinfo ENOTFOUND api.openai.com"
    release.metadata_json = json.dumps({"remote_prod_deploy": {"status": "passed"}})
    release.smoke_evidence_json = json.dumps({"status": "public_probe_passed"})
    db_session.commit()

    response = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
        target_commit_sha="retry-openai-mcp",
    )

    assert response.status_code == 200
    task = response.json()
    assert task["task_metadata"]["resumeRunnerState"] == "openai_smoke_running"
    deployed = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_MCP_REMOTE_PROD", "actor": "operator"},
    )
    assert deployed.status_code == 200
    assert (
        deployed.json()["task_metadata"]["mcpReleaseStatus"] == "openai_smoke_running"
    )
    assert (
        db_session.get(McpServerReleaseRow, release_id).status == "openai_smoke_running"
    )


def test_mcp_remote_failed_deploy_retry_resumes_public_probe(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "retry-deploy-mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)
    release = db_session.get(McpServerReleaseRow, release_id)
    release.status = "failed"
    release.metadata_json = json.dumps({"remote_prod_deploy": {"status": "passed"}})
    release.smoke_evidence_json = "{broken"
    db_session.commit()

    response = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
        target_commit_sha="retry-deploy-mcp",
    )

    assert response.status_code == 200
    assert (
        response.json()["task_metadata"]["resumeRunnerState"] == "remote_prod_deployed"
    )

    release = db_session.get(McpServerReleaseRow, release_id)
    release.status = "failed"
    release.metadata_json = json.dumps(
        {"last_failed_runner_state": "remote_prod_deploying"}
    )
    release.smoke_evidence_json = "{}"
    db_session.commit()
    assert mcp_remote_tasks._retry_runner_state(release) == "remote_prod_deploying"


def test_mcp_remote_manual_completion_requires_verified_smoke(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)
    task = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    ).json()

    blocked = synced_client.patch(
        f"/api/releases/tasks/{task['id']}",
        json={"status": "completed", "operator": "operator", "note": "manual complete"},
    )
    assert blocked.status_code == 400
    assert "remote prod smoke is verified" in blocked.json()["detail"]

    release = db_session.get(McpServerReleaseRow, release_id)
    release.status = "remote_prod_verified"
    db_session.commit()
    completed = synced_client.patch(
        f"/api/releases/tasks/{task['id']}",
        json={"status": "completed", "operator": "operator", "note": "verified"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["deployment_record_id"] is None


def test_mcp_remote_failure_summary_keeps_network_root_cause():
    summary = mcp_server_runner._failure_summary(
        """
node:internal/modules/run_main:107
    triggerUncaughtException(
    ^

[TypeError: fetch failed] {
  [cause]: Error: getaddrinfo ENOTFOUND api.openai.com
      at GetAddrInfoReqWrap.onlookupall [as oncomplete] (node:dns:121:26) {
    errno: -3008,
    code: 'ENOTFOUND',
    syscall: 'getaddrinfo',
    hostname: 'api.openai.com'
  }
}

Node.js v25.9.0
""",
        fallback="openai_remote_smoke failed",
    )

    assert summary == "[cause]: Error: getaddrinfo ENOTFOUND api.openai.com"


def test_mcp_remote_runner_verifies_openai_smoke_and_completes_linked_task(
    monkeypatch, synced_client, db_session, tmp_path
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    monkeypatch.setenv("SYNAPSE_AGENT_KEY", "agt_secret")
    monkeypatch.setenv("SYNAPSE_REMOTE_MCP_AUTH_TOKEN", "remote_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "openai_secret")
    monkeypatch.setattr(mcp_server_runner, "_run_step", lambda *_args, **_kwargs: None)
    release_id = _create_ready_mcp_release(synced_client, db_session, tmp_path / "mcp")
    task = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    ).json()
    synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_MCP_REMOTE_PROD", "actor": "operator"},
    )

    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    assert (
        db_session.get(McpServerReleaseRow, release_id).status == "remote_prod_deployed"
    )
    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    assert (
        db_session.get(McpServerReleaseRow, release_id).status == "openai_smoke_running"
    )
    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )

    release = db_session.get(McpServerReleaseRow, release_id)
    assert release.status == "remote_prod_verified"
    assert json.loads(release.smoke_evidence_json)["provider"] == "openai"
    row = db_session.get(ReleaseTaskRow, task["id"])
    assert row.status == "completed"
    assert row.deployment_record_id is None


def test_mcp_remote_sync_linked_task_skips_until_verified(
    monkeypatch, synced_client, db_session
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    release_id = _create_ready_mcp_release(synced_client, db_session)
    other_release_id = _create_ready_mcp_release(synced_client, db_session)
    task = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    ).json()
    other_task = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=other_release_id,
    ).json()
    for task_id in (task["id"], other_task["id"]):
        row = db_session.get(ReleaseTaskRow, task_id)
        row.status = "deploying"
    db_session.get(ReleaseTaskRow, other_task["id"]).metadata_json = json.dumps(
        {"mcpServerReleaseId": 999999}
    )
    release = db_session.get(McpServerReleaseRow, release_id)
    db_session.commit()

    mcp_remote_tasks.sync_linked_task_for_release(db_session, release)
    assert db_session.get(ReleaseTaskRow, task["id"]).status == "deploying"

    release.status = "remote_prod_verified"
    mcp_remote_tasks.sync_linked_task_for_release(db_session, release)
    db_session.commit()
    assert db_session.get(ReleaseTaskRow, task["id"]).status == "completed"
    assert db_session.get(ReleaseTaskRow, other_task["id"]).status == "deploying"


def test_mcp_remote_byok_deploy_does_not_require_customer_token(
    monkeypatch, synced_client, db_session, tmp_path
):
    monkeypatch.setattr(
        "server.services.releases.mcp_remote_tasks._mcp_main_commit_sha",
        lambda: "abc123mcp",
    )
    monkeypatch.delenv("SYNAPSE_AGENT_KEY", raising=False)
    monkeypatch.delenv("SYNAPSE_REMOTE_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(mcp_server_runner, "_run_step", lambda *_args, **_kwargs: None)
    release_id = _create_ready_mcp_release(synced_client, db_session, tmp_path / "mcp")
    task = _create_task(
        synced_client,
        source_type="mcp_remote_gcloud",
        project_key="synapse-network-mcp-server",
        project_display_name="Synapse-Network-MCP-Server",
        service_key="remote-mcp",
        environment="production",
        branch_name="main",
        mcp_server_release_id=release_id,
    ).json()
    synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy",
        json={"confirm_phrase": "DEPLOY_MCP_REMOTE_PROD", "actor": "operator"},
    )

    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    release = db_session.get(McpServerReleaseRow, release_id)
    assert release.status == "remote_prod_deployed"
    assert release.failure_summary is None


def test_mcp_remote_openai_smoke_requires_token_and_openai_key(
    monkeypatch, synced_client, db_session, tmp_path
):
    monkeypatch.delenv("SYNAPSE_REMOTE_MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(mcp_server_runner, "_run_step", lambda *_args, **_kwargs: None)
    release_id = _create_ready_mcp_release(synced_client, db_session, tmp_path / "mcp")
    release = db_session.get(McpServerReleaseRow, release_id)
    release.status = "openai_smoke_running"
    db_session.commit()

    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    release = db_session.get(McpServerReleaseRow, release_id)
    assert release.status == "failed"
    assert "SYNAPSE_REMOTE_MCP_AUTH_TOKEN" in release.failure_summary
    assert "OPENAI_API_KEY" in release.failure_summary


def test_mcp_remote_public_probe_uses_readyz_and_mcp_unauthenticated_probe():
    steps = mcp_server_runner._steps("remote_prod_deployed")

    assert len(steps) == 1
    assert 'host="mcp.synapse-network.ai"' in steps[0].command
    assert 'ready_url="https://${host}/readyz"' in steps[0].command
    assert 'mcp_url="https://${host}/mcp"' in steps[0].command
    assert "dig +short" in steps[0].command
    assert "--resolve" in steps[0].command
    assert "https://mcp.synapse-network.ai/healthz" not in steps[0].command


def test_mcp_remote_main_commit_sha_handles_local_git_failures(monkeypatch):
    monkeypatch.setattr(mcp_remote_tasks.config, "E2E_MODE", True)
    assert mcp_remote_tasks._mcp_main_commit_sha() == "e2e-mcp-main"

    monkeypatch.setattr(mcp_remote_tasks.config, "E2E_MODE", False)
    monkeypatch.setattr(mcp_remote_tasks.shutil, "which", lambda _name: None)
    assert mcp_remote_tasks._mcp_main_commit_sha() is None

    monkeypatch.setattr(mcp_remote_tasks.shutil, "which", lambda _name: "/usr/bin/git")

    def timeout_run(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("git", 10)

    monkeypatch.setattr(mcp_remote_tasks.subprocess, "run", timeout_run)
    assert mcp_remote_tasks._mcp_main_commit_sha() is None

    class FailedResult:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(
        mcp_remote_tasks.subprocess, "run", lambda *_args, **_kwargs: FailedResult()
    )
    assert mcp_remote_tasks._mcp_main_commit_sha() is None

    class PassedResult:
        returncode = 0
        stdout = " current-main-sha \n"

    monkeypatch.setattr(
        mcp_remote_tasks.subprocess, "run", lambda *_args, **_kwargs: PassedResult()
    )
    assert mcp_remote_tasks._mcp_main_commit_sha() == "current-main-sha"


def test_staging_deploy_creates_local_runner_record(synced_client, db_session):
    task = _create_task(synced_client).json()

    response = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "operator", "note": "staging via local runner"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deploying"
    assert payload["deployment_record_id"] is not None
    record = db_session.get(DeploymentRecordRow, payload["deployment_record_id"])
    assert record.trigger_source == "local_deploy_runner"
    assert record.workflow_file == "local_deploy_runner"
    metadata = json.loads(record.metadata_json)
    assert metadata["localDeployRunner"] is True
    assert metadata["localRunnerCommand"][0:2] == [
        "bash",
        "scripts/local/deploy_synapse_staging.sh",
    ]
    assert metadata["deployScope"] == "gateway"


def test_agent_staging_deploy_requires_matching_token(monkeypatch, synced_client):
    monkeypatch.setattr("server.config.OPS_AGENT_DEPLOY_API_TOKEN", "deploy-token")
    task = _create_task(synced_client).json()

    blocked = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        json={"actor": "codex/test-thread"},
    )
    allowed = synced_client.post(
        f"/api/releases/tasks/{task['id']}/deploy-staging",
        headers={"X-Growing-Agent-Deploy-Token": "deploy-token"},
        json={"actor": "codex/test-thread"},
    )

    assert blocked.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["deployment_record_id"] is not None


def test_sync_deployment_statuses_only_summarizes_local_runner_records(
    synced_client, db_session
):
    running = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="running",
        health_status="checking",
        trigger_source="local_deploy_runner",
    )
    succeeded = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="succeeded",
        health_status="passed",
        trigger_source="local_deploy_runner",
    )
    failed = DeploymentRecordRow(
        project_key="synapse-network",
        environment="staging",
        action="deploy",
        status="failed",
        health_status="failed",
        trigger_source="local_deploy_runner",
    )
    db_session.add_all([running, succeeded, failed])
    db_session.commit()

    response = synced_client.post("/api/releases/tasks/sync-deployment-statuses")

    assert response.status_code == 200
    payload = response.json()
    assert payload["local_runner_only"] is True
    assert set(payload["running_ids"]) == {int(running.id)}
    assert set(payload["succeeded_ids"]) == {int(succeeded.id)}
    assert set(payload["failed_ids"]) == {int(failed.id)}


def test_release_task_status_patch_is_local_state_only(synced_client, db_session):
    task = _create_task(synced_client).json()

    response = synced_client.patch(
        f"/api/releases/tasks/{task['id']}",
        json={"status": "failed", "operator": "operator", "note": "manual fail"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["note"] == "manual fail"
    row = db_session.get(ReleaseTaskRow, task["id"])
    assert row.status == "failed"


def test_release_task_rejects_unknown_service(synced_client):
    response = _create_task(synced_client, service_key="nope")

    assert response.status_code == 400
    assert "service_key must be one of" in response.json()["detail"]
