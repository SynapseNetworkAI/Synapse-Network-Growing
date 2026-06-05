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
    frames = [
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
    ]
    return GrowthAIVisibilityDesignHandoffOut(
        title="Synapse AI Agent Payments Stitch To Figma Handoff",
        canonical_domain=CANONICAL_HOMEPAGE,
        figma_file_name="Synapse AI Agent Payments Docs - AI Visibility",
        stitch_prompt=plan.design_plan.stitch_prompt,
        frames=frames,
        component_specs=_component_specs(),
        design_tokens={
            "surface": "#0b1020",
            "panel": "#101827",
            "accent": "#22d3ee",
            "success": "#34d399",
            "warning": "#f59e0b",
            "text_primary": "#f8fafc",
            "text_secondary": "#94a3b8",
            "radius": "8px",
        },
        import_steps=[
            "Generate the three frames in Stitch using the frame-specific prompts.",
            "Export Stitch output as image or HTML reference and import into Figma as exploration only.",
            "Create Figma components for DefinitionBlock, MachineReadableFacts, PaymentFlowSteps, ComparisonTable, FAQSection, and LastUpdated.",
            "Map every visual block back to an MDX section from the docs blueprint before implementation.",
            "Do not treat Figma text as source of truth; final content lives in MDX, llms.txt, sitemap, and schema.",
        ],
        implementation_notes=[
            f"Target repo: {blueprint.target_repo}",
            f"Implementation root: {blueprint.implementation_root}",
            "Cards should stay compact with 8px radius or less and no nested cards.",
            "Use dense technical documentation layout, not a marketing hero.",
            "Every page needs extractable definition, facts table, FAQ, schema metadata, and last updated date.",
        ],
        acceptance_checks=[
            "Figma frame includes the canonical www homepage and docs canonical URL.",
            "Each component maps to a docs-front reusable block or plain MDX section.",
            "Comparison table is readable on desktop and collapses without text overlap on mobile.",
            "Definition blocks are 40-60 words and can stand alone when quoted by answer engines.",
            "Implementation can be validated by docs build, sitemap/llms curl, and Growing local validation rows.",
        ],
    )


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
    ]
