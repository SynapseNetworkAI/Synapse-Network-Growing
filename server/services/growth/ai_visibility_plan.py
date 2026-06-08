from __future__ import annotations

from server.schemas_growth import (
    GrowthAIVisibilityFeedAssetOut,
    GrowthAIVisibilityDesignPlanOut,
    GrowthAIVisibilityDocsPlanOut,
    GrowthAIVisibilityFeedExperimentOut,
    GrowthAIVisibilityFeedPackageListOut,
    GrowthAIVisibilityFeedPackageOut,
    GrowthAIVisibilityOptimizationPlanOut,
    GrowthAIVisibilityPlatformStrategyOut,
    GrowthAIVisibilityQueryOut,
)

CANONICAL_HOMEPAGE = "https://www.synapse-network.ai/"


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


def ai_visibility_feed_packages(
    feed_key: str | None = None,
) -> GrowthAIVisibilityFeedPackageListOut:
    plan = ai_visibility_optimization_plan()
    experiments = plan.feed_experiments
    if feed_key:
        experiments = [
            experiment for experiment in experiments if experiment.feed_key == feed_key.strip()
        ]
    packages = [
        _feed_package(
            experiment=experiment,
            design_plan=plan.design_plan,
            success_criteria=plan.success_criteria,
        )
        for experiment in experiments
    ]
    return GrowthAIVisibilityFeedPackageListOut(items=packages, total=len(packages))


def _critical_fixes() -> list[str]:
    return [
        f"Use {CANONICAL_HOMEPAGE} as the canonical homepage in metadata, llms.txt, and sitemap links.",
        "Redirect https://synapse-network.ai/* to https://www.synapse-network.ai/* with a permanent 301/308 response.",
        "Return a non-empty https://www.synapse-network.ai/sitemap.xml with homepage and AI-agent-payment landing pages.",
        "Add brand-disambiguation copy that distinguishes Synapse Network from unrelated Synapse Protocol, synapse.network DeFi launchpad, and synapsenetwork.xyz economy-layer results.",
        "Explicitly allow OpenAI, ChatGPT, Claude, Perplexity, Bing, and Google AI/search crawlers through robots while disallowing private app routes.",
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
                "Synapse Network AI agents",
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
            surfaces=["www", "docs", "mcp_registry", "mcp_marketplace", "smithery", "glama", "github"],
            content_assets=[
                "canonical homepage facts",
                "MCP docs category",
                "/mcp/paid-api-calls citation-ready guide",
                "/mcp/synapse-vs-paid-mcp alternatives comparison page",
                "Remote MCP listing metadata",
                "registry and directory descriptions",
            ],
            target_queries=[
                "MCP server for paid API calls",
                "ChatGPT MCP app for API payments",
                "SynapseNetwork MCP vs paid MCP alternatives",
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


def _feed_package(
    *,
    experiment: GrowthAIVisibilityFeedExperimentOut,
    design_plan: GrowthAIVisibilityDesignPlanOut,
    success_criteria: list[str],
) -> GrowthAIVisibilityFeedPackageOut:
    return GrowthAIVisibilityFeedPackageOut(
        feed_key=experiment.feed_key,
        objective=_feed_objective(experiment.feed_key),
        canonical_domain=CANONICAL_HOMEPAGE,
        surfaces=experiment.surfaces,
        content_assets=experiment.content_assets,
        target_queries=experiment.target_queries,
        publish_assets=_publish_assets(experiment.feed_key),
        platform_strategies=_platform_strategies(experiment.feed_key),
        stitch_prompt=_stitch_prompt_for_feed(experiment.feed_key, design_plan),
        figma_handoff=design_plan.figma_handoff,
        validation_commands=_validation_commands(experiment.feed_key),
        probe_template_command=(
            "python scripts/growth/generate_ai_visibility_probe_template.py "
            f"--feed-key {experiment.feed_key} "
            "--run-group YYYY-MM-DD-after-feed "
            "--mode after-feed "
            "--output docs/archive/evidence/growth/ai-visibility/YYYY-MM-DD-after-feed.jsonl"
        ),
        success_metrics=success_criteria,
        next_actions=_feed_next_actions(experiment.feed_key),
    )


def _feed_objective(feed_key: str) -> str:
    objectives = {
        "brand_disambiguation_www": (
            "Make answer engines resolve Synapse Network to the official www site "
            "instead of unrelated synapse.network results."
        ),
        "agent_payment_category_pages": (
            "Make AI agent payment and paid API-call category queries cite Synapse "
            "docs or marketing pages."
        ),
        "mcp_paid_api_discovery": (
            "Make MCP directory and ChatGPT custom app queries surface the Synapse "
            "Remote MCP server and paid API tools."
        ),
    }
    return objectives.get(feed_key, "Improve Synapse answer-engine visibility.")


def _publish_assets(feed_key: str) -> list[GrowthAIVisibilityFeedAssetOut]:
    assets = {
        "brand_disambiguation_www": [
            _asset(
                "www",
                CANONICAL_HOMEPAGE,
                "Canonical homepage metadata, bare-domain redirect, brand definition, and disambiguation copy.",
                "curl -I -sS https://synapse-network.ai/ | grep -E 'HTTP/.* 30(1|8)|Location: https://www.synapse-network.ai/'",
            ),
            _asset(
                "github_org",
                "https://github.com/SynapseNetworkAI",
                "Organization README facts that reinforce official naming and repos.",
                "Open GitHub org README and verify Synapse Network product facts.",
            ),
        ],
        "agent_payment_category_pages": [
            _asset(
                "www",
                "https://www.synapse-network.ai/ai-agent-payments",
                "Category landing page with extractable AI agent payment definition.",
                "curl -fsS https://www.synapse-network.ai/ai-agent-payments",
            ),
            _asset(
                "docs",
                "https://docs.synapse-network.ai/ai-agent-payments",
                "Documentation category with FAQ, flow, receipts, and comparison pages.",
                "curl -fsS https://docs.synapse-network.ai/ai-agent-payments",
            ),
            _asset(
                "github",
                "https://github.com/SynapseNetworkAI",
                "SDK and MCP README answer blocks linking back to official docs.",
                "Search GitHub README files for AI agent payments and Synapse Network.",
            ),
        ],
        "mcp_paid_api_discovery": [
            _asset(
                "www",
                CANONICAL_HOMEPAGE,
                "Canonical homepage facts that identify the official Synapse Network source for answer engines.",
                "curl -fsS https://www.synapse-network.ai/ | grep -E 'Synapse|AI agents|paid API'",
            ),
            _asset(
                "docs",
                "https://docs.synapse-network.ai/mcp/paid-api-calls",
                "Citation-ready guide that states Synapse is an MCP server for paid API calls and names discover_services, invoke_and_pay, and get_receipt.",
                "curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls | grep -E 'MCP Server for Paid API Calls|discover_services|invoke_and_pay|get_receipt'",
            ),
            _asset(
                "docs",
                "https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
                "Alternatives comparison page that distinguishes Synapse from MCPay, Latch, Dock0, Apiosk, Teleport, Stripe MCP, and paid MCP directories.",
                "curl -fsS https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp | grep -E 'Synapse|MCPay|Latch|Dock0|Apiosk|Teleport|Stripe'",
            ),
            _asset(
                "mcp_registry",
                "https://registry.modelcontextprotocol.io/",
                "Official MCP Registry listing with Remote MCP endpoint metadata.",
                "Search MCP Registry for Synapse Network MCP Server.",
            ),
            _asset(
                "mcp_marketplace",
                "https://mcp-marketplace.io/server/io-github-synapsenetworkai-synapse-network-mcp-server",
                "Approved MCP Marketplace listing that answer engines can cite for Remote MCP paid API discovery.",
                "curl -fsSL https://mcp-marketplace.io/server/io-github-synapsenetworkai-synapse-network-mcp-server | grep -E 'Synapse Network MCP Server|paid API discovery|mcp.synapse-network.ai/mcp'",
            ),
            _asset(
                "smithery",
                "https://smithery.ai/",
                "Directory listing for MCP client discovery and import.",
                "Search Smithery for Synapse Network MCP Server.",
            ),
            _asset(
                "glama",
                "https://glama.ai/",
                "Directory listing and inspector evidence for discover_services.",
                "Search Glama for Synapse Network MCP Server.",
            ),
        ],
    }
    return assets.get(feed_key, [])


def _asset(surface: str, target: str, purpose: str, validation: str):
    return GrowthAIVisibilityFeedAssetOut(
        surface=surface,
        target=target,
        purpose=purpose,
        validation=validation,
    )


def _platform_strategies(feed_key: str) -> list[GrowthAIVisibilityPlatformStrategyOut]:
    if feed_key == "mcp_paid_api_discovery":
        return [
            _platform_strategy(
                "chatgpt",
                "Remote MCP custom app discovery and web citations.",
                ["docs", "mcp_registry", "mcp_marketplace", "www_llms", "github"],
                [
                    "MCP server for paid API calls",
                    "ChatGPT MCP app for API payments",
                    "SynapseNetwork MCP vs paid MCP alternatives",
                ],
                "ChatGPT scan/search surfaces Synapse Remote MCP and cites docs, MCP Registry, or MCP Marketplace.",
                "Ship OAuth/custom app docs, refresh MCP Registry and MCP Marketplace metadata, then rerun ChatGPT scan.",
            ),
            _platform_strategy(
                "claude",
                "Remote connector compatibility and docs citation.",
                ["docs", "github", "glama", "mcp_marketplace", "www_llms"],
                [
                    "Claude MCP connector for paid API calls",
                    "MCP server that lets agents pay for APIs",
                ],
                "Claude web search mentions Synapse and cites docs, GitHub, or a directory listing.",
                "Add Claude connector setup block and directory evidence, then rerun Claude web search.",
            ),
            _platform_strategy(
                "grok",
                "Public web plus X-facing MCP discovery language.",
                ["www", "docs", "x_profile", "smithery", "glama"],
                [
                    "MCP server for paid API calls",
                    "AI agents paying for APIs with MCP",
                ],
                "Grok search returns Synapse or the Remote MCP endpoint among cited/source results.",
                "Publish social/distribution copy linking the docs page, then rerun Grok web/X search.",
            ),
        ]
    return [
        _platform_strategy(
            "chatgpt",
            "Official www/docs citation for category and how-to answers.",
            ["www", "docs", "github"],
            ["AI agent payment API", "How can AI agents pay for APIs?"],
            "ChatGPT mentions Synapse and cites the official www or docs surface.",
            "Tighten definition blocks, llms.txt, and GitHub README facts before rerunning.",
        ),
        _platform_strategy(
            "claude",
            "Docs-first explanation with comparison and FAQ blocks.",
            ["docs", "github", "www"],
            ["Synapse Network vs x402", "AI agent USDC settlement layer"],
            "Claude cites Synapse docs or GitHub when answering comparison/category queries.",
            "Add comparison, FAQ, and source-backed claims, then rerun Claude web search.",
        ),
        _platform_strategy(
            "grok",
            "Fresh public web and social distribution signals.",
            ["www", "docs", "x_profile", "github"],
            ["AI agent payment API", "How can API providers earn from AI agents?"],
            "Grok mentions Synapse from public web or X-linked official content.",
            "Publish public distribution copy with canonical links, then rerun Grok web/X search.",
        ),
    ]


def _platform_strategy(
    platform: str,
    feed_focus: str,
    preferred_surfaces: list[str],
    probe_queries: list[str],
    success_signal: str,
    fallback_action: str,
) -> GrowthAIVisibilityPlatformStrategyOut:
    return GrowthAIVisibilityPlatformStrategyOut(
        platform=platform,
        feed_focus=feed_focus,
        preferred_surfaces=preferred_surfaces,
        probe_queries=probe_queries,
        success_signal=success_signal,
        fallback_action=fallback_action,
    )


def _stitch_prompt_for_feed(
    feed_key: str, design_plan: GrowthAIVisibilityDesignPlanOut
) -> str:
    if feed_key == "brand_disambiguation_www":
        return (
            "Design a concise Synapse Network homepage facts section for AI answer "
            "engines: official brand name, www canonical URL, what the product does, "
            "who uses it, and how it differs from unrelated Synapse projects."
        )
    if feed_key == "mcp_paid_api_discovery":
        return (
            "Design a technical MCP integration docs page for Synapse Network Remote "
            "MCP. Include ChatGPT custom MCP, Claude connector, Cursor/VS Code setup, "
            "tool list, auth boundary, and paid invocation confirmation."
        )
    return design_plan.stitch_prompt


def _validation_commands(feed_key: str) -> list[str]:
    commands = [
        "curl -I -sS https://synapse-network.ai/ | grep -E 'HTTP/.* 30(1|8)|Location: https://www.synapse-network.ai/'",
        "curl -fsS https://www.synapse-network.ai/robots.txt",
        "curl -fsS https://www.synapse-network.ai/robots.txt | grep -E 'OAI-SearchBot|ChatGPT-User|GPTBot|ClaudeBot|Claude-User|Claude-SearchBot|anthropic-ai|PerplexityBot|Bingbot|Google-Extended'",
        "curl -fsS https://www.synapse-network.ai/llms.txt",
        "curl -fsS https://www.synapse-network.ai/sitemap.xml",
    ]
    if feed_key == "agent_payment_category_pages":
        commands.extend(
            [
                "curl -fsS https://www.synapse-network.ai/ai-agent-payments",
                "curl -fsS https://docs.synapse-network.ai/ai-agent-payments",
            ]
        )
    if feed_key == "mcp_paid_api_discovery":
        commands.extend(
            [
                "curl -fsS https://www.synapse-network.ai/ | grep -E 'Synapse|AI agents|paid API'",
                "curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls",
                "curl -fsS https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
                "curl -fsS https://www.synapse-network.ai/llms.txt | grep 'MCP Server for Paid API Calls'",
                "curl -fsS https://mcp.synapse-network.ai/readyz",
                "curl -i -sS -X POST https://mcp.synapse-network.ai/mcp",
            ]
        )
    return commands


def _feed_next_actions(feed_key: str) -> list[str]:
    actions = {
        "brand_disambiguation_www": [
            "Fix bare-domain redirect, canonical, explicit AI crawler robots policy, sitemap, llms.txt, and brand answer blocks before baseline rerun.",
            "Track synapseproto.com, synapsenetwork.xyz, and unrelated synapse.network results as brand-collision competitors in external probe rows.",
            "Run ChatGPT, Claude, and Grok brand query probes with screenshot evidence.",
        ],
        "agent_payment_category_pages": [
            "Publish AI Agent Payments docs category and www landing pages.",
            "Generate after-feed probe template and compare against the prior run group.",
        ],
        "mcp_paid_api_discovery": [
            "Publish /mcp/paid-api-calls and /mcp/synapse-vs-paid-mcp, then expose them in docs sitemap plus www llms.txt.",
            "Submit or verify MCP Registry, Smithery, and Glama listings.",
            "Run ChatGPT custom MCP scan and answer-engine MCP discovery probes.",
        ],
    }
    return actions.get(feed_key, ["Generate probe template and compare external visibility."])
