"""Remote MCP feed readiness policy helpers."""

from __future__ import annotations

from typing import Protocol


class ProbeLike(Protocol):
    status: int

    @property
    def ok(self) -> bool: ...


def mcp_feed_missing(
    *,
    homepage_ready: bool,
    docs_page: ProbeLike,
    docs_ready: bool,
    llms_ready: bool,
    docs_robots: ProbeLike,
    docs_crawler_ready: bool,
    readyz: ProbeLike,
    unauth_mcp: ProbeLike,
) -> list[str]:
    return [
        message
        for ok, message in [
            (
                homepage_ready,
                "Canonical homepage https://www.synapse-network.ai/ must be live and include Synapse facts.",
            ),
            (docs_page.ok, "Docs /mcp/paid-api-calls page must be live."),
            (
                docs_ready,
                "Docs /mcp/paid-api-calls must expose MCP paid API answer text and tool names.",
            ),
            (
                llms_ready,
                "www llms.txt must include the MCP paid API calls guide and Remote MCP endpoint.",
            ),
            (docs_robots.ok, "Docs robots.txt must be publicly reachable."),
            (
                docs_crawler_ready,
                "Docs robots.txt must not block answer-engine search crawlers from public docs.",
            ),
            (readyz.ok, "Remote MCP /readyz must be reachable."),
            (unauth_mcp.status == 401, "Unauthenticated /mcp POST must return 401."),
        ]
        if not ok
    ]


def mcp_next_action(
    *,
    passed: bool,
    homepage_ready: bool,
    docs_ready: bool,
    llms_ready: bool,
    docs_crawler_ready: bool,
    remote_ready: bool,
) -> str:
    if passed:
        return "Run MCP discovery probes and ChatGPT/Claude connector checks."
    if not homepage_ready:
        return (
            "Fix the canonical www homepage feed before external MCP discovery "
            "probes so answer engines can resolve the official Synapse source."
        )
    if not docs_ready or not llms_ready:
        return (
            "Publish /mcp/paid-api-calls and www llms.txt MCP feed updates before "
            "external answer-engine probes."
        )
    if not docs_crawler_ready:
        return "Fix docs robots.txt AI crawler access before external MCP discovery probes."
    if not remote_ready:
        return "Fix Remote MCP readiness/auth boundary before external MCP discovery probes."
    return "Review MCP feed validation blockers before external MCP discovery probes."
