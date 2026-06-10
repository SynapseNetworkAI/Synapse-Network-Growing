from server.services.growth import ai_visibility_release_unblock as release_unblock
from server.services.growth.ai_visibility_remote_mcp_metadata import (
    RemoteMcpPublicMetadataCheckOut,
)
from server.services.growth.ai_visibility_release_snapshot import build_snapshot


EXPECTED_PENDING_URLS = {
    "https://www.synapse-network.ai/mcp-server-for-paid-api-calls",
    "https://www.synapse-network.ai/chatgpt-mcp-app-api-payments",
}


def test_release_unblock_plan_exposes_verified_jsonld_publication_surfaces():
    payload = release_unblock.build_release_unblock_plan(
        target_commit=release_unblock.DEFAULT_TARGET_COMMIT,
        actor="codex/test-ai-visibility",
    )

    assert payload["source_pr"]["number"] == 223
    assert payload["source_pr"]["state"] == "MERGED"
    assert payload["source_pr"]["merge_commit"] == (
        "b0fab9bcdfaed5715b62e0aa8dbc21136d983055"
    )
    assert payload["pending_source_prs"] == []
    merged_jsonld_pr = next(
        item for item in payload["source_prs"] if item["number"] == 216
    )
    assert "JSON-LD" in merged_jsonld_pr["purpose"]
    assert payload["pending_publication_gaps"] == []
    assert {item["url"] for item in payload["verified_publication_surfaces"]} == (
        EXPECTED_PENDING_URLS
    )
    assert all(
        item["current_status"] == item["expected_after_merge"] == 200
        for item in payload["verified_publication_surfaces"]
    )
    assert all(item["surface"] == "www-jsonld" for item in payload["verified_publication_surfaces"])
    assert any(
        "Production source-host feed terms agent402" in blocker
        for blocker in payload["known_blockers"]
    )
    validation_commands = "\n".join(
        command
        for group in payload["command_groups"]
        if group["key"] in {"staging_validation", "production_validation"}
        for command in group["commands"]
    )
    assert "https://www.synapse-network.ai/mcp-server-for-paid-api-calls" in (
        validation_commands
    )
    assert "https://www.synapse-network.ai/chatgpt-mcp-app-api-payments" in (
        validation_commands
    )
    assert "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp" in (
        validation_commands
    )
    assert "agent402|mcpay.fun|Cashfree" in validation_commands
    assert "application/ld\\+json" in validation_commands
    assert "FAQPage" in validation_commands
    assert "SoftwareApplication" in validation_commands
    assert any("JSON-LD FAQPage" in item for item in payload["success_criteria"])
    indexnow_group = next(
        group
        for group in payload["command_groups"]
        if group["key"] == "post_publish_indexnow_submission"
    )
    indexnow_commands = "\n".join(indexnow_group["commands"])
    assert "submit_indexnow_ai_visibility.mjs" in indexnow_commands
    assert "--execute" in indexnow_commands
    assert "2026-06-05-after-prod-indexnow.json" in indexnow_commands
    assert "www.synapse-network.ai" in indexnow_commands
    assert "docs.synapse-network.ai" in indexnow_commands
    assert any("IndexNow submission" in item for item in payload["success_criteria"])


def test_release_snapshot_preserves_pending_publication_gaps(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("XAI_API_KEY", "test-xai")
    monkeypatch.setattr(
        "server.services.growth.ai_visibility_release_snapshot._gcloud_project_check",
        lambda project_id: {
            "project_id": project_id,
            "ok": True,
            "status": "ok",
            "summary": project_id,
        },
    )
    monkeypatch.setattr(
        "server.services.growth.ai_visibility_release_snapshot.ai_visibility_live_readiness",
        lambda **_: type(
            "Ready",
            (),
            {
                "model_dump": lambda self, mode: {
                    "status": "ready",
                    "ready_count": 1,
                    "blocked_count": 0,
                    "items": [],
                }
            },
        )(),
    )
    monkeypatch.setattr(
        "server.services.growth.ai_visibility_release_snapshot.remote_mcp_public_metadata_check",
        lambda: RemoteMcpPublicMetadataCheckOut(
            url="https://mcp.synapse-network.ai/.well-known/glama.json",
            ok=True,
            status="ready",
            http_status=200,
            missing_fields=[],
            summary="Remote MCP public metadata has complete AI directory fields.",
        ),
    )

    payload = build_snapshot(
        target_commit=release_unblock.DEFAULT_TARGET_COMMIT,
        actor="codex/test-ai-visibility",
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-pending-publication",
    )

    assert payload["pending_source_prs"] == []
    assert payload["pending_publication_gaps"] == []
    assert {item["url"] for item in payload["verified_publication_surfaces"]} == (
        EXPECTED_PENDING_URLS
    )
