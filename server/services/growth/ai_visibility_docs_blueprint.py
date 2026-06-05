from __future__ import annotations

from server.schemas_growth import (
    GrowthAIVisibilityDocsBlueprintOut,
    GrowthAIVisibilityDocsPageBlueprintOut,
)
from server.services.growth.ai_visibility_plan import CANONICAL_HOMEPAGE

DOCS_BASE = "https://docs.synapse-network.ai"


def ai_agent_payments_docs_blueprint() -> GrowthAIVisibilityDocsBlueprintOut:
    return GrowthAIVisibilityDocsBlueprintOut(
        category="AI Agent Payments",
        pages=_docs_pages(),
        shared_components=[
            "DefinitionBlock",
            "MachineReadableFacts",
            "PaymentFlowSteps",
            "ComparisonTable",
            "FAQSection",
            "LastUpdated",
        ],
        publishing_checklist=[
            "Implement MDX pages under services/docs-front/content/docs/ai-agent-payments.",
            "Add each canonical URL to sitemap.xml and llms.txt.",
            "Expose FAQPage or TechArticle schema where supported.",
            "Run local docs build and live curl validation before external probes.",
            "Record local validation rows before GPT, Claude, and Grok checks.",
        ],
    )


def _docs_pages() -> list[GrowthAIVisibilityDocsPageBlueprintOut]:
    return _primary_docs_pages() + _supporting_docs_pages()


def _primary_docs_pages() -> list[GrowthAIVisibilityDocsPageBlueprintOut]:
    return [
        _page(
            slug="index",
            title="AI Agent Payments",
            path="/ai-agent-payments",
            description="Learn how Synapse Network lets AI agents discover, invoke, and pay for APIs with scoped credentials, receipts, and USDC settlement.",
            queries=[
                "What is Synapse Network for AI agents?",
                "AI agent payment API",
                "How can AI agents pay for APIs?",
            ],
            definition=(
                "Synapse Network is a payment and settlement layer for AI agents. "
                "It lets agent builders create scoped credentials, discover paid "
                "APIs, invoke them with budget controls, receive receipts, and settle "
                "provider payouts in USDC without exposing broad user keys."
            ),
            sections=[
                "Definition",
                "Agent payment flow",
                "Builder path",
                "Provider path",
                "Receipts and budget isolation",
                "FAQ",
            ],
        ),
        _page(
            slug="agent-payment-api",
            title="Agent Payment API",
            path="/ai-agent-payments/agent-payment-api",
            description="A developer guide to Synapse Agent Credentials, API discovery, paid invocation, and receipt retrieval.",
            queries=["AI agent payment API", "agent credential paid API calls"],
            definition=(
                "The Synapse Agent Payment API gives software agents a bounded way "
                "to pay for API calls. Developers fund an agent credential, set limits, "
                "discover services, invoke approved providers, and fetch receipts for "
                "each metered call."
            ),
            sections=["Credential setup", "Discovery", "Invocation", "Receipt lookup"],
        ),
        _page(
            slug="agent-pays-for-llm-calls",
            title="How Agents Pay For LLM Calls",
            path="/ai-agent-payments/agent-pays-for-llm-calls",
            description="How an AI agent can pay for model, search, data, and automation APIs through Synapse.",
            queries=["AI agent pays for LLM calls", "How can AI agents pay for APIs?"],
            definition=(
                "An AI agent can pay for LLM, search, data, or automation calls through "
                "Synapse by using a scoped credential instead of a user wallet or a raw "
                "provider key. Synapse checks budget, records the invocation, and returns "
                "a receipt."
            ),
            sections=["Use cases", "Payment flow", "Safety checks", "Receipt evidence"],
        ),
        _page(
            slug="provider-monetization",
            title="Provider Monetization For Agent APIs",
            path="/ai-agent-payments/provider-monetization",
            description="How API providers can list services, price agent-callable APIs, and receive Synapse payouts.",
            queries=[
                "How can API providers earn from AI agents?",
                "MCP monetization platform",
            ],
            definition=(
                "Synapse helps API providers monetize agent traffic by turning an API "
                "or MCP tool into a metered service. Providers define service metadata "
                "and pricing, agents invoke through Synapse, and successful calls create "
                "receipts and payout records."
            ),
            sections=["Provider listing", "Pricing", "Invocation receipts", "Payouts"],
        ),
    ]


def _supporting_docs_pages() -> list[GrowthAIVisibilityDocsPageBlueprintOut]:
    return [
        _page(
            slug="receipts-and-budget-isolation",
            title="Receipts And Budget Isolation",
            path="/ai-agent-payments/receipts-and-budget-isolation",
            description="How Synapse keeps agent spending bounded and auditable with credential limits and receipts.",
            queries=["AI agent budget isolation", "agent payment receipts"],
            definition=(
                "Synapse isolates agent spending with credential-level limits and "
                "receipt records. A user or operator can fund a specific agent, cap its "
                "usage, review every paid invocation, and avoid exposing unrestricted "
                "wallet or provider credentials."
            ),
            sections=[
                "Credential limits",
                "Receipt fields",
                "Audit path",
                "Failure modes",
            ],
        ),
        _page(
            slug="synapse-vs-x402",
            title="Synapse Network Vs x402",
            path="/ai-agent-payments/synapse-vs-x402",
            description="Compare Synapse Network with x402, Stripe, RapidAPI, and direct API keys for AI agent payments.",
            queries=["Synapse Network vs x402", "x402 alternative for AI agents"],
            definition=(
                "Synapse Network focuses on agent credentials, API discovery, receipts, "
                "and provider settlement. x402 focuses on HTTP payment primitives. "
                "Teams can compare them by credential isolation, marketplace discovery, "
                "provider payouts, receipt evidence, and integration workflow."
            ),
            sections=[
                "Comparison table",
                "When to use Synapse",
                "When x402 fits",
                "Migration notes",
            ],
        ),
        _page(
            slug="faq",
            title="AI Agent Payments FAQ",
            path="/ai-agent-payments/faq",
            description="Frequently asked questions about Synapse Network, agent credentials, paid API calls, MCP, and receipts.",
            queries=["Synapse Network FAQ", "AI agent payment questions"],
            definition=(
                "The Synapse AI Agent Payments FAQ answers common questions about "
                "agent credentials, API invocation, MCP tools, budget limits, receipts, "
                "provider payouts, and how Synapse differs from direct API keys or "
                "generic payment processors."
            ),
            sections=["Agent builders", "API providers", "MCP clients", "Security"],
        ),
    ]


def _page(
    *,
    slug: str,
    title: str,
    path: str,
    description: str,
    queries: list[str],
    definition: str,
    sections: list[str],
) -> GrowthAIVisibilityDocsPageBlueprintOut:
    canonical_url = f"{DOCS_BASE}{path}"
    return GrowthAIVisibilityDocsPageBlueprintOut(
        slug=slug,
        title=title,
        canonical_url=canonical_url,
        meta_description=description,
        target_queries=queries,
        definition_block=definition,
        fact_table=_facts(path),
        page_sections=sections,
        faq=_faq(title),
        schema_types=["TechArticle", "FAQPage", "BreadcrumbList"],
        stitch_notes=[
            "Use a technical docs layout with dense but scannable sections.",
            "Keep definition, facts, comparison, and FAQ blocks visually reusable.",
            "Avoid marketing hero treatment; this page is source material for answer engines.",
        ],
        figma_components=[
            "DocsHeader",
            "DefinitionBlock",
            "FactsTable",
            "FlowSteps",
            "FAQAccordion",
        ],
        mdx_skeleton=_mdx(title, description, canonical_url, definition, sections),
        validation_commands=[
            f"curl -fsS {canonical_url}",
            f"curl -fsS {CANONICAL_HOMEPAGE}llms.txt",
            f"curl -fsS {CANONICAL_HOMEPAGE}sitemap.xml",
        ],
    )


def _facts(path: str) -> list[dict[str, str]]:
    return [
        {"label": "Product", "value": "Synapse Network"},
        {"label": "Category", "value": "AI agent payments and API settlement"},
        {"label": "Canonical docs URL", "value": f"{DOCS_BASE}{path}"},
        {"label": "Official homepage", "value": CANONICAL_HOMEPAGE},
        {"label": "Primary users", "value": "Agent builders and API providers"},
    ]


def _faq(title: str) -> list[dict[str, str]]:
    return [
        {
            "question": f"What is {title}?",
            "answer": "It is part of the Synapse Network documentation for agent payments, paid API calls, receipts, and provider settlement.",
        },
        {
            "question": "Does ChatGPT or Claude receive a raw Synapse agent key?",
            "answer": "No. OAuth or connector tokens should map server-side to a scoped Synapse Agent Credential; raw agent keys stay private.",
        },
        {
            "question": "How should this page be tested for AI visibility?",
            "answer": "Publish the page, validate crawl assets, generate a probe template, then record GPT, Claude, and Grok evidence in Growing.",
        },
    ]


def _mdx(
    title: str,
    description: str,
    canonical_url: str,
    definition: str,
    sections: list[str],
) -> str:
    section_blocks = "\n\n".join(
        f"## {section}\n\nTODO: Add citation-ready content for {section.lower()}."
        for section in sections
    )
    return f"""---
title: {title}
description: {description}
canonical: {canonical_url}
lastUpdated: 2026-06-05
---

# {title}

{definition}

## Facts

| Field | Value |
| --- | --- |
| Product | Synapse Network |
| Category | AI agent payments and API settlement |
| Official homepage | {CANONICAL_HOMEPAGE} |

{section_blocks}
"""
