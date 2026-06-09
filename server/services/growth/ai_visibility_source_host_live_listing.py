"""Live-listing verification guidance for AI visibility source hosts."""

from __future__ import annotations

from server.services.growth.ai_visibility_source_host_surfaces import (
    source_host_surface,
)

DIRECTORY_LIVE_SEARCH_URLS = {
    "mcp.directory": [
        "https://mcp.directory/?q=Synapse%20Network",
        "https://mcp.directory/?q=SynapseNetwork%20MCP%20Server",
    ],
    "alternativeto.net": [
        "https://alternativeto.net/browse/search/?q=SynapseNetwork%20MCP%20Server",
        "https://alternativeto.net/browse/search/?q=Synapse%20Network%20MCP",
    ],
    "aitoolnet.com": [
        "https://www.aitoolnet.com/search?q=SynapseNetwork%20MCP%20Server",
        "https://www.aitoolnet.com/search?q=Synapse%20Network%20Remote%20MCP",
    ],
    "glama.ai": [
        "https://glama.ai/mcp/servers?query=Synapse%20Network%20MCP",
        "https://glama.ai/mcp/servers?query=SynapseNetwork%20MCP%20Server",
    ],
    "mcpservers.org": [
        "https://mcpservers.org/?q=Synapse%20Network",
        "https://mcpservers.org/?q=SynapseNetwork%20MCP%20Server",
    ],
    "mcpfind.org": [
        "https://mcpfind.org/?q=Synapse%20Network",
        "https://mcpfind.org/?q=SynapseNetwork%20MCP%20Server",
    ],
    "mcp-marketplace.io": [
        "https://mcp-marketplace.io/?q=Synapse%20Network",
        "https://mcp-marketplace.io/?q=SynapseNetwork%20MCP%20Server",
    ],
    "protodex.io": [
        "https://protodex.io/?q=Synapse%20Network",
        "https://protodex.io/?q=SynapseNetwork%20MCP%20Server",
    ],
    "pulsemcp.com": [
        "https://www.pulsemcp.com/servers/synapse-network",
        "https://www.pulsemcp.com/search?q=SynapseNetwork%20MCP%20Server",
    ],
}


def live_listing_search_urls(
    *,
    host: str,
    draft_type: str,
    target_url: str,
) -> list[str]:
    if draft_type != "directory_submission":
        return []
    return DIRECTORY_LIVE_SEARCH_URLS.get(host, [f"{target_url.rstrip('/')}/"])


def live_listing_validation_steps(*, host: str, draft_type: str) -> list[str]:
    if draft_type != "directory_submission":
        return []
    surface = source_host_surface(host)
    return [
        "Open the search URLs and confirm a public listing page, not only a submitted form receipt.",
        "Verify the public page includes Synapse Network, the Remote MCP endpoint, GitHub or npm, and at least one tool name.",
        (
            "Record the public listing with "
            "record_ai_visibility_source_host_execution.py "
            f"--surface {surface} --evidence-mode live-listing --source-url <public-listing-url>."
        ),
        "Rerun the unchanged answer-engine probe matrix only after live-listing evidence is recorded.",
    ]
