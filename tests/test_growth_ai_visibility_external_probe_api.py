import json


def test_growth_ai_visibility_external_probe_gate_partial_ready(
    monkeypatch,
    synced_client,
):
    from scripts.growth.record_ai_visibility_probe import ProbeRecord

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-secret")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GENIMI_API_KEY", raising=False)

    def fake_validate_feed(*, feed_key: str, run_group: str):
        return [
            ProbeRecord(
                query="Remote MCP live readiness",
                platform="mcp_live_validation",
                feed_key=feed_key,
                run_group=run_group,
                answer_summary="Live feed validation passed.",
                synapse_mentioned=True,
                synapse_cited=True,
                cited_urls=["https://www.synapse-network.ai/"],
            )
        ]

    monkeypatch.setattr(
        "server.services.growth.ai_visibility_live_readiness."
        "feed_validation.validate_feed",
        fake_validate_feed,
    )

    response = synced_client.get(
        "/api/growth/ai-visibility/external-probe-gate"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-05-external"
    )

    assert response.status_code == 200
    payload = response.json()
    rendered = json.dumps(payload)
    assert payload["status"] == "ready_for_partial_external_probes"
    assert payload["ready_to_execute"] is False
    assert payload["partial_ready_to_execute"] is True
    assert payload["manual_ready_to_execute"] is True
    assert payload["feed_ready"] is True
    assert payload["api_keys_ready"] is False
    assert payload["ready_platforms"] == ["chatgpt", "claude"]
    assert payload["missing_platforms"] == ["grok", "gemini"]
    assert "--platforms chatgpt,claude" in payload["partial_api_readiness_command"]
    assert "--platforms chatgpt,claude" in payload["partial_api_execute_command"]
    assert "--platforms chatgpt,claude,grok,gemini" in payload["api_readiness_command"]
    assert "--platforms chatgpt,claude,grok,gemini" in payload["manual_probe_template_command"]
    assert "grok missing XAI_API_KEY." in payload["blockers"]
    assert "gemini missing GEMINI_API_KEY." in payload["blockers"]
    assert "sk-test-openai-secret" not in rendered
    assert "sk-test-anthropic-secret" not in rendered


def test_growth_ai_visibility_external_probe_gate_ready_redacts_keys(
    monkeypatch,
    synced_client,
):
    from scripts.growth.record_ai_visibility_probe import ProbeRecord

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-secret")
    monkeypatch.setenv("XAI_API_KEY", "xai-test-secret")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GENIMI_API_KEY", "gemini-test-secret")

    def fake_validate_feed(*, feed_key: str, run_group: str):
        return [
            ProbeRecord(
                query="Remote MCP live readiness",
                platform="mcp_live_validation",
                feed_key=feed_key,
                run_group=run_group,
                answer_summary="Live feed validation passed.",
                synapse_mentioned=True,
                synapse_cited=True,
                cited_urls=["https://www.synapse-network.ai/"],
            )
        ]

    monkeypatch.setattr(
        "server.services.growth.ai_visibility_live_readiness."
        "feed_validation.validate_feed",
        fake_validate_feed,
    )

    response = synced_client.get(
        "/api/growth/ai-visibility/external-probe-gate"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-05-external"
    )

    assert response.status_code == 200
    payload = response.json()
    rendered = json.dumps(payload)
    assert payload["status"] == "ready_to_execute_external_probes"
    assert payload["ready_to_execute"] is True
    assert payload["partial_ready_to_execute"] is True
    assert payload["manual_ready_to_execute"] is True
    assert payload["feed_ready"] is True
    assert payload["api_keys_ready"] is True
    assert payload["ready_platforms"] == ["chatgpt", "claude", "grok", "gemini"]
    assert payload["missing_platforms"] == []
    assert all(item["configured"] for item in payload["provider_readiness"])
    assert (
        "generate_ai_visibility_probe_template.py"
        in payload["manual_probe_template_command"]
    )
    assert "sk-test-openai-secret" not in rendered
    assert "sk-test-anthropic-secret" not in rendered
    assert "xai-test-secret" not in rendered
    assert "gemini-test-secret" not in rendered


def test_growth_ai_visibility_release_snapshot_api(monkeypatch, synced_client):
    def fake_snapshot(**kwargs):
        return {
            "module_key": "ai_visibility",
            "snapshot_type": "release_blocker",
            "generated_at": "2026-06-05T00:00:00Z",
            "feed_key": kwargs["feed_key"],
            "run_group": kwargs["run_group"],
            "target_commit_sha": kwargs["target_commit"],
            "official_homepage": "https://www.synapse-network.ai/",
            "status": "blocked",
            "release_plan_status": "blocked_until_gcloud_auth",
            "deploy_readiness_status": "ready_for_release_runner_after_gcloud_auth",
            "confirmed_facts": [
                "Official homepage canonical is https://www.synapse-network.ai/.",
            ],
            "deployment_gaps": [],
            "live_readiness": {"status": "blocked"},
            "gcloud": {"production": {"ok": False}},
            "external_probe_keys": {"chatgpt": {"configured": False}},
            "blockers": ["GCloud auth fails non-interactively."],
            "next_actions": ["Run gcloud auth login."],
        }

    monkeypatch.setattr(
        "server.routers.growth_ai_visibility.ai_visibility_release_snapshot.build_snapshot",
        fake_snapshot,
    )

    response = synced_client.get(
        "/api/growth/ai-visibility/release-snapshot"
        "?feed_key=mcp_paid_api_discovery"
        "&run_group=2026-06-05-release-snapshot"
        "&target_commit=d8b5371e11fea2d962dcc656b9b8d08d0c1379d9"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["official_homepage"] == "https://www.synapse-network.ai/"
    assert payload["status"] == "blocked"
    assert payload["feed_key"] == "mcp_paid_api_discovery"
    assert payload["run_group"] == "2026-06-05-release-snapshot"


def test_ai_visibility_weekly_report_uses_latest_validation_surface(synced_client):
    stale_blocker = "Synthetic stale redirect blocker should disappear."
    first = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "Brand feed validation",
            "platform": "www_live_validation",
            "answer_summary": "Bare domain did not redirect.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "missing_facts": [stale_blocker],
            "next_action": "Fix synthetic redirect blocker.",
            "feed_key": "brand_disambiguation_www",
            "run_group": "2026-06-04-live-predeploy",
        },
    )
    assert first.status_code == 201
    blocked = synced_client.get("/api/growth/ai-visibility/weekly-report")
    assert stale_blocker in blocked.json()["blockers"]

    second = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "Brand feed validation",
            "platform": "www_live_validation",
            "answer_summary": "Bare domain redirects and public assets are live.",
            "synapse_mentioned": True,
            "synapse_cited": True,
            "cited_urls": ["https://www.synapse-network.ai/"],
            "feed_key": "brand_disambiguation_www",
            "run_group": "2026-06-05-live-refresh",
        },
    )
    assert second.status_code == 201
    refreshed = synced_client.get("/api/growth/ai-visibility/weekly-report")
    assert stale_blocker not in refreshed.json()["blockers"]
    next_cycle = synced_client.get("/api/growth/ai-visibility/next-cycle")
    assert stale_blocker not in next_cycle.json()["blockers"]


def test_ai_visibility_weekly_report_supersedes_old_validation_run_group(
    synced_client,
):
    stale_blocker = (
        "Production docs page "
        "https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet."
    )
    first = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "Remote MCP docs validation",
            "platform": "docs_live_validation",
            "answer_summary": "MCP docs were not published.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "missing_facts": [stale_blocker],
            "next_action": "Publish MCP paid API docs.",
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-04-live-predeploy",
        },
    )
    assert first.status_code == 201
    blocked = synced_client.get("/api/growth/ai-visibility/weekly-report")
    assert stale_blocker in blocked.json()["blockers"]

    second = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "Remote MCP live readiness",
            "platform": "mcp_live_validation",
            "answer_summary": "Homepage, docs, llms.txt, and MCP readiness are live.",
            "synapse_mentioned": True,
            "synapse_cited": True,
            "cited_urls": [
                "https://www.synapse-network.ai/",
                "https://docs.synapse-network.ai/mcp/paid-api-calls",
                "https://mcp.synapse-network.ai/mcp",
            ],
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-05-goal-continuation",
        },
    )
    assert second.status_code == 201

    refreshed = synced_client.get("/api/growth/ai-visibility/weekly-report")
    assert stale_blocker not in refreshed.json()["blockers"]


def test_ai_visibility_goal_audit_requires_latest_feed_platforms(synced_client):
    historical = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "AI agent payment API",
            "platform": "claude",
            "answer_summary": "Historical Claude evidence mentioned Synapse.",
            "synapse_mentioned": True,
            "synapse_cited": False,
            "feed_key": "agent_payment_category_pages",
            "run_group": "2026-06-04-category",
        },
    )
    assert historical.status_code == 201
    latest = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "MCP server for paid API calls",
            "platform": "chatgpt",
            "answer_summary": "Current ChatGPT result did not mention Synapse.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "missing_facts": ["Synapse Network was not mentioned."],
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-05-after-mcp-registry",
        },
    )
    assert latest.status_code == 201

    report = synced_client.get("/api/growth/ai-visibility/weekly-report").json()
    assert report["covered_platforms"] == ["chatgpt", "claude"]
    latest_report = next(
        item
        for item in report["feed_reports"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    assert latest_report["missing_platforms"] == ["claude", "grok"]

    audit = synced_client.get("/api/growth/ai-visibility/goal-audit").json()
    external = next(
        item
        for item in audit["requirements"]
        if item["key"] == "external_search_evidence"
    )
    assert "claude" in external["blocker"]
    assert "grok" in external["blocker"]
