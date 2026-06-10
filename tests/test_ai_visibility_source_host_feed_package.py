from datetime import datetime, timezone


def test_ai_visibility_source_host_feed_package_api_uses_presence_actions(
    synced_client,
):
    for host in (
        "mcpservers.org",
        "aitoolnet.com",
        "alternativeto.net",
        "mcp.directory",
        "glama.ai",
        "lobehub.com",
        "aws.amazon.com",
        "python-docs.synapse.org",
    ):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": "chatgpt",
                "answer_summary": f"ChatGPT cited {host}.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "metadata": {"source_hosts": [host]},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-06-source-host-feed",
            },
        )
        assert response.status_code == 201

    package = synced_client.get(
        "/api/growth/ai-visibility/source-host-feed-package"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-host-feed"
    )

    assert package.status_code == 200
    payload = package.json()
    assert payload["status"] == "ready_for_operator_feed"
    draft_by_host = {item["host"]: item for item in payload["drafts"]}
    assert draft_by_host["mcpservers.org"]["draft_type"] == "directory_submission"
    assert draft_by_host["mcpservers.org"]["status"] == "ready_to_submit"
    assert draft_by_host["mcpservers.org"]["submit_url"] == (
        "https://mcpservers.org/submit"
    )
    assert (
        draft_by_host["mcpservers.org"]["submission_payload"]["category"] == "finance"
    )
    assert draft_by_host["mcpservers.org"]["submission_payload"]["plan"] == "free"
    assert (
        "category"
        in draft_by_host["mcpservers.org"]["submission_payload"]["form_fields"]
    )
    assert draft_by_host["aitoolnet.com"]["draft_type"] == "directory_submission"
    assert draft_by_host["aitoolnet.com"]["status"] == "ready_to_submit"
    assert draft_by_host["aitoolnet.com"]["submit_url"] == (
        "https://www.aitoolnet.com/finish"
    )
    assert (
        draft_by_host["aitoolnet.com"]["submission_payload"]["stitch_figma_frame"]
        == "Directory Source-Host Submission Pack"
    )
    assert "support@aitoolnet.com" in " ".join(
        draft_by_host["aitoolnet.com"]["operator_notes"]
    )
    assert (
        "support@aitoolnet.com"
        in draft_by_host["aitoolnet.com"]["submission_payload"]["submission_method"]
    )
    assert (
        "Remote MCP endpoint: https://mcp.synapse-network.ai/mcp"
        in draft_by_host["aitoolnet.com"]["submission_payload"]["email_body"]
    )
    assert (
        "Tools: discover_services, invoke_and_pay, get_receipt"
        in draft_by_host["aitoolnet.com"]["submission_payload"]["email_body"]
    )
    assert (
        draft_by_host["aitoolnet.com"]["submission_payload"]["contact_email"]
        == "support@synapse-network.ai"
    )
    assert (
        "Free review queue"
        in draft_by_host["aitoolnet.com"]["submission_payload"]["pricing_or_plan"]
    )
    assert (
        "operator email send/draft receipt"
        in draft_by_host["aitoolnet.com"]["submission_payload"]["submission_blocker"]
    )
    assert "browser/form confirmation" in " ".join(
        draft_by_host["alternativeto.net"]["operator_notes"]
    )
    assert draft_by_host["alternativeto.net"]["status"] == "operator_login_required"
    assert (
        draft_by_host["alternativeto.net"]["submit_url"] == "https://alternativeto.net/"
    )
    assert (
        "authenticated/manual community submission path"
        in draft_by_host["alternativeto.net"]["submission_payload"][
            "submission_blocker"
        ]
    )
    assert "Synapse Network MCP Server" in draft_by_host["mcpservers.org"]["title"]
    assert draft_by_host["lobehub.com"]["draft_type"] == "directory_submission"
    assert draft_by_host["lobehub.com"]["status"] == "ready_to_submit"
    assert draft_by_host["lobehub.com"]["target_url"] == "https://lobehub.com/mcp"
    assert (
        draft_by_host["lobehub.com"]["submission_payload"]["public_listing_url"]
        == "https://lobehub.com/mcp/synapsenetworkai-synapse-network-mcp-server"
    )
    assert "LobeHub MCP marketplace" in (
        draft_by_host["lobehub.com"]["submission_payload"]["submission_method"]
    )
    assert draft_by_host["aws.amazon.com"]["draft_type"] == (
        "contextual_partner_or_guest_pitch"
    )
    assert draft_by_host["aws.amazon.com"]["status"] == "needs_operator_review"
    assert draft_by_host["python-docs.synapse.org"]["draft_type"] == (
        "owned_brand_disambiguation_refresh"
    )
    assert draft_by_host["python-docs.synapse.org"]["status"] == (
        "ready_to_publish_on_owned_channels"
    )
    assert (
        "Synapse.org and Sage Bionetworks"
        in draft_by_host["python-docs.synapse.org"]["submission_payload"][
            "recommended_copy"
        ]
    )
    assert (
        "SynapseNetworkAI/Synapse-Network-MCP-Server"
        in draft_by_host["python-docs.synapse.org"]["body_markdown"]
    )
    assert "after_feed_probe" in payload["commands"]

    checklist = synced_client.get(
        "/api/growth/ai-visibility/source-host-execution-checklist"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-host-feed"
    )

    assert checklist.status_code == 200
    checklist_payload = checklist.json()
    item_by_host = {item["host"]: item for item in checklist_payload["items"]}
    assert item_by_host["mcpservers.org"]["execution_status"] == "pending_submission"
    mcpservers_fields = item_by_host["mcpservers.org"]["submission_fields"]
    assert {
        "Server or product name",
        "Short description",
        "Link",
        "Category",
        "Contact email",
        "Plan",
    }.issubset({field["label"] for field in mcpservers_fields})
    assert any(
        field["label"] == "Category" and field["value"] == "finance"
        for field in mcpservers_fields
    )
    assert any(
        field["label"] == "Plan" and field["value"] == "free"
        for field in mcpservers_fields
    )
    assert item_by_host["aitoolnet.com"]["execution_status"] == "pending_submission"
    assert item_by_host["mcp.directory"]["execution_status"] == "pending_submission"
    assert (
        "--surface mcp_directory"
        in item_by_host["mcp.directory"]["submission_confirmation_command"]
    )
    mcp_directory_fields = item_by_host["mcp.directory"]["submission_fields"]
    assert {
        "GitHub repository URL",
        "NPM package",
        "PyPI package",
        "Short description",
        "Contact email",
    }.issubset({field["label"] for field in mcp_directory_fields})
    assert any(
        field["value"]
        == "https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server"
        for field in mcp_directory_fields
    )
    assert any(
        "Remote MCP endpoint" in field["label"]
        and field["value"] == "https://mcp.synapse-network.ai/mcp"
        for field in mcp_directory_fields
    )
    assert (
        "operator-owned browser session"
        in item_by_host["mcp.directory"]["submission_steps"][0]
    )
    assert any(
        "--surface mcp_directory" in step
        for step in item_by_host["mcp.directory"]["evidence_recording_steps"]
    )
    assert item_by_host["mcp.directory"]["live_listing_search_urls"][0] == (
        "https://mcp.directory/?q=Synapse%20Network"
    )
    assert item_by_host["mcp.directory"]["latest_live_evidence_status"] == (
        "missing_required_terms"
    )
    assert (
        "mcp.synapse-network.ai"
        in item_by_host["mcp.directory"]["latest_live_missing_terms"]
    )
    assert (
        "Latest live check failed"
        in item_by_host["mcp.directory"]["evidence_recording_steps"][0]
    )
    assert (
        "--evidence-mode live-listing"
        in item_by_host["mcp.directory"]["live_listing_validation_steps"][2]
    )
    assert (
        "YYYY-MM-DD-mcp_directory-submission-confirmation.json"
        in item_by_host["mcp.directory"]["submission_confirmation_command"]
    )
    assert item_by_host["aitoolnet.com"]["design_handoff_frame"] == (
        "Directory Source-Host Submission Pack"
    )
    aitoolnet_fields = item_by_host["aitoolnet.com"]["submission_fields"]
    aitoolnet_labels = {field["label"] for field in aitoolnet_fields}
    assert {
        "Category",
        "Pricing or plan",
        "Listing content",
        "Contact email",
    }.issubset(aitoolnet_labels)
    assert any(
        field["label"] == "Contact email"
        and field["value"] == "support@synapse-network.ai"
        and "Operator-owned email only" in field["notes"]
        and "required" in field["notes"]
        for field in aitoolnet_fields
    )
    assert any(
        field["label"] == "Listing content"
        and "https://mcp.synapse-network.ai/mcp" in field["value"]
        and "@synapse-network-ai/mcp-server" in field["value"]
        for field in aitoolnet_fields
    )
    assert (
        "--evidence-mode submission-confirmation"
        in item_by_host["aitoolnet.com"]["submission_confirmation_command"]
    )
    assert (
        "YYYY-MM-DD-aitoolnet-submission-confirmation.json"
        in item_by_host["aitoolnet.com"]["submission_confirmation_command"]
    )
    assert item_by_host["glama.ai"]["execution_status"] == "pending_submission"
    assert item_by_host["glama.ai"]["target_url"] == "https://glama.ai/mcp/servers"
    assert item_by_host["glama.ai"]["design_handoff_frame"] == (
        "Directory Source-Host Submission Pack"
    )
    assert item_by_host["glama.ai"]["live_listing_search_urls"][0] == (
        "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP"
    )
    assert item_by_host["lobehub.com"]["execution_status"] == "pending_submission"
    assert item_by_host["lobehub.com"]["target_url"] == "https://lobehub.com/mcp"
    assert item_by_host["lobehub.com"]["live_listing_search_urls"][0] == (
        "https://lobehub.com/mcp/synapsenetworkai-synapse-network-mcp-server"
    )


    assert item_by_host["lobehub.com"]["latest_live_evidence_status"] == (
        "live_verified"
    )
    assert item_by_host["lobehub.com"]["latest_live_evidence_url"] == (
        "https://lobehub.com/mcp/synapsenetworkai-synapse-network-mcp-server"
    )
    assert (
        item_by_host["alternativeto.net"]["execution_status"]
        == "pending_operator_login"
    )
    assert (
        item_by_host["alternativeto.net"]["target_url"] == "https://alternativeto.net/"
    )
    assert (
        "operator-owned account" in item_by_host["alternativeto.net"]["action_required"]
    )
    assert any(
        field["label"] == "Website URL"
        and field["value"] == "https://www.synapse-network.ai/"
        for field in item_by_host["alternativeto.net"]["submission_fields"]
    )
    assert item_by_host["alternativeto.net"]["live_listing_search_urls"][0] == (
        "https://alternativeto.net/browse/search/?q=SynapseNetwork%20MCP%20Server"
    )
    assert (
        "submission_url_or_receipt"
        in item_by_host["mcpservers.org"]["required_evidence"]
    )
    assert item_by_host["aws.amazon.com"]["execution_status"] == (
        "pending_operator_review"
    )
    assert item_by_host["python-docs.synapse.org"]["execution_status"] == (
        "pending_owned_publish"
    )
    assert item_by_host["python-docs.synapse.org"]["draft_type"] == (
        "owned_brand_disambiguation_refresh"
    )
    assert "after_feed_probe" in checklist_payload["commands"]

    spot_check = synced_client.get(
        "/api/growth/ai-visibility/source-host-live-spot-check"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-06-source-host-feed"
    )
    assert spot_check.status_code == 200
    spot_payload = spot_check.json()
    assert spot_payload["status"] == "ready_to_execute"
    assert any(
        item["host"] == "mcp.directory"
        and item["search_url"] == "https://mcp.directory/?q=Synapse%20Network"
        and item["status"] == "pending_execute"
        for item in spot_payload["items"]
    )


def test_ai_visibility_source_host_feed_package_handles_agent_payment_context(
    synced_client,
):
    response = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "agents paying for APIs",
            "platform": "chatgpt",
            "answer_summary": "ChatGPT cited Moesif MCP monetization guidance.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "metadata": {"source_hosts": ["moesif.com"]},
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-11-agent-payment-context-package",
        },
    )
    assert response.status_code == 201

    package = synced_client.get(
        "/api/growth/ai-visibility/source-host-feed-package"
        "?feed_key=mcp_paid_api_discovery"
        "&run_group=2026-06-11-agent-payment-context-package"
    )

    assert package.status_code == 200
    payload = package.json()
    draft = payload["drafts"][0]
    assert draft["host"] == "moesif.com"
    assert draft["draft_type"] == "owned_agent_payment_context_refresh"
    assert draft["status"] == "ready_to_publish_on_owned_channels"
    assert "not third-party submission" in draft["body_markdown"]
    assert "Do not count it as GPT/Claude citation evidence" in draft[
        "body_markdown"
    ]
    assert draft["submission_payload"]["evidence_status"] == (
        "source_host_context_not_external_citation"
    )

    checklist = synced_client.get(
        "/api/growth/ai-visibility/source-host-execution-checklist"
        "?feed_key=mcp_paid_api_discovery"
        "&run_group=2026-06-11-agent-payment-context-package"
    )

    assert checklist.status_code == 200
    item = checklist.json()["items"][0]
    assert item["host"] == "moesif.com"
    assert item["draft_type"] == "owned_agent_payment_context_refresh"
    assert item["execution_status"] == "pending_owned_publish"
    assert item["submission_fields"] == []
    assert item["required_evidence"] == [
        "published_url",
        "git_commit_or_pr",
        "live_curl_validation",
    ]
    assert "owned docs or llms surfaces" in item["action_required"]


def test_ai_visibility_source_host_live_spot_check_detects_candidate(
    db_session,
):
    from server.services.growth.ai_visibility_source_host_live_spot_check import (
        ai_visibility_source_host_live_spot_check,
    )
    from server.services.growth.ai_visibility_discovery import create_ai_check
    from server.schemas_growth import GrowthAIVisibilityCheckCreate

    create_ai_check(
        db_session,
        GrowthAIVisibilityCheckCreate(
            query="Synapse vs paid MCP alternatives",
            platform="chatgpt",
            answer_summary="ChatGPT cited mcp.directory.",
            synapse_mentioned=False,
            synapse_cited=False,
            metadata={"source_hosts": ["mcp.directory"]},
            feed_key="mcp_paid_api_discovery",
            run_group="2026-06-06-source-host-live",
        ),
    )

    def fake_fetcher(url: str):  # noqa: ARG001
        return (
            200,
            "Directory result for Synapse Network MCP Server at "
            "https://mcp.synapse-network.ai/mcp for "
            "SynapseNetworkAI/Synapse-Network-MCP-Server",
        )

    result = ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-source-host-live",
        execute=True,
        fetcher=fake_fetcher,
    )

    assert result.status == "candidate_found_needs_live_listing_evidence"
    assert result.items[0].status == "candidate_found"
    assert "synapse network" in result.items[0].matched_terms
    assert (
        "record_ai_visibility_source_host_execution.py"
        in result.commands["record_live_listing"]
    )


def test_ai_visibility_source_host_feed_package_outputs_comparison_answer_blocks(
    synced_client,
):
    for host in ("docs.mcpay.tech", "cashfree.com"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "ChatGPT MCP app for API payments",
                "platform": "chatgpt",
                "answer_summary": f"ChatGPT cited {host}.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "metadata": {"source_hosts": [host]},
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-10-comparison-answer-blocks",
            },
        )
        assert response.status_code == 201

    package = synced_client.get(
        "/api/growth/ai-visibility/source-host-feed-package"
        "?feed_key=mcp_paid_api_discovery"
        "&run_group=2026-06-10-comparison-answer-blocks"
    )

    assert package.status_code == 200
    draft_by_host = {item["host"]: item for item in package.json()["drafts"]}
    mcpay = draft_by_host["docs.mcpay.tech"]
    cashfree = draft_by_host["cashfree.com"]

    assert mcpay["draft_type"] == "owned_comparison_refresh"
    assert mcpay["title"].startswith("Synapse Network vs MCPay")
    assert "## Answer-engine source block" in mcpay["body_markdown"]
    assert "MCP server for paid API calls" in mcpay["body_markdown"]
    assert "MCPay" in mcpay["body_markdown"]
    assert "mcpay.fun" in mcpay["body_markdown"]
    assert "x402" in mcpay["body_markdown"]
    assert "bounded USDC spend" in mcpay["body_markdown"]
    assert cashfree["title"].startswith("Synapse Network vs Cashfree")
    assert "Cashfree" in cashfree["body_markdown"]
    assert "ChatGPT MCP app for API payments" in cashfree["body_markdown"]


def test_ai_visibility_source_host_checklist_keeps_reserved_mcp_directories(
    db_session,
):
    from server.services.growth.ai_visibility_discovery import create_ai_check
    from server.services.growth.ai_visibility_source_host_feed import (
        ai_visibility_source_host_execution_checklist,
    )
    from server.schemas_growth import GrowthAIVisibilityCheckCreate

    create_ai_check(
        db_session,
        GrowthAIVisibilityCheckCreate(
            query="MCP server for paid API calls",
            platform="chatgpt",
            answer_summary="ChatGPT cited several MCP directory and competitor hosts.",
            synapse_mentioned=False,
            synapse_cited=False,
            metadata={
                "source_hosts": [
                    "docs.mcpay.tech",
                    "mcp.directory",
                    "agent402.dev",
                    "cloud.tencent.com",
                    "crowcrowcrow.com",
                    "developer.paddle.com",
                    "docs.opensearch.org",
                    "anythingmcp.com",
                    "glama.ai",
                    "lobehub.com",
                    "mcpservers.org",
                ]
            },
            feed_key="mcp_paid_api_discovery",
            run_group="2026-06-06-reserved-source-hosts",
        ),
    )

    checklist = ai_visibility_source_host_execution_checklist(
        db_session,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-reserved-source-hosts",
    )

    item_by_host = {item.host: item for item in checklist.items}
    assert item_by_host["glama.ai"].draft_type == "directory_submission"
    assert item_by_host["glama.ai"].target_url == "https://glama.ai/mcp/servers"
    assert item_by_host["glama.ai"].priority == 8
    assert item_by_host["lobehub.com"].draft_type == "directory_submission"
    assert item_by_host["lobehub.com"].target_url == "https://lobehub.com/mcp"
    assert item_by_host["lobehub.com"].priority == 9
    assert item_by_host["mcpservers.org"].draft_type == "directory_submission"
    assert item_by_host["mcpservers.org"].target_url == "https://mcpservers.org/submit"
    assert item_by_host["mcpservers.org"].priority == 10


def test_ai_visibility_source_host_live_spot_check_blocks_without_search_urls(
    monkeypatch,
    db_session,
):
    from server.schemas_growth import GrowthAIVisibilitySourceHostExecutionChecklistOut
    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    monkeypatch.setattr(
        svc,
        "ai_visibility_source_host_execution_checklist",
        lambda _db, **_kwargs: GrowthAIVisibilitySourceHostExecutionChecklistOut(
            generated_at=datetime.now(timezone.utc),
            feed_key="mcp_paid_api_discovery",
            status="ready_for_operator_execution",
            items=[],
        ),
    )

    result = svc.ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        execute=True,
    )

    assert result.status == "blocked_until_search_urls"
    assert "No source-host live listing search URLs are available." in result.blockers


def test_ai_visibility_source_host_live_spot_check_reports_fetch_failure(
    monkeypatch,
    db_session,
):
    from server.schemas_growth import (
        GrowthAIVisibilitySourceHostExecutionChecklistOut,
        GrowthAIVisibilitySourceHostExecutionItemOut,
    )
    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    monkeypatch.setattr(
        svc,
        "ai_visibility_source_host_execution_checklist",
        lambda _db, **_kwargs: GrowthAIVisibilitySourceHostExecutionChecklistOut(
            generated_at=datetime.now(timezone.utc),
            feed_key="mcp_paid_api_discovery",
            status="ready_for_operator_execution",
            items=[
                GrowthAIVisibilitySourceHostExecutionItemOut(
                    key="mcp_directory",
                    host="mcp.directory",
                    draft_type="directory_submission",
                    execution_status="pending_submission",
                    target_url="https://mcp.directory/",
                    action_required="Submit listing.",
                    live_listing_search_urls=["https://mcp.directory/?q=Synapse"],
                    validation_command="python scripts/growth/probe.py",
                    re_probe_command="python scripts/growth/probe.py",
                    completion_gate="Live listing evidence recorded.",
                )
            ],
        ),
    )

    result = svc.ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        execute=True,
        fetcher=lambda _url: (_ for _ in ()).throw(RuntimeError("host unavailable")),
    )

    assert result.status == "partial_fetch_failure"
    assert result.items[0].status == "fetch_failed"
    assert result.items[0].evidence_excerpt == "host unavailable"
    assert "No Synapse source-host listing candidate was found" in result.blockers[-1]


def test_ai_visibility_source_host_live_spot_check_marks_challenge_fetch_blocked():
    from server.schemas_growth import (
        GrowthAIVisibilitySourceHostExecutionChecklistOut,
        GrowthAIVisibilitySourceHostExecutionItemOut,
    )
    from server.services.growth.ai_visibility_source_host_offline_live import (
        source_host_live_spot_check_from_checklist_model,
    )

    checklist = GrowthAIVisibilitySourceHostExecutionChecklistOut(
        generated_at=datetime.now(timezone.utc),
        feed_key="mcp_paid_api_discovery",
        status="ready_for_operator_execution",
        items=[
            GrowthAIVisibilitySourceHostExecutionItemOut(
                key="alternativeto",
                host="alternativeto.net",
                draft_type="directory_submission",
                execution_status="pending_operator_login",
                target_url="https://alternativeto.net/",
                action_required="Use operator login or contact path.",
                live_listing_search_urls=[
                    "https://alternativeto.net/browse/search/?q=SynapseNetwork%20MCP%20Server"
                ],
                validation_command="Record browser confirmation.",
                re_probe_command="python scripts/growth/probe.py",
                completion_gate="Live listing evidence recorded.",
            )
        ],
    )

    result = source_host_live_spot_check_from_checklist_model(
        checklist,
        execute=True,
        fetcher=lambda _url: (
            403,
            "<title>Just a moment...</title>"
            '<meta name="robots" content="noindex,nofollow">'
            "Checking if the site connection is secure. "
            "https://challenges.cloudflare.com challenge-platform",
        ),
    )

    assert result.status == "partial_fetch_failure"
    assert result.items[0].status == "fetch_blocked"
    assert result.items[0].http_status == 403
    assert result.items[0].matched_terms == []
    assert "operator-owned browser session" in result.items[0].next_action


def test_ai_visibility_source_host_live_spot_check_detects_glama_listing_identity():
    from server.schemas_growth import (
        GrowthAIVisibilitySourceHostExecutionChecklistOut,
        GrowthAIVisibilitySourceHostExecutionItemOut,
    )
    from server.services.growth.ai_visibility_source_host_offline_live import (
        source_host_live_spot_check_from_checklist_model,
    )

    checklist = GrowthAIVisibilitySourceHostExecutionChecklistOut(
        generated_at=datetime.now(timezone.utc),
        feed_key="mcp_paid_api_discovery",
        status="ready_for_operator_execution",
        items=[
            GrowthAIVisibilitySourceHostExecutionItemOut(
                key="glama",
                host="glama.ai",
                draft_type="directory_submission",
                execution_status="pending_submission",
                target_url="https://glama.ai/mcp/servers",
                action_required="Submit listing.",
                live_listing_search_urls=[
                    "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP"
                ],
                validation_command="curl -fsS https://glama.ai/mcp/servers",
                re_probe_command="python scripts/growth/probe.py",
                completion_gate="Live listing evidence recorded.",
            )
        ],
    )

    result = source_host_live_spot_check_from_checklist_model(
        checklist,
        execute=True,
        fetcher=lambda _url: (
            200,
            "<title>Synapse Network MCP MCP Servers | Glama</title>"
            '<a href="/mcp/connectors/io.github.SynapseNetworkAI/'
            'synapse-network-mcp-server">'
            "SynapseNetwork MCP Server for paid API calls "
            "https://mcp.synapse-network.ai/mcp</a>",
        ),
    )

    assert result.status == "candidate_found_needs_live_listing_evidence"
    assert result.items[0].status == "candidate_found"
    assert "synapsenetwork" in result.items[0].matched_terms
    assert "mcp.synapse-network.ai" in result.items[0].matched_terms
    assert "synapse-network-mcp-server" in result.items[0].matched_terms
    assert "--evidence-mode live " in result.commands["record_live_listing"]


def test_ai_visibility_source_host_live_spot_check_marks_incomplete_directory_metadata():
    from server.schemas_growth import (
        GrowthAIVisibilitySourceHostExecutionChecklistOut,
        GrowthAIVisibilitySourceHostExecutionItemOut,
    )
    from server.services.growth.ai_visibility_source_host_offline_live import (
        source_host_live_spot_check_from_checklist_model,
    )

    checklist = GrowthAIVisibilitySourceHostExecutionChecklistOut(
        generated_at=datetime.now(timezone.utc),
        feed_key="mcp_paid_api_discovery",
        status="ready_for_operator_execution",
        items=[
            GrowthAIVisibilitySourceHostExecutionItemOut(
                key="glama",
                host="glama.ai",
                draft_type="directory_submission",
                execution_status="pending_submission",
                target_url="https://glama.ai/mcp/servers",
                action_required="Submit listing.",
                live_listing_search_urls=[
                    "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP"
                ],
                validation_command="curl -fsS https://glama.ai/mcp/servers",
                re_probe_command="python scripts/growth/probe.py",
                completion_gate="Live listing evidence recorded.",
            )
        ],
    )

    result = source_host_live_spot_check_from_checklist_model(
        checklist,
        execute=True,
        fetcher=lambda _url: (
            200,
            "<title>Synapse Network MCP MCP Servers | Glama</title>"
            '<a href="/mcp/connectors/io.github.SynapseNetworkAI/'
            'synapse-network-mcp-server">'
            "SynapseNetwork MCP Server for paid API calls</a>",
        ),
    )

    assert result.status == "candidate_incomplete_needs_metadata_refresh"
    assert result.items[0].status == "candidate_incomplete"
    assert "synapsenetwork" in result.items[0].matched_terms
    assert "synapse-network-mcp-server" in result.items[0].matched_terms
    assert "mcp.synapse-network.ai" in result.items[0].missing_terms
    assert "Refresh directory metadata" in result.items[0].next_action


def test_ai_visibility_source_host_live_spot_check_ignores_search_query_echo():
    from server.schemas_growth import (
        GrowthAIVisibilitySourceHostExecutionChecklistOut,
        GrowthAIVisibilitySourceHostExecutionItemOut,
    )
    from server.services.growth.ai_visibility_source_host_offline_live import (
        source_host_live_spot_check_from_checklist_model,
    )

    checklist = GrowthAIVisibilitySourceHostExecutionChecklistOut(
        generated_at=datetime.now(timezone.utc),
        feed_key="mcp_paid_api_discovery",
        status="ready_for_operator_execution",
        items=[
            GrowthAIVisibilitySourceHostExecutionItemOut(
                key="alternativeto",
                host="alternativeto.net",
                draft_type="directory_submission",
                execution_status="pending_operator_login",
                target_url="https://alternativeto.net/",
                action_required="Use operator login or contact path.",
                live_listing_search_urls=[
                    "https://alternativeto.net/browse/search/?q=SynapseNetwork%20MCP%20Server"
                ],
                validation_command="Record browser confirmation.",
                re_probe_command="python scripts/growth/probe.py",
                completion_gate="Live listing evidence recorded.",
            )
        ],
    )

    result = source_host_live_spot_check_from_checklist_model(
        checklist,
        execute=True,
        fetcher=lambda _url: (
            200,
            "<title>Search results for &quot;SynapseNetwork MCP Server&quot;</title>"
            '<meta name="description" content="Search results for SynapseNetwork MCP Server"/>'
            '<meta name="robots" content="noindex"/>',
        ),
    )

    assert result.status == "no_candidate_found"
    assert result.items[0].status == "not_found"
    assert "synapsenetwork mcp server" in result.items[0].matched_terms
    assert result.items[0].next_action == (
        "Submit or wait for the directory listing, then rerun this spot check."
    )


def test_ai_visibility_source_host_live_spot_check_reports_no_candidate(
    db_session,
):
    from server.services.growth.ai_visibility_source_host_live_spot_check import (
        ai_visibility_source_host_live_spot_check,
    )
    from server.services.growth.ai_visibility_discovery import create_ai_check
    from server.schemas_growth import GrowthAIVisibilityCheckCreate

    create_ai_check(
        db_session,
        GrowthAIVisibilityCheckCreate(
            query="Synapse vs paid MCP alternatives",
            platform="chatgpt",
            answer_summary="ChatGPT cited mcp.directory.",
            synapse_mentioned=False,
            synapse_cited=False,
            metadata={"source_hosts": ["mcp.directory"]},
            feed_key="mcp_paid_api_discovery",
            run_group="2026-06-06-source-host-none",
        ),
    )

    result = ai_visibility_source_host_live_spot_check(
        db_session,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-source-host-none",
        execute=True,
        fetcher=lambda _url: (200, "Search result only echoed SynapseNetwork."),
    )

    assert result.status == "no_candidate_found"
    assert result.items[0].status == "not_found"
    assert result.items[0].next_action == (
        "Submit or wait for the directory listing, then rerun this spot check."
    )


def test_ai_visibility_source_host_live_spot_check_fetch_url_handles_http(
    monkeypatch,
):
    import io
    import urllib.error

    from server.services.growth import ai_visibility_source_host_offline_live as svc

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int):
            return b"Synapse Network MCP result"

    def fake_urlopen(request, **_kwargs):
        assert request.headers["Accept"].startswith("text/markdown")
        return FakeResponse()

    monkeypatch.setattr(svc.urllib.request, "urlopen", fake_urlopen)
    assert svc._fetch_url("https://example.com/search") == (
        200,
        "Synapse Network MCP result",
    )

    def raise_http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://example.com/search",
            429,
            "Too Many Requests",
            hdrs=None,
            fp=io.BytesIO(b"rate limited"),
        )

    monkeypatch.setattr(svc.urllib.request, "urlopen", raise_http_error)
    assert svc._fetch_url("https://example.com/search") == (429, "rate limited")
