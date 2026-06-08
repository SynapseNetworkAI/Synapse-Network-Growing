from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json

from sqlalchemy.orm import Session

from server.database_growth import GrowthAIVisibilityCheckRow
from server.schemas_growth import (
    GrowthAIVisibilityComparisonOut,
    GrowthAIVisibilityFeedReportOut,
)
from server.services.growth.ai_visibility_comparison_status import (
    comparison_status_from_counts,
)
from server.services.growth.ai_visibility_official_sources import (
    is_official_citation_url,
)
from server.services.growth.ai_visibility_probe_failures import (
    has_provider_failure_missing_fact,
    is_external_api_key_setup_blocker,
)
from server.services.growth.ai_visibility_text import unique_strings

AI_VISIBILITY_REQUIRED_STABLE_RUNS = 3
AI_VISIBILITY_TARGET_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]
KNOWN_BRAND_COLLISION_COMPETITORS = {
    "synapseproto.com",
    "synapsenetwork.xyz",
    "synapse.network",
    "forbes.com/digital-assets/assets/synapse-network-zksnp",
}


def _comparison_out(
    key: tuple[str, str],
    rows: list[GrowthAIVisibilityCheckRow],
    *,
    previous: GrowthAIVisibilityComparisonOut | None = None,
) -> GrowthAIVisibilityComparisonOut:
    platforms = sorted({row.platform for row in rows if row.platform})
    external_rows = [
        row for row in rows if _is_external_visibility_platform(row.platform)
    ]
    provider_failure_rows = [
        row for row in external_rows if _is_provider_failure_row(row)
    ]
    completed_external_rows = [
        row for row in external_rows if not _is_provider_failure_row(row)
    ]
    external_platforms = sorted({row.platform for row in external_rows if row.platform})
    aggregate = _comparison_row_aggregate(rows)
    counts = _comparison_counts(completed_external_rows, previous)
    official_cited_urls = _official_cited_urls(completed_external_rows)
    known_collision_competitors = _known_collision_mentions(
        aggregate["top_competitors"]
    )
    comparison_status = comparison_status_from_counts(
        external_checks_count=len(external_rows),
        completed_external_count=len(completed_external_rows),
        previous_exists=previous is not None,
        mentioned_delta=counts["mentioned_delta"],
        cited_delta=counts["cited_delta"],
        provider_failure_count=len(provider_failure_rows),
    )
    citation_quality_status = _citation_quality_status(
        external_checks_count=len(completed_external_rows),
        official_cited_urls=official_cited_urls,
        known_collision_competitors=known_collision_competitors,
    )
    return GrowthAIVisibilityComparisonOut(
        feed_key=key[0],
        run_group=key[1],
        previous_run_group=_previous_run_group(previous),
        platforms=platforms,
        external_platforms=external_platforms,
        total_checks=len(rows),
        external_checks_count=len(external_rows),
        local_validation_count=len(rows) - len(external_rows),
        mentioned_count=counts["mentioned_count"],
        cited_count=counts["cited_count"],
        previous_mentioned_count=counts["previous_mentioned_count"],
        previous_cited_count=counts["previous_cited_count"],
        mentioned_delta=counts["mentioned_delta"],
        cited_delta=counts["cited_delta"],
        comparison_status=comparison_status,
        citation_quality_status=citation_quality_status,
        feed_effective=(
            comparison_status == "improved"
            and citation_quality_status == "official_citation_verified"
        ),
        missing_platforms=_missing_platforms(external_platforms),
        top_competitors=aggregate["top_competitors"],
        source_hosts=aggregate["source_hosts"],
        known_collision_competitors=known_collision_competitors,
        official_cited_urls=official_cited_urls,
        next_actions=aggregate["next_actions"],
        evidence_urls=aggregate["evidence_urls"],
        latest_run_at=aggregate["latest_run_at"],
    )


def _comparison_counts(
    external_rows: list[GrowthAIVisibilityCheckRow],
    previous: GrowthAIVisibilityComparisonOut | None,
) -> dict:
    mentioned_count = sum(1 for row in external_rows if row.synapse_mentioned)
    cited_count = sum(1 for row in external_rows if row.synapse_cited)
    previous_mentioned_count = previous.mentioned_count if previous else 0
    previous_cited_count = previous.cited_count if previous else 0
    return {
        "mentioned_count": mentioned_count,
        "cited_count": cited_count,
        "previous_mentioned_count": previous_mentioned_count,
        "previous_cited_count": previous_cited_count,
        "mentioned_delta": mentioned_count - previous_mentioned_count,
        "cited_delta": cited_count - previous_cited_count,
    }


def _previous_run_group(previous: GrowthAIVisibilityComparisonOut | None) -> str:
    return previous.run_group if previous else ""


def _missing_platforms(external_platforms: list[str]) -> list[str]:
    return [
        platform
        for platform in AI_VISIBILITY_TARGET_PLATFORMS
        if platform not in external_platforms
    ]


def _comparison_row_aggregate(rows: list[GrowthAIVisibilityCheckRow]) -> dict:
    competitors: Counter[str] = Counter()
    source_hosts: Counter[str] = Counter()
    next_actions: list[str] = []
    evidence_urls: list[str] = []
    latest_run_at = None
    for row in rows:
        competitors.update(_json_list(row.competitor_mentions_json))
        source_hosts.update(_metadata_source_hosts(row.metadata_json))
        latest_run_at = _latest_run_at(latest_run_at, row.run_at)
        if not is_external_api_key_setup_blocker(row.next_action):
            _append_unique(next_actions, row.next_action)
        _append_unique(evidence_urls, row.evidence_url)
    _append_source_host_next_action(next_actions, source_hosts)
    return {
        "top_competitors": [item for item, _count in competitors.most_common(5)],
        "source_hosts": [item for item, _count in source_hosts.most_common(8)],
        "next_actions": next_actions[:5],
        "evidence_urls": evidence_urls[:5],
        "latest_run_at": latest_run_at,
    }


def _latest_run_at(current, candidate):
    if current is None or candidate > current:
        return candidate
    return current


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _previous_comparison_by_key(
    grouped: dict[tuple[str, str], list[GrowthAIVisibilityCheckRow]],
) -> dict[tuple[str, str], GrowthAIVisibilityComparisonOut]:
    by_feed: dict[
        str, list[tuple[tuple[str, str], list[GrowthAIVisibilityCheckRow]]]
    ] = {}
    for key, rows in grouped.items():
        by_feed.setdefault(key[0], []).append((key, rows))

    previous: dict[tuple[str, str], GrowthAIVisibilityComparisonOut] = {}
    for _feed_key, group_items in by_feed.items():
        ordered = sorted(
            group_items,
            key=lambda item: max(row.run_at for row in item[1]),
        )
        last: GrowthAIVisibilityComparisonOut | None = None
        for key, rows in ordered:
            if last is not None:
                previous[key] = last
            last = _comparison_out(key, rows, previous=None)
    return previous


def _latest_comparison_by_feed(
    comparisons: list[GrowthAIVisibilityComparisonOut],
) -> list[GrowthAIVisibilityComparisonOut]:
    latest: dict[str, GrowthAIVisibilityComparisonOut] = {}
    for item in comparisons:
        current = latest.get(item.feed_key)
        if current is None or (item.latest_run_at or datetime.min) > (
            current.latest_run_at or datetime.min
        ):
            latest[item.feed_key] = item
    return sorted(
        latest.values(),
        key=lambda item: item.latest_run_at or datetime.min,
        reverse=True,
    )


def _feed_report(
    comparison: GrowthAIVisibilityComparisonOut,
) -> GrowthAIVisibilityFeedReportOut:
    return GrowthAIVisibilityFeedReportOut(
        feed_key=comparison.feed_key,
        latest_run_group=comparison.run_group,
        comparison_status=comparison.comparison_status,
        citation_quality_status=comparison.citation_quality_status,
        feed_effective=comparison.feed_effective,
        external_platforms=comparison.external_platforms,
        missing_platforms=comparison.missing_platforms,
        known_collision_competitors=comparison.known_collision_competitors,
        source_hosts=comparison.source_hosts,
        official_cited_urls=comparison.official_cited_urls,
        mentioned_count=comparison.mentioned_count,
        cited_count=comparison.cited_count,
        mentioned_delta=comparison.mentioned_delta,
        cited_delta=comparison.cited_delta,
        latest_run_at=comparison.latest_run_at,
        next_actions=comparison.next_actions,
    )


def _stable_positive_runs(comparisons: list[GrowthAIVisibilityComparisonOut]) -> int:
    latest_external_runs = sorted(
        [item for item in comparisons if item.external_checks_count > 0],
        key=lambda item: item.latest_run_at or datetime.min,
        reverse=True,
    )
    streak = 0
    for item in latest_external_runs:
        if item.comparison_status == "inconclusive_provider_failure":
            continue
        if not _is_positive_external_run(item):
            break
        streak += 1
    return streak


def _is_positive_external_run(item: GrowthAIVisibilityComparisonOut) -> bool:
    platforms = set(item.external_platforms)
    return (
        "chatgpt" in platforms
        and "claude" in platforms
        and "grok" in platforms
        and "gemini" in platforms
        and item.mentioned_count >= 2
        and item.cited_count >= 1
        and item.comparison_status in {"baseline", "improved", "flat"}
        and not _known_collision_mentions(item.top_competitors)
    )


def _weekly_blockers(
    *,
    comparisons: list[GrowthAIVisibilityComparisonOut],
    missing_platforms: list[str],
    stable_positive_runs: int,
    validation_blockers: list[str],
) -> list[str]:
    blockers: list[str] = list(validation_blockers)
    if not comparisons:
        blockers.append("No external GPT/Claude/Grok probe evidence has been recorded.")
    if "chatgpt" in missing_platforms:
        blockers.append("ChatGPT probe evidence is missing.")
    if "claude" in missing_platforms:
        blockers.append("Claude probe evidence is missing.")
    if stable_positive_runs < AI_VISIBILITY_REQUIRED_STABLE_RUNS:
        blockers.append(
            "Fewer than three stable positive external runs have been recorded."
        )
    collision_mentions = _comparison_collision_mentions(
        _latest_comparison_by_feed(comparisons)
    )
    if collision_mentions:
        blockers.append(
            "Known Synapse brand collision results still appear in external "
            f"probe evidence: {', '.join(collision_mentions)}."
        )
    if not any(item.cited_count > 0 for item in comparisons):
        blockers.append("No answer-engine citation to Synapse has been recorded.")
    return unique_strings(blockers)


def _weekly_next_actions(
    feed_reports: list[GrowthAIVisibilityFeedReportOut],
    missing_platforms: list[str],
    *,
    validation_blockers: list[str],
    collision_mentions: list[str] | None = None,
) -> list[str]:
    actions: list[str] = []
    collision_mentions = collision_mentions or []
    if validation_blockers:
        actions.append(
            "Resolve latest validation blockers before the next external probe."
        )
    if missing_platforms:
        actions.append(
            f"Run and record missing platform probes: {', '.join(missing_platforms)}."
        )
    for report in feed_reports:
        if report.comparison_status in {
            "needs_external_probe",
            "inconclusive_provider_failure",
            "regressed",
            "flat",
        }:
            actions.extend(report.next_actions[:2])
    if collision_mentions:
        actions.append(
            "Add or strengthen disambiguation copy for known collision domains: "
            f"{', '.join(collision_mentions)}."
        )
    if not actions:
        actions.append("Schedule the next weekly GPT/Claude/Grok stability probe.")
    return unique_strings(actions)[:6]


def _comparison_collision_mentions(
    comparisons: list[GrowthAIVisibilityComparisonOut],
) -> list[str]:
    collisions: set[str] = set()
    for item in comparisons:
        collisions.update(_known_collision_mentions(item.top_competitors))
    return sorted(collisions)


def _official_cited_urls(rows: list[GrowthAIVisibilityCheckRow]) -> list[str]:
    urls: list[str] = []
    for row in rows:
        urls.extend(_json_list(row.cited_urls_json))
    return sorted({url for url in urls if is_official_citation_url(url)})


def _citation_quality_status(
    *,
    external_checks_count: int,
    official_cited_urls: list[str],
    known_collision_competitors: list[str],
) -> str:
    if external_checks_count <= 0:
        return "needs_external_probe"
    if known_collision_competitors:
        return "brand_collision_present"
    if not official_cited_urls:
        return "missing_official_citation"
    return "official_citation_verified"


def _known_collision_mentions(values: list[str]) -> list[str]:
    collisions: set[str] = set()
    for value in values:
        normalized = str(value or "").strip().lower()
        for collision in KNOWN_BRAND_COLLISION_COMPETITORS:
            if collision in normalized:
                collisions.add(collision)
    return sorted(collisions)


def _latest_validation_blockers(db: Session, *, limit: int = 200) -> list[str]:
    rows = (
        db.query(GrowthAIVisibilityCheckRow)
        .order_by(
            GrowthAIVisibilityCheckRow.run_at.desc(),
            GrowthAIVisibilityCheckRow.id.desc(),
        )
        .limit(max(limit, 1))
        .all()
    )
    blockers: list[str] = []
    latest_run_group_by_feed: dict[str, str] = {}
    seen_validation_surfaces: set[tuple[str, str]] = set()
    for row in rows:
        if _is_external_visibility_platform(row.platform):
            continue
        feed_key = str(row.feed_key or "unassigned").strip()
        run_group = str(row.run_group or "manual").strip()
        latest_run_group_by_feed.setdefault(feed_key, run_group)
        if run_group != latest_run_group_by_feed[feed_key]:
            continue
        surface_key = (
            feed_key,
            str(row.platform or "validation").strip().lower(),
        )
        if surface_key in seen_validation_surfaces:
            continue
        seen_validation_surfaces.add(surface_key)
        if row.synapse_mentioned and row.synapse_cited:
            continue
        blockers.extend(
            blocker
            for blocker in _json_list(row.missing_facts_json)
            if not is_external_api_key_setup_blocker(blocker)
        )
        if row.next_action:
            if not is_external_api_key_setup_blocker(row.next_action):
                blockers.append(row.next_action)
    return unique_strings(blockers)[:8]


def _is_provider_failure_row(row: GrowthAIVisibilityCheckRow) -> bool:
    return has_provider_failure_missing_fact(_json_list(row.missing_facts_json))


def _recommended_feed_key(feed_reports: list[GrowthAIVisibilityFeedReportOut]) -> str:
    for status in (
        "needs_external_probe",
        "inconclusive_provider_failure",
        "regressed",
        "flat",
    ):
        for report in feed_reports:
            if report.comparison_status == status:
                return report.feed_key
    if feed_reports:
        return feed_reports[0].feed_key
    return "brand_disambiguation_www"


def _probe_template_command(feed_key: str) -> str:
    return (
        "python scripts/growth/generate_ai_visibility_probe_template.py "
        f"--feed-key {feed_key} "
        "--run-group YYYY-MM-DD-weekly "
        "--mode after-feed "
        "--output docs/archive/evidence/growth/ai-visibility/YYYY-MM-DD-weekly.jsonl"
    )


def _is_external_visibility_platform(platform: str | None) -> bool:
    normalized = (platform or "").strip().lower()
    if not normalized:
        return False
    if normalized.endswith("_validation"):
        return False
    if normalized in {"local", "docs_local", "www_local", "staging_validation"}:
        return False
    return True


def _json_list(value: str) -> list[str]:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded if str(item).strip()]


def _metadata_source_hosts(value: str) -> list[str]:
    try:
        loaded = json.loads(value or "{}")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, dict):
        return []
    hosts = loaded.get("source_hosts")
    if not isinstance(hosts, list):
        return []
    return [str(item).strip().lower() for item in hosts if str(item).strip()]


def _append_source_host_next_action(
    next_actions: list[str], source_hosts: Counter[str]
) -> None:
    if not source_hosts:
        return
    hosts = [item for item, _count in source_hosts.most_common(3)]
    _append_unique(
        next_actions,
        "Prioritize third-party presence on cited answer-engine hosts: "
        + ", ".join(hosts)
        + ".",
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
