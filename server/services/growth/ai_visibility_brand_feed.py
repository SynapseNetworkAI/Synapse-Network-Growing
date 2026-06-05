"""Brand-disambiguation feed readiness policy helpers."""

from __future__ import annotations

from typing import Protocol


class ProbeLike(Protocol):
    ok: bool
    body_snippet: str
    body_match_text: str


def github_org_profile_ready(profile: ProbeLike) -> bool:
    text = profile.body_match_text or profile.body_snippet
    return profile.ok and all(
        item in text
        for item in [
            "SynapseNetwork is the settlement layer",
            "https://www.synapse-network.ai/",
            "https://mcp.synapse-network.ai/mcp",
        ]
    )


def brand_feed_missing(
    *,
    bare_redirect_ready: bool,
    robots_ready: bool,
    blocked_crawlers: object,
    llms_ready: bool,
    sitemap_ready: bool,
    github_profile_ready: bool,
) -> list[str]:
    return [
        message
        for ok, message in [
            (
                bare_redirect_ready,
                "Bare domain must permanently redirect to https://www.synapse-network.ai/.",
            ),
            (robots_ready, "robots.txt must be publicly reachable."),
            (
                robots_ready and not blocked_crawlers,
                "robots.txt must not block answer-engine search crawlers from public pages.",
            ),
            (llms_ready, "llms.txt must contain Synapse Network product facts."),
            (sitemap_ready, "sitemap.xml must include www canonical URLs."),
            (
                github_profile_ready,
                "GitHub organization profile must expose Synapse homepage and Remote MCP facts.",
            ),
        ]
        if not ok
    ]


def brand_next_action(passed: bool) -> str:
    if passed:
        return "Run GPT/Claude/Grok brand probes with generated template."
    return (
        "Deploy canonical www redirect, robots, llms.txt, sitemap, and GitHub "
        "organization profile fixes before external probes."
    )
