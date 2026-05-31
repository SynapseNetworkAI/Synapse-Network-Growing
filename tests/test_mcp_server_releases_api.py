import json
import subprocess

from server.database_growth import GrowthDiscoveryListingRow
from server.services.releases import mcp_server_runner
from server.services.releases.mcp_server_helpers import _json_load
from server.services.releases.mcp_server_models import McpServerReleaseRow, McpServerRow


def _create_release(client, version: str = "0.1.0"):
    response = client.post(
        "/api/releases/mcp-servers",
        json={"package_version": version, "release_notes": "Initial MCP release."},
    )
    assert response.status_code == 201
    return response.json()


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


def _point_release_server_to_repo(db_session, release_id: int, repo_path):
    row = db_session.query(McpServerReleaseRow).filter_by(id=release_id).one()
    server = db_session.query(McpServerRow).filter_by(id=row.mcp_server_id).one()
    server.local_repo_path = str(repo_path)
    db_session.commit()


def test_mcp_server_release_create_list_filter_and_events(synced_client):
    created = _create_release(synced_client)

    assert created["server_name"] == "SynapseNetwork MCP Server"
    assert created["package_name"] == "@synapse-network-ai/mcp-server"
    assert created["package_registry"] == "npm"
    assert (
        created["registry_name"]
        == "io.github.synapsenetworkai/synapse-network-mcp-server"
    )
    assert created["install_command"] == "npx -y @synapse-network-ai/mcp-server"
    assert created["status"] == "planned"
    assert {surface["surface_key"] for surface in created["surfaces"]} >= {
        "official_mcp_registry",
        "smithery",
        "glama",
        "openai_remote_mcp",
    }
    openai = next(
        item
        for item in created["surfaces"]
        if item["surface_key"] == "openai_remote_mcp"
    )
    assert openai["status"] == "blocked_requires_remote_mcp"

    listed = synced_client.get("/api/releases/mcp-servers?search=mcp-server")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    events = synced_client.get(f"/api/releases/mcp-servers/{created['id']}/events")
    assert events.status_code == 200
    assert [event["action"] for event in events.json()] == ["initialize_mcp_release"]

    assert synced_client.get("/api/releases/mcp-servers/999").status_code == 404


def test_mcp_server_release_fail_closed_api_boundaries(synced_client):
    invalid = synced_client.post(
        "/api/releases/mcp-servers", json={"package_version": "latest"}
    )
    assert invalid.status_code == 400

    created = _create_release(synced_client)
    duplicate = _create_release(synced_client)
    assert duplicate["id"] == created["id"]

    assert (
        synced_client.get(
            f"/api/releases/mcp-servers/{created['id']}/events"
        ).status_code
        == 200
    )
    assert synced_client.get("/api/releases/mcp-servers/999/events").status_code == 404

    page = synced_client.get(
        "/api/releases/mcp-servers?status=planned&page=0&page_size=0"
    )
    assert page.status_code == 200
    assert page.json()["page"] == 1
    assert page.json()["page_size"] == 1

    publish = synced_client.post(
        f"/api/releases/mcp-servers/{created['id']}/publish-npm",
        json={"actor": "operator", "confirm_phrase": "PUBLISH_MCP_0.1.0"},
    )
    assert publish.status_code == 400
    assert "readiness" in publish.json()["detail"]

    registry = synced_client.post(
        f"/api/releases/mcp-servers/{created['id']}/submit-registry",
        json={"actor": "operator"},
    )
    assert registry.status_code == 400
    assert "published" in registry.json()["detail"]

    smoke = synced_client.post(
        f"/api/releases/mcp-servers/{created['id']}/prod-smoke",
        json={"actor": "operator"},
    )
    assert smoke.status_code == 400
    assert "Registry" in smoke.json()["detail"]

    complete = synced_client.post(
        f"/api/releases/mcp-servers/{created['id']}/complete",
        json={"actor": "operator"},
    )
    assert complete.status_code == 400
    assert "prod smoke" in complete.json()["detail"]

    missing_complete = synced_client.post(
        "/api/releases/mcp-servers/999/complete", json={"actor": "operator"}
    )
    assert missing_complete.status_code == 404

    invalid_surface = synced_client.patch(
        f"/api/releases/mcp-servers/{created['id']}/surfaces/smithery",
        json={"status": "maybe"},
    )
    assert invalid_surface.status_code == 400

    missing_surface = synced_client.patch(
        f"/api/releases/mcp-servers/{created['id']}/surfaces/missing",
        json={"status": "listed"},
    )
    assert missing_surface.status_code == 404

    missing_release_surface = synced_client.patch(
        "/api/releases/mcp-servers/999/surfaces/smithery",
        json={"status": "listed"},
    )
    assert missing_release_surface.status_code == 404

    assert _json_load(None) == {}
    assert _json_load("{") == {}
    assert _json_load("[]") == {}


def test_mcp_server_catalog_lists_multiple_repos_and_surface_catalog(synced_client):
    surfaces = synced_client.get("/api/releases/mcp-surfaces")
    assert surfaces.status_code == 200
    surface_keys = {item["surface_key"] for item in surfaces.json()}
    assert {
        "official_mcp_registry",
        "openai_remote_mcp",
        "claude_remote_mcp",
    } <= surface_keys

    created_server = synced_client.post(
        "/api/releases/mcp-servers/catalog",
        json={
            "server_key": "synapse-remote-mcp-demo",
            "server_name": "Synapse Remote MCP Demo",
            "repo_full_name": "SynapseNetworkAI/Synapse-Remote-MCP-Demo",
            "repo_url": "https://github.com/SynapseNetworkAI/Synapse-Remote-MCP-Demo",
            "package_name": "@synapse-network-ai/remote-mcp-demo",
            "registry_name": "io.github.synapsenetworkai/synapse-remote-mcp-demo",
            "transport_kind": "remote_http",
            "remote_endpoint_url": "https://mcp.synapse-network.ai/mcp",
            "install_command": "npx -y @synapse-network-ai/remote-mcp-demo",
            "tools": ["discover_services"],
        },
    )
    assert created_server.status_code == 201

    release = synced_client.post(
        f"/api/releases/mcp-servers/catalog/{created_server.json()['id']}/releases",
        json={"package_version": "0.3.0", "release_notes": "Remote MCP preview."},
    )
    assert release.status_code == 201
    ai_surfaces = [
        surface
        for surface in release.json()["surfaces"]
        if surface["category"] == "llm_platform"
    ]
    assert {surface["status"] for surface in ai_surfaces} == {"candidate"}

    matrix = synced_client.get("/api/releases/mcp-servers/catalog?search=remote")
    assert matrix.status_code == 200
    assert matrix.json()["total"] == 1
    assert matrix.json()["items"][0]["latest_release"]["package_version"] == "0.3.0"


def test_mcp_surface_config_and_readiness_fail_closed(synced_client, monkeypatch):
    monkeypatch.delenv("NODE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("NPM_TOKEN", raising=False)

    created = _create_release(synced_client)
    server_id = created["mcp_server_id"]

    config = synced_client.get("/api/releases/mcp-surfaces/npm_registry/config")
    assert config.status_code == 200
    assert config.json()["credential_ref"] == "env:NODE_AUTH_TOKEN|NPM_TOKEN"
    assert config.json()["required_env_vars"] == ["NODE_AUTH_TOKEN|NPM_TOKEN"]

    verified = synced_client.post("/api/releases/mcp-surfaces/npm_registry/config/verify")
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "not_configured"
    assert "NODE_AUTH_TOKEN|NPM_TOKEN" in verified.json()["missing_env_vars"]

    readiness = synced_client.get(
        f"/api/releases/mcp-servers/{server_id}/submission-readiness"
    )
    assert readiness.status_code == 200
    npm = next(
        item
        for item in readiness.json()["items"]
        if item["surface_key"] == "npm_registry"
    )
    assert npm["readiness_status"] == "not_configured"

    submit = synced_client.post(
        f"/api/releases/mcp-servers/{created['id']}/submit-surface",
        json={"surface_key": "smithery", "actor": "operator"},
    )
    assert submit.status_code == 400
    assert "not verified" in submit.json()["detail"]


def test_remote_mcp_surface_config_can_be_submit_eligible(
    synced_client, db_session
):
    created_server = synced_client.post(
        "/api/releases/mcp-servers/catalog",
        json={
            "server_key": "remote-mcp-submit-ready",
            "server_name": "Remote MCP Submit Ready",
            "repo_full_name": "SynapseNetworkAI/Remote-MCP-Submit-Ready",
            "repo_url": "https://github.com/SynapseNetworkAI/Remote-MCP-Submit-Ready",
            "package_name": "@synapse-network-ai/remote-submit-ready",
            "registry_name": "io.github.synapsenetworkai/remote-submit-ready",
            "transport_kind": "remote_http",
            "remote_endpoint_url": "https://mcp.synapse-network.ai/mcp",
            "install_command": "npx -y @synapse-network-ai/remote-submit-ready",
            "tools": ["tools/list"],
        },
    )
    assert created_server.status_code == 201
    server_id = created_server.json()["id"]
    release = synced_client.post(
        f"/api/releases/mcp-servers/catalog/{server_id}/releases",
        json={"package_version": "0.4.0", "release_notes": "Remote platform submit."},
    )
    assert release.status_code == 201

    patched = synced_client.patch(
        "/api/releases/mcp-surfaces/openai_remote_mcp/config",
        json={
            "submission_mode": "readonly",
            "auth_mode": "none",
            "credential_ref": "",
            "required_env_vars": [],
        },
    )
    assert patched.status_code == 200
    verified = synced_client.post(
        "/api/releases/mcp-surfaces/openai_remote_mcp/config/verify"
    )
    assert verified.status_code == 200
    assert verified.json()["verification_status"] == "verified"

    readiness = synced_client.get(
        f"/api/releases/mcp-servers/{server_id}/submission-readiness"
    )
    assert readiness.status_code == 200
    openai = next(
        item
        for item in readiness.json()["items"]
        if item["surface_key"] == "openai_remote_mcp"
    )
    assert openai["readiness_status"] == "submit_eligible"

    submitted = synced_client.post(
        f"/api/releases/mcp-servers/{release.json()['id']}/submit-surface",
        json={"surface_key": "openai_remote_mcp", "actor": "operator"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "under_review"

    live_check = synced_client.post(
        f"/api/releases/mcp-servers/{release.json()['id']}/surface-live-check",
        json={"surface_key": "openai_remote_mcp", "actor": "operator"},
    )
    assert live_check.status_code == 200
    assert live_check.json()["status"] == "pass"

    db_session.expire_all()


def test_mcp_server_release_flow_and_growth_listing_sync(
    synced_client, db_session, tmp_path, monkeypatch
):
    _write_mcp_repo(tmp_path / "mcp", "0.1.0")
    monkeypatch.setattr(mcp_server_runner, "MCP_REPO", tmp_path / "mcp")
    monkeypatch.setattr(mcp_server_runner, "_run_step", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("NODE_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("NPM_TOKEN", raising=False)
    monkeypatch.delenv("SYNAPSE_AGENT_KEY", raising=False)

    created = _create_release(synced_client)
    release_id = created["id"]
    _point_release_server_to_repo(db_session, release_id, tmp_path / "mcp")

    readiness = synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/readiness",
        json={"actor": "operator"},
    )
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "readiness_running"

    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    ready = synced_client.get(f"/api/releases/mcp-servers/{release_id}").json()
    assert ready["status"] == "ready_to_publish"

    bad_publish = synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/publish-npm",
        json={"actor": "operator", "confirm_phrase": "wrong"},
    )
    assert bad_publish.status_code == 400

    publish = synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/publish-npm",
        json={"actor": "operator", "confirm_phrase": "PUBLISH_MCP_0.1.0"},
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "npm_publishing"

    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    failed = db_session.query(McpServerReleaseRow).filter_by(id=release_id).one()
    assert failed.status == "failed"
    assert "NODE_AUTH_TOKEN" in failed.failure_summary

    failed.status = "ready_to_publish"
    failed.failure_summary = None
    db_session.commit()
    monkeypatch.setenv("NODE_AUTH_TOKEN", "npm-token")
    synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/publish-npm",
        json={"actor": "operator", "confirm_phrase": "PUBLISH_MCP_0.1.0"},
    )
    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    npm_done = synced_client.get(f"/api/releases/mcp-servers/{release_id}").json()
    assert npm_done["status"] == "npm_published"
    assert (
        npm_done["package_url"]
        == "https://www.npmjs.com/package/@synapse-network-ai/mcp-server/v/0.1.0"
    )

    registry = synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/submit-registry",
        json={"actor": "operator"},
    )
    assert registry.status_code == 200
    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    registry_done = synced_client.get(f"/api/releases/mcp-servers/{release_id}").json()
    assert registry_done["status"] == "registry_listed"
    official = next(
        item
        for item in registry_done["surfaces"]
        if item["surface_key"] == "official_mcp_registry"
    )
    assert official["status"] == "listed"
    assert registry_done["registry_url"]

    listing = (
        db_session.query(GrowthDiscoveryListingRow)
        .filter_by(surface="official_mcp_registry")
        .one()
    )
    assert listing.package_name == "@synapse-network-ai/mcp-server"
    assert listing.status == "listed"

    smoke = synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/prod-smoke",
        json={"actor": "operator"},
    )
    assert smoke.status_code == 200
    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    failed_smoke = db_session.query(McpServerReleaseRow).filter_by(id=release_id).one()
    assert failed_smoke.status == "failed"
    assert "SYNAPSE_AGENT_KEY" in failed_smoke.failure_summary

    failed_smoke.status = "registry_listed"
    failed_smoke.failure_summary = None
    db_session.commit()
    monkeypatch.setenv("SYNAPSE_AGENT_KEY", "agt_test")
    synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/prod-smoke",
        json={"actor": "operator"},
    )
    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    smoke_done = synced_client.get(f"/api/releases/mcp-servers/{release_id}").json()
    assert smoke_done["status"] == "directories_pending"
    assert smoke_done["smoke_evidence"]["status"] == "passed"

    completed = synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/complete",
        json={"actor": "operator"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_mcp_runner_records_step_failure(
    synced_client, db_session, tmp_path, monkeypatch
):
    _write_mcp_repo(tmp_path / "mcp", "0.1.0")
    monkeypatch.setattr(mcp_server_runner, "MCP_REPO", tmp_path / "mcp")

    def failing_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            ["npm"], 1, stdout="first line", stderr="readiness failed\nlast line"
        )

    monkeypatch.setattr(mcp_server_runner.subprocess, "run", failing_run)

    created = _create_release(synced_client)
    release_id = created["id"]
    _point_release_server_to_repo(db_session, release_id, tmp_path / "mcp")
    synced_client.post(
        f"/api/releases/mcp-servers/{release_id}/readiness",
        json={"actor": "operator"},
    )

    assert (
        mcp_server_runner.process_mcp_server_release(db_session, release_id=release_id)
        == 1
    )
    row = db_session.query(McpServerReleaseRow).filter_by(id=release_id).one()
    assert row.status == "failed"
    assert row.failure_summary == "last line"

    events = synced_client.get(f"/api/releases/mcp-servers/{release_id}/events").json()
    assert "runner_step_started" in {event["action"] for event in events}
    assert "runner_step_finished" in {event["action"] for event in events}
    assert "runner_failed" in {event["action"] for event in events}


def test_mcp_runner_manifest_failures(synced_client, db_session, tmp_path, monkeypatch):
    _write_mcp_repo(tmp_path / "mcp", "0.2.0")
    monkeypatch.setattr(mcp_server_runner, "MCP_REPO", tmp_path / "mcp")
    created = _create_release(synced_client, version="0.1.0")
    _point_release_server_to_repo(db_session, created["id"], tmp_path / "mcp")

    synced_client.post(
        f"/api/releases/mcp-servers/{created['id']}/readiness",
        json={"actor": "operator"},
    )

    assert (
        mcp_server_runner.process_mcp_server_release(
            db_session, release_id=created["id"]
        )
        == 1
    )
    row = db_session.query(McpServerReleaseRow).filter_by(id=created["id"]).one()
    assert row.status == "failed"
    assert "manifest_version_mismatch" in row.failure_summary


def test_mcp_server_status_sync_projects_running_states(synced_client, db_session):
    versions = ["0.1.1", "0.1.2", "0.1.3", "0.1.4"]
    statuses = [
        "readiness_running",
        "npm_publishing",
        "registry_submitting",
        "prod_smoke_running",
    ]
    ids: list[int] = []
    for version, status in zip(versions, statuses, strict=True):
        created = _create_release(synced_client, version=version)
        row = db_session.query(McpServerReleaseRow).filter_by(id=created["id"]).one()
        row.status = status
        ids.append(int(row.id))
    db_session.commit()

    sync = synced_client.post("/api/releases/mcp-servers/sync-statuses?max_records=20")

    assert sync.status_code == 200
    body = sync.json()
    assert body["processed_count"] == 4
    assert body["ready_ids"] == [ids[0]]
    assert body["package_published_ids"] == [ids[1]]
    assert body["registry_listed_ids"] == [ids[2]]
    assert body["smoke_passed_ids"] == [ids[3]]


def test_mcp_server_surface_patch_and_sync_projection(synced_client):
    created = _create_release(synced_client)

    patched = synced_client.patch(
        f"/api/releases/mcp-servers/{created['id']}/surfaces/smithery",
        json={
            "status": "listed",
            "listing_url": "https://smithery.ai/server/synapse-network",
            "evidence": {"source": "manual"},
        },
    )

    assert patched.status_code == 200
    assert patched.json()["status"] == "listed"
    assert patched.json()["listing_url"] == "https://smithery.ai/server/synapse-network"

    sync = synced_client.post("/api/releases/mcp-servers/sync-statuses")
    assert sync.status_code == 200
    assert sync.json()["processed_count"] == 0
