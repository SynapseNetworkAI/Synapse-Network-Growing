from scripts.growth.generate_ai_visibility_probe_template import (
    default_queries_for_feed,
    official_source_urls_for_feed,
)
from server.services.growth.ai_visibility_official_sources import (
    ai_visibility_official_sources,
    is_official_citation_url,
)
from server.services.growth.ai_visibility_plan import ai_visibility_feed_packages


COMPARISON_QUERY = "SynapseNetwork MCP vs paid MCP alternatives"
COMPARISON_URL = "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp"
MCP_MARKETPLACE_URL = (
    "https://mcp-marketplace.io/server/"
    "io-github-synapsenetworkai-synapse-network-mcp-server"
)
OFFICIAL_HOMEPAGE = "https://www.synapse-network.ai/"


def test_mcp_paid_api_feed_tracks_comparison_query_and_docs_page():
    package = ai_visibility_feed_packages("mcp_paid_api_discovery").items[0]
    chatgpt_strategy = next(
        strategy
        for strategy in package.platform_strategies
        if strategy.platform == "chatgpt"
    )

    assert package.canonical_domain == OFFICIAL_HOMEPAGE
    assert COMPARISON_QUERY in package.target_queries
    assert COMPARISON_QUERY in chatgpt_strategy.probe_queries
    assert COMPARISON_URL in {asset.target for asset in package.publish_assets}
    assert MCP_MARKETPLACE_URL in {asset.target for asset in package.publish_assets}
    assert any(COMPARISON_URL in command for command in package.validation_commands)


def test_mcp_paid_api_probe_defaults_include_comparison_source():
    source_urls = official_source_urls_for_feed("mcp_paid_api_discovery")

    assert COMPARISON_QUERY in default_queries_for_feed("mcp_paid_api_discovery")
    assert OFFICIAL_HOMEPAGE in source_urls
    assert COMPARISON_URL in source_urls
    assert MCP_MARKETPLACE_URL in source_urls


def test_mcp_paid_api_official_sources_include_non_blocking_comparison_page():
    sources = {
        item.surface_key: item for item in ai_visibility_official_sources().items
    }
    comparison = sources["docs_mcp_paid_api_comparison"]
    marketplace = sources["mcp_marketplace_listing"]

    assert comparison.canonical_url == COMPARISON_URL
    assert comparison.feed_keys == ["mcp_paid_api_discovery"]
    assert comparison.required_for_success is False
    assert marketplace.canonical_url == MCP_MARKETPLACE_URL
    assert marketplace.feed_keys == ["mcp_paid_api_discovery"]
    assert marketplace.required_for_success is False


def test_mcp_registry_citation_requires_synapse_network_mcp_identifier():
    assert is_official_citation_url(
        "https://registry.modelcontextprotocol.io/v0.1/servers"
        "?search=io.github.SynapseNetworkAI/synapse-network-mcp-server"
    )
    assert is_official_citation_url(
        "https://registry.modelcontextprotocol.io/?q=%40synapse-network-ai%2Fmcp-server"
    )

    assert not is_official_citation_url(
        "https://registry.modelcontextprotocol.io/?q=io.github.MPP32%2Fmpp32-mcp-server"
    )
    assert not is_official_citation_url("https://registry.modelcontextprotocol.io/")
