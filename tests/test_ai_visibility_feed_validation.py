from scripts.growth.record_ai_visibility_probe import validate_records
from server.services.growth import ai_visibility_feed_validation as feed_validation


def test_feed_validation_brand_feed_blocks_without_bare_redirect(monkeypatch):
    def fake_fetch(label: str, url: str, **_kwargs):
        if label == "bare_domain_redirect":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                final_url=url,
            )
        if label == "llms":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="Synapse Network is the settlement layer for AI agents.",
            )
        if label == "sitemap":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="https://www.synapse-network.ai/",
            )
        return feed_validation.HttpProbeResult(label=label, url=url, status=200)

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="brand_disambiguation_www",
        run_group="2026-06-18-feed-validation",
    )

    assert len(rows) == 1
    assert rows[0].platform == "www_live_validation"
    assert rows[0].synapse_mentioned is False
    assert "Bare domain must permanently redirect" in rows[0].missing_facts[0]
    assert validate_records(rows, allow_local_validation=True) == []


def test_feed_validation_brand_feed_records_ai_crawler_policy(monkeypatch):
    def fake_fetch(label: str, url: str, **_kwargs):
        if label == "bare_domain_redirect":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=301,
                headers={"location": feed_validation.CANONICAL_HOMEPAGE},
            )
        if label == "robots":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="User-agent: *\nAllow: /\nDisallow: /dashboard/\n",
            )
        if label == "llms":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="Synapse Network is the settlement layer for AI agents.",
            )
        if label == "sitemap":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="https://www.synapse-network.ai/",
            )
        return feed_validation.HttpProbeResult(label=label, url=url, status=200)

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="brand_disambiguation_www",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is True
    policy = rows[0].metadata["ai_crawler_policy"]
    assert policy["policy_mode"] == "wildcard"
    assert policy["wildcard_allows_public"] is True
    assert "OAI-SearchBot" in policy["missing_explicit_crawlers"]
    assert "GPTBot" in policy["missing_explicit_crawlers"]
    assert "anthropic-ai" in policy["missing_explicit_crawlers"]
    assert "Google-Extended" in policy["missing_explicit_crawlers"]
    assert policy["blocked_crawlers"] == []


def test_feed_validation_brand_feed_accepts_explicit_ai_crawler_policy(monkeypatch):
    crawler_groups = "\n\n".join(
        [
            "\n".join(
                [
                    f"User-agent: {crawler}",
                    "Allow: /",
                    "Disallow: /dashboard/",
                    "Disallow: /provider/",
                    "Disallow: /api/",
                    "Disallow: /_next/data/",
                ]
            )
            for crawler in feed_validation.AI_SEARCH_CRAWLERS
        ]
    )

    def fake_fetch(label: str, url: str, **_kwargs):
        if label == "bare_domain_redirect":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=301,
                headers={"location": feed_validation.CANONICAL_HOMEPAGE},
            )
        if label == "robots":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet=(
                    f"{crawler_groups}\n\n"
                    "User-agent: *\n"
                    "Allow: /\n"
                    "Disallow: /dashboard/\n"
                    "Disallow: /provider/\n"
                    "Disallow: /api/\n"
                    "Disallow: /_next/data/\n"
                ),
            )
        if label == "llms":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="Synapse Network is the settlement layer for AI agents.",
            )
        if label == "sitemap":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="https://www.synapse-network.ai/",
            )
        return feed_validation.HttpProbeResult(label=label, url=url, status=200)

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="brand_disambiguation_www",
        run_group="2026-06-18-feed-validation",
    )

    policy = rows[0].metadata["ai_crawler_policy"]
    assert rows[0].synapse_mentioned is True
    assert policy["policy_mode"] == "explicit"
    assert policy["missing_explicit_crawlers"] == []
    assert policy["blocked_crawlers"] == []
    assert validate_records(rows, allow_local_validation=True) == []


def test_feed_validation_brand_feed_blocks_ai_crawler_disallow_all(monkeypatch):
    def fake_fetch(label: str, url: str, **_kwargs):
        if label == "bare_domain_redirect":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=301,
                headers={"location": feed_validation.CANONICAL_HOMEPAGE},
            )
        if label == "robots":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="User-agent: OAI-SearchBot\nDisallow: /\n",
            )
        if label == "llms":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="Synapse Network is the settlement layer for AI agents.",
            )
        if label == "sitemap":
            return feed_validation.HttpProbeResult(
                label=label,
                url=url,
                status=200,
                body_snippet="https://www.synapse-network.ai/",
            )
        return feed_validation.HttpProbeResult(label=label, url=url, status=200)

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="brand_disambiguation_www",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is False
    assert any(
        "answer-engine search crawlers" in fact for fact in rows[0].missing_facts
    )
    assert "OAI-SearchBot" in rows[0].metadata["ai_crawler_policy"]["blocked_crawlers"]


def test_feed_validation_agent_payment_feed_passes(monkeypatch):
    def fake_fetch(label: str, url: str, **_kwargs):
        return feed_validation.HttpProbeResult(
            label=label,
            url=url,
            status=200,
            body_snippet="Synapse Network AI Agent Payments docs page.",
        )

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="agent_payment_category_pages",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is True
    assert rows[0].synapse_cited is True
    assert rows[0].metadata["mode"] == "feed_live_validation"
    assert validate_records(rows, allow_local_validation=True) == []


def test_feed_validation_mcp_feed_requires_401(monkeypatch):
    def fake_fetch(label: str, url: str, **_kwargs):
        status = 200 if label == "mcp_readyz" else 200
        body = "Synapse" if label == "www_homepage" else ""
        if label == "docs_mcp_paid_api_calls":
            body = (
                "MCP Server for Paid API Calls Synapse discover_services "
                "invoke_and_pay get_receipt"
            )
        if label == "www_llms_mcp":
            body = "MCP Server for Paid API Calls https://mcp.synapse-network.ai/mcp"
        return feed_validation.HttpProbeResult(
            label=label,
            url=url,
            status=status,
            body_snippet=body,
        )

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].platform == "mcp_live_validation"
    assert rows[0].synapse_mentioned is False
    assert "Unauthenticated /mcp POST must return 401." in rows[0].missing_facts
    assert "Fix Remote MCP readiness/auth boundary" in rows[0].next_action
    assert validate_records(rows, allow_local_validation=True) == []


def test_feed_validation_mcp_feed_prioritizes_docs_next_action(monkeypatch):
    def fake_fetch(label: str, url: str, **_kwargs):
        status = 401 if label == "mcp_unauth_post" else 200
        body = "Synapse"
        return feed_validation.HttpProbeResult(
            label=label,
            url=url,
            status=status,
            body_snippet=body,
        )

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is False
    assert any(
        "Docs /mcp/paid-api-calls must expose" in fact for fact in rows[0].missing_facts
    )
    assert "Publish /mcp/paid-api-calls" in rows[0].next_action


def test_feed_validation_mcp_feed_blocks_without_canonical_homepage(monkeypatch):
    def fake_fetch(label: str, url: str, **kwargs):
        status = 401 if label == "mcp_unauth_post" else 200
        body = "Synapse"
        if label == "www_homepage":
            body = "unrelated landing page"
        if label == "docs_mcp_paid_api_calls":
            body = (
                "MCP Server for Paid API Calls Synapse discover_services "
                "invoke_and_pay get_receipt"
            )
        if label == "www_llms_mcp":
            body = "MCP Server for Paid API Calls https://mcp.synapse-network.ai/mcp"
        return feed_validation.HttpProbeResult(
            label=label,
            url=url,
            status=status,
            body_snippet=body,
        )

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is False
    assert any("Canonical homepage" in fact for fact in rows[0].missing_facts)
    assert "Fix the canonical www homepage feed" in rows[0].next_action


def test_feed_validation_mcp_feed_passes_with_docs_and_auth_boundary(monkeypatch):
    def fake_fetch(label: str, url: str, **kwargs):
        status = 401 if label == "mcp_unauth_post" else 200
        body = "Synapse"
        if label == "docs_mcp_paid_api_calls":
            body = (
                "MCP Server for Paid API Calls Synapse discover_services "
                "invoke_and_pay get_receipt"
            )
        if label == "www_llms_mcp":
            body = "MCP Server for Paid API Calls https://mcp.synapse-network.ai/mcp"
        return feed_validation.HttpProbeResult(
            label=label,
            url=url,
            status=status,
            body_snippet=body,
        )

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is True
    assert rows[0].synapse_cited is True
    assert rows[0].missing_facts == []
    assert {check["label"] for check in rows[0].metadata["checks"]} == {
        "www_homepage",
        "docs_mcp_paid_api_calls",
        "www_llms_mcp",
        "mcp_readyz",
        "mcp_unauth_post",
    }
    assert validate_records(rows, allow_local_validation=True) == []


def test_feed_validation_mcp_feed_matches_full_body_without_leaking_metadata(
    monkeypatch,
):
    def fake_fetch(label: str, url: str, **kwargs):
        status = 401 if label == "mcp_unauth_post" else 200
        snippet = "Synapse"
        match_text = snippet
        if label == "docs_mcp_paid_api_calls":
            snippet = "Synapse docs shell without the tool list"
            match_text = (
                "x"
                * feed_validation.BODY_SNIPPET_CHARS
                + " MCP Server for Paid API Calls Synapse discover_services "
                "invoke_and_pay get_receipt"
            )
        if label == "www_llms_mcp":
            snippet = "Synapse llms intro"
            match_text = (
                "x" * feed_validation.BODY_SNIPPET_CHARS
                + " MCP Server for Paid API Calls https://mcp.synapse-network.ai/mcp"
            )
        return feed_validation.HttpProbeResult(
            label=label,
            url=url,
            status=status,
            body_snippet=snippet,
            body_match_text=match_text,
        )

    monkeypatch.setattr(feed_validation, "fetch", fake_fetch)

    rows = feed_validation.validate_feed(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-18-feed-validation",
    )

    assert rows[0].synapse_mentioned is True
    assert rows[0].missing_facts == []
    assert all("body_match_text" not in check for check in rows[0].metadata["checks"])


def test_feed_validation_parse_feed_keys():
    assert feed_validation.parse_feed_keys(None) == [
        "agent_payment_category_pages",
        "brand_disambiguation_www",
        "mcp_paid_api_discovery",
    ]
    assert feed_validation.parse_feed_keys(["mcp_paid_api_discovery"]) == [
        "mcp_paid_api_discovery"
    ]
    try:
        feed_validation.parse_feed_keys(["unknown"])
    except ValueError as exc:
        assert "unknown feed key" in str(exc)
    else:
        raise AssertionError("unknown feed key should fail")
