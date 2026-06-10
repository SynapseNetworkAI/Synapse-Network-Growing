#!/usr/bin/env python3
"""Record manual answer-engine AI visibility probe results.

The script intentionally does not call ChatGPT, Claude, Grok, or search APIs.
Operators run the external probe, capture answer evidence, then feed this script
JSON/JSONL rows so Growing can compare runs by feed_key + run_group.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from server.services.growth.ai_visibility_official_sources import (  # noqa: E402
    is_official_citation_url,
)

DEFAULT_API_BASE = "http://localhost:9700/api"

EXTERNAL_PLATFORMS = {
    "chatgpt",
    "claude",
    "grok",
    "perplexity",
    "google_ai",
    "bing_copilot",
    "gemini",
    "grok",
    "public_web_search",
}


@dataclass(frozen=True)
class ProbeRecord:
    query: str
    platform: str
    feed_key: str
    run_group: str
    answer_summary: str = ""
    synapse_mentioned: bool = False
    synapse_cited: bool = False
    cited_urls: list[str] = field(default_factory=list)
    competitor_mentions: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    next_action: str = ""
    result_rank: int = 0
    evidence_url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def api_payload(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "platform": self.platform,
            "answer_summary": self.answer_summary,
            "synapse_mentioned": self.synapse_mentioned,
            "synapse_cited": self.synapse_cited,
            "cited_urls": self.cited_urls,
            "competitor_mentions": self.competitor_mentions,
            "missing_facts": self.missing_facts,
            "next_action": self.next_action,
            "feed_key": self.feed_key,
            "run_group": self.run_group,
            "result_rank": self.result_rank,
            "evidence_url": self.evidence_url,
            "metadata": self.metadata,
        }


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Validate and optionally record AI visibility probe rows."
    )
    parser.add_argument("probe_file", help="JSON array/object or JSONL probe file.")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--apply", action="store_true", help="POST rows to API.")
    parser.add_argument(
        "--db-apply",
        action="store_true",
        help="Insert rows through OPS_DATABASE_URL when the local API is unavailable.",
    )
    parser.add_argument(
        "--allow-local-validation",
        action="store_true",
        help="Allow *_validation rows. External probe mode rejects validation evidence.",
    )
    args = parser.parse_args()

    try:
        records = parse_probe_file(Path(args.probe_file))
        errors = validate_records(
            records,
            allow_local_validation=bool(args.allow_local_validation),
        )
        if args.apply and args.db_apply:
            errors.append("--apply and --db-apply are mutually exclusive")
        if errors:
            emit(
                {
                    "status": "failed",
                    "dry_run": not (args.apply or args.db_apply),
                    "record_count": len(records),
                    "errors": errors,
                },
                stderr=True,
            )
            return 2
        target = "dry_run"
        if args.apply:
            created = post_records(args.api_base, records)
            target = "api"
        elif args.db_apply:
            created = insert_records_with_db(records)
            target = "db"
        else:
            created = []
        emit(
            {
                "status": "succeeded",
                "dry_run": target == "dry_run",
                "target": target,
                "record_count": len(records),
                "created_ids": [item.get("id") for item in created],
                "platforms": sorted({record.platform for record in records}),
                "feed_keys": sorted({record.feed_key for record in records}),
                "run_groups": sorted({record.run_group for record in records}),
            }
        )
        return 0
    except Exception as exc:
        emit(
            {
                "status": "failed",
                "dry_run": not (args.apply or args.db_apply),
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
            stderr=True,
        )
        return 1


def parse_probe_file(path: Path) -> list[ProbeRecord]:
    raw = path.read_text(encoding="utf-8")
    payloads = parse_json_or_jsonl(raw)
    return [
        record_from_payload(payload, index=index)
        for index, payload in enumerate(payloads)
    ]


def parse_json_or_jsonl(raw: str) -> list[dict[str, Any]]:
    stripped = raw.strip()
    if not stripped:
        raise ValueError("probe file is empty")
    if stripped[0] in "[{":
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError as exc:
            if "Extra data" not in str(exc):
                raise
        else:
            if isinstance(loaded, dict):
                return [loaded]
            if isinstance(loaded, list):
                if not all(isinstance(item, dict) for item in loaded):
                    raise ValueError("JSON array must contain objects only")
                return loaded
            raise ValueError("probe JSON must be an object or array")
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        loaded = json.loads(line)
        if not isinstance(loaded, dict):
            raise ValueError(f"JSONL line {line_no} must be an object")
        rows.append(loaded)
    if not rows:
        raise ValueError("probe JSONL did not contain any rows")
    return rows


def record_from_payload(payload: dict[str, Any], *, index: int) -> ProbeRecord:
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"record {index}: metadata must be an object")
    return ProbeRecord(
        query=string_field(payload, "query"),
        platform=string_field(payload, "platform").lower(),
        feed_key=string_field(payload, "feed_key"),
        run_group=string_field(payload, "run_group"),
        answer_summary=string_field(payload, "answer_summary", required=False),
        synapse_mentioned=bool(payload.get("synapse_mentioned", False)),
        synapse_cited=bool(payload.get("synapse_cited", False)),
        cited_urls=string_list_field(payload, "cited_urls"),
        competitor_mentions=string_list_field(payload, "competitor_mentions"),
        missing_facts=string_list_field(payload, "missing_facts"),
        next_action=string_field(payload, "next_action", required=False),
        result_rank=max(int(payload.get("result_rank") or 0), 0),
        evidence_url=string_field(payload, "evidence_url", required=False),
        metadata=metadata,
    )


def validate_records(
    records: list[ProbeRecord], *, allow_local_validation: bool = False
) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, record in enumerate(records):
        prefix = f"record {index}"
        key = (record.feed_key, record.run_group, record.platform, record.query)
        if key in seen:
            errors.append(f"{prefix}: duplicate feed/run/platform/query")
        seen.add(key)
        if not record.query:
            errors.append(f"{prefix}: query is required")
        if not record.feed_key:
            errors.append(f"{prefix}: feed_key is required")
        if not record.run_group:
            errors.append(f"{prefix}: run_group is required")
        if not record.platform:
            errors.append(f"{prefix}: platform is required")
        elif record.platform.endswith("_validation") and not allow_local_validation:
            errors.append(
                f"{prefix}: validation platform is not external probe evidence"
            )
        elif (
            not record.platform.endswith("_validation")
            and record.platform not in EXTERNAL_PLATFORMS
        ):
            errors.append(
                f"{prefix}: platform must be one of {sorted(EXTERNAL_PLATFORMS)}"
            )
        if record.synapse_cited and not (record.cited_urls or record.evidence_url):
            errors.append(
                f"{prefix}: synapse_cited=true requires cited_urls or evidence_url"
            )
        if record.synapse_cited and record.cited_urls and not _has_official_citation(
            record.cited_urls
        ):
            errors.append(
                f"{prefix}: synapse_cited=true requires at least one official Synapse cited_url"
            )
        if record.synapse_cited and not record.synapse_mentioned:
            errors.append(
                f"{prefix}: cited result must also mark synapse_mentioned=true"
            )
    return errors


def _has_official_citation(urls: list[str]) -> bool:
    return any(is_official_citation_url(url) for url in urls)


def post_records(api_base: str, records: list[ProbeRecord]) -> list[Any]:
    created: list[dict[str, Any]] = []
    url = f"{api_base.rstrip('/')}/growth/ai-visibility/checks"
    for record in records:
        request = urllib.request.Request(
            url,
            data=json.dumps(record.api_payload()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                created.append(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"POST {url} failed with {exc.code}: {body}") from exc
    return created


def insert_records_with_db(records: list[ProbeRecord]) -> list[Any]:
    from server.database import SessionLocal, init_db
    from server.schemas_growth import GrowthAIVisibilityCheckCreate
    from server.services.growth.ai_visibility_discovery import create_ai_check

    init_db()
    db = SessionLocal()
    try:
        created = [
            create_ai_check(
                db,
                GrowthAIVisibilityCheckCreate(**record.api_payload()),
            ).model_dump(mode="json")
            for record in records
        ]
        return created
    finally:
        db.close()


def string_field(
    payload: dict[str, Any], field_name: str, *, required: bool = True
) -> str:
    value = payload.get(field_name, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if required and not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def string_list_field(payload: dict[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name) or []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def emit(payload: dict[str, Any], *, stderr: bool = False) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
