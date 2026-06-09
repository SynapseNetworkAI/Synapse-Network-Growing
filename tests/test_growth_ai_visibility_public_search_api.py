def test_public_web_search_diagnostic_records_do_not_cover_target_platforms(
    synced_client,
):
    response = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "MCP server for paid API calls Synapse",
            "platform": "public_web_search",
            "answer_summary": "Public web search did not return Synapse.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "competitor_mentions": ["MCPay", "Hud Remote MCP Server"],
            "missing_facts": ["Public web search returned no official Synapse result."],
            "next_action": "Refresh IndexNow and rerun public web search.",
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-19-public-web-search",
            "metadata": {"mode": "public_web_search_snapshot"},
        },
    )

    assert response.status_code == 201
    comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons"
        "?feed_key=mcp_paid_api_discovery"
        "&run_group=2026-06-19-public-web-search"
    ).json()["items"][0]
    assert comparison["external_platforms"] == ["public_web_search"]
    assert comparison["external_checks_count"] == 1
    assert comparison["mentioned_count"] == 0
    assert comparison["cited_count"] == 0
    assert set(comparison["missing_platforms"]) == {
        "chatgpt",
        "claude",
        "grok",
        "gemini",
    }
    assert "MCPay" in comparison["top_competitors"]

    scorecard = synced_client.get("/api/growth/ai-visibility/feed-scorecard").json()
    mcp_score = next(
        item
        for item in scorecard["items"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    assert "public_web_search" not in mcp_score["covered_platforms"]
    assert set(mcp_score["missing_platforms"]) == {
        "chatgpt",
        "claude",
        "grok",
        "gemini",
    }
    assert "Refresh IndexNow and rerun public web search." in mcp_score["next_actions"]


def test_goal_audit_keeps_target_platform_evidence_after_public_search_diagnostic(
    synced_client,
):
    for platform in ("chatgpt", "claude", "grok", "gemini"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "SynapseNetworkAI Remote MCP paid API calls",
                "platform": platform,
                "answer_summary": f"{platform} cited official Synapse docs.",
                "synapse_mentioned": True,
                "synapse_cited": True,
                "cited_urls": ["https://docs.synapse-network.ai/mcp/paid-api-calls"],
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-19-target-platforms",
                "result_rank": 1,
            },
        )
        assert response.status_code == 201

    diagnostic = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "site:mcpfind.org Synapse Network MCP Server",
            "platform": "public_web_search",
            "answer_summary": "Public web search did not return a Synapse MCPFind listing.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "competitor_mentions": ["MCPFind"],
            "missing_facts": ["No MCPFind listing returned."],
            "next_action": "Submit MCPFind and rerun public web search.",
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-19-mcpfind-public-search",
            "metadata": {
                "mode": "public_web_search_snapshot",
                "source_hosts": ["mcpfind.org"],
            },
        },
    )
    assert diagnostic.status_code == 201

    goal_audit = synced_client.get("/api/growth/ai-visibility/goal-audit")
    assert goal_audit.status_code == 200
    requirement_by_key = {
        item["key"]: item for item in goal_audit.json()["requirements"]
    }
    external = requirement_by_key["external_search_evidence"]
    assert external["status"] == "completed"
    for platform in ("chatgpt", "claude", "grok", "gemini"):
        assert platform in external["evidence"]
