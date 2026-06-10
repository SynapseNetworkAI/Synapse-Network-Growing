def test_ai_visibility_comparison_surfaces_source_hosts(synced_client):
    for platform, cited, hosts in (
        (
            "chatgpt",
            False,
            ["docs.mcpay.tech", "mcpservers.org", "chat.mcp.so", "dock0.dev"],
        ),
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
        "chat.mcp.so",
        "dock0.dev",
        "synapse-network.ai",
    }
    assert "MCPay" in payload["top_competitors"]
    assert any(
        "Prioritize third-party presence on cited answer-engine hosts" in action
        for action in payload["next_actions"]
    )
    action_by_host = {item["host"]: item for item in payload["source_host_actions"]}
    assert action_by_host["mcpservers.org"]["surface"] == "mcpservers"
    assert action_by_host["mcpservers.org"]["priority"] == "p0"
    assert action_by_host["mcpservers.org"]["draft_type"] == "mcp_directory_listing"
    assert action_by_host["mcpservers.org"]["observed_count"] == 1
    assert action_by_host["docs.mcpay.tech"]["surface"] == "docs_mcpay_tech"
    assert action_by_host["docs.mcpay.tech"]["priority"] == "p1"
    assert action_by_host["chat.mcp.so"]["surface"] == "chat_mcp_so"
    assert action_by_host["chat.mcp.so"]["priority"] == "p0"
    assert action_by_host["chat.mcp.so"]["draft_type"] == "mcp_search_surface_review"
    assert action_by_host["dock0.dev"]["surface"] == "dock0_dev"
    assert action_by_host["dock0.dev"]["priority"] == "p0"
    assert action_by_host["dock0.dev"]["draft_type"] == (
        "competitor_source_host_review"
    )

    weekly = synced_client.get("/api/growth/ai-visibility/weekly-report")
    report = next(
        item
        for item in weekly.json()["feed_reports"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    assert "docs.mcpay.tech" in report["source_hosts"]
    assert "chat.mcp.so" in report["source_hosts"]
    assert "dock0.dev" in report["source_hosts"]
    report_action_by_host = {
        item["host"]: item for item in report["source_host_actions"]
    }
    assert report_action_by_host["mcpservers.org"]["surface"] == "mcpservers"

    scorecard = synced_client.get("/api/growth/ai-visibility/feed-scorecard")
    score = next(
        item
        for item in scorecard.json()["items"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    score_action_by_host = {item["host"]: item for item in score["source_host_actions"]}
    assert score_action_by_host["mcpservers.org"]["draft_type"] == (
        "mcp_directory_listing"
    )


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
    assert payload["feed_effective"] is False

    weekly = synced_client.get("/api/growth/ai-visibility/weekly-report")
    assert weekly.status_code == 200
    weekly_payload = weekly.json()
    assert any(
        "mcp.synapse.org, python-docs.synapse.org, synapse.org" in blocker
        for blocker in weekly_payload["blockers"]
    )


def test_ai_visibility_presence_plan_api_uses_source_hosts(synced_client):
    for host in (
        "mcpservers.org",
        "lobehub.com",
        "mcpfind.org",
        "protodex.io",
        "pulsemcp.com",
        "docs.mcpay.tech",
        "cashfree.com",
        "rapid-mcp.com",
        "docs-dev.seamless.ai",
        "github.com",
    ):
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
        "lobehub.com",
        "mcpfind.org",
        "protodex.io",
        "pulsemcp.com",
        "docs.mcpay.tech",
        "cashfree.com",
        "rapid-mcp.com",
        "docs-dev.seamless.ai",
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
        == "support@synapse-network.ai"
    )
    assert (
        action_by_host["mcpservers.org"]["submission_payload"]["category"] == "finance"
    )
    assert action_by_host["mcpservers.org"]["submission_payload"]["plan"] == "free"
    assert action_by_host["lobehub.com"]["action_type"] == "directory_listing"
    assert action_by_host["lobehub.com"]["submit_url"] == ("https://lobehub.com/mcp")
    assert (
        action_by_host["lobehub.com"]["submission_payload"]["remote_mcp_endpoint"]
        == "https://mcp.synapse-network.ai/mcp"
    )
    assert (
        action_by_host["lobehub.com"]["submission_payload"]["public_listing_url"]
        == "https://lobehub.com/mcp/synapsenetworkai-synapse-network-mcp-server"
    )
    assert "Directory Source-Host Submission Pack" in " ".join(
        action_by_host["lobehub.com"]["operator_notes"]
    )
    assert action_by_host["mcpfind.org"]["action_type"] == "directory_listing"
    assert action_by_host["mcpfind.org"]["submit_url"] == ("https://mcpfind.org/submit")
    assert (
        action_by_host["mcpfind.org"]["submission_payload"]["remote_mcp_endpoint"]
        == "https://mcp.synapse-network.ai/mcp"
    )
    assert action_by_host["mcpfind.org"]["submission_payload"]["category"] == "payments"
    assert action_by_host["protodex.io"]["action_type"] == "directory_listing"
    assert (
        "LuciferForge/mcp-directory/issues/new"
        in action_by_host["protodex.io"]["submit_url"]
    )
    assert (
        action_by_host["protodex.io"]["submission_payload"]["github_issue_repository"]
        == "LuciferForge/mcp-directory"
    )
    assert (
        action_by_host["protodex.io"]["submission_payload"]["category"]
        == "API Integration"
    )
    assert action_by_host["pulsemcp.com"]["action_type"] == "directory_listing"
    assert action_by_host["pulsemcp.com"]["source_reference_url"] == (
        "https://pulsemcp.com/"
    )
    assert "pulsemcp.com" in action_by_host["pulsemcp.com"]["validation_command"]
    assert action_by_host["docs.mcpay.tech"]["ownership"] == "not_directly_editable"
    assert action_by_host["docs.mcpay.tech"]["submission_payload"]["cited_terms"] == [
        "MCPay",
        "mcpay.fun",
        "x402",
    ]
    assert (
        "MCP server for paid API calls"
        in action_by_host["docs.mcpay.tech"]["submission_payload"][
            "answer_engine_queries"
        ]
    )
    assert (
        "bounded USDC spend"
        in action_by_host["docs.mcpay.tech"]["submission_payload"][
            "answer_engine_source_block"
        ]
    )
    assert action_by_host["cashfree.com"]["action_type"] == "comparison_presence"
    assert (
        "Cashfree"
        in action_by_host["cashfree.com"]["submission_payload"]["cited_terms"]
    )
    assert action_by_host["rapid-mcp.com"]["action_type"] == "comparison_presence"
    assert action_by_host["docs-dev.seamless.ai"]["action_type"] == (
        "comparison_presence"
    )
    assert (
        action_by_host["rapid-mcp.com"]["submission_payload"]["owned_comparison_url"]
        == "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp"
    )
    assert action_by_host["github.com"]["action_type"] == "owned_or_partner_listing"
    assert "https://mcp.synapse-network.ai/mcp" in "\n".join(
        action_by_host["mcpservers.org"]["copy_points"]
    )
    assert "chatgpt,claude,grok,gemini" in payload["next_probe_command"]
    assert payload["validation_commands"]
