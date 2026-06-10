"""Observed source-host recommendation helpers for AI visibility probes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from server.services.growth.ai_visibility_feed_diagnosis_models import (
    SourceHostExecution,
    TARGET_PLATFORMS,
)
from server.services.growth.ai_visibility_text import unique_strings


OBSERVED_SOURCE_HOST_ACTIONS = {
    "aitoolnet.com": {
        "surface": "aitoolnet",
        "draft_type": "ai_tool_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": "AIToolNet appeared in answer-engine source hosts for paid-MCP alternative queries, so Synapse needs a matching AI tool directory listing.",
        "brief": (
            "Submit SynapseNetwork MCP Server to AIToolNet with website, GitHub, "
            "Remote MCP endpoint, npm package, and the discover_services / "
            "invoke_and_pay / get_receipt tool loop. Mark the action complete "
            "only after browser/form confirmation or a public listing exists."
        ),
        "validation": (
            "Record AIToolNet browser/form confirmation or public listing URL; "
            "CLI probes may receive site-level 403."
        ),
    },
    "alternativeto.net": {
        "surface": "alternativeto",
        "draft_type": "software_alternative_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": "AlternativeTo appeared in answer-engine source hosts for paid-MCP alternative queries, so Synapse needs a software-alternative listing.",
        "brief": (
            "Submit SynapseNetwork MCP Server to AlternativeTo as a developer/API/"
            "payment alternative for agent-paid API calls. Include GitHub, docs, "
            "Remote MCP endpoint, npm package, and the three-tool payment loop."
        ),
        "validation": (
            "Record AlternativeTo browser/form confirmation or public listing URL; "
            "CLI probes may receive site-level 403."
        ),
    },
    "mcp.directory": {
        "surface": "mcp_directory",
        "draft_type": "mcp_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": "MCP Directory appeared repeatedly in answer-engine source hosts for paid-MCP discovery queries, so Synapse needs a matching MCP directory listing.",
        "brief": (
            "Submit SynapseNetwork MCP Server to MCP Directory with the hosted "
            "Remote MCP endpoint, GitHub repository, npm package, docs URL, "
            "and discover_services / invoke_and_pay / get_receipt tool loop."
        ),
        "validation": (
            "Record MCP Directory browser/form confirmation or public listing URL; "
            "do not count source-host intent as external citation evidence."
        ),
    },
    "mcpservers.org": {
        "surface": "mcpservers",
        "draft_type": "mcp_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": "MCPServers appeared in answer-engine source hosts for paid-MCP discovery queries, so Synapse needs a matching MCP directory listing.",
        "brief": (
            "Submit SynapseNetwork MCP Server to MCPServers with the hosted "
            "Remote MCP endpoint, GitHub repository, npm package, docs URL, "
            "and discover_services / invoke_and_pay / get_receipt tool loop."
        ),
        "validation": (
            "Record MCPServers browser/form confirmation or public listing URL; "
            "do not count source-host intent as external citation evidence."
        ),
    },
    "lobehub.com": {
        "surface": "lobehub",
        "draft_type": "mcp_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "LobeHub appeared in ChatGPT source hosts for paid-MCP discovery "
            "queries, so Synapse needs a fresh LobeHub MCP marketplace listing "
            "with hosted Remote MCP and official metadata."
        ),
        "brief": (
            "Verify or refresh the SynapseNetwork MCP Server listing on LobeHub "
            "with the hosted Remote MCP endpoint, GitHub repository, npm package, "
            "docs URL, and discover_services / invoke_and_pay / get_receipt tool loop."
        ),
        "validation": (
            "Record the LobeHub public listing URL and matched canonical terms; "
            "do not count source-host intent as external citation evidence."
        ),
    },
    "mcpfind.org": {
        "surface": "mcpfind",
        "draft_type": "mcp_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": "MCPFind appeared in public search results for paid-MCP discovery queries, so Synapse needs a matching MCP directory listing.",
        "brief": (
            "Submit SynapseNetwork MCP Server to MCPFind with the hosted Remote "
            "MCP endpoint, GitHub repository, npm package, docs URL, and "
            "discover_services / invoke_and_pay / get_receipt tool loop."
        ),
        "validation": (
            "Record MCPFind browser/form confirmation or public listing URL; "
            "do not count source-host intent as external citation evidence."
        ),
    },
    "protodex.io": {
        "surface": "protodex",
        "draft_type": "mcp_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "Protodex is a public MCP server index with GitHub issue submission, "
            "so Synapse needs a matching MCP directory listing for AI and MCP "
            "client discovery."
        ),
        "brief": (
            "Submit SynapseNetwork MCP Server to Protodex with the public GitHub "
            "repository, API Integration category, hosted Remote MCP endpoint, npm "
            "package, docs URL, and discover_services / invoke_and_pay / "
            "get_receipt tool loop."
        ),
        "validation": (
            "Record the Protodex GitHub issue URL or public listing URL; do not "
            "count source-host intent as external citation evidence."
        ),
    },
    "pulsemcp.com": {
        "surface": "pulsemcp",
        "draft_type": "mcp_directory_listing",
        "priority": "p1",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "PulseMCP is a live MCP directory surface that exposes official "
            "server.json and Remote MCP metadata, so Synapse should keep its "
            "listing fresh for MCP client and answer-engine discovery."
        ),
        "brief": (
            "Verify the PulseMCP SynapseNetwork listing and refresh upstream "
            "server.json or MCP Registry metadata if the Remote MCP endpoint, "
            "npm package, tools, or auth boundary drift."
        ),
        "validation": (
            "Record the PulseMCP public listing URL and matched canonical terms; "
            "do not count source-host intent as external citation evidence."
        ),
    },
    "python-docs.synapse.org": {
        "surface": "docs_disambiguation_links",
        "draft_type": "brand_disambiguation_answer_block",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "ChatGPT cited Synapse.org biomedical documentation for exact "
            "SynapseNetwork MCP queries, so Synapse Network needs stronger "
            "owned disambiguation language on docs, README, and registry surfaces."
        ),
        "brief": (
            "Refresh official Synapse Network MCP source hosts with an explicit "
            "disambiguation block: Synapse Network at synapse-network.ai is the "
            "agent-payment and Remote MCP product, not Synapse.org/Sage "
            "Bionetworks biomedical data infrastructure. Repeat the exact "
            "identifiers SynapseNetworkAI/Synapse-Network-MCP-Server, "
            "io.github.SynapseNetworkAI/synapse-network-mcp-server, and "
            "https://mcp.synapse-network.ai/mcp."
        ),
        "validation": (
            "Verify official docs, GitHub README, and MCP Registry metadata carry "
            "the disambiguation block, then rerun exact identifier probes."
        ),
    },
}


class ObservedSourceHostsResult(BaseModel):
    hosts_by_surface: dict[str, list[str]] = Field(default_factory=dict)


def observed_source_host_recommendations(
    *, external_records: list[Any], rerun: str
) -> list[SourceHostExecution]:
    recommendations = []
    observed = observed_hosts_by_surface(external_records).hosts_by_surface
    for host, config in OBSERVED_SOURCE_HOST_ACTIONS.items():
        queries = observed.get(host)
        if not queries:
            continue
        recommendations.append(
            SourceHostExecution(
                surface=config["surface"],
                draft_type=config["draft_type"],
                priority=config["priority"],
                target_platforms=[
                    item for item in config["platforms"] if item in TARGET_PLATFORMS
                ],
                target_queries=queries[:8],
                rationale=config["rationale"],
                content_brief=config["brief"],
                validation_command=config["validation"],
                next_probe_command=rerun,
            )
        )
    return recommendations


def observed_hosts_by_surface(
    external_records: list[Any],
) -> ObservedSourceHostsResult:
    result: dict[str, list[str]] = {}
    for record in external_records:
        metadata = getattr(record, "metadata", {}) or {}
        hosts = metadata.get("source_hosts") if isinstance(metadata, dict) else []
        if not isinstance(hosts, list):
            continue
        for host in hosts:
            normalized = normalize_host(host)
            if not normalized:
                continue
            result.setdefault(normalized, [])
            result[normalized] = unique_strings(result[normalized] + [record.query])
    return ObservedSourceHostsResult(hosts_by_surface=result)


def normalize_host(value: object) -> str:
    host = str(value or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host
