"""Observed source-host recommendation helpers for AI visibility probes."""

from __future__ import annotations

from typing import Any

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
}


def observed_source_host_recommendations(
    *, external_records: list[Any], rerun: str
) -> list[SourceHostExecution]:
    recommendations = []
    observed = observed_hosts_by_surface(external_records)
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


def observed_hosts_by_surface(external_records: list[Any]) -> dict[str, list[str]]:
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
    return result


def normalize_host(value: object) -> str:
    host = str(value or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host
