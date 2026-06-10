#!/usr/bin/env python3
"""Generate manual answer-engine probe templates for AI visibility checks.

The template is intentionally blank evidence: operators run ChatGPT, Claude,
Grok, Gemini, or another answer engine, then fill the generated rows before applying
them with scripts/growth/record_ai_visibility_probe.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import (  # noqa: E402
    emit_failure,
    write_text_or_stdout,
)
from scripts.growth.record_ai_visibility_probe import EXTERNAL_PLATFORMS  # noqa: E402
from server.services.growth.ai_visibility_official_sources import (  # noqa: E402
    ai_visibility_official_sources,
)
from server.services.growth.ai_visibility_plan import (  # noqa: E402
    ai_visibility_optimization_plan,
)

CANONICAL_HOMEPAGE = "https://www.synapse-network.ai/"
KNOWN_COLLISION_DOMAINS = [
    "python-docs.synapse.org",
    "mcp.synapse.org",
    "synapse.org",
    "synapseproto.com",
    "synapsenetwork.xyz",
    "synapse.network",
    "forbes.com/digital-assets/assets/synapse-network-zksnp",
]
DEFAULT_FEED_KEY = "agent_payment_category_pages"
DEFAULT_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]
DEFAULT_MODE = "manual_template"
PLATFORM_ENTRY_URLS = {
    "chatgpt": "https://chatgpt.com/",
    "claude": "https://claude.ai/",
    "grok": "https://grok.com/",
    "perplexity": "https://www.perplexity.ai/",
    "google_ai": "https://www.google.com/search",
    "bing_copilot": "https://www.bing.com/chat",
    "gemini": "https://gemini.google.com/",
}


@dataclass(frozen=True)
class ProbeTemplateRecord:
    query: str
    platform: str
    feed_key: str
    run_group: str
    answer_summary: str
    synapse_mentioned: bool
    synapse_cited: bool
    cited_urls: list[str]
    competitor_mentions: list[str]
    missing_facts: list[str]
    next_action: str
    result_rank: int
    evidence_url: str
    metadata: dict[str, object]


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Generate JSONL rows for manual ChatGPT/Claude/Grok/Gemini AI visibility probes."
    )
    parser.add_argument("--feed-key", default=DEFAULT_FEED_KEY)
    parser.add_argument(
        "--run-group",
        default=f"{date.today().isoformat()}-baseline",
        help="Experiment run group, for example 2026-06-18-after-docs-launch.",
    )
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="Comma-separated platforms. Defaults to chatgpt,claude,grok,gemini.",
    )
    parser.add_argument(
        "--query",
        action="append",
        dest="queries",
        help="Custom query. Repeat for multiple queries. Defaults to the plan baseline queries.",
    )
    parser.add_argument(
        "--mode",
        choices=["baseline", "after-feed"],
        default="baseline",
        help="Labels the template and default next action.",
    )
    parser.add_argument("--output", help="Write JSONL to this path instead of stdout.")
    args = parser.parse_args()

    try:
        platforms = parse_platforms(args.platforms)
        queries = args.queries or default_queries_for_feed(args.feed_key)
        rows = generate_records(
            feed_key=args.feed_key,
            run_group=args.run_group,
            platforms=platforms,
            queries=queries,
            mode=args.mode,
        )
        payload = "\n".join(json.dumps(asdict(row), ensure_ascii=False) for row in rows)
        write_text_or_stdout(payload, output=args.output)
        return 0
    except Exception as exc:
        emit_failure(exc)
        return 1


def parse_platforms(value: str) -> list[str]:
    platforms = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not platforms:
        raise ValueError("at least one platform is required")
    unknown = [platform for platform in platforms if platform not in EXTERNAL_PLATFORMS]
    if unknown:
        raise ValueError(
            f"unknown platform(s): {', '.join(unknown)}; expected one of {sorted(EXTERNAL_PLATFORMS)}"
        )
    return platforms


def baseline_queries() -> list[str]:
    return [item.query for item in ai_visibility_optimization_plan().baseline_queries]


def default_queries_for_feed(feed_key: str) -> list[str]:
    safe_feed_key = (feed_key or "").strip()
    plan = ai_visibility_optimization_plan()
    for experiment in plan.feed_experiments:
        if experiment.feed_key == safe_feed_key:
            return list(experiment.target_queries)
    return baseline_queries()


def official_source_urls_for_feed(feed_key: str) -> list[str]:
    safe_feed_key = (feed_key or "").strip()
    sources = ai_visibility_official_sources().items
    matched = [
        source.canonical_url
        for source in sources
        if safe_feed_key in source.feed_keys
    ]
    if matched:
        return sorted(set(matched))
    return sorted({source.canonical_url for source in sources})


def generate_records(
    *,
    feed_key: str,
    run_group: str,
    platforms: Iterable[str],
    queries: Iterable[str],
    mode: str,
) -> list[ProbeTemplateRecord]:
    normalized_queries = [query.strip() for query in queries if query.strip()]
    normalized_platforms = [
        platform.strip().lower() for platform in platforms if platform.strip()
    ]
    _validate_generate_inputs(
        feed_key=feed_key,
        run_group=run_group,
        queries=normalized_queries,
        platforms=normalized_platforms,
    )
    official_source_urls = official_source_urls_for_feed(feed_key)
    return _template_records(
        feed_key=feed_key.strip(),
        run_group=run_group.strip(),
        platforms=normalized_platforms,
        queries=normalized_queries,
        mode=mode,
        official_source_urls=official_source_urls,
    )


def _validate_generate_inputs(
    *,
    feed_key: str,
    run_group: str,
    queries: list[str],
    platforms: list[str],
) -> None:
    if not feed_key.strip():
        raise ValueError("feed_key is required")
    if not run_group.strip():
        raise ValueError("run_group is required")
    if not queries:
        raise ValueError("at least one query is required")
    if not platforms:
        raise ValueError("at least one platform is required")


def _template_records(
    *,
    feed_key: str,
    run_group: str,
    platforms: list[str],
    queries: list[str],
    mode: str,
    official_source_urls: list[str],
) -> list[ProbeTemplateRecord]:
    generated_at = date.today().isoformat()
    return [
        template_record(
            query=query,
            platform=platform,
            feed_key=feed_key,
            run_group=run_group,
            mode=mode,
            generated_at=generated_at,
            official_source_urls=official_source_urls,
        )
        for query in queries
        for platform in platforms
    ]


def template_record(
    *,
    query: str,
    platform: str,
    feed_key: str,
    run_group: str,
    mode: str,
    generated_at: str,
    official_source_urls: list[str],
) -> ProbeTemplateRecord:
    return ProbeTemplateRecord(
        query=query,
        platform=platform,
        feed_key=feed_key,
        run_group=run_group,
        answer_summary="",
        synapse_mentioned=False,
        synapse_cited=False,
        cited_urls=[],
        competitor_mentions=[],
        missing_facts=[],
        next_action=next_action_for_mode(mode),
        result_rank=0,
        evidence_url=(
            "docs/archive/evidence/growth/ai-visibility/"
            f"{slugify(run_group)}/{platform}-{slugify(query)}.png"
        ),
        metadata={
            "mode": DEFAULT_MODE,
            "probe_mode": mode,
            "answer_engine": platform,
            "feed_key": feed_key,
            "canonical_homepage": CANONICAL_HOMEPAGE,
            "generated_at": generated_at,
            "platform_entry_url": PLATFORM_ENTRY_URLS.get(platform, ""),
            "question_to_ask": query,
            "official_source_urls": official_source_urls,
            "known_collision_domains": KNOWN_COLLISION_DOMAINS,
            "success_decision_rule": (
                "Success requires the answer to mention Synapse Network and cite "
                "at least one official_source_urls host. Known collision domains "
                "must be recorded in competitor_mentions, not counted as Synapse "
                "success."
            ),
            "evidence_capture": (
                "Capture a screenshot of the full answer, cited/source URLs, "
                "competitor names, known collision domains, and whether an "
                "official_source_urls surface appears. Do not edit the question "
                "between platforms."
            ),
        },
    )


def next_action_for_mode(mode: str) -> str:
    if mode == "after-feed":
        return (
            "Capture answer, cited URLs, competitors, missing facts, and compare against "
            "the previous run group before deciding whether the feed improved visibility."
        )
    return (
        "Capture baseline answer, cited URLs, competitors, and missing facts before "
        "publishing the next Synapse feed asset."
    )


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "probe"


if __name__ == "__main__":
    raise SystemExit(main())
