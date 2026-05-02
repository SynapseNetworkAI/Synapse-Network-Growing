"""Seed channels for developer distribution."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DistributionSeedAccount:
    platform: str
    channel_key: str
    display_name: str
    signup_url: str
    account_type: str
    priority: str
    notes: str
    publish_mode: str = "manual_only"
    api_capability: str = "none"


DEFAULT_DISTRIBUTION_ACCOUNTS = (
    DistributionSeedAccount(
        "x",
        "official",
        "X Official Account",
        "https://x.com/SynapseNetworkA",
        "official",
        "P0",
        "Official X account. API posting is allowed only after Human Gate confirmation.",
        "api_human_gated",
        "post",
    ),
    DistributionSeedAccount(
        "hacker_news",
        "news.ycombinator.com",
        "Hacker News",
        "https://news.ycombinator.com/login",
        "founder_operator",
        "P0",
        "Show HN, hard technical articles, demos, and open-source tools. Keep titles factual and non-marketing.",
        "manual_only",
        "none",
    ),
    DistributionSeedAccount(
        "reddit",
        "reddit.com",
        "Reddit",
        "https://www.reddit.com/register/",
        "official_and_founder",
        "P0",
        "Use the account for discussion and technical explanations. Warm up via comments before posting links.",
        "manual_only",
        "post",
    ),
    DistributionSeedAccount(
        "reddit",
        "r/LocalLLaMA",
        "Reddit r/LocalLLaMA",
        "https://www.reddit.com/r/LocalLLaMA/",
        "subreddit",
        "P0",
        "Only distribute local/open-source agent, MCP, tooling, and cost-control content.",
        "manual_only",
        "post",
    ),
    DistributionSeedAccount(
        "reddit",
        "r/OpenAI",
        "Reddit r/OpenAI",
        "https://www.reddit.com/r/OpenAI/",
        "subreddit",
        "P0",
        "Frame posts as engineering lessons or architecture retrospectives, not ads.",
        "manual_only",
        "post",
    ),
    DistributionSeedAccount(
        "reddit",
        "r/java",
        "Reddit r/java",
        "https://www.reddit.com/r/java/",
        "subreddit",
        "P0",
        "Use only when Java SDK, MCP server, or provider runtime content is real and stable.",
        "manual_only",
        "post",
    ),
    DistributionSeedAccount(
        "v2ex",
        "v2ex.com",
        "V2EX",
        "https://www.v2ex.com/signup",
        "founder_operator",
        "P0",
        "Chinese engineering discussion, launch retrospectives, and architecture notes.",
        "manual_only",
        "none",
    ),
    DistributionSeedAccount(
        "v2ex",
        "programmer",
        "V2EX 程序员",
        "https://www.v2ex.com/go/programmer",
        "community_node",
        "P0",
        "Engineering retrospectives and agent developer tooling. Avoid AI-generated reply spam.",
        "manual_only",
        "none",
    ),
    DistributionSeedAccount(
        "v2ex",
        "openai",
        "V2EX OpenAI",
        "https://www.v2ex.com/go/openai",
        "community_node",
        "P0",
        "OpenAI/Codex/agent workflow content for Chinese technical readers.",
        "manual_only",
        "none",
    ),
    DistributionSeedAccount(
        "v2ex",
        "java",
        "V2EX Java",
        "https://www.v2ex.com/go/java",
        "community_node",
        "P0",
        "Java SDK and MCP server posts after the Java artifacts are real.",
        "manual_only",
        "none",
    ),
    DistributionSeedAccount(
        "dev",
        "dev.to",
        "DEV Community",
        "https://dev.to/enter",
        "official_author",
        "P1",
        "English technical tutorials, SDK quickstarts, and developer blogs. Set canonical URL.",
        "manual_only",
        "article",
    ),
    DistributionSeedAccount(
        "hashnode",
        "hashnode.com",
        "Hashnode",
        "https://hashnode.com/",
        "team_blog",
        "P1",
        "Developer blog mirrors and tutorials. Set canonical URL for SEO hygiene.",
        "manual_only",
        "article",
    ),
    DistributionSeedAccount(
        "product_hunt",
        "producthunt.com",
        "Product Hunt",
        "https://www.producthunt.com/",
        "launch_only",
        "P1",
        "Launch-day distribution only; not part of daily article distribution.",
        "manual_only",
        "none",
    ),
)
