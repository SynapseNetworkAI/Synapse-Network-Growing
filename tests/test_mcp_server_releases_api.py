import json

from server.database_growth import GrowthDiscoveryListingRow
from server.services.releases import mcp_server_runner
from server.services.releases.mcp_server_models import McpServerReleaseRow


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
    }

    listed = synced_client.get("/api/releases/mcp-servers?search=mcp-server")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    events = synced_client.get(f"/api/releases/mcp-servers/{created['id']}/events")
    assert events.status_code == 200
    assert [event["action"] for event in events.json()] == ["initialize_mcp_release"]

    assert synced_client.get("/api/releases/mcp-servers/999").status_code == 404


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
