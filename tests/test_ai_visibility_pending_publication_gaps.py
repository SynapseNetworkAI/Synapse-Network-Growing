from server.services.growth import ai_visibility_release_unblock as release_unblock
from server.services.growth.ai_visibility_release_snapshot import build_snapshot


EXPECTED_PENDING_URLS = {
    "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
    "https://www.synapse-network.ai/mcp-server-for-paid-api-calls",
    "https://www.synapse-network.ai/chatgpt-mcp-app-api-payments",
}


def test_release_unblock_plan_exposes_pending_pr_and_publication_gaps():
    payload = release_unblock.build_release_unblock_plan(
        target_commit=release_unblock.DEFAULT_TARGET_COMMIT,
        actor="codex/test-ai-visibility",
    )

    assert payload["pending_source_prs"][0]["number"] == 215
    assert payload["pending_source_prs"][0]["state"] == "OPEN"
    assert {item["url"] for item in payload["pending_publication_gaps"]} == (
        EXPECTED_PENDING_URLS
    )
    assert all(
        item["expected_after_merge"] == 200
        for item in payload["pending_publication_gaps"]
    )
    assert any("PR #215" in blocker for blocker in payload["known_blockers"])


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

    payload = build_snapshot(
        target_commit=release_unblock.DEFAULT_TARGET_COMMIT,
        actor="codex/test-ai-visibility",
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-pending-publication",
    )

    assert payload["pending_source_prs"][0]["number"] == 215
    assert {item["url"] for item in payload["pending_publication_gaps"]} == (
        EXPECTED_PENDING_URLS
    )
    assert any("PR #215" in blocker for blocker in payload["blockers"])
