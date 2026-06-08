def test_ai_visibility_comparison_surfaces_source_hosts(synced_client):
    for platform, cited, hosts in (
        ("chatgpt", False, ["docs.mcpay.tech", "mcpservers.org"]),
        ("claude", True, ["synapse-network.ai"]),
    ):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": platform,
                "answer_summary": f"{platform} result",
                "synapse_mentioned": cited,
                "synapse_cited": cited,
                "cited_urls": ["https://www.synapse-network.ai/"] if cited else [],
                "competitor_mentions": ["MCPay"] if not cited else [],
                "next_action": "Keep feeding MCP registry evidence.",
                "metadata": {"source_hosts": hosts},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-06-source-hosts",
            },
        )
        assert response.status_code == 201

    comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-hosts"
    )

    assert comparison.status_code == 200
    payload = comparison.json()["items"][0]
    assert set(payload["source_hosts"]) == {
        "docs.mcpay.tech",
        "mcpservers.org",
        "synapse-network.ai",
    }
    assert "MCPay" in payload["top_competitors"]
    assert any(
        "Prioritize third-party presence on cited answer-engine hosts" in action
        for action in payload["next_actions"]
    )

    weekly = synced_client.get("/api/growth/ai-visibility/weekly-report")
    report = next(
        item
        for item in weekly.json()["feed_reports"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    assert "docs.mcpay.tech" in report["source_hosts"]


def test_ai_visibility_comparison_flags_synapse_org_source_host_collision(
    synced_client,
):
    response = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "SynapseNetwork MCP vs paid MCP alternatives",
            "platform": "chatgpt",
            "answer_summary": "ChatGPT surfaced an unrelated Synapse MCP source.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "metadata": {
                "source_hosts": ["python-docs.synapse.org", "mcp.synapse.org"]
            },
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-08-synapse-org-source-collision",
        },
    )
    assert response.status_code == 201

    comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons"
        "?feed_key=mcp_paid_api_discovery"
        "&run_group=2026-06-08-synapse-org-source-collision"
    )

    assert comparison.status_code == 200
    payload = comparison.json()["items"][0]
    assert payload["citation_quality_status"] == "brand_collision_present"
    assert payload["known_collision_competitors"] == [
        "mcp.synapse.org",
        "python-docs.synapse.org",
        "synapse.org",
    ]
    assert payload["next_actions"][0] == (
        "Add or strengthen disambiguation copy for known collision domains: "
        "mcp.synapse.org, python-docs.synapse.org, synapse.org."
    )


def test_ai_visibility_presence_plan_api_uses_source_hosts(synced_client):
    for host in ("mcpservers.org", "docs.mcpay.tech", "github.com"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": "chatgpt",
                "answer_summary": f"ChatGPT cited {host}.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "competitor_mentions": ["MCPay"] if "mcpay" in host else [],
                "metadata": {"source_hosts": [host]},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-06-presence-plan",
            },
        )
        assert response.status_code == 201

    plan = synced_client.get(
        "/api/growth/ai-visibility/presence-plan"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-presence-plan"
    )

    assert plan.status_code == 200
    payload = plan.json()
    assert payload["status"] == "ready_for_presence_work"
    assert set(payload["source_hosts"]) == {
        "mcpservers.org",
        "docs.mcpay.tech",
        "github.com",
    }
    action_by_host = {item["host"]: item for item in payload["actions"]}
    assert action_by_host["mcpservers.org"]["action_type"] == "directory_listing"
    assert action_by_host["mcpservers.org"]["submit_url"] == (
        "https://mcpservers.org/submit"
    )
    assert (
        action_by_host["mcpservers.org"]["submission_payload"]["remote_mcp_endpoint"]
        == "https://mcp.synapse-network.ai/mcp"
    )
    assert (
        action_by_host["mcpservers.org"]["submission_payload"]["contact_email"]
        == "<operator email>"
    )
    assert action_by_host["docs.mcpay.tech"]["ownership"] == "not_directly_editable"
    assert action_by_host["github.com"]["action_type"] == "owned_or_partner_listing"
    assert "https://mcp.synapse-network.ai/mcp" in "\n".join(
        action_by_host["mcpservers.org"]["copy_points"]
    )
    assert "chatgpt,claude,grok,gemini" in payload["next_probe_command"]
    assert payload["validation_commands"]
