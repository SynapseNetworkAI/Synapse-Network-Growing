"""Live AI visibility feed validation service."""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from scripts.growth.record_ai_visibility_probe import ProbeRecord
from server.services.growth.ai_visibility_mcp_feed import (
    mcp_feed_missing,
    mcp_next_action,
)
from server.services.growth.ai_visibility_robots import (
    AI_SEARCH_CRAWLERS,
    blocked_ai_crawlers,
    group_blocks_public,
    parse_robots_groups,
    robots_ai_crawler_policy,
    wildcard_allows_public,
)

CANONICAL_HOMEPAGE = "https://www.synapse-network.ai/"
FEED_KEYS = {
    "brand_disambiguation_www",
    "agent_payment_category_pages",
    "mcp_paid_api_discovery",
}
BODY_SNIPPET_CHARS = 1200
BODY_MATCH_CHARS = 250_000

__all__ = [
    "AI_SEARCH_CRAWLERS",
    "CANONICAL_HOMEPAGE",
    "FEED_KEYS",
    "HttpProbeResult",
    "blocked_ai_crawlers",
    "group_blocks_public",
    "parse_feed_keys",
    "parse_robots_groups",
    "robots_ai_crawler_policy",
    "validate_feed",
    "wildcard_allows_public",
]


@dataclass(frozen=True)
class HttpProbeResult:
    label: str
    url: str
    status: int = 0
    final_url: str = ""
    body_snippet: str = ""
    body_match_text: str = field(default="", repr=False)
    error: str = ""
    contains_synapse: bool = False
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 400


def parse_feed_keys(raw_values: list[str] | None) -> list[str]:
    if not raw_values:
        return sorted(FEED_KEYS)
    feed_keys = [item.strip() for item in raw_values if item.strip()]
    unknown = [item for item in feed_keys if item not in FEED_KEYS]
    if unknown:
        raise ValueError(
            f"unknown feed key(s): {', '.join(unknown)}; expected one of {sorted(FEED_KEYS)}"
        )
    return feed_keys


def validate_feed(*, feed_key: str, run_group: str) -> list[ProbeRecord]:
    if feed_key == "brand_disambiguation_www":
        return validate_brand_feed(run_group)
    if feed_key == "agent_payment_category_pages":
        return validate_agent_payment_feed(run_group)
    if feed_key == "mcp_paid_api_discovery":
        return validate_mcp_feed(run_group)
    raise ValueError(f"unsupported feed key: {feed_key}")


def validate_brand_feed(run_group: str) -> list[ProbeRecord]:
    bare, robots, llms, sitemap = _brand_feed_checks()
    crawler_policy = robots_ai_crawler_policy(robots.body_snippet if robots.ok else "")
    passed = _brand_feed_passed(
        bare=bare,
        robots=robots,
        llms=llms,
        sitemap=sitemap,
        crawler_policy=crawler_policy,
    )
    return [
        record(
            feed_key="brand_disambiguation_www",
            run_group=run_group,
            platform="www_live_validation",
            query="Brand disambiguation live feed readiness",
            passed=passed,
            checks=[bare, robots, llms, sitemap],
            missing_facts=_brand_feed_missing(
                bare=bare,
                robots=robots,
                llms=llms,
                sitemap=sitemap,
                crawler_policy=crawler_policy,
            ),
            next_action=_brand_feed_next_action(passed),
            metadata_extra={"ai_crawler_policy": crawler_policy},
        )
    ]


def _brand_feed_checks() -> tuple[
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
]:
    bare = fetch(
        "bare_domain_redirect",
        "https://synapse-network.ai/",
        method="HEAD",
        follow_redirects=False,
    )
    robots = fetch("robots", "https://www.synapse-network.ai/robots.txt")
    llms = fetch("llms", "https://www.synapse-network.ai/llms.txt")
    sitemap = fetch("sitemap", "https://www.synapse-network.ai/sitemap.xml")
    return bare, robots, llms, sitemap


def _brand_feed_passed(
    *,
    bare: HttpProbeResult,
    robots: HttpProbeResult,
    llms: HttpProbeResult,
    sitemap: HttpProbeResult,
    crawler_policy: dict[str, object],
) -> bool:
    return (
        is_redirect_to_www(bare)
        and robots.ok
        and not crawler_policy["blocked_crawlers"]
        and llms.ok
        and has_synapse_content(llms)
        and sitemap.ok
        and "www.synapse-network.ai" in sitemap.body_snippet
    )


def _brand_feed_missing(
    *,
    bare: HttpProbeResult,
    robots: HttpProbeResult,
    llms: HttpProbeResult,
    sitemap: HttpProbeResult,
    crawler_policy: dict[str, object],
) -> list[str]:
    return missing_for_checks(
        [
            (
                is_redirect_to_www(bare),
                "Bare domain must permanently redirect to https://www.synapse-network.ai/.",
            ),
            (robots.ok, "robots.txt must be publicly reachable."),
            (
                robots.ok and not crawler_policy["blocked_crawlers"],
                "robots.txt must not block answer-engine search crawlers from public pages.",
            ),
            (
                llms.ok and has_synapse_content(llms),
                "llms.txt must contain Synapse Network product facts.",
            ),
            (
                sitemap.ok and "www.synapse-network.ai" in sitemap.body_snippet,
                "sitemap.xml must include www canonical URLs.",
            ),
        ]
    )


def _brand_feed_next_action(passed: bool) -> str:
    if passed:
        return "Run GPT/Claude/Grok brand probes with generated template."
    return (
        "Deploy canonical www redirect, robots, llms.txt, and sitemap fixes before "
        "external probes."
    )


def validate_agent_payment_feed(run_group: str) -> list[ProbeRecord]:
    www_page = fetch(
        "www_ai_agent_payments",
        "https://www.synapse-network.ai/ai-agent-payments",
    )
    api_page = fetch(
        "www_agent_payment_api",
        "https://www.synapse-network.ai/agent-payment-api",
    )
    docs_page = fetch(
        "docs_ai_agent_payments",
        "https://docs.synapse-network.ai/ai-agent-payments",
    )
    checks = [www_page, api_page, docs_page]
    passed = all(check.ok for check in checks) and all(
        has_synapse_content(check) for check in checks
    )
    missing = missing_for_checks(
        [
            (www_page.ok, "www /ai-agent-payments must be live."),
            (api_page.ok, "www /agent-payment-api must be live."),
            (docs_page.ok, "docs AI Agent Payments category must be live."),
            (passed, "Live pages must include extractable Synapse answer text."),
        ]
    )
    return [
        record(
            feed_key="agent_payment_category_pages",
            run_group=run_group,
            platform="www_live_validation",
            query="AI Agent Payments live feed readiness",
            passed=passed,
            checks=checks,
            missing_facts=missing,
            next_action=(
                "Run GPT/Claude/Grok category probes for AI agent payment queries."
                if passed
                else "Deploy AI Agent Payments www/docs pages before external probes."
            ),
        )
    ]


def validate_mcp_feed(run_group: str) -> list[ProbeRecord]:
    homepage, docs_page, docs_robots, www_llms, readyz, unauth_mcp, registry = (
        _mcp_feed_checks()
    )
    checks = [homepage, docs_page, docs_robots, www_llms, readyz, unauth_mcp, registry]
    docs_crawler_policy = _mcp_docs_crawler_policy(docs_robots)
    (
        homepage_ready,
        docs_ready,
        llms_ready,
        docs_crawler_ready,
        remote_ready,
        registry_ready,
    ) = (
        _mcp_feed_readiness(
            homepage=homepage,
            docs_page=docs_page,
            docs_robots=docs_robots,
            www_llms=www_llms,
            readyz=readyz,
            unauth_mcp=unauth_mcp,
            registry=registry,
            docs_crawler_policy=docs_crawler_policy,
        )
    )
    passed = all(
        [homepage_ready, docs_ready, docs_crawler_ready, llms_ready, remote_ready, registry_ready]
    )
    missing = mcp_feed_missing(
        homepage_ready=homepage_ready,
        docs_page=docs_page,
        docs_ready=docs_ready,
        llms_ready=llms_ready,
        docs_robots=docs_robots,
        docs_crawler_ready=docs_crawler_ready,
        readyz=readyz,
        unauth_mcp=unauth_mcp,
        registry_ready=registry_ready,
    )
    return [
        record(
            feed_key="mcp_paid_api_discovery",
            run_group=run_group,
            platform="mcp_live_validation",
            query="Remote MCP live readiness",
            passed=passed,
            checks=checks,
            missing_facts=missing,
            next_action=mcp_next_action(
                passed=passed,
                homepage_ready=homepage_ready,
                docs_ready=docs_ready,
                llms_ready=llms_ready,
                docs_crawler_ready=docs_crawler_ready,
                remote_ready=remote_ready,
                registry_ready=registry_ready,
            ),
            metadata_extra={
                "docs_ai_crawler_policy": docs_crawler_policy,
            },
        )
    ]


def _mcp_feed_checks() -> tuple[
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
    HttpProbeResult,
]:
    homepage = fetch("www_homepage", CANONICAL_HOMEPAGE)
    docs_page = fetch(
        "docs_mcp_paid_api_calls",
        "https://docs.synapse-network.ai/mcp/paid-api-calls",
    )
    docs_robots = fetch("docs_robots", "https://docs.synapse-network.ai/robots.txt")
    www_llms = fetch("www_llms_mcp", "https://www.synapse-network.ai/llms.txt")
    readyz = fetch("mcp_readyz", "https://mcp.synapse-network.ai/readyz")
    unauth_mcp = fetch(
        "mcp_unauth_post",
        "https://mcp.synapse-network.ai/mcp",
        method="POST",
        data=b"{}",
    )
    registry = fetch(
        "mcp_registry",
        "https://registry.modelcontextprotocol.io/v0.1/servers"
        "?search=io.github.SynapseNetworkAI/synapse-network-mcp-server",
    )
    return homepage, docs_page, docs_robots, www_llms, readyz, unauth_mcp, registry


def _mcp_docs_crawler_policy(docs_robots: HttpProbeResult) -> dict[str, object]:
    docs_crawler_source = (
        (docs_robots.body_match_text or docs_robots.body_snippet)
        if docs_robots.ok
        else ""
    )
    return robots_ai_crawler_policy(docs_crawler_source)


def _mcp_feed_readiness(
    *,
    homepage: HttpProbeResult,
    docs_page: HttpProbeResult,
    docs_robots: HttpProbeResult,
    www_llms: HttpProbeResult,
    readyz: HttpProbeResult,
    unauth_mcp: HttpProbeResult,
    registry: HttpProbeResult,
    docs_crawler_policy: dict[str, object],
) -> tuple[bool, bool, bool, bool, bool, bool]:
    homepage_ready = homepage.ok and has_synapse_content(homepage)
    docs_ready = docs_page.ok and has_all_text(
        docs_page,
        [
            "MCP Server for Paid API Calls",
            "Synapse",
            "discover_services",
            "invoke_and_pay",
            "get_receipt",
        ],
    )
    llms_ready = www_llms.ok and has_all_text(
        www_llms,
        ["MCP Server for Paid API Calls", "https://mcp.synapse-network.ai/mcp"],
    )
    docs_crawler_ready = docs_robots.ok and not docs_crawler_policy["blocked_crawlers"]
    remote_ready = readyz.ok and unauth_mcp.status == 401
    registry_ready = registry.ok and has_all_text(
        registry,
        [
            "io.github.SynapseNetworkAI/synapse-network-mcp-server",
            "https://mcp.synapse-network.ai/mcp",
            "hosted Remote MCP",
            "paid API discovery",
        ],
    )
    return homepage_ready, docs_ready, llms_ready, docs_crawler_ready, remote_ready, registry_ready


def fetch(
    label: str,
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    timeout: int = 20,
    follow_redirects: bool = True,
) -> HttpProbeResult:
    request = urllib.request.Request(url, data=data, method=method)
    try:
        opener = urllib.request.urlopen if follow_redirects else no_redirect_urlopen
        with opener(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(BODY_MATCH_CHARS).decode("utf-8", errors="replace")
            return HttpProbeResult(
                label=label,
                url=url,
                status=int(response.status),
                final_url=response.geturl(),
                body_snippet=body[:BODY_SNIPPET_CHARS],
                body_match_text=body,
                contains_synapse=has_synapse_brand_fact(body),
                headers={key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(BODY_MATCH_CHARS).decode("utf-8", errors="replace")
        return HttpProbeResult(
            label=label,
            url=url,
            status=int(exc.code),
            final_url=exc.geturl(),
            body_snippet=body[:BODY_SNIPPET_CHARS],
            body_match_text=body,
            contains_synapse=has_synapse_brand_fact(body),
            headers={key.lower(): value for key, value in exc.headers.items()},
            error="",
        )
    except Exception as exc:
        return HttpProbeResult(label=label, url=url, error=str(exc))


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def no_redirect_urlopen(request, *, timeout: int):  # noqa: ANN001
    return urllib.request.build_opener(NoRedirectHandler).open(request, timeout=timeout)


def is_redirect_to_www(result: HttpProbeResult) -> bool:
    location = result.headers.get("location", "")
    canonical_root = CANONICAL_HOMEPAGE.rstrip("/")
    return result.status in {301, 308} and location.rstrip("/") == canonical_root


def has_synapse_brand_fact(text: str) -> bool:
    return "Synapse" in text


def has_synapse_content(result: HttpProbeResult) -> bool:
    return result.contains_synapse or has_synapse_brand_fact(result.body_snippet)


def has_all_text(result: HttpProbeResult, expected: list[str]) -> bool:
    searchable_body = result.body_match_text or result.body_snippet
    return all(item in searchable_body for item in expected)


def missing_for_checks(checks: list[tuple[bool, str]]) -> list[str]:
    return [message for ok, message in checks if not ok]


def record(
    *,
    feed_key: str,
    run_group: str,
    platform: str,
    query: str,
    passed: bool,
    checks: list[HttpProbeResult],
    missing_facts: list[str],
    next_action: str,
    metadata_extra: dict[str, object] | None = None,
) -> ProbeRecord:
    return ProbeRecord(
        query=query,
        platform=platform,
        feed_key=feed_key,
        run_group=run_group,
        answer_summary=summary_for_checks(passed, checks),
        synapse_mentioned=passed,
        synapse_cited=passed,
        cited_urls=[check.url for check in checks if check.ok],
        missing_facts=missing_facts,
        next_action=next_action,
        evidence_url="",
        metadata={
            "mode": "feed_live_validation",
            "checked_at": datetime.now(UTC).isoformat(),
            "checks": [probe_result_metadata(check) for check in checks],
            **(metadata_extra or {}),
        },
    )


def probe_result_metadata(result: HttpProbeResult) -> dict[str, object]:
    payload = asdict(result)
    payload.pop("body_match_text", None)
    return payload


def summary_for_checks(passed: bool, checks: list[HttpProbeResult]) -> str:
    status = "passed" if passed else "blocked"
    parts = [
        f"{check.label}={check.status or check.error or 'unknown'}" for check in checks
    ]
    return f"Live feed validation {status}: " + "; ".join(parts)
