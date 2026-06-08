"""Scoring policy for paid AI visibility API probe answers."""

from __future__ import annotations

import re

from scripts.growth.generate_ai_visibility_probe_template import (
    KNOWN_COLLISION_DOMAINS,
)

OFFICIAL_MENTION_TOKENS = (
    "synapsenetworkai",
    "synapse-network.ai",
    "docs.synapse-network.ai",
    "mcp.synapse-network.ai",
    "github.com/synapsenetworkai",
    "@synapse-network-ai",
    "synapse remote mcp",
)
OFFICIAL_TOOL_TOKENS = ("discover_services", "invoke_and_pay", "get_receipt")
KNOWN_COLLISION_TEXT = (
    "synapse protocol",
    "project synapse",
    "sage bionetworks",
)


def answer_payload(
    *,
    platform: str,
    model: str,
    text: str,
    urls: list[str],
    request_id: str,
) -> dict[str, object]:
    if not text.strip():
        raise RuntimeError(f"{platform} API returned no answer text")
    cited_synapse_urls = [url for url in urls if is_synapse_url(url)]
    mentioned = is_official_synapse_mention(text.lower(), cited_synapse_urls)
    competitors = competitor_mentions(text, urls)
    return {
        "summary": text[:1200],
        "synapse_mentioned": mentioned,
        "synapse_cited": bool(cited_synapse_urls),
        "cited_urls": cited_synapse_urls,
        "source_urls": urls,
        "competitor_mentions": competitors,
        "missing_facts": missing_facts(mentioned),
        "next_action": next_action(mentioned),
        "result_rank": 1 if mentioned else 0,
        "model": model,
        "request_id": request_id,
        "platform": platform,
    }


def is_official_synapse_mention(
    lowered_text: str, cited_synapse_urls: list[str]
) -> bool:
    if cited_synapse_urls:
        return True
    if any(token in lowered_text for token in OFFICIAL_MENTION_TOKENS):
        return True
    if "agent credentials" in lowered_text and any(
        token in lowered_text for token in OFFICIAL_TOOL_TOKENS
    ):
        return True
    return False


def missing_facts(mentioned: bool) -> list[str]:
    if mentioned:
        return []
    return ["Official SynapseNetworkAI source or identity was not mentioned."]


def next_action(mentioned: bool) -> str:
    if mentioned:
        return "Compare against previous run group and keep feeding cited surfaces."
    return "Deploy/refresh feed assets and rerun the same API probe."


def is_synapse_url(url: str) -> bool:
    return any(
        host in url
        for host in (
            "www.synapse-network.ai",
            "docs.synapse-network.ai",
            "github.com/SynapseNetworkAI",
            "mcp.synapse-network.ai",
            "registry.modelcontextprotocol.io",
        )
    )


def competitor_mentions(text: str, urls: list[str]) -> list[str]:
    haystack = " ".join([text, *urls]).lower()
    competitors = []
    for label in ["x402", "stripe", "rapidapi", "masumi", "locus", "payspawn"]:
        if re.search(rf"\b{re.escape(label)}\b", haystack):
            competitors.append(label)
    for domain in KNOWN_COLLISION_DOMAINS:
        if collision_domain_mentioned(domain, haystack):
            competitors.append(domain)
    for label in KNOWN_COLLISION_TEXT:
        if label in haystack:
            competitors.append(label)
    return competitors


def collision_domain_mentioned(domain: str, haystack: str) -> bool:
    lowered_domain = domain.lower()
    if "/" in lowered_domain:
        return lowered_domain in haystack
    escaped = re.escape(lowered_domain)
    return bool(re.search(rf"(?<![a-z0-9-]){escaped}(?![a-z0-9-])", haystack))
