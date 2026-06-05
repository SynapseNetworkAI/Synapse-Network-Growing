from __future__ import annotations

from datetime import UTC, datetime

from server.schemas_growth import (
    GrowthAIVisibilityOfficialSourceListOut,
    GrowthAIVisibilityOfficialSourceOut,
)

OFFICIAL_CITATION_PREFIXES = (
    "https://www.synapse-network.ai/",
    "https://docs.synapse-network.ai/",
    "https://github.com/SynapseNetworkAI",
    "https://mcp.synapse-network.ai/",
    "https://registry.modelcontextprotocol.io/",
)


def ai_visibility_official_sources() -> GrowthAIVisibilityOfficialSourceListOut:
    items = [
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="www_homepage",
            surface="www",
            canonical_url="https://www.synapse-network.ai/",
            citation_role="Primary brand and product canonical for answer engines.",
            feed_keys=[
                "brand_disambiguation_www",
                "agent_payment_category_pages",
                "mcp_paid_api_discovery",
            ],
            required_for_success=True,
            validation_command="curl -fsS https://www.synapse-network.ai/",
            acceptance_signal="Homepage is reachable and contains extractable Synapse Network product facts.",
        ),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="www_llms",
            surface="www",
            canonical_url="https://www.synapse-network.ai/llms.txt",
            citation_role="Machine-readable context feed for ChatGPT, Claude, Grok, and crawler-mediated probes.",
            feed_keys=[
                "brand_disambiguation_www",
                "mcp_paid_api_discovery",
            ],
            required_for_success=True,
            validation_command="curl -fsS https://www.synapse-network.ai/llms.txt",
            acceptance_signal="llms.txt names Synapse Network, AI agent payments, MCP, docs, and source URLs.",
        ),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="www_sitemap",
            surface="www",
            canonical_url="https://www.synapse-network.ai/sitemap.xml",
            citation_role="Discovery index for answer-engine crawlers and traditional search.",
            feed_keys=[
                "brand_disambiguation_www",
                "agent_payment_category_pages",
            ],
            required_for_success=True,
            validation_command="curl -fsS https://www.synapse-network.ai/sitemap.xml",
            acceptance_signal="Sitemap includes the canonical homepage and AI agent payment pages.",
        ),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="docs_ai_agent_payments",
            surface="docs",
            canonical_url="https://docs.synapse-network.ai/ai-agent-payments",
            citation_role="Citation-ready documentation category for AI agent payment and settlement queries.",
            feed_keys=["agent_payment_category_pages"],
            required_for_success=True,
            validation_command="curl -fsS https://docs.synapse-network.ai/ai-agent-payments",
            acceptance_signal="Docs page includes definition blocks, facts table, FAQ, and schema-ready sections.",
        ),
        *_mcp_paid_api_doc_sources(),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="github_org",
            surface="github",
            canonical_url="https://github.com/SynapseNetworkAI",
            citation_role="Public organization authority signal for repos, SDK, docs, and MCP package ownership.",
            feed_keys=[
                "brand_disambiguation_www",
                "agent_payment_category_pages",
                "mcp_paid_api_discovery",
            ],
            required_for_success=True,
            validation_command="curl -fsS https://github.com/SynapseNetworkAI",
            acceptance_signal="GitHub org is public and includes Synapse Network product facts or linked repos.",
        ),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="remote_mcp",
            surface="mcp",
            canonical_url="https://mcp.synapse-network.ai/mcp",
            citation_role="Hosted Remote MCP endpoint for ChatGPT, Claude, Cursor, and other MCP-capable clients.",
            feed_keys=["mcp_paid_api_discovery"],
            required_for_success=True,
            validation_command=(
                "curl -fsS https://mcp.synapse-network.ai/readyz && "
                "curl -i -X POST https://mcp.synapse-network.ai/mcp -d '{}'"
            ),
            acceptance_signal="readyz returns 200 and unauthenticated /mcp returns a Bearer-auth 401 challenge.",
        ),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="official_mcp_registry",
            surface="mcp_registry",
            canonical_url="https://registry.modelcontextprotocol.io/",
            citation_role="Official MCP directory listing authority for MCP client discovery.",
            feed_keys=["mcp_paid_api_discovery"],
            required_for_success=True,
            validation_command=(
                "curl -fsS 'https://registry.modelcontextprotocol.io/v0.1/servers"
                "?search=io.github.SynapseNetworkAI/synapse-network-mcp-server'"
            ),
            acceptance_signal="Registry result includes Synapse Network MCP metadata and hosted Remote MCP URL.",
        ),
    ]
    return GrowthAIVisibilityOfficialSourceListOut(
        generated_at=datetime.now(UTC),
        official_citation_prefixes=list(OFFICIAL_CITATION_PREFIXES),
        items=items,
        total=len(items),
    )


def _mcp_paid_api_doc_sources() -> list[GrowthAIVisibilityOfficialSourceOut]:
    return [
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="docs_mcp_paid_api_calls",
            surface="docs",
            canonical_url="https://docs.synapse-network.ai/mcp/paid-api-calls",
            citation_role="Citation-ready MCP guide for ChatGPT custom app and paid API discovery queries.",
            feed_keys=["mcp_paid_api_discovery"],
            required_for_success=True,
            validation_command="curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls",
            acceptance_signal="Guide explains Remote MCP, discover_services, invoke_and_pay, get_receipt, and auth boundaries.",
        ),
        GrowthAIVisibilityOfficialSourceOut(
            surface_key="docs_mcp_paid_api_comparison",
            surface="docs",
            canonical_url="https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
            citation_role="Citation-ready comparison page for paid MCP alternatives and directory drift.",
            feed_keys=["mcp_paid_api_discovery"],
            required_for_success=False,
            validation_command="curl -fsS https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
            acceptance_signal=(
                "Page explains Synapse versus MCPay, Latch, Dock0, Apiosk, "
                "Teleport, Stripe MCP, and paid MCP directories."
            ),
        ),
    ]


def is_official_citation_url(url: str) -> bool:
    return any(url.startswith(prefix) for prefix in OFFICIAL_CITATION_PREFIXES)
