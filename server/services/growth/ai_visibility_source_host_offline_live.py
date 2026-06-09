"""Offline live-listing spot checks for source-host checklist evidence."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from server.schemas_growth import (
    GrowthAIVisibilitySourceHostExecutionChecklistOut,
    GrowthAIVisibilitySourceHostLiveSpotCheckItemOut,
    GrowthAIVisibilitySourceHostLiveSpotCheckOut,
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
FETCH_BLOCK_HTTP_STATUSES = {403, 429}
FETCH_BLOCK_MARKERS = [
    "cf-mitigated",
    "challenge-platform",
    "challenges.cloudflare.com",
    "cloudflare",
    "just a moment",
    "attention required",
    "noindex,nofollow",
    "verify you are human",
    "browser check",
    "captcha",
]


def source_host_live_spot_check_from_checklist(
    checklist_path: str | Path,
    *,
    execute: bool = False,
) -> GrowthAIVisibilitySourceHostLiveSpotCheckOut:
    checklist = GrowthAIVisibilitySourceHostExecutionChecklistOut.model_validate(
        _read_json(checklist_path)
    )
    return source_host_live_spot_check_from_checklist_model(
        checklist,
        execute=execute,
        fetcher=None,
        execute_command=(
            "python scripts/growth/generate_ai_visibility_source_host_live_spot_check.py "
            f"--checklist-file {checklist_path} --execute"
        ),
    )


def source_host_live_spot_check_from_checklist_model(
    checklist: GrowthAIVisibilitySourceHostExecutionChecklistOut,
    *,
    execute: bool = False,
    fetcher: Callable[[str], tuple[int, str]] | None = None,
    execute_command: str = "",
) -> GrowthAIVisibilitySourceHostLiveSpotCheckOut:
    items = [
        _check_search_url(
            host=item.host,
            search_url=url,
            execute=execute,
            fetcher=fetcher,
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
            "execute": (
                execute_command
                or "python scripts/growth/generate_ai_visibility_source_host_live_spot_check.py --execute"
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
    if _is_fetch_blocked(http_status, body):
        return GrowthAIVisibilitySourceHostLiveSpotCheckItemOut(
            host=host,
            search_url=search_url,
            status="fetch_blocked",
            http_status=http_status,
            missing_terms=MATCH_TERMS,
            evidence_excerpt=_excerpt(body),
            next_action=(
                "Open the search URL in an operator-owned browser session and "
                "record browser or screenshot evidence; CLI cannot verify this host."
            ),
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
            "Record live-listing evidence."
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
    return (
        [term for term in MATCH_TERMS if term in lowered],
        [term for term in MATCH_TERMS if term not in lowered],
    )


def _has_brand_and_payload_match(matched: list[str]) -> bool:
    matched_set = set(matched)
    return bool(matched_set.intersection(BRAND_TERMS)) and bool(
        matched_set.intersection(PAYLOAD_TERMS)
    )


def _is_fetch_blocked(http_status: int, body: str) -> bool:
    if http_status not in FETCH_BLOCK_HTTP_STATUSES:
        return False
    lowered = body.lower()
    return any(marker in lowered for marker in FETCH_BLOCK_MARKERS)


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
    if any(item.status in {"fetch_failed", "fetch_blocked"} for item in items):
        return "partial_fetch_failure"
    return "no_candidate_found"


def _read_json(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload
