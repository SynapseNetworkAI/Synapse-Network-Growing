"""AI visibility feed-cycle matrix for continuous answer-engine optimization."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.database_growth import GrowthAIVisibilityCheckRow
from server.schemas_growth import (
    GrowthAIVisibilityFeedCycleListOut,
    GrowthAIVisibilityFeedCycleOut,
)
from server.services.growth.ai_visibility_plan import ai_visibility_feed_packages
from server.services.growth.ai_visibility_discovery import (
    AI_VISIBILITY_TARGET_PLATFORMS,
    list_ai_comparisons,
)
from server.services.growth.ai_visibility_text import unique_strings


def ai_visibility_feed_cycles(db: Session) -> GrowthAIVisibilityFeedCycleListOut:
    packages = ai_visibility_feed_packages().items
    latest_comparison = {}
    for item in list_ai_comparisons(db, limit=100).items:
        latest_comparison.setdefault(item.feed_key, item)
    validation = _validation_by_feed(db)
    items = [
        _cycle_for_package(
            package=package,
            comparison=latest_comparison.get(package.feed_key),
            validation=validation.get(package.feed_key),
        )
        for package in packages
    ]
    recommended = _recommended_feed(items)
    return GrowthAIVisibilityFeedCycleListOut(
        generated_at=_utcnow(),
        target_platforms=AI_VISIBILITY_TARGET_PLATFORMS,
        recommended_feed_key=recommended,
        items=items,
        total=len(items),
    )


def _cycle_for_package(package, comparison, validation: dict | None):
    feed_key = package.feed_key
    run_group = f"{_utcnow().date().isoformat()}-{feed_key}-weekly"
    output_path = f"docs/archive/evidence/growth/ai-visibility/{run_group}.jsonl"
    validation_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-feed-validation.jsonl"
    )
    blockers = list((validation or {}).get("blockers") or [])
    if validation is None:
        blockers.append("Feed validation has not been recorded for this feed.")
    feed_ready = not blockers
    comparison_defaults = _comparison_defaults(comparison)
    missing_platforms = comparison_defaults["missing_platforms"]
    status = _cycle_status(
        feed_ready=feed_ready,
        comparison=comparison,
        missing_platforms=missing_platforms,
    )
    next_actions = _next_actions(
        status=status,
        blockers=blockers,
        package_next_actions=package.next_actions,
        missing_platforms=missing_platforms,
    )
    api_base = (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} "
        f"--run-group {run_group} "
        f"--platforms {','.join(AI_VISIBILITY_TARGET_PLATFORMS)}"
    )
    return GrowthAIVisibilityFeedCycleOut(
        feed_key=feed_key,
        status=status,
        objective=package.objective,
        latest_run_group=comparison_defaults["latest_run_group"],
        latest_comparison_status=comparison_defaults["latest_comparison_status"],
        feed_ready=feed_ready,
        external_probe_ready=feed_ready and status == "ready_for_external_probe",
        feed_effective=comparison_defaults["feed_effective"],
        external_platforms=comparison_defaults["external_platforms"],
        missing_platforms=missing_platforms,
        mentioned_count=comparison_defaults["mentioned_count"],
        cited_count=comparison_defaults["cited_count"],
        blockers=unique_strings(blockers)[:8],
        next_actions=next_actions,
        publish_surfaces=[asset.surface for asset in package.publish_assets],
        feed_validation_command=(
            "python scripts/growth/run_ai_visibility_feed_validation.py "
            f"--feed-key {feed_key} "
            f"--run-group {run_group} "
            f"--output {validation_output_path}"
        ),
        manual_probe_template_command=_manual_template_command(
            package.probe_template_command,
            run_group=run_group,
            output_path=output_path,
        ),
        api_readiness_command=api_base,
        api_execute_command=f"{api_base} --output {output_path} --execute",
        compare_command=(
            "curl -fsS "
            f"'http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key={feed_key}&run_group={run_group}' "
            "| python -m json.tool"
        ),
        latest_run_at=comparison_defaults["latest_run_at"],
    )


def _comparison_defaults(comparison) -> dict:
    if comparison:
        return {
            "latest_run_group": comparison.run_group,
            "latest_comparison_status": comparison.comparison_status,
            "feed_effective": bool(comparison.feed_effective),
            "external_platforms": comparison.external_platforms,
            "missing_platforms": comparison.missing_platforms,
            "mentioned_count": comparison.mentioned_count,
            "cited_count": comparison.cited_count,
            "latest_run_at": comparison.latest_run_at,
        }
    return {
        "latest_run_group": "",
        "latest_comparison_status": "needs_external_probe",
        "feed_effective": False,
        "external_platforms": [],
        "missing_platforms": list(AI_VISIBILITY_TARGET_PLATFORMS),
        "mentioned_count": 0,
        "cited_count": 0,
        "latest_run_at": None,
    }


def _cycle_status(*, feed_ready: bool, comparison, missing_platforms: list[str]) -> str:
    if not feed_ready:
        return "feed_blocked"
    if comparison is None or comparison.external_checks_count <= 0:
        return "ready_for_external_probe"
    if missing_platforms:
        return "partial_external_probe"
    if comparison.cited_count > 0:
        return "citation_observed"
    if comparison.mentioned_count > 0:
        return "mention_observed"
    return "not_visible_yet"


def _next_actions(
    *,
    status: str,
    blockers: list[str],
    package_next_actions: list[str],
    missing_platforms: list[str],
) -> list[str]:
    if status == "feed_blocked":
        return unique_strings(
            blockers + ["Resolve feed blockers before external probes."]
        )[:6]
    if status == "ready_for_external_probe":
        return ["Run unchanged ChatGPT, Claude, Grok, and Gemini probes for this feed."]
    if status == "partial_external_probe":
        return [f"Complete missing external probes: {', '.join(missing_platforms)}."]
    if status in {"citation_observed", "mention_observed"}:
        return [
            "Compare against the previous run group and schedule the next stability probe."
        ]
    return unique_strings(package_next_actions)[:6]


def _validation_by_feed(db: Session) -> dict[str, dict]:
    rows = (
        db.query(GrowthAIVisibilityCheckRow)
        .order_by(
            GrowthAIVisibilityCheckRow.run_at.desc(),
            GrowthAIVisibilityCheckRow.id.desc(),
        )
        .limit(300)
        .all()
    )
    latest: dict[tuple[str, str], GrowthAIVisibilityCheckRow] = {}
    for row in rows:
        if _is_external(row.platform):
            continue
        feed_key = str(row.feed_key or "unassigned").strip()
        platform = str(row.platform or "validation").strip().lower()
        latest.setdefault((feed_key, platform), row)
    by_feed: dict[str, dict] = {}
    for (feed_key, _platform), row in latest.items():
        current = by_feed.setdefault(feed_key, {"blockers": []})
        if row.synapse_mentioned and row.synapse_cited:
            continue
        current["blockers"].extend(_json_list(row.missing_facts_json))
        if row.next_action:
            current["blockers"].append(str(row.next_action))
    return by_feed


def _manual_template_command(command: str, *, run_group: str, output_path: str) -> str:
    return (
        command.replace("YYYY-MM-DD-weekly", run_group)
        .replace("YYYY-MM-DD-after-feed", run_group)
        .replace(
            "docs/archive/evidence/growth/ai-visibility/YYYY-MM-DD-weekly.jsonl",
            output_path,
        )
    )


def _recommended_feed(items: list[GrowthAIVisibilityFeedCycleOut]) -> str:
    for status in (
        "feed_blocked",
        "ready_for_external_probe",
        "partial_external_probe",
        "not_visible_yet",
    ):
        for item in items:
            if item.status == status:
                return item.feed_key
    return items[0].feed_key if items else ""


def _is_external(platform: str | None) -> bool:
    normalized = str(platform or "").strip().lower()
    return bool(normalized and not normalized.endswith("_validation"))


def _json_list(value: str) -> list[str]:
    try:
        loaded = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return (
        [str(item) for item in loaded if str(item).strip()]
        if isinstance(loaded, list)
        else []
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
