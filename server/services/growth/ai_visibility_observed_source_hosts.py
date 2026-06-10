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
    "apiosk.com": {
        "surface": "apiosk_com",
        "draft_type": "api_monetization_source_host_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "grok", "gemini"],
        "rationale": (
            "Apiosk appeared in ChatGPT source hosts for AI-agent payment and "
            "API-provider monetization queries, so Synapse needs a targeted "
            "comparison or truthful listing path for this answer-engine route."
        ),
        "brief": (
            "Audit Apiosk as an API monetization source host and refresh owned "
            "comparison copy that explains Synapse Network for AI-agent paid API "
            "calls, Remote MCP discovery, scoped credentials, receipts, and USDC "
            "settlement. If Apiosk has a listing, partner, or correction path, "
            "record the browser/form evidence before treating it as submitted."
        ),
        "validation": (
            "Record Apiosk public audit evidence plus either a listing/correction "
            "submission confirmation or the owned comparison refresh URL; rerun "
            "the unchanged payment/API-provider probes after the source-host "
            "change is live."
        ),
    },
    "chat.mcp.so": {
        "surface": "chat_mcp_so",
        "draft_type": "mcp_search_surface_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "chat.mcp.so appeared in ChatGPT source hosts for exact "
            "SynapseNetwork MCP queries, so Synapse needs a verified listing "
            "or recorded no-public-submit path on this MCP search/chat surface."
        ),
        "brief": (
            "Inspect chat.mcp.so for a SynapseNetwork MCP Server result or "
            "submission/correction path. Use exact identifiers: "
            "SynapseNetworkAI/Synapse-Network-MCP-Server, "
            "io.github.SynapseNetworkAI/synapse-network-mcp-server, "
            "https://mcp.synapse-network.ai/mcp, and the "
            "discover_services / invoke_and_pay / get_receipt tool loop. If no "
            "public listing path exists, record the boundary and strengthen "
            "mcp.so, official registry, GitHub README, and docs disambiguation."
        ),
        "validation": (
            "Record the chat.mcp.so public listing URL, correction/submission "
            "path, or no-public-submit evidence; rerun exact identifier probes "
            "after a listing or upstream metadata change."
        ),
    },
    "dock0.dev": {
        "surface": "dock0_dev",
        "draft_type": "competitor_source_host_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "dock0.dev appeared in ChatGPT source hosts for exact "
            "SynapseNetwork MCP paid-API queries, so Synapse needs competitor "
            "positioning and source-host evidence for this answer-engine path."
        ),
        "brief": (
            "Audit dock0.dev as a competitor/control source host. Record whether "
            "it has llms.txt, sitemap, MCP/payment positioning, partner/contact "
            "paths, or comparison hooks. Do not ask for an unrelated listing; "
            "use the findings to refresh Synapse owned comparison copy and "
            "source-host probes."
        ),
        "validation": (
            "Record dock0.dev public audit evidence and the owned comparison "
            "copy update or decision not to pursue direct outreach."
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
    "mcp.so": {
        "surface": "mcp_so",
        "draft_type": "mcp_directory_listing",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "mcp.so appeared in exact SynapseNetwork MCP answer sources, so "
            "Synapse needs either a corrected public listing or a recorded "
            "review path that uses the exact SynapseNetworkAI identifiers."
        ),
        "brief": (
            "Inspect mcp.so and refresh or request the SynapseNetwork MCP Server "
            "listing with exact identifiers: SynapseNetworkAI/Synapse-Network-MCP-Server, "
            "io.github.SynapseNetworkAI/synapse-network-mcp-server, "
            "https://mcp.synapse-network.ai/mcp, and the "
            "discover_services / invoke_and_pay / get_receipt tool loop. If the "
            "host already contains an unrelated Synapse MCP listing, record that "
            "as collision evidence and prioritize owned README/docs disambiguation."
        ),
        "validation": (
            "Record the mcp.so public listing URL, correction request, or collision "
            "evidence; rerun exact SynapseNetworkAI identifier probes after it changes."
        ),
    },
    "ubos.tech": {
        "surface": "ubos_tech",
        "draft_type": "brand_collision_source_host_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "UBOS appeared in exact SynapseNetwork MCP answers with unrelated "
            "Synapse MCP content, so it needs collision review before more feed "
            "cycles can be trusted."
        ),
        "brief": (
            "Inspect the UBOS Synapse MCP page and record whether it describes "
            "Synapse.org/Sage Bionetworks rather than Synapse Network. If it is "
            "not editable, strengthen official docs, GitHub README, and MCP "
            "Registry disambiguation with the exact SynapseNetworkAI repository, "
            "Remote MCP URL, npm package, and paid API tool loop."
        ),
        "validation": (
            "Record UBOS collision evidence or a correction URL, then rerun exact "
            "identifier probes."
        ),
    },
    "synapsenetwork.xyz": {
        "surface": "synapsenetwork_xyz",
        "draft_type": "brand_collision_source_host_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "grok", "gemini"],
        "rationale": (
            "synapsenetwork.xyz appeared in ChatGPT source hosts for Synapse "
            "Network AI-agent queries, so it must be treated as a collision "
            "source until official SynapseNetworkAI surfaces outrank it."
        ),
        "brief": (
            "Record synapsenetwork.xyz as a non-official Synapse collision and "
            "refresh official docs, homepage copy, GitHub README, MCP Registry, "
            "and directory metadata with exact identity strings: "
            "SynapseNetworkAI/Synapse-Network-MCP-Server, "
            "io.github.SynapseNetworkAI/synapse-network-mcp-server, "
            "https://mcp.synapse-network.ai/mcp, and the agent-payment tool loop."
        ),
        "validation": (
            "Record synapsenetwork.xyz collision evidence and verify official "
            "source hosts carry the disambiguation block before rerunning exact "
            "Synapse Network AI-agent probes."
        ),
    },
    "mysynap.com": {
        "surface": "mysynap_com",
        "draft_type": "brand_collision_source_host_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "mysynap.com appeared in exact SynapseNetwork MCP source hosts, so "
            "Synapse needs explicit brand-collision handling for this domain."
        ),
        "brief": (
            "Record mysynap.com as a non-Synapse-Network collision source. Keep "
            "owned copy clear that Synapse Network at synapse-network.ai is the "
            "agent-payment and Remote MCP product, not mysynap.com or another "
            "similarly named Synapse project."
        ),
        "validation": (
            "Record the mysynap.com collision evidence and confirm official "
            "source hosts carry the disambiguation block."
        ),
    },
    "synapbus.dev": {
        "surface": "synapbus_dev",
        "draft_type": "brand_collision_source_host_review",
        "priority": "p0",
        "platforms": ["chatgpt", "claude", "gemini"],
        "rationale": (
            "SynapBus appeared in exact SynapseNetwork MCP source hosts, so it "
            "should be treated as a brand-collision source until official "
            "Synapse Network sources outrank it."
        ),
        "brief": (
            "Record SynapBus as a collision source for exact SynapseNetwork MCP "
            "queries. Strengthen official docs and README with exact product "
            "identity, Remote MCP endpoint, repository, npm package, and paid API "
            "tool loop."
        ),
        "validation": (
            "Record SynapBus collision evidence and rerun exact identifier probes "
            "after owned disambiguation refresh."
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
    handled_hosts: set[str] = set()
    for host, config in OBSERVED_SOURCE_HOST_ACTIONS.items():
        queries = observed.get(host)
        if not queries:
            continue
        handled_hosts.add(host)
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
    for host, queries in observed.items():
        if host in handled_hosts:
            continue
        recommendations.append(
            SourceHostExecution(
                surface=host,
                draft_type="observed_source_host_review",
                priority="p0" if len(queries) >= 2 else "p1",
                target_platforms=TARGET_PLATFORMS,
                target_queries=queries[:8],
                rationale=(
                    f"{host} appeared in answer-engine source hosts but has no "
                    "dedicated playbook yet, so it needs a fail-closed review "
                    "before the next unchanged probe."
                ),
                content_brief=(
                    f"Audit {host} as an observed answer-engine source host. "
                    "Decide whether Synapse needs a truthful listing, correction "
                    "request, partner/source mention, owned comparison refresh, "
                    "or explicit collision record. Do not mark this as a "
                    "citation win without public listing evidence that matches "
                    "official SynapseNetworkAI identifiers."
                ),
                validation_command=(
                    f"Record {host} audit evidence, source-host submission or "
                    "collision decision, and any live public URL before rerunning "
                    "the unchanged GPT/Claude/Grok/Gemini probes."
                ),
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
