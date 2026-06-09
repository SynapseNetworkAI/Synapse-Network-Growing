from __future__ import annotations

from server.schemas_growth import (
    GrowthAIVisibilityDesignFrameOut,
    GrowthAIVisibilityDesignHandoffOut,
)
from server.services.growth.ai_visibility_docs_blueprint import (
    ai_agent_payments_docs_blueprint,
)
from server.services.growth.ai_visibility_plan import (
    CANONICAL_HOMEPAGE,
    ai_visibility_optimization_plan,
)


def ai_agent_payments_design_handoff() -> GrowthAIVisibilityDesignHandoffOut:
    plan = ai_visibility_optimization_plan()
    blueprint = ai_agent_payments_docs_blueprint()
    return GrowthAIVisibilityDesignHandoffOut(
        title="Synapse AI Agent Payments Stitch To Figma Handoff",
        canonical_domain=CANONICAL_HOMEPAGE,
        figma_file_name="Synapse AI Agent Payments Docs - AI Visibility",
        stitch_prompt=plan.design_plan.stitch_prompt,
        frames=_design_frames(),
        component_specs=_component_specs(),
        design_tokens=_design_tokens(),
        import_steps=_import_steps(),
        implementation_notes=_implementation_notes(blueprint),
        acceptance_checks=_acceptance_checks(),
    )


def _design_frames() -> list[GrowthAIVisibilityDesignFrameOut]:
    return [
        _frame(
            name="AI Agent Payments Docs Landing",
            slug="index",
            purpose="Primary documentation landing page for AI answer engines and developer readers.",
            prompt_suffix="Create the main docs landing page with definition, facts, payment flow, builder/provider paths, comparison preview, and FAQ preview.",
        ),
        _frame(
            name="Agent Payment API Deep Dive",
            slug="agent-payment-api",
            purpose="Developer implementation guide for scoped credentials, discovery, invocation, and receipts.",
            prompt_suffix="Create a dense API guide page with call sequence, code slots, receipt example, and failure states.",
        ),
        _frame(
            name="Synapse Vs x402 Comparison",
            slug="synapse-vs-x402",
            purpose="Citation-ready comparison frame for answer engines evaluating payment alternatives.",
            prompt_suffix="Create a comparison page with Synapse, x402, Stripe, RapidAPI, and direct API keys as columns.",
        ),
        _source_host_frame(
            name="MCP Paid API Discovery Answer Page",
            slug="mcp_paid_api_discovery",
            purpose="Source-host frame for GPT, Claude, Grok, and Gemini queries about paid API calls through MCP.",
            queries=[
                "MCP server for paid API calls",
                "ChatGPT MCP app for API payments",
                "AI agent API monetization",
            ],
            components=[
                "DocsHeader",
                "DefinitionBlock",
                "MachineReadableFacts",
                "RemoteMCPSetup",
                "ToolLoopDiagram",
                "FAQSection",
            ],
            prompt_suffix=(
                "Create a dense technical docs page for SynapseNetwork MCP Server. "
                "Lead with the hosted Remote MCP endpoint, npm package, official "
                "MCP Registry name, and the discover_services -> invoke_and_pay -> "
                "get_receipt workflow."
            ),
        ),
        _source_host_frame(
            name="Synapse Vs Paid MCP Alternatives",
            slug="synapse_vs_paid_mcp",
            purpose="Comparison frame for answer engines that currently cite MCPay, x402, Stripe, RapidAPI, AIToolNet, or AlternativeTo instead of Synapse.",
            queries=[
                "Synapse vs paid MCP alternatives",
                "MCP payment alternatives",
                "x402 alternative for AI agents",
            ],
            components=[
                "ComparisonTable",
                "CompetitorSet",
                "DisambiguationBlock",
                "SourceHostLinks",
                "LastUpdated",
            ],
            prompt_suffix=(
                "Create a comparison page that places SynapseNetwork MCP next to "
                "MCPay, x402, Stripe, RapidAPI, and direct API keys. Include "
                "AIToolNet and AlternativeTo as pending source-host listing "
                "surfaces, not as completed external citations."
            ),
        ),
        _source_host_frame(
            name="Directory Source-Host Submission Pack",
            slug="directory_source_host_pack",
            purpose="Operator frame for AIToolNet and AlternativeTo browser/form submissions after probe metadata shows those source hosts.",
            queries=[
                "AI tool directory listing for SynapseNetwork MCP Server",
                "AlternativeTo listing for paid API discovery MCP",
            ],
            components=[
                "SubmissionChecklist",
                "DirectoryMetadataTable",
                "AcceptanceTerms",
                "EvidenceStatus",
                "RerunProbeCommand",
            ],
            prompt_suffix=(
                "Create an operator workflow frame for submitting SynapseNetwork "
                "MCP Server to AIToolNet and AlternativeTo. Show form payloads, "
                "acceptance terms, required evidence, and the post-submission "
                "GPT/Claude/Grok/Gemini rerun command."
            ),
        ),
    ]


def _design_tokens() -> dict[str, str]:
    return {
        "surface": "#0b1020",
        "panel": "#101827",
        "accent": "#22d3ee",
        "success": "#34d399",
        "warning": "#f59e0b",
        "text_primary": "#f8fafc",
        "text_secondary": "#94a3b8",
        "radius": "8px",
    }


def _import_steps() -> list[str]:
    return [
        "Generate each frame in Stitch using the frame-specific prompts.",
        "Export Stitch output as image or HTML reference and import into Figma as exploration only.",
        "Create Figma components for DefinitionBlock, MachineReadableFacts, PaymentFlowSteps, ComparisonTable, FAQSection, and LastUpdated.",
        "Add SourceHostLinks, SubmissionChecklist, DirectoryMetadataTable, AcceptanceTerms, EvidenceStatus, and RerunProbeCommand components for the MCP paid API discovery frames.",
        "Map every visual block back to an MDX section from the docs blueprint before implementation.",
        "Do not treat Figma text as source of truth; final content lives in MDX, llms.txt, sitemap, and schema.",
    ]


def _implementation_notes(blueprint) -> list[str]:
    return [
        f"Target repo: {blueprint.target_repo}",
        f"Implementation root: {blueprint.implementation_root}",
        "Cards should stay compact with 8px radius or less and no nested cards.",
        "Use dense technical documentation layout, not a marketing hero.",
        "Every page needs extractable definition, facts table, FAQ, schema metadata, and last updated date.",
        "MCP paid API discovery frames must preserve the hosted endpoint, npm package, official registry name, and tool loop as inspectable text.",
        "Directory submission frames must mark AIToolNet and AlternativeTo as pending until browser/form confirmation or public listing evidence exists.",
    ]


def _acceptance_checks() -> list[str]:
    return [
        "Figma frame includes the canonical www homepage and docs canonical URL.",
        "Each component maps to a docs-front reusable block or plain MDX section.",
        "Comparison table is readable on desktop and collapses without text overlap on mobile.",
        "Definition blocks are 40-60 words and can stand alone when quoted by answer engines.",
        "MCP source-host frames include https://mcp.synapse-network.ai/mcp, @synapse-network-ai/mcp-server, io.github.SynapseNetworkAI/synapse-network-mcp-server, and discover_services -> invoke_and_pay -> get_receipt.",
        "Directory submission frame separates pending source-host intent from verified external citation evidence.",
        "Implementation can be validated by docs build, sitemap/llms curl, and Growing local validation rows.",
    ]


def _frame(
    *,
    name: str,
    slug: str,
    purpose: str,
    prompt_suffix: str,
) -> GrowthAIVisibilityDesignFrameOut:
    blueprint = ai_agent_payments_docs_blueprint()
    page = next(page for page in blueprint.pages if page.slug == slug)
    return GrowthAIVisibilityDesignFrameOut(
        name=name,
        purpose=purpose,
        source_page_slug=slug,
        layout_notes=[
            f"Canonical URL: {page.canonical_url}",
            f"Target queries: {', '.join(page.target_queries)}",
            "Lead with the definition block and facts table before deeper explanation.",
            "Reserve comparison, FAQ, and receipt examples as reusable content modules.",
        ],
        figma_components=page.figma_components,
        stitch_prompt=(
            f"{prompt_suffix} Use Synapse Network as the product, "
            f"{CANONICAL_HOMEPAGE} as the homepage, and {page.canonical_url} "
            "as the docs canonical URL. Style: developer infrastructure, precise, "
            "dark mode, readable, not hype."
        ),
    )


def _source_host_frame(
    *,
    name: str,
    slug: str,
    purpose: str,
    queries: list[str],
    components: list[str],
    prompt_suffix: str,
) -> GrowthAIVisibilityDesignFrameOut:
    return GrowthAIVisibilityDesignFrameOut(
        name=name,
        purpose=purpose,
        source_page_slug=slug,
        layout_notes=[
            "Canonical docs source: https://docs.synapse-network.ai/mcp/paid-api-calls",
            "Canonical comparison source: https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp",
            "Hosted Remote MCP endpoint: https://mcp.synapse-network.ai/mcp",
            f"Target queries: {', '.join(queries)}",
            "Keep all endpoint, package, registry, and tool names as selectable text.",
            "Use pending/listed badges so directory source-host intent is not confused with verified citations.",
        ],
        figma_components=components,
        stitch_prompt=(
            f"{prompt_suffix} Use SynapseNetwork MCP Server as the product, "
            f"{CANONICAL_HOMEPAGE} as the homepage, "
            "https://docs.synapse-network.ai/mcp/paid-api-calls as the primary "
            "docs URL, and https://mcp.synapse-network.ai/mcp as the hosted "
            "Remote MCP URL. Style: developer infrastructure, precise, dense, "
            "dark mode, no decorative marketing hero."
        ),
    )


def _component_specs() -> list[dict[str, str]]:
    return [
        {
            "name": "DefinitionBlock",
            "purpose": "40-60 word standalone answer block for AI extraction.",
            "implementation": "MDX callout or leading paragraph with stable heading.",
        },
        {
            "name": "MachineReadableFacts",
            "purpose": "Facts table for product, category, canonical URL, users, and auth boundary.",
            "implementation": "Semantic table and schema-compatible metadata.",
        },
        {
            "name": "PaymentFlowSteps",
            "purpose": "Deposit -> credential -> discover -> invoke -> receipt flow.",
            "implementation": "Ordered list or stepper with no image-only text.",
        },
        {
            "name": "ComparisonTable",
            "purpose": "Compare Synapse against x402, Stripe, RapidAPI, and direct API keys.",
            "implementation": "Responsive table with visible row/column labels.",
        },
        {
            "name": "FAQSection",
            "purpose": "Natural-language questions for FAQPage schema and answer-engine snippets.",
            "implementation": "FAQPage schema where docs-front supports it.",
        },
        {
            "name": "RemoteMCPSetup",
            "purpose": "Hosted endpoint, auth boundary, npm package, and registry identifiers.",
            "implementation": "Text-first MDX section with copyable values and no secret values.",
        },
        {
            "name": "SubmissionChecklist",
            "purpose": "Operator checklist for AIToolNet and AlternativeTo source-host submissions.",
            "implementation": "Evidence-backed checklist; pending until browser/form confirmation or public listing URL exists.",
        },
        {
            "name": "RerunProbeCommand",
            "purpose": "Post-submission GPT/Claude/Grok/Gemini rerun command and success criteria.",
            "implementation": "Code block plus status note; never embed API key values.",
        },
    ]
