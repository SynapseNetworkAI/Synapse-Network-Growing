from __future__ import annotations

from server.schemas_growth import (
    GrowthAIVisibilityDesignPlanOut,
    GrowthAIVisibilityDocsPlanOut,
    GrowthAIVisibilityFeedExperimentOut,
    GrowthAIVisibilityOptimizationPlanOut,
    GrowthAIVisibilityQueryOut,
)


def ai_visibility_optimization_plan() -> GrowthAIVisibilityOptimizationPlanOut:
    return GrowthAIVisibilityOptimizationPlanOut(
        objective=(
            "Make Synapse Network discoverable and citable in ChatGPT, Claude, "
            "and Grok for AI agent payments, paid API calls, MCP tooling, and "
            "provider monetization queries."
        ),
        critical_fixes=_critical_fixes(),
        baseline_queries=_baseline_queries(),
        feed_experiments=_feed_experiments(),
        product_docs=_product_docs_plan(),
        design_plan=_design_plan(),
        growing_workflows=_growing_workflows(),
        success_criteria=_success_criteria(),
    )


def _critical_fixes() -> list[str]:
    return [
        "Use https://www.synapse-network.ai/ as the canonical homepage in metadata, llms.txt, and sitemap links.",
        "Return a non-empty https://www.synapse-network.ai/sitemap.xml with homepage and AI-agent-payment landing pages.",
        "Add brand-disambiguation copy that distinguishes Synapse Network from unrelated synapse.network DeFi launchpad results.",
        "Allow OAI-SearchBot, Claude-User, Claude-SearchBot, and mainstream web search crawlers through robots and edge protection.",
    ]


def _baseline_queries() -> list[GrowthAIVisibilityQueryOut]:
    return [
        _query("What is Synapse Network for AI agents?", "brand_disambiguation"),
        _query("AI agent payment API", "category"),
        _query("How can AI agents pay for APIs?", "how_to"),
        _query("MCP server for paid API calls", "mcp_discovery"),
        _query("AI agent USDC settlement layer", "settlement"),
        _query("Synapse Network vs x402", "comparison"),
        _query("How can API providers earn from AI agents?", "provider_monetization"),
    ]


def _feed_experiments() -> list[GrowthAIVisibilityFeedExperimentOut]:
    return [
        GrowthAIVisibilityFeedExperimentOut(
            feed_key="brand_disambiguation_www",
            surfaces=["www", "docs", "github_org", "x_profile"],
            content_assets=[
                "canonical homepage metadata",
                "About page answer block",
                "GitHub organization README facts",
                "X profile bio and pinned thread",
            ],
            target_queries=[
                "What is Synapse Network for AI agents?",
                "SynapseNetwork settlement layer for AI agents",
            ],
        ),
        GrowthAIVisibilityFeedExperimentOut(
            feed_key="agent_payment_category_pages",
            surfaces=["www", "docs", "devto", "github"],
            content_assets=[
                "/ai-agent-payments",
                "/agent-payment-api",
                "DEV article",
                "SDK README answer block",
            ],
            target_queries=[
                "AI agent payment API",
                "How can AI agents pay for APIs?",
                "AI agent pays for LLM calls",
            ],
        ),
        GrowthAIVisibilityFeedExperimentOut(
            feed_key="mcp_paid_api_discovery",
            surfaces=["docs", "mcp_registry", "smithery", "glama", "github"],
            content_assets=[
                "MCP docs category",
                "Remote MCP listing metadata",
                "registry and directory descriptions",
            ],
            target_queries=[
                "MCP server for paid API calls",
                "ChatGPT MCP app for API payments",
            ],
        ),
    ]


def _product_docs_plan() -> GrowthAIVisibilityDocsPlanOut:
    return GrowthAIVisibilityDocsPlanOut(
        docs_category="AI Agent Payments",
        pages=[
            "/ai-agent-payments",
            "/ai-agent-payments/agent-payment-api",
            "/ai-agent-payments/agent-pays-for-llm-calls",
            "/ai-agent-payments/provider-monetization",
            "/ai-agent-payments/receipts-and-budget-isolation",
            "/ai-agent-payments/synapse-vs-x402",
            "/ai-agent-payments/faq",
        ],
        required_blocks=[
            "40-60 word standalone definition block",
            "machine-readable facts table",
            "agent builder and API provider user paths",
            "deposit to credential to discover to invoke to receipt flow",
            "comparison table against x402, Stripe, RapidAPI, and direct API keys",
            "FAQPage-ready natural language questions",
            "last updated timestamp and source links",
        ],
        schema_types=[
            "SoftwareApplication",
            "TechArticle",
            "FAQPage",
            "BreadcrumbList",
        ],
    )


def _design_plan() -> GrowthAIVisibilityDesignPlanOut:
    return GrowthAIVisibilityDesignPlanOut(
        stitch_prompt=(
            "Design a technical documentation landing page for Synapse Network, "
            "the settlement layer for AI agents. Include a concise definition, "
            "a machine-to-machine payment flow, two user paths for agent builders "
            "and API providers, code examples, a Synapse vs x402 vs Stripe vs "
            "RapidAPI comparison table, FAQ blocks, and citation-ready fact cards. "
            "Style: developer infrastructure, dark mode, precise, credible, not hype."
        ),
        figma_handoff=[
            "Import Stitch output as an exploration, then normalize typography, spacing, and components in Figma.",
            "Mark definition blocks, fact cards, comparison rows, and FAQ sections as reusable docs-front components.",
            "Keep MDX, schema, llms.txt, and sitemap as source of truth; Figma is visual guidance only.",
        ],
        implementation_targets=[
            "Synapse-Network services/docs-front content/docs/ai-agent-payments/*.mdx",
            "Synapse-Network production site pages for /ai-agent-payments and /agent-payment-api",
            "Growing /growth AI Visibility ledger for weekly search probes and feed experiments",
        ],
    )


def _growing_workflows() -> list[str]:
    return [
        "ai_visibility_baseline_sweep",
        "ai_visibility_search_probe",
        "ai_visibility_content_feed_planner",
        "ai_visibility_docs_gap_sweep",
        "ai_visibility_weekly_report",
    ]


def _success_criteria() -> list[str]:
    return [
        "Brand query returns www.synapse-network.ai or docs.synapse-network.ai in ChatGPT, Claude, and Grok evidence.",
        "At least 6 of 12 priority category queries mention Synapse in two target platforms.",
        "At least 3 answer-engine citations point to docs, GitHub, MCP registry, or the official www domain.",
        "Results remain stable for three consecutive weekly runs before marking the visibility goal achieved.",
    ]


def _query(query: str, intent: str) -> GrowthAIVisibilityQueryOut:
    return GrowthAIVisibilityQueryOut(
        query=query,
        intent=intent,
        target_platforms=["chatgpt", "claude", "grok"],
        success_signal="Synapse mentioned with a citation to the official www/docs/GitHub surface.",
    )
