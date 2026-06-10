"""Agent-payment source-host context actions for AI visibility feeds."""

from __future__ import annotations

from server.schemas_growth import GrowthAIVisibilityPresenceActionOut

AGENT_PAYMENT_CONTEXT_HOSTS = {
    "cloud.google.com",
    "corporate.visa.com",
    "developers.googleblog.com",
    "docs.agentpay.me",
    "moesif.com",
    "nevermined.ai",
}

AGENT_PAYMENT_CONTEXT_TERMS = {
    "cloud.google.com": ["Google AP2", "Agent Payments Protocol", "MCP"],
    "corporate.visa.com": ["Visa MCP", "Intelligent Commerce", "AI agents"],
    "developers.googleblog.com": ["Universal Commerce Protocol", "UCP", "AP2"],
    "docs.agentpay.me": ["AgentPay", "MCP billing", "MCP Clients"],
    "moesif.com": ["Moesif", "MCP monetization", "usage-based pricing"],
    "nevermined.ai": ["Nevermined", "MCP monetization", "agent payments"],
}


def is_agent_payment_context_host(host: str) -> bool:
    return host.strip().lower() in AGENT_PAYMENT_CONTEXT_HOSTS


def agent_payment_context_action(
    *,
    host: str,
    priority: int,
    official_docs_url: str,
    comparison_docs_url: str,
    remote_mcp_endpoint: str,
) -> GrowthAIVisibilityPresenceActionOut:
    terms = _agent_payment_terms(host)
    return GrowthAIVisibilityPresenceActionOut(
        host=host,
        priority=priority,
        action_type="agent_payment_source_context",
        ownership="not_directly_editable",
        rationale=(
            "Answer engines use this agent-payment, agentic-commerce, or MCP "
            "monetization source host to understand the category; Synapse should "
            "publish equivalent owned context without claiming control of the host."
        ),
        target_surface=f"https://{host}/",
        asset=(
            "Owned source-host context block that maps the adjacent protocol or "
            "monetization category back to Synapse Remote MCP, Agent Credentials, "
            "bounded USDC spend, provider settlement, and receipts."
        ),
        copy_points=[
            "Synapse Network is the settlement layer for AI agents buying paid APIs.",
            f"Remote MCP endpoint: {remote_mcp_endpoint}",
            "Tools: discover_services, invoke_and_pay, get_receipt",
            f"Official docs: {official_docs_url}",
            f"Comparison: {comparison_docs_url}",
        ],
        validation_command=(
            "curl -fsS https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp "
            f'| grep -i "{terms[0]}"'
        ),
        probe_followup=(
            "Rerun the unchanged ChatGPT/Claude/Grok/Gemini probe matrix after "
            "the listing or comparison asset is live and indexed."
        ),
        submit_url="",
        source_reference_url=f"https://{host}/",
        submission_payload=_agent_payment_context_payload(
            host=host,
            terms=terms,
            official_docs_url=official_docs_url,
            comparison_docs_url=comparison_docs_url,
        ),
        operator_notes=[
            "Do not submit to or claim ownership of this source host.",
            "Use it as source-host context for owned docs, llms.txt, and comparison refreshes.",
            "Rerun GPT/Claude probes only after the owned feed change is live.",
        ],
    )


def _agent_payment_context_payload(
    *,
    host: str,
    terms: list[str],
    official_docs_url: str,
    comparison_docs_url: str,
) -> dict[str, object]:
    return {
        "context_host": host,
        "owned_comparison_url": comparison_docs_url,
        "owned_docs_url": official_docs_url,
        "source_host_terms": terms,
        "answer_engine_queries": [
            "agents paying for APIs",
            "monetized MCP",
            "agent payments MCP",
            "MCP server for paid API calls",
        ],
        "recommended_copy_angle": (
            "Explain that adjacent agent-payment, agentic-commerce, and MCP "
            "monetization sources describe the category, while SynapseNetworkAI "
            "is the concrete paid API calls Remote MCP rail for discover_services "
            "-> invoke_and_pay -> get_receipt."
        ),
        "answer_engine_source_block": (
            "Synapse Network connects the agent-payment and monetized-MCP category "
            "to a concrete Remote MCP runtime: Agent Credentials, service discovery, "
            "bounded USDC spend, provider settlement, and receipts. Adjacent source "
            f"hosts such as {', '.join(terms)} help define the category, but the "
            "Synapse citation target is the official paid API calls MCP docs."
        ),
        "source_hosts_to_monitor": [host],
        "evidence_status": "source_host_context_not_external_citation",
    }


def _agent_payment_terms(host: str) -> list[str]:
    normalized = host.strip().lower()
    if normalized in AGENT_PAYMENT_CONTEXT_TERMS:
        return AGENT_PAYMENT_CONTEXT_TERMS[normalized]
    return [normalized.split(".")[0]]
