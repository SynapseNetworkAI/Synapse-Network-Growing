"""Remote MCP feed readiness policy helpers."""

from __future__ import annotations

from typing import Protocol


class ProbeLike(Protocol):
    status: int
    body_snippet: str
    body_match_text: str
    contains_synapse: bool

    @property
    def ok(self) -> bool: ...


def mcp_feed_readiness(
    *,
    homepage: ProbeLike,
    docs_page: ProbeLike,
    docs_robots: ProbeLike,
    www_llms: ProbeLike,
    readyz: ProbeLike,
    unauth_mcp: ProbeLike,
    npm_package: ProbeLike,
    registry: ProbeLike,
    docs_crawler_policy: dict[str, object],
) -> tuple[bool, bool, bool, bool, bool, bool, bool]:
    homepage_ready = homepage.ok and _has_synapse_content(homepage)
    docs_ready = docs_page.ok and _has_all_text(
        docs_page,
        [
            "MCP Server for Paid API Calls",
            "Synapse",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
    )
    llms_ready = www_llms.ok and _has_all_text(
        www_llms,
        ["MCP Server for Paid API Calls", "https://mcp.synapse-network.ai/mcp"],
    )
    docs_crawler_ready = docs_robots.ok and not docs_crawler_policy["blocked_crawlers"]
    remote_ready = readyz.ok and unauth_mcp.status == 401
    npm_package_ready = npm_package.ok and _has_all_text(npm_package, ['"0.1.4"'])
    registry_ready = registry.ok and _has_all_text(
        registry,
        [
            "io.github.SynapseNetworkAI/synapse-network-mcp-server",
            "https://mcp.synapse-network.ai/mcp",
            "hosted Remote MCP",
            "paid API discovery",
        ],
    )
    return (
        homepage_ready,
        docs_ready,
        llms_ready,
        docs_crawler_ready,
        remote_ready,
        npm_package_ready,
        registry_ready,
    )


def _has_synapse_content(result: ProbeLike) -> bool:
    return result.contains_synapse or "Synapse" in result.body_snippet


def _has_all_text(result: ProbeLike, expected: list[str]) -> bool:
    searchable_body = result.body_match_text or result.body_snippet
    return all(item in searchable_body for item in expected)


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
    npm_package_ready: bool,
    registry_ready: bool,
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
            (
                npm_package_ready,
                "npm package @synapse-network-ai/mcp-server must publish version 0.1.4 before the MCP Registry can refresh.",
            ),
            (
                registry_ready,
                "Official MCP Registry listing must include refreshed hosted Remote MCP paid API discovery metadata.",
            ),
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
    npm_package_ready: bool,
    registry_ready: bool,
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
    if not npm_package_ready:
        return (
            "Publish @synapse-network-ai/mcp-server@0.1.4 to npm, then refresh "
            "the official MCP Registry metadata with mcp-publisher."
        )
    if not registry_ready:
        return (
            "Refresh the official MCP Registry metadata with mcp-publisher before "
            "external MCP discovery probes."
        )
    return "Review MCP feed validation blockers before external MCP discovery probes."
