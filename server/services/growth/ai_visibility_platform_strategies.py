from __future__ import annotations

from server.schemas_growth import GrowthAIVisibilityPlatformStrategyOut


def platform_strategies(
    feed_key: str,
) -> list[GrowthAIVisibilityPlatformStrategyOut]:
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
            _platform_strategy(
                "gemini",
                "Google-indexed docs, llms.txt, and Remote MCP metadata for Gemini answers.",
                ["www", "docs", "github", "mcp_registry", "www_llms"],
                [
                    "Gemini MCP server for paid API calls",
                    "AI agent payment API with MCP",
                ],
                "Gemini mentions Synapse and cites the official www, docs, GitHub, or MCP Registry surface.",
                "Refresh sitemap/robots/llms feed plus Google-indexable docs, then rerun Gemini grounded search.",
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
        _platform_strategy(
            "gemini",
            "Google-indexed canonical docs and structured answer blocks.",
            ["www", "docs", "github", "sitemap"],
            ["AI agent payment API", "How can AI agents pay for APIs?"],
            "Gemini mentions Synapse and cites the official www, docs, or GitHub surface.",
            "Refresh indexable docs, sitemap, and schema-backed answer blocks before rerunning Gemini grounded search.",
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
