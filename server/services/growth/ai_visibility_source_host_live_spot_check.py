"""Read-only spot checks for source-host public listing visibility."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
import re
import urllib.error
import urllib.request

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilitySourceHostLiveSpotCheckItemOut,
    GrowthAIVisibilitySourceHostLiveSpotCheckOut,
)
from server.services.growth.ai_visibility_presence_plan import DEFAULT_FEED_KEY
from server.services.growth.ai_visibility_source_host_feed import (
    ai_visibility_source_host_execution_checklist,
)

BRAND_TERMS = ["synapse network", "synapsenetwork"]
PAYLOAD_TERMS = [
    "mcp.synapse-network.ai",
    "github.com/synapsenetworkai/synapse-network-mcp-server",
    "@synapse-network-ai/mcp-server",
    "discover_services",
    "invoke_and_pay",
    "get_receipt",
]
MATCH_TERMS = [*BRAND_TERMS, *PAYLOAD_TERMS]


def ai_visibility_source_host_live_spot_check(
    db: Session,
    *,
    feed_key: str = DEFAULT_FEED_KEY,
    run_group: str | None = None,
    execute: bool = False,
    fetcher: Callable[[str], tuple[int, str]] | None = None,
) -> GrowthAIVisibilitySourceHostLiveSpotCheckOut:
    checklist = ai_visibility_source_host_execution_checklist(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )
    items = [
        _check_search_url(
            host=item.host, search_url=url, execute=execute, fetcher=fetcher
        )
        for item in checklist.items
        for url in item.live_listing_search_urls
    ]
    blockers = list(checklist.blockers)
    if not items:
        blockers.append("No source-host live listing search URLs are available.")
    if (
        execute
        and items
        and not any(item.status == "candidate_found" for item in items)
    ):
        blockers.append(
            "No Synapse source-host listing candidate was found in search URLs."
        )
    return GrowthAIVisibilitySourceHostLiveSpotCheckOut(
        generated_at=datetime.now(timezone.utc),
        feed_key=checklist.feed_key,
        run_group=checklist.run_group,
        execute=execute,
        status=_overall_status(items, execute),
        items=items,
        blockers=blockers,
        commands={
            "export_dry_run": (
                "python scripts/growth/generate_ai_visibility_source_host_live_spot_check.py "
                f"--feed-key {checklist.feed_key} "
                "--output docs/archive/evidence/growth/ai-visibility/"
                "YYYY-MM-DD-source-host-live-spot-check.json"
            ),
            "execute": (
                "python scripts/growth/generate_ai_visibility_source_host_live_spot_check.py "
                f"--feed-key {checklist.feed_key} --execute "
                "--output docs/archive/evidence/growth/ai-visibility/"
                "YYYY-MM-DD-source-host-live-spot-check.json"
            ),
            "record_live_listing": (
                "python scripts/growth/record_ai_visibility_source_host_execution.py "
                "--evidence-mode live-listing --surface <surface> "
                "--source-url <public-listing-url>"
            ),
        },
    )


def _check_search_url(
    *,
    host: str,
    search_url: str,
    execute: bool,
    fetcher: Callable[[str], tuple[int, str]] | None,
) -> GrowthAIVisibilitySourceHostLiveSpotCheckItemOut:
    if not execute:
        return GrowthAIVisibilitySourceHostLiveSpotCheckItemOut(
            host=host,
            search_url=search_url,
            status="pending_execute",
            missing_terms=MATCH_TERMS,
            next_action="Run with --execute to fetch this search URL.",
        )
    try:
        http_status, body = (fetcher or _fetch_url)(search_url)
    except Exception as exc:  # noqa: BLE001 - bounded public diagnostic
        return GrowthAIVisibilitySourceHostLiveSpotCheckItemOut(
            host=host,
            search_url=search_url,
            status="fetch_failed",
            missing_terms=MATCH_TERMS,
            evidence_excerpt=str(exc)[:300],
            next_action="Open the search URL in a browser or retry after the host is reachable.",
        )
    matched, missing = _term_matches(body)
    candidate_found = _has_brand_and_payload_match(matched)
    return GrowthAIVisibilitySourceHostLiveSpotCheckItemOut(
        host=host,
        search_url=search_url,
        status="candidate_found" if candidate_found else "not_found",
        http_status=http_status,
        matched_terms=matched,
        missing_terms=missing,
        evidence_excerpt=_excerpt(body),
        next_action=(
            "Open the candidate result, capture the public listing URL, and record live-listing evidence."
            if matched
            else "Submit or wait for the directory listing, then rerun this spot check."
        ),
    )


def _fetch_url(url: str) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Synapse-Growing-AI-Visibility-SpotCheck/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
            return response.status, response.read(300_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(20_000).decode("utf-8", "replace")
        return exc.code, body


def _term_matches(body: str) -> tuple[list[str], list[str]]:
    lowered = body.lower()
    matched = [term for term in MATCH_TERMS if term in lowered]
    missing = [term for term in MATCH_TERMS if term not in lowered]
    return matched, missing


def _has_brand_and_payload_match(matched: list[str]) -> bool:
    matched_set = set(matched)
    return bool(matched_set.intersection(BRAND_TERMS)) and bool(
        matched_set.intersection(PAYLOAD_TERMS)
    )


def _excerpt(body: str) -> str:
    compact = re.sub(r"\s+", " ", body).strip()
    lower = compact.lower()
    index = min(
        [lower.find(term) for term in MATCH_TERMS if lower.find(term) >= 0],
        default=0,
    )
    return compact[max(index - 120, 0) : index + 380]


def _overall_status(
    items: list[GrowthAIVisibilitySourceHostLiveSpotCheckItemOut],
    execute: bool,
) -> str:
    if not items:
        return "blocked_until_search_urls"
    if not execute:
        return "ready_to_execute"
    if any(item.status == "candidate_found" for item in items):
        return "candidate_found_needs_live_listing_evidence"
    if any(item.status == "fetch_failed" for item in items):
        return "partial_fetch_failure"
    return "no_candidate_found"
