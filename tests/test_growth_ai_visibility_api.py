import json
from types import SimpleNamespace

from server.database_growth import GrowthDiscoveryListingRow


def _fake_external_probe_gate():
    return SimpleNamespace(
        status="ready_for_partial_external_probes",
        ready_platforms=["chatgpt", "claude"],
        missing_platforms=["grok"],
        partial_api_readiness_command=(
            "python scripts/growth/run_ai_visibility_api_probe.py "
            "--feed-key mcp_paid_api_discovery --platforms chatgpt,claude"
        ),
        blockers=["grok missing XAI_API_KEY."],
    )


def test_growth_ai_visibility_and_discovery_listing(
    monkeypatch,
    synced_client,
    db_session,
):
    plan = synced_client.get("/api/growth/ai-visibility/optimization-plan")
    assert plan.status_code == 200
    plan_payload = plan.json()
    assert plan_payload["canonical_domain"] == "https://www.synapse-network.ai/"
    assert any(
        "Redirect https://synapse-network.ai/*" in fix
        for fix in plan_payload["critical_fixes"]
    )
    assert any(
        "synapsenetwork.xyz" in fix for fix in plan_payload["critical_fixes"]
    )
    assert plan_payload["product_docs"]["docs_category"] == "AI Agent Payments"
    assert plan_payload["baseline_queries"][0]["target_platforms"] == [
        "chatgpt",
        "claude",
        "grok",
    ]
    assert {
        experiment["feed_key"] for experiment in plan_payload["feed_experiments"]
    } >= {
        "brand_disambiguation_www",
        "agent_payment_category_pages",
        "mcp_paid_api_discovery",
    }
    assert "ai_visibility_search_probe" in plan_payload["growing_workflows"]
    packages = synced_client.get("/api/growth/ai-visibility/feed-package")
    assert packages.status_code == 200
    package_payload = packages.json()
    assert package_payload["total"] == 3
    package_by_key = {item["feed_key"]: item for item in package_payload["items"]}
    assert package_by_key["agent_payment_category_pages"]["canonical_domain"] == (
        "https://www.synapse-network.ai/"
    )
    assert {
        asset["surface"]
        for asset in package_by_key["agent_payment_category_pages"]["publish_assets"]
    } >= {"www", "docs", "github"}
    assert any(
        "https://synapse-network.ai/" in command
        and "https://www.synapse-network.ai/" in command
        for command in package_by_key["brand_disambiguation_www"]["validation_commands"]
    )
    assert "Synapse Network AI agents" in package_by_key[
        "brand_disambiguation_www"
    ]["target_queries"]
    assert any(
        "synapsenetwork.xyz" in action
        for action in package_by_key["brand_disambiguation_www"]["next_actions"]
    )
    assert (
        "--feed-key agent_payment_category_pages"
        in package_by_key["agent_payment_category_pages"]["probe_template_command"]
    )
    mcp_package = synced_client.get(
        "/api/growth/ai-visibility/feed-package?feed_key=mcp_paid_api_discovery"
    )
    assert mcp_package.status_code == 200
    assert mcp_package.json()["total"] == 1
    assert mcp_package.json()["items"][0]["feed_key"] == "mcp_paid_api_discovery"
    assert {
        strategy["platform"]
        for strategy in mcp_package.json()["items"][0]["platform_strategies"]
    } == {"chatgpt", "claude", "grok"}
    assert any(
        "Remote MCP custom app" in strategy["feed_focus"]
        for strategy in mcp_package.json()["items"][0]["platform_strategies"]
    )
    assert any(
        "https://mcp.synapse-network.ai/readyz" in command
        for command in mcp_package.json()["items"][0]["validation_commands"]
    )
    release_plan = synced_client.get("/api/growth/ai-visibility/release-unblock-plan")
    assert release_plan.status_code == 200
    release_payload = release_plan.json()
    assert release_payload["status"] == "blocked_until_gcloud_auth"
    assert release_payload["official_homepage"] == "https://www.synapse-network.ai/"
    assert release_payload["services"] == ["docs-front", "user-front"]
    assert release_payload["target_commit_sha"] == (
        "d8b5371e11fea2d962dcc656b9b8d08d0c1379d9"
    )
    assert release_payload["source_pr"]["number"] == 204
    assert release_payload["source_pr"]["state"] == "MERGED"
    assert {item["number"] for item in release_payload["source_prs"]} == {203, 204}
    assert release_payload["deployment_gaps"][0]["service_key"] == "docs-front"
    assert release_payload["predeploy_evidence"]["status"] == (
        "target_branch_ready_live_prod_blocked"
    )
    assert release_payload["predeploy_evidence"]["validation_count"] >= 5
    assert release_payload["deploy_readiness_status"] == (
        "ready_for_release_runner_after_gcloud_auth"
    )
    assert any(
        fact == "Official homepage canonical is https://www.synapse-network.ai/."
        for fact in release_payload["confirmed_facts"]
    )
    assert any(
        "homepage https://www.synapse-network.ai/ is reachable" in blocker
        for blocker in release_payload["known_blockers"]
    )
    rendered_release_plan = json.dumps(release_payload)
    assert "gcloud auth login" in rendered_release_plan
    assert "X-Growing-Agent-Deploy-Token" in rendered_release_plan
    assert "scripts/local/run_deploy_worker.py" in rendered_release_plan
    assert not any(
        command.strip().startswith("gcloud run deploy")
        for group in release_payload["command_groups"]
        for command in group["commands"]
    )
    feed_cycles = synced_client.get("/api/growth/ai-visibility/feed-cycles")
    assert feed_cycles.status_code == 200
    cycle_payload = feed_cycles.json()
    assert cycle_payload["total"] == 3
    assert cycle_payload["target_platforms"] == ["chatgpt", "claude", "grok"]
    assert {item["feed_key"] for item in cycle_payload["items"]} == {
        "brand_disambiguation_www",
        "agent_payment_category_pages",
        "mcp_paid_api_discovery",
    }
    mcp_cycle = next(
        item
        for item in cycle_payload["items"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    assert mcp_cycle["status"] == "feed_blocked"
    assert "Feed validation has not been recorded" in mcp_cycle["blockers"][0]
    assert (
        "run_ai_visibility_feed_validation.py" in mcp_cycle["feed_validation_command"]
    )
    assert "--query" not in mcp_cycle["api_readiness_command"]
    scorecard = synced_client.get("/api/growth/ai-visibility/feed-scorecard")
    assert scorecard.status_code == 200
    scorecard_payload = scorecard.json()
    assert scorecard_payload["total"] == 3
    assert scorecard_payload["recommended_feed_key"] in {
        "brand_disambiguation_www",
        "agent_payment_category_pages",
        "mcp_paid_api_discovery",
    }
    assert "Impact score rewards feed readiness" in scorecard_payload["ranking_basis"]
    assert {item["feed_key"] for item in scorecard_payload["items"]} == {
        "brand_disambiguation_www",
        "agent_payment_category_pages",
        "mcp_paid_api_discovery",
    }
    monkeypatch.setattr(
        "server.services.growth.ai_visibility_brief.build_snapshot",
        lambda **_: {
            "feed_key": "mcp_paid_api_discovery",
            "status": "blocked",
            "deploy_readiness_status": "ready_for_release_runner_after_gcloud_auth",
            "blockers": ["GCloud auth fails non-interactively."],
            "next_actions": ["Run gcloud auth login."],
        },
    )
    monkeypatch.setattr(
        "server.services.growth.ai_visibility_brief.ai_visibility_external_probe_gate",
        lambda **_: _fake_external_probe_gate(),
    )

    brief = synced_client.get("/api/growth/ai-visibility/optimization-brief")
    assert brief.status_code == 200
    brief_payload = brief.json()
    assert brief_payload["title"] == "Synapse AI Visibility Optimization Brief"
    assert brief_payload["official_homepage"] == "https://www.synapse-network.ai/"
    assert brief_payload["recommended_feed_key"] in {
        "brand_disambiguation_www",
        "agent_payment_category_pages",
        "mcp_paid_api_discovery",
    }
    assert "mcp_paid_api_discovery" in brief_payload["markdown"]
    assert "Release snapshot: blocked" in brief_payload["markdown"]
    assert (
        "External probe gate: ready_for_partial_external_probes"
        in brief_payload["markdown"]
    )
    assert "Ready platforms: chatgpt, claude" in brief_payload["markdown"]
    assert "Missing platforms: grok" in brief_payload["markdown"]
    assert (
        "generate_ai_visibility_optimization_brief.py"
        in brief_payload["export_command"]
    )
    assert brief_payload["artifact_path"].endswith("-optimization-brief.md")
    docs_blueprint = synced_client.get("/api/growth/ai-visibility/docs-blueprint")
    assert docs_blueprint.status_code == 200
    docs_payload = docs_blueprint.json()
    assert docs_payload["category"] == "AI Agent Payments"
    assert docs_payload["canonical_domain"] == "https://www.synapse-network.ai/"
    assert docs_payload["implementation_root"] == (
        "services/docs-front/content/docs/ai-agent-payments"
    )
    assert len(docs_payload["pages"]) == 7
    first_page = docs_payload["pages"][0]
    assert first_page["slug"] == "index"
    assert first_page["canonical_url"] == (
        "https://docs.synapse-network.ai/ai-agent-payments"
    )
    assert (
        "Synapse Network is a payment and settlement layer"
        in first_page["definition_block"]
    )
    assert "DefinitionBlock" in first_page["figma_components"]
    assert "# AI Agent Payments" in first_page["mdx_skeleton"]
    design_handoff = synced_client.get("/api/growth/ai-visibility/design-handoff")
    assert design_handoff.status_code == 200
    design_payload = design_handoff.json()
    assert design_payload["figma_file_name"] == (
        "Synapse AI Agent Payments Docs - AI Visibility"
    )
    assert design_payload["source_tool"] == "Stitch"
    assert design_payload["target_tool"] == "Figma"
    assert len(design_payload["frames"]) == 3
    assert design_payload["frames"][0]["source_page_slug"] == "index"
    assert "DefinitionBlock" in {
        component["name"] for component in design_payload["component_specs"]
    }
    assert design_payload["design_tokens"]["radius"] == "8px"
    assert any(
        "Generate the three frames in Stitch" in step
        for step in design_payload["import_steps"]
    )

    check = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "MCP monetization platform",
            "platform": "perplexity",
            "answer_summary": "Synapse was not mentioned.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "competitor_mentions": ["RapidAPI"],
            "next_action": "Create MCP monetization answer block.",
            "feed_key": "mcp_paid_api_discovery",
            "run_group": "2026-06-04-baseline",
            "result_rank": 3,
            "evidence_url": "https://example.com/perplexity-proof",
            "metadata": {"search_mode": "manual"},
        },
    )
    assert check.status_code == 201
    assert check.json()["feed_key"] == "mcp_paid_api_discovery"
    assert check.json()["run_group"] == "2026-06-04-baseline"
    assert check.json()["result_rank"] == 3
    assert check.json()["metadata"]["search_mode"] == "manual"
    collision_check = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "What is Synapse Network for AI agents?",
            "platform": "chatgpt",
            "answer_summary": "A result cites a brand-collision domain.",
            "synapse_mentioned": True,
            "synapse_cited": True,
            "cited_urls": ["https://www.synapsenetwork.xyz/"],
            "competitor_mentions": ["synapsenetwork.xyz"],
            "feed_key": "brand_disambiguation_www",
            "run_group": "2026-06-05-brand-collision",
        },
    )
    assert collision_check.status_code == 400
    assert "official Synapse cited_url" in collision_check.json()["detail"]
    for platform, cited in (("chatgpt", True), ("claude", False)):
        synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": platform,
                "answer_summary": f"{platform} result",
                "synapse_mentioned": cited,
                "synapse_cited": cited,
                "cited_urls": ["https://www.synapse-network.ai/"] if cited else [],
                "competitor_mentions": ["RapidAPI"] if not cited else [],
                "next_action": "Keep feeding MCP registry evidence.",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-04-baseline",
            },
        )
    comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery"
    )
    assert comparison.status_code == 200
    comparison_payload = comparison.json()["items"][0]
    assert comparison_payload["feed_key"] == "mcp_paid_api_discovery"
    assert comparison_payload["run_group"] == "2026-06-04-baseline"
    assert comparison_payload["total_checks"] == 3
    assert comparison_payload["external_checks_count"] == 3
    assert comparison_payload["local_validation_count"] == 0
    assert comparison_payload["cited_count"] == 1
    assert comparison_payload["citation_quality_status"] == "official_citation_verified"
    assert comparison_payload["official_cited_urls"] == [
        "https://www.synapse-network.ai/"
    ]
    assert comparison_payload["known_collision_competitors"] == []
    assert "grok" in comparison_payload["missing_platforms"]
    assert "RapidAPI" in comparison_payload["top_competitors"]
    assert (
        synced_client.get("/api/growth/ai-visibility/checks?q=MCP").json()["total"] == 3
    )

    for platform, cited in (
        ("chatgpt", True),
        ("claude", True),
        ("grok", False),
    ):
        synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "MCP server for paid API calls",
                "platform": platform,
                "answer_summary": f"{platform} after feed",
                "synapse_mentioned": True,
                "synapse_cited": cited,
                "cited_urls": ["https://www.synapse-network.ai/"] if cited else [],
                "competitor_mentions": ["RapidAPI"] if not cited else [],
                "next_action": "Keep feeding registry and docs evidence.",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-18-after-registry-feed",
            },
        )
    after_comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery&run_group=2026-06-18-after-registry-feed"
    ).json()["items"][0]
    assert after_comparison["previous_run_group"] == "2026-06-04-baseline"
    assert after_comparison["previous_cited_count"] == 1
    assert after_comparison["cited_count"] == 2
    assert after_comparison["cited_delta"] == 1
    assert after_comparison["mentioned_delta"] == 2
    assert after_comparison["comparison_status"] == "improved"
    assert after_comparison["citation_quality_status"] == "official_citation_verified"
    assert after_comparison["known_collision_competitors"] == []
    assert after_comparison["feed_effective"] is True
    improved_scorecard = synced_client.get(
        "/api/growth/ai-visibility/feed-scorecard"
    ).json()
    mcp_score = next(
        item
        for item in improved_scorecard["items"]
        if item["feed_key"] == "mcp_paid_api_discovery"
    )
    assert mcp_score["feed_effective"] is True
    assert mcp_score["impact_score"] > 0
    assert mcp_score["mentioned_delta"] == 2
    assert mcp_score["cited_delta"] == 1
    assert "Resolve feed blockers" in mcp_score["recommended_action"]
    weekly_report = synced_client.get("/api/growth/ai-visibility/weekly-report")
    assert weekly_report.status_code == 200
    weekly_payload = weekly_report.json()
    assert weekly_payload["goal_achieved"] is False
    assert weekly_payload["goal_status"] == "optimizing"
    assert weekly_payload["stable_positive_runs"] == 1
    assert weekly_payload["required_stable_runs"] == 3
    assert weekly_payload["covered_platforms"] == ["chatgpt", "claude", "grok"]
    assert (
        "Fewer than three stable positive external runs have been recorded."
        in weekly_payload["blockers"]
    )
    assert weekly_payload["recommended_probe_template_command"].startswith(
        "python scripts/growth/generate_ai_visibility_probe_template.py"
    )
    browser_blocker = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "ChatGPT browser probe readiness",
            "platform": "browser_probe_validation",
            "answer_summary": "Chrome selected profile does not expose the Codex Chrome Extension.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "missing_facts": [
                "Codex Chrome Extension unavailable in selected Chrome profile Profile 3.",
                "No live ChatGPT browser result captured.",
            ],
            "next_action": "Enable the Codex Chrome Extension in the selected Chrome profile.",
            "feed_key": "brand_disambiguation_www",
            "run_group": "2026-06-05-browser-probe-blockers",
        },
    )
    assert browser_blocker.status_code == 201
    blocker_report = synced_client.get("/api/growth/ai-visibility/weekly-report")
    blocker_payload = blocker_report.json()
    assert (
        "Codex Chrome Extension unavailable in selected Chrome profile Profile 3."
        in blocker_payload["blockers"]
    )
    assert (
        "Resolve latest validation blockers before the next external probe."
        in blocker_payload["next_actions"]
    )
    next_cycle = synced_client.get("/api/growth/ai-visibility/next-cycle")
    assert next_cycle.status_code == 200
    next_cycle_payload = next_cycle.json()
    assert next_cycle_payload["feed_key"] == "brand_disambiguation_www"
    assert next_cycle_payload["run_group"].endswith("-brand_disambiguation_www-weekly")
    assert (
        "Codex Chrome Extension unavailable in selected Chrome profile Profile 3."
        in next_cycle_payload["blockers"]
    )
    assert next_cycle_payload["manual_probe_template_command"].startswith(
        "python scripts/growth/generate_ai_visibility_probe_template.py"
    )
    assert (
        "run_ai_visibility_feed_validation.py"
        in next_cycle_payload["feed_validation_command"]
    )
    assert (
        "run_ai_visibility_api_probe.py" in next_cycle_payload["api_readiness_command"]
    )
    assert "--query" not in next_cycle_payload["api_readiness_command"]
    assert "--query" not in next_cycle_payload["api_execute_command"]
    assert "--execute" in next_cycle_payload["api_execute_command"]
    assert next_cycle_payload["apply_command"].startswith(
        "python scripts/growth/record_ai_visibility_probe.py"
    )
    assert (
        "comparisons?feed_key=brand_disambiguation_www"
        in next_cycle_payload["compare_command"]
    )

    local_only = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "How can AI agents pay for APIs?",
            "platform": "www_local_validation",
            "answer_summary": "Local www page renders and contains extractable answer blocks.",
            "synapse_mentioned": True,
            "synapse_cited": True,
            "feed_key": "agent_payment_category_pages",
            "run_group": "2026-06-04-local-feed",
        },
    )
    assert local_only.status_code == 201
    local_comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons?feed_key=agent_payment_category_pages"
    ).json()["items"][0]
    assert local_comparison["total_checks"] == 1
    assert local_comparison["local_validation_count"] == 1
    assert local_comparison["external_checks_count"] == 0
    assert local_comparison["cited_count"] == 0
    assert set(local_comparison["missing_platforms"]) == {
        "chatgpt",
        "claude",
        "grok",
    }

    live_validation = synced_client.post(
        "/api/growth/ai-visibility/checks",
        json={
            "query": "AI agent payment API live crawl",
            "platform": "www_live_validation",
            "answer_summary": "Live www page still returns 404 before deploy.",
            "synapse_mentioned": False,
            "synapse_cited": False,
            "feed_key": "agent_payment_category_pages",
            "run_group": "2026-06-04-live-predeploy",
        },
    )
    assert live_validation.status_code == 201
    live_comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons?feed_key=agent_payment_category_pages&run_group=2026-06-04-live-predeploy"
    ).json()["items"][0]
    assert live_comparison["external_checks_count"] == 0
    assert live_comparison["local_validation_count"] == 1

    listing = synced_client.post(
        "/api/growth/discovery-listings",
        json={
            "surface": "official_mcp_registry",
            "target_repo": "SynapseNetworkAI/Synapse-MCP",
            "package_name": "synapse-network-mcp",
            "status": "candidate",
        },
    )
    assert listing.status_code == 201
    listing_id = listing.json()["id"]
    patched = synced_client.patch(
        f"/api/growth/discovery-listings/{listing_id}",
        json={
            "status": "listed",
            "listing_url": "https://registry.modelcontextprotocol.io/servers/synapse",
            "verification_evidence": {"checked_by": "operator"},
        },
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "listed"
    assert db_session.query(GrowthDiscoveryListingRow).count() == 1


def test_growth_ai_visibility_live_readiness_api(monkeypatch, synced_client):
    from scripts.growth.record_ai_visibility_probe import ProbeRecord

    def fake_validate_feed(*, feed_key: str, run_group: str):
        return [
            ProbeRecord(
                query="Remote MCP live readiness",
                platform="mcp_live_validation",
                feed_key=feed_key,
                run_group=run_group,
                answer_summary="Live feed validation blocked: docs=404",
                synapse_mentioned=False,
                synapse_cited=False,
                missing_facts=[
                    "Docs /mcp/paid-api-calls page must be live.",
                    "www llms.txt must include the MCP paid API calls guide.",
                ],
                next_action="Publish MCP docs before external probes.",
                metadata={
                    "checks": [
                        {
                            "label": "docs_mcp_paid_api_calls",
                            "url": "https://docs.synapse-network.ai/mcp/paid-api-calls",
                            "status": 404,
                            "final_url": "https://docs.synapse-network.ai/mcp/paid-api-calls",
                            "error": "",
                            "contains_synapse": False,
                        }
                    ]
                },
            )
        ]

    monkeypatch.setattr(
        "server.services.growth.ai_visibility_live_readiness."
        "feed_validation.validate_feed",
        fake_validate_feed,
    )

    response = synced_client.get(
        "/api/growth/ai-visibility/live-readiness"
        "?feed_key=mcp_paid_api_discovery&run_group=2026-06-05-live-readiness"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["canonical_homepage"] == "https://www.synapse-network.ai/"
    assert payload["blocked_count"] == 1
    assert payload["items"][0]["feed_key"] == "mcp_paid_api_discovery"
    assert payload["items"][0]["checks"][0]["status"] == 404
    assert "run_ai_visibility_feed_validation.py" in payload["validation_command"]
    assert "record_ai_visibility_probe.py" in payload["apply_command"]


def test_growth_ai_visibility_external_probe_gate_blocks_until_feed_ready(
    monkeypatch,
    synced_client,
):
    from scripts.growth.record_ai_visibility_probe import ProbeRecord

    for env_key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "XAI_API_KEY"):
        monkeypatch.delenv(env_key, raising=False)

    def fake_validate_feed(*, feed_key: str, run_group: str):
        return [
            ProbeRecord(
                query="Remote MCP live readiness",
                platform="mcp_live_validation",
                feed_key=feed_key,
                run_group=run_group,
                answer_summary="Live feed validation blocked: docs=404",
                synapse_mentioned=False,
                synapse_cited=False,
                missing_facts=["Docs /mcp/paid-api-calls page must be live."],
                next_action="Publish MCP docs before external probes.",
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
    assert payload["status"] == "blocked_until_feed_ready"
    assert payload["ready_to_execute"] is False
    assert payload["partial_ready_to_execute"] is False
    assert payload["manual_ready_to_execute"] is False
    assert payload["feed_ready"] is False
    assert payload["api_keys_ready"] is False
    assert payload["target_platforms"] == ["chatgpt", "claude", "grok"]
    assert payload["ready_platforms"] == []
    assert payload["missing_platforms"] == ["chatgpt", "claude", "grok"]
    assert "Docs /mcp/paid-api-calls page must be live." in payload["blockers"]
    assert "OPENAI_API_KEY" in json.dumps(payload)
    assert "generate_ai_visibility_probe_template.py" in payload[
        "manual_probe_template_command"
    ]
    assert "--mode after-feed" in payload["manual_probe_template_command"]
    assert "run_ai_visibility_api_probe.py" in payload["api_readiness_command"]
    assert "--execute" in payload["api_execute_command"]
    assert "record_ai_visibility_probe.py" in payload["record_probe_command"]


def test_ai_visibility_weekly_report_blocks_known_brand_collisions(synced_client):
    for platform in ("chatgpt", "claude", "grok"):
        response = synced_client.post(
            "/api/growth/ai-visibility/checks",
            json={
                "query": "What is Synapse Network for AI agents?",
                "platform": platform,
                "answer_summary": f"{platform} cites Synapse but also surfaces a collision.",
                "synapse_mentioned": True,
                "synapse_cited": True,
                "cited_urls": ["https://www.synapse-network.ai/"],
                "competitor_mentions": ["synapsenetwork.xyz"]
                if platform == "chatgpt"
                else [],
                "next_action": "Strengthen brand disambiguation copy.",
                "feed_key": "brand_disambiguation_www",
                "run_group": "2026-06-05-brand-collision-check",
            },
        )
        assert response.status_code == 201

    report = synced_client.get("/api/growth/ai-visibility/weekly-report")

    assert report.status_code == 200
    payload = report.json()
    assert payload["covered_platforms"] == ["chatgpt", "claude", "grok"]
    assert payload["stable_positive_runs"] == 0
    assert any(
        "synapsenetwork.xyz" in blocker for blocker in payload["blockers"]
    )
    assert any(
        "disambiguation copy" in action and "synapsenetwork.xyz" in action
        for action in payload["next_actions"]
    )
    comparison = synced_client.get(
        "/api/growth/ai-visibility/comparisons"
        "?feed_key=brand_disambiguation_www"
        "&run_group=2026-06-05-brand-collision-check"
    )
    comparison_payload = comparison.json()["items"][0]
    assert comparison_payload["citation_quality_status"] == "brand_collision_present"
    assert comparison_payload["known_collision_competitors"] == ["synapsenetwork.xyz"]
    assert comparison_payload["official_cited_urls"] == [
        "https://www.synapse-network.ai/"
    ]


def test_growth_ai_visibility_external_probe_gate_partial_ready(
    monkeypatch,
    synced_client,
):
    from scripts.growth.record_ai_visibility_probe import ProbeRecord

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-anthropic-secret")
    monkeypatch.delenv("XAI_API_KEY", raising=False)

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
    assert payload["missing_platforms"] == ["grok"]
    assert "--platforms chatgpt,claude" in payload["partial_api_readiness_command"]
    assert "--platforms chatgpt,claude" in payload["partial_api_execute_command"]
    assert "--platforms chatgpt,claude,grok" in payload["api_readiness_command"]
    assert "--platforms chatgpt,claude,grok" in payload[
        "manual_probe_template_command"
    ]
    assert "grok missing XAI_API_KEY." in payload["blockers"]
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
    assert payload["ready_platforms"] == ["chatgpt", "claude", "grok"]
    assert payload["missing_platforms"] == []
    assert all(item["configured"] for item in payload["provider_readiness"])
    assert "generate_ai_visibility_probe_template.py" in payload[
        "manual_probe_template_command"
    ]
    assert "sk-test-openai-secret" not in rendered
    assert "sk-test-anthropic-secret" not in rendered
    assert "xai-test-secret" not in rendered


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
