#!/usr/bin/env python3
"""Convert public web-search snapshots into AI visibility probe rows.

The script does not call a search engine. It converts an operator-captured
snapshot into the same JSONL contract used by record_ai_visibility_probe.py so
Growing can compare web-search result drift alongside GPT/Claude/Grok/Gemini probes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.ai_visibility_cli import emit_failure  # noqa: E402
from scripts.growth.record_ai_visibility_probe import ProbeRecord  # noqa: E402
from server.services.growth.ai_visibility_official_sources import (  # noqa: E402
    is_official_citation_url,
)
from server.services.growth.ai_visibility_text import unique_strings  # noqa: E402

DEFAULT_PLATFORM = "public_web_search"


def main() -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(
        description="Convert public web search snapshots to probe JSONL rows."
    )
    parser.add_argument("snapshot_file", help="Public web search snapshot JSON file.")
    parser.add_argument("--output", help="Write JSONL probe rows to this path.")
    args = parser.parse_args()

    try:
        snapshot_path = Path(args.snapshot_file)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        records = records_from_snapshot(snapshot, source_path=str(snapshot_path))
        rendered = "\n".join(
            json.dumps(record.api_payload(), ensure_ascii=False) for record in records
        )
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0
    except Exception as exc:
        emit_failure(exc)
        return 1


def records_from_snapshot(
    snapshot: dict[str, Any], *, source_path: str
) -> list[ProbeRecord]:
    feed_key = str(snapshot.get("feed_key") or "").strip()
    run_group = str(snapshot.get("run_group") or "").strip()
    if not feed_key:
        raise ValueError("snapshot feed_key is required")
    if not run_group:
        raise ValueError("snapshot run_group is required")

    queries = snapshot.get("queries") or []
    if not isinstance(queries, list) or not queries:
        raise ValueError("snapshot queries must be a non-empty array")

    records = []
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            raise ValueError(f"queries[{index}] must be an object")
        records.append(
            _record_from_query(
                item,
                snapshot=snapshot,
                source_path=source_path,
            )
        )
    return records


def _record_from_query(
    item: dict[str, Any], *, snapshot: dict[str, Any], source_path: str
) -> ProbeRecord:
    query = str(item.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    result_items = _result_items(item)
    official_rank = _first_official_rank(result_items)
    synapse_found = _synapse_found(item, official_rank=official_rank)
    return ProbeRecord(
        query=query,
        platform=DEFAULT_PLATFORM,
        feed_key=str(snapshot.get("feed_key") or "").strip(),
        run_group=str(snapshot.get("run_group") or "").strip(),
        answer_summary=_answer_summary(query, synapse_found=synapse_found),
        synapse_mentioned=synapse_found,
        synapse_cited=False,
        cited_urls=[],
        competitor_mentions=unique_strings(_competitor_names(result_items)),
        missing_facts=_missing_facts(query, synapse_found=synapse_found),
        next_action=_next_action(snapshot, synapse_found=synapse_found),
        result_rank=official_rank,
        evidence_url=source_path,
        metadata=_metadata(
            snapshot, result_items=result_items, source_path=source_path
        ),
    )


def _result_items(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw = item.get("observed_competitors_or_adjacent_results") or []
    if not isinstance(raw, list):
        raise ValueError("observed_competitors_or_adjacent_results must be an array")
    return [result for result in raw if isinstance(result, dict)]


def _first_official_rank(results: list[dict[str, Any]]) -> int:
    for index, result in enumerate(results, start=1):
        if is_official_citation_url(str(result.get("url") or "")):
            return index
    return 0


def _synapse_found(item: dict[str, Any], *, official_rank: int) -> bool:
    return bool(item.get("synapse_found_in_returned_results")) or official_rank > 0


def _competitor_names(results: list[dict[str, Any]]) -> list[str]:
    names = []
    for result in results:
        if is_official_citation_url(str(result.get("url") or "")):
            continue
        names.append(str(result.get("name") or result.get("url") or "").strip())
    return names


def _result_urls(results: list[dict[str, Any]]) -> list[str]:
    return [
        str(result.get("url") or "").strip()
        for result in results
        if str(result.get("url") or "").strip()
    ]


def _metadata(
    snapshot: dict[str, Any], *, result_items: list[dict[str, Any]], source_path: str
) -> dict[str, Any]:
    return {
        "mode": "public_web_search_snapshot",
        "snapshot_type": str(snapshot.get("snapshot_type") or ""),
        "observed_at": str(snapshot.get("observed_at") or ""),
        "official_homepage": str(snapshot.get("official_homepage") or ""),
        "source_path": source_path,
        "result_urls": _result_urls(result_items)[:10],
        "result_count": len(result_items),
        "diagnostic_only": True,
    }


def _answer_summary(query: str, *, synapse_found: bool) -> str:
    if synapse_found:
        return f"Public web search returned an official Synapse result for: {query}"
    return f"Public web search did not return an official Synapse result for: {query}"


def _missing_facts(query: str, *, synapse_found: bool) -> list[str]:
    if synapse_found:
        return []
    return [f"Public web search returned no official Synapse result for query: {query}"]


def _next_action(snapshot: dict[str, Any], *, synapse_found: bool) -> str:
    if synapse_found:
        return (
            "Compare web-search rank drift against the previous public search snapshot."
        )
    actions = [str(item).strip() for item in snapshot.get("next_actions") or []]
    for action in actions:
        if action:
            return action
    return "Refresh indexing feeds and rerun public web search plus GPT/Claude/Grok/Gemini probes."


if __name__ == "__main__":
    raise SystemExit(main())
