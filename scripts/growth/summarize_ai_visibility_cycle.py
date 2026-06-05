#!/usr/bin/env python3
"""Summarize one AI visibility optimization cycle from probe JSONL evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.growth.record_ai_visibility_probe import (  # noqa: E402
    ProbeRecord,
    parse_probe_file,
    validate_records,
)
from server.services.growth.ai_visibility_plan import (  # noqa: E402
    ai_visibility_feed_packages,
)
from server.services.growth.ai_visibility_text import unique_strings  # noqa: E402

TARGET_PLATFORMS = ["chatgpt", "claude", "grok"]


def main() -> int:  # pragma: no cover - subprocess CLI wrapper
    parser = argparse.ArgumentParser(
        description="Export an operator summary for one AI visibility cycle."
    )
    parser.add_argument("probe_file", help="JSON/JSONL feed validation or probe file.")
    parser.add_argument(
        "--previous",
        help="Optional previous JSON/JSONL probe file for delta comparison.",
    )
    parser.add_argument("--output", help="Write JSON summary to this path.")
    args = parser.parse_args()

    try:
        records = parse_probe_file(Path(args.probe_file))
        errors = validate_records(records, allow_local_validation=True)
        if errors:
            emit({"status": "failed", "errors": errors}, stderr=True)
            return 2
        previous_records = (
            parse_probe_file(Path(args.previous)) if args.previous else None
        )
        if previous_records is not None:
            previous_errors = validate_records(
                previous_records,
                allow_local_validation=True,
            )
            if previous_errors:
                emit(
                    {"status": "failed", "previous_errors": previous_errors},
                    stderr=True,
                )
                return 2
        summary = summarize_cycle(
            records,
            source_path=args.probe_file,
            previous_records=previous_records,
            previous_source_path=args.previous or "",
        )
        rendered = json.dumps(summary, indent=2, ensure_ascii=False)
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0
    except Exception as exc:
        emit(
            {
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            },
            stderr=True,
        )
        return 1


def summarize_cycle(
    records: list[ProbeRecord],
    *,
    source_path: str,
    previous_records: list[ProbeRecord] | None = None,
    previous_source_path: str = "",
) -> Any:
    scope = cycle_scope(records)
    validation_records, external_records, failed_validation = partition_records(records)
    covered_platforms, missing_platforms = platform_coverage(external_records)
    blockers = cycle_blockers(
        failed_validation=failed_validation,
        external_records=external_records,
        missing_platforms=missing_platforms,
    )
    status = cycle_status(
        failed_validation=failed_validation,
        external_records=external_records,
        missing_platforms=missing_platforms,
    )
    strategy_platforms = missing_platforms if missing_platforms else TARGET_PLATFORMS
    platform_strategies = platform_strategies_for(
        feed_key=scope["feed_key"],
        platforms=strategy_platforms,
    )
    feed_improvements = feed_improvements_for(records)
    next_actions = cycle_next_actions(
        records=records,
        status=status,
        feed_key=scope["feed_key"],
        run_group=scope["run_group"],
        missing_platforms=missing_platforms,
        feed_improvements=feed_improvements,
    )
    previous_external_records = [
        record for record in (previous_records or []) if not is_local_validation(record)
    ]
    comparison = comparison_summary(
        current_external_records=external_records,
        previous_external_records=previous_external_records,
        previous_source_path=previous_source_path,
    )
    return {
        "module_key": "ai_visibility",
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_path": source_path,
        "feed_key": scope["feed_key"],
        "run_group": scope["run_group"],
        "feed_keys": scope["feed_keys"],
        "run_groups": scope["run_groups"],
        "record_count": len(records),
        "local_validation_count": len(validation_records),
        "external_probe_count": len(external_records),
        "external_mentioned_count": sum(
            1 for record in external_records if record.synapse_mentioned
        ),
        "external_cited_count": sum(
            1 for record in external_records if record.synapse_cited
        ),
        "target_platforms": TARGET_PLATFORMS,
        "covered_platforms": covered_platforms,
        "missing_platforms": missing_platforms,
        "blockers": blockers,
        "feed_improvements": feed_improvements,
        "next_actions": next_actions[:8],
        "platform_strategies": platform_strategies,
        "comparison": comparison,
        "commands": commands_for(
            feed_key=scope["feed_key"],
            run_group=scope["run_group"],
        ),
    }


def cycle_scope(records: list[ProbeRecord]) -> Any:
    feed_keys = sorted({record.feed_key for record in records if record.feed_key})
    run_groups = sorted({record.run_group for record in records if record.run_group})
    return {
        "feed_keys": feed_keys,
        "run_groups": run_groups,
        "feed_key": feed_keys[0] if len(feed_keys) == 1 else "mixed",
        "run_group": run_groups[0] if len(run_groups) == 1 else "mixed",
    }


def partition_records(
    records: list[ProbeRecord],
) -> tuple[list[ProbeRecord], list[ProbeRecord], list[ProbeRecord]]:
    validation_records = [record for record in records if is_local_validation(record)]
    external_records = [record for record in records if not is_local_validation(record)]
    failed_validation = [
        record
        for record in validation_records
        if not record.synapse_mentioned or record.missing_facts
    ]
    return validation_records, external_records, failed_validation


def platform_coverage(
    external_records: list[ProbeRecord],
) -> tuple[list[str], list[str]]:
    covered_platforms = sorted(
        {
            record.platform
            for record in external_records
            if record.platform in TARGET_PLATFORMS
        }
    )
    missing_platforms = [
        platform for platform in TARGET_PLATFORMS if platform not in covered_platforms
    ]
    return covered_platforms, missing_platforms


def cycle_blockers(
    *,
    failed_validation: list[ProbeRecord],
    external_records: list[ProbeRecord],
    missing_platforms: list[str],
) -> list[str]:
    blockers = unique_strings(
        [fact for record in failed_validation for fact in record.missing_facts]
    )
    if not external_records:
        blockers.append("No external GPT/Claude/Grok probe evidence has been recorded.")
    if external_records and missing_platforms:
        blockers.append(
            f"Missing external platform probes: {', '.join(missing_platforms)}."
        )
    return blockers


def cycle_next_actions(
    *,
    records: list[ProbeRecord],
    status: str,
    feed_key: str,
    run_group: str,
    missing_platforms: list[str],
    feed_improvements: list[str],
) -> list[str]:
    return unique_strings(
        [record.next_action for record in records if record.next_action]
        + recommended_actions(status, feed_key, run_group, missing_platforms)
        + feed_improvements
    )


def cycle_status(
    *,
    failed_validation: list[ProbeRecord],
    external_records: list[ProbeRecord],
    missing_platforms: list[str],
) -> str:
    if failed_validation:
        return "feed_blocked"
    if not external_records:
        return "ready_for_external_probe"
    if missing_platforms:
        return "partial_external_probe"
    if any(record.synapse_cited for record in external_records):
        return "citation_observed"
    if any(record.synapse_mentioned for record in external_records):
        return "mention_observed"
    return "not_visible_yet"


def recommended_actions(
    status: str,
    feed_key: str,
    run_group: str,
    missing_platforms: list[str],
) -> list[str]:
    if status == "feed_blocked":
        return ["Fix live feed blockers before running external answer-engine probes."]
    if status == "ready_for_external_probe":
        return [
            "Run the generated ChatGPT, Claude, and Grok probe template with unchanged questions."
        ]
    if status == "partial_external_probe":
        return [f"Complete missing external probes for {', '.join(missing_platforms)}."]
    if status in {"citation_observed", "mention_observed"}:
        return [
            "Compare this run against the previous run group and schedule the next weekly stability probe."
        ]
    return [
        f"Publish another feed asset for {feed_key} and rerun probes for {run_group}."
    ]


def commands_for(*, feed_key: str, run_group: str) -> Any:
    safe_feed_key = feed_key if feed_key != "mixed" else "agent_payment_category_pages"
    safe_run_group = run_group if run_group != "mixed" else "YYYY-MM-DD-weekly"
    output_base = f"docs/archive/evidence/growth/ai-visibility/{safe_run_group}"
    return {
        "feed_validation": (
            "python scripts/growth/run_ai_visibility_feed_validation.py "
            f"--feed-key {safe_feed_key} "
            f"--run-group {safe_run_group} "
            f"--output {output_base}-feed-validation.jsonl"
        ),
        "manual_probe_template": (
            "python scripts/growth/generate_ai_visibility_probe_template.py "
            f"--feed-key {safe_feed_key} "
            f"--run-group {safe_run_group} "
            "--mode after-feed "
            f"--output {output_base}.jsonl"
        ),
        "api_readiness": (
            "python scripts/growth/run_ai_visibility_api_probe.py "
            f"--feed-key {safe_feed_key} "
            f"--run-group {safe_run_group} "
            "--platforms chatgpt,claude,grok"
        ),
        "record_evidence": (
            f"python scripts/growth/record_ai_visibility_probe.py {output_base}.jsonl --apply"
        ),
        "compare": (
            'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons'
            f'?feed_key={safe_feed_key}&run_group={safe_run_group}" | python -m json.tool'
        ),
    }


def feed_improvements_for(records: list[ProbeRecord]) -> list[str]:
    improvements: list[str] = []
    for record in records:
        policy = record.metadata.get("ai_crawler_policy")
        if not isinstance(policy, dict):
            continue
        missing = [
            str(item)
            for item in policy.get("missing_explicit_crawlers", [])
            if str(item).strip()
        ]
        blocked = [
            str(item)
            for item in policy.get("blocked_crawlers", [])
            if str(item).strip()
        ]
        if blocked:
            improvements.append(
                "Fix robots.txt crawler blocks for answer-engine search bots: "
                + ", ".join(blocked)
                + "."
            )
        elif missing and bool(policy.get("wildcard_allows_public")):
            improvements.append(
                "Make robots.txt crawler policy explicit for answer engines: "
                + ", ".join(missing)
                + "."
            )
    return unique_strings(improvements)


def comparison_summary(
    *,
    current_external_records: list[ProbeRecord],
    previous_external_records: list[ProbeRecord],
    previous_source_path: str,
) -> Any:
    current_mentions = sum(
        1 for record in current_external_records if record.synapse_mentioned
    )
    current_citations = sum(
        1 for record in current_external_records if record.synapse_cited
    )
    previous_mentions = sum(
        1 for record in previous_external_records if record.synapse_mentioned
    )
    previous_citations = sum(
        1 for record in previous_external_records if record.synapse_cited
    )
    mentioned_delta = current_mentions - previous_mentions
    cited_delta = current_citations - previous_citations
    return {
        "previous_source_path": previous_source_path,
        "previous_external_probe_count": len(previous_external_records),
        "previous_mentioned_count": previous_mentions,
        "previous_cited_count": previous_citations,
        "mentioned_delta": mentioned_delta,
        "cited_delta": cited_delta,
        "comparison_status": comparison_status(
            previous_external_records=previous_external_records,
            current_external_records=current_external_records,
            mentioned_delta=mentioned_delta,
            cited_delta=cited_delta,
        ),
    }


def comparison_status(
    *,
    previous_external_records: list[ProbeRecord],
    current_external_records: list[ProbeRecord],
    mentioned_delta: int,
    cited_delta: int,
) -> str:
    if not current_external_records:
        return "needs_external_probe"
    if not previous_external_records:
        return "baseline"
    if mentioned_delta > 0 or cited_delta > 0:
        return "improved"
    if mentioned_delta < 0 or cited_delta < 0:
        return "regressed"
    return "flat"


def platform_strategies_for(*, feed_key: str, platforms: list[str]) -> list[Any]:
    if feed_key == "mixed":
        return []
    packages = ai_visibility_feed_packages(feed_key=feed_key)
    items = packages.items if hasattr(packages, "items") else []
    if not items:
        return []
    wanted = set(platforms)
    strategies = []
    for strategy in items[0].platform_strategies:
        if strategy.platform not in wanted:
            continue
        if hasattr(strategy, "model_dump"):
            strategies.append(strategy.model_dump(mode="json"))
        else:
            strategies.append(strategy.dict())
    return strategies


def is_local_validation(record: ProbeRecord) -> bool:
    return record.platform.endswith("_validation")


def emit(payload: dict[str, Any], *, stderr: bool = False) -> None:
    print(
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        file=sys.stderr if stderr else sys.stdout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
