#!/usr/bin/env python3
"""Validate a live source-host page and emit AI visibility feed evidence."""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import emit_failure, write_json_payload  # noqa: E402
from server.services.growth.ai_visibility_source_host_execution_models import (  # noqa: E402
    SourceHostExecutionEvidence,
)
from server.services.growth.ai_visibility_text import unique_strings  # noqa: E402

DEFAULT_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]
SOURCE_HOST_USER_AGENT = (
    "SynapseNetwork-Growing-AIVisibility/1.0 "
    "(source-host evidence checker; https://www.synapse-network.ai/)"
)


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Record live source-host evidence for an AI visibility feed."
    )
    parser.add_argument("--feed-key", required=True)
    parser.add_argument("--run-group", required=True)
    parser.add_argument("--surface", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument(
        "--required-term",
        action="append",
        default=[],
        help="Required term that must appear in the source content. Repeatable.",
    )
    parser.add_argument(
        "--target-platform",
        action="append",
        default=[],
        help="Target answer engine for this source-host execution. Repeatable.",
    )
    parser.add_argument(
        "--target-query",
        action="append",
        default=[],
        help="Probe query this source-host execution is meant to influence.",
    )
    parser.add_argument("--output", help="Write JSON evidence to this path.")
    args = parser.parse_args()

    try:
        content = fetch_text(args.source_url)
        evidence = build_source_host_evidence(
            feed_key=args.feed_key,
            run_group=args.run_group,
            surface=args.surface,
            source_url=args.source_url,
            content=content,
            required_terms=args.required_term,
            target_platforms=args.target_platform or DEFAULT_PLATFORMS,
            target_queries=args.target_query,
        )
        write_json_payload(evidence.model_dump(), args.output)
        return 0 if evidence.status == "live_verified" else 2
    except Exception as exc:
        emit_failure(exc)
        return 1


def build_source_host_evidence(
    *,
    feed_key: str,
    run_group: str,
    surface: str,
    source_url: str,
    content: str,
    required_terms: list[str],
    target_platforms: list[str],
    target_queries: list[str],
) -> SourceHostExecutionEvidence:
    required = unique_strings(required_terms)
    matched, missing = match_terms(content, required)
    status = "live_verified" if not missing else "missing_required_terms"
    return SourceHostExecutionEvidence(
        status=status,
        feed_key=feed_key,
        run_group=run_group,
        surface=surface,
        source_url=source_url,
        checked_at=datetime.now(UTC).isoformat(),
        required_terms=required,
        matched_terms=matched,
        missing_terms=missing,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        content_bytes=len(content.encode("utf-8")),
        target_platforms=unique_strings(target_platforms),
        target_queries=unique_strings(target_queries),
        validation_summary=validation_summary(status, surface, matched, missing),
        next_probe_command=next_probe_command(feed_key, run_group, target_platforms),
    )


def match_terms(content: str, required_terms: list[str]) -> tuple[list[str], list[str]]:
    haystack = content.casefold()
    matched = [term for term in required_terms if term.casefold() in haystack]
    missing = [term for term in required_terms if term not in matched]
    return matched, missing


def validation_summary(
    status: str, surface: str, matched: list[str], missing: list[str]
) -> str:
    if status == "live_verified":
        return (
            f"{surface} source host is live and matched {len(matched)} required terms."
        )
    return f"{surface} source host is missing required terms: {', '.join(missing)}."


def next_probe_command(feed_key: str, run_group: str, platforms: list[str]) -> str:
    platform_arg = ",".join(unique_strings(platforms) or DEFAULT_PLATFORMS)
    return (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} --run-group {run_group}-after-source-host "
        f"--platforms {platform_arg} --execute"
    )


def fetch_text(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(parsed.path).read_text(encoding="utf-8")
    if parsed.scheme != "https":
        raise ValueError("source_url must use https or file")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": SOURCE_HOST_USER_AGENT,
            "Accept": "text/html,application/json,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:  # nosec B310
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
