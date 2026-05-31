from __future__ import annotations

from typing import Any

from server.schemas_growth import GrowthSourceConfigCreate

DEFAULT_SOURCE_KEY = "agent_api_mcp_provider_discovery"


def default_source_body() -> GrowthSourceConfigCreate:
    return GrowthSourceConfigCreate(
        config_key=DEFAULT_SOURCE_KEY,
        name="Provider Discovery: MCP + API Services",
        config_type="github_mcp_repos",
        status="enabled",
        description="Find API/MCP providers that agents can invoke through metered Synapse rails.",
        query={
            "queries": [
                "mcp server search api",
                "model-context-protocol web scraping API",
                "agent tools API",
            ],
            "seed_urls": ["https://github.com/firecrawl/firecrawl-mcp-server"],
            "lead_type": "provider",
            "send_policy": "manual_gmail_draft_only",
            "max_results": 25,
        },
        cadence={"cadence": "daily", "suggested_local_time": "10:30"},
        thresholds={"create_lead_score": 70, "auto_draft_score": 80},
    )


def firecrawl_candidate() -> dict[str, Any]:
    return {
        "name": "Firecrawl",
        "organization": "Firecrawl",
        "source_kind": "github",
        "source_url": "https://github.com/firecrawl/firecrawl-mcp-server",
        "fit_score": 92,
        "confidence_score": 86,
        "next_action": "Draft provider onboarding message",
        "why_this_provider": "Firecrawl exposes web search, scrape, crawl, and extraction tools through an official MCP server, making it a strong metered API provider candidate for agent workflows.",
        "contact_channels": [
            {
                "kind": "email",
                "value": "partnerships@firecrawl.dev",
                "confidence": "high",
                "source_url": "https://docs.firecrawl.dev/partner-integration",
                "provenance": "official_partner_docs",
            }
        ],
        "contact_provenance": [
            {
                "source_url": "https://docs.firecrawl.dev/partner-integration",
                "reason": "Official partner docs ask partner applicants to email partnerships@firecrawl.dev.",
                "confidence": "high",
            },
            {
                "source_url": "https://www.firecrawl.dev/partner-program",
                "reason": "Official partner page lists partnerships@firecrawl.dev.",
                "confidence": "high",
            },
        ],
        "evidence": [
            {"source": "github", "reason": "Official MCP server for search, scrape, crawl, and extraction."},
            {"source": "readme", "reason": "Uses API keys and agent-ready web data workflows."},
            {"source": "partner_docs", "reason": "Public partner contact is available for partnership review."},
        ],
        "provider_scorecard": {
            "public_api": True,
            "mcp_server": True,
            "agent_native": True,
            "usage_based_fit": True,
            "docs_quality": "strong",
        },
    }


def tavily_candidate() -> dict[str, Any]:
    item = firecrawl_candidate()
    item.update(
        {
            "name": "Tavily",
            "organization": "Tavily",
            "source_url": "https://github.com/tavily-ai/tavily-mcp",
            "fit_score": 88,
            "why_this_provider": "Tavily provides search, extract, map, and crawl tools for AI agents through MCP.",
            "contact_channels": [],
            "contact_provenance": [],
        }
    )
    return item
