"""Record builders for AI visibility API probe evidence."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from scripts.growth.generate_ai_visibility_probe_template import (
    official_source_urls_for_feed,
    template_record,
)
from scripts.growth.record_ai_visibility_probe import record_from_payload


def api_readiness_blocker_records(
    *,
    feed_key: str,
    run_group: str,
    missing: list[dict[str, str]],
    query_count: int,
) -> list[Any]:
    official_source_urls = official_source_urls_for_feed(feed_key)
    rows = []
    generated_at = datetime.now(UTC).date().isoformat()
    query = "ChatGPT Claude Grok Gemini API probe readiness"
    for item in missing:
        platform = item["platform"]
        env_key = item["missing_env"]
        template = template_record(
            query=query,
            platform=platform,
            feed_key=feed_key,
            run_group=run_group,
            mode="after-feed",
            generated_at=generated_at,
            official_source_urls=official_source_urls,
        )
        payload = asdict(template)
        payload.update(
            {
                "answer_summary": (
                    f"{platform} API probe is blocked because {env_key} is not "
                    "present in the current execution environment. No paid probe "
                    "was executed."
                ),
                "synapse_mentioned": False,
                "synapse_cited": False,
                "cited_urls": [],
                "competitor_mentions": [],
                "missing_facts": [
                    f"{env_key} is required to execute {platform} answer-engine probe."
                ],
                "next_action": (
                    f"Set {env_key} after production feed validation passes, then "
                    "rerun run_ai_visibility_api_probe.py with --execute."
                ),
                "result_rank": 0,
                "evidence_url": "",
                "metadata": {
                    **payload["metadata"],
                    "mode": "api_probe_readiness_blocker",
                    "execute": False,
                    "missing_env": env_key,
                    "blocked_query_count": str(query_count),
                },
            }
        )
        rows.append(record_from_payload(payload, index=len(rows)))
    return rows
