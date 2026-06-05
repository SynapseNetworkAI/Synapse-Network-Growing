"""Score feed experiments for the AI visibility optimization loop."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilityComparisonOut,
    GrowthAIVisibilityFeedScoreOut,
    GrowthAIVisibilityFeedScorecardOut,
)
from server.services.growth.ai_visibility_cycles import ai_visibility_feed_cycles
from server.services.growth.ai_visibility_discovery import (
    AI_VISIBILITY_TARGET_PLATFORMS,
    list_ai_comparisons,
)


def ai_visibility_feed_scorecard(db: Session) -> GrowthAIVisibilityFeedScorecardOut:
    cycles = ai_visibility_feed_cycles(db)
    latest_comparisons = _latest_comparison_by_feed(
        list_ai_comparisons(db, limit=100).items
    )
    items = [
        _score_item(
            cycle=cycle,
            comparison=latest_comparisons.get(cycle.feed_key),
        )
        for cycle in cycles.items
    ]
    ranked = sorted(
        items,
        key=lambda item: (
            item.impact_score,
            item.cited_count,
            item.mentioned_count,
            item.external_checks_count,
        ),
        reverse=True,
    )
    for index, item in enumerate(ranked, start=1):
        item.rank = index
    return GrowthAIVisibilityFeedScorecardOut(
        generated_at=datetime.now(timezone.utc),
        recommended_feed_key=cycles.recommended_feed_key,
        ranking_basis=(
            "Impact score rewards feed readiness, GPT/Claude/Grok coverage, "
            "official Synapse citations, positive deltas, durable feed effectiveness, "
            "and penalizes missing citations or known brand-collision results."
        ),
        items=ranked,
        total=len(ranked),
    )


def _latest_comparison_by_feed(
    comparisons: list[GrowthAIVisibilityComparisonOut],
) -> dict[str, GrowthAIVisibilityComparisonOut]:
    latest: dict[str, GrowthAIVisibilityComparisonOut] = {}
    for item in comparisons:
        current = latest.get(item.feed_key)
        if current is None or (item.latest_run_at or datetime.min) > (
            current.latest_run_at or datetime.min
        ):
            latest[item.feed_key] = item
    return latest


def _score_item(*, cycle, comparison) -> GrowthAIVisibilityFeedScoreOut:
    metrics = _score_metrics(cycle=cycle, comparison=comparison)
    score = _impact_score(
        cycle=cycle,
        comparison=comparison,
        covered_platforms=metrics["covered_platforms"],
        missing_platforms=metrics["missing_platforms"],
        mentioned_count=metrics["mentioned_count"],
        cited_count=metrics["cited_count"],
        feed_effective=metrics["feed_effective"],
        citation_quality_status=str(metrics["citation_quality_status"]),
    )
    return GrowthAIVisibilityFeedScoreOut(
        feed_key=cycle.feed_key,
        impact_score=score,
        status=cycle.status,
        objective=cycle.objective,
        latest_run_group=metrics["latest_run_group"],
        comparison_status=metrics["comparison_status"],
        citation_quality_status=str(metrics["citation_quality_status"]),
        feed_ready=cycle.feed_ready,
        external_probe_ready=cycle.external_probe_ready,
        feed_effective=metrics["feed_effective"],
        target_platforms=AI_VISIBILITY_TARGET_PLATFORMS,
        covered_platforms=metrics["covered_platforms"],
        missing_platforms=metrics["missing_platforms"],
        external_checks_count=comparison.external_checks_count if comparison else 0,
        local_validation_count=comparison.local_validation_count if comparison else 0,
        mentioned_count=metrics["mentioned_count"],
        cited_count=metrics["cited_count"],
        known_collision_competitors=metrics["known_collision_competitors"],
        official_cited_urls=metrics["official_cited_urls"],
        mentioned_delta=comparison.mentioned_delta if comparison else 0,
        cited_delta=comparison.cited_delta if comparison else 0,
        blockers=cycle.blockers,
        next_actions=cycle.next_actions,
        recommended_action=_recommended_action(
            cycle,
            missing_platforms=metrics["missing_platforms"],
            feed_effective=metrics["feed_effective"],
            citation_quality_status=str(metrics["citation_quality_status"]),
            known_collision_competitors=metrics["known_collision_competitors"],
        ),
        feed_validation_command=cycle.feed_validation_command,
        api_readiness_command=cycle.api_readiness_command,
        api_execute_command=cycle.api_execute_command,
        compare_command=cycle.compare_command,
    )


def _score_metrics(*, cycle, comparison) -> dict[str, object]:
    if comparison:
        return {
            "latest_run_group": comparison.run_group,
            "comparison_status": comparison.comparison_status,
            "citation_quality_status": comparison.citation_quality_status,
            "feed_effective": bool(comparison.feed_effective),
            "covered_platforms": comparison.external_platforms,
            "missing_platforms": comparison.missing_platforms,
            "mentioned_count": comparison.mentioned_count,
            "cited_count": comparison.cited_count,
            "known_collision_competitors": comparison.known_collision_competitors,
            "official_cited_urls": comparison.official_cited_urls,
        }
    return {
        "latest_run_group": cycle.latest_run_group,
        "comparison_status": cycle.latest_comparison_status,
        "citation_quality_status": "unknown",
        "feed_effective": cycle.feed_effective,
        "covered_platforms": cycle.external_platforms,
        "missing_platforms": cycle.missing_platforms,
        "mentioned_count": cycle.mentioned_count,
        "cited_count": cycle.cited_count,
        "known_collision_competitors": [],
        "official_cited_urls": [],
    }


def _impact_score(
    *,
    cycle,
    comparison,
    covered_platforms: list[str],
    missing_platforms: list[str],
    mentioned_count: int,
    cited_count: int,
    feed_effective: bool,
    citation_quality_status: str,
) -> int:
    score = 0
    if cycle.feed_ready:
        score += 10
    score += min(len(covered_platforms), 3) * 8
    score += min(mentioned_count, 6) * 8
    score += min(cited_count, 6) * 12
    if comparison:
        score += max(comparison.mentioned_delta, 0) * 4
        score += max(comparison.cited_delta, 0) * 6
        if comparison.comparison_status == "regressed":
            score -= 8
        if comparison.comparison_status == "flat":
            score -= 2
    if citation_quality_status == "official_citation_verified":
        score += 8
    if citation_quality_status == "missing_official_citation":
        score -= 10
    if citation_quality_status == "brand_collision_present":
        score -= 18
    if feed_effective:
        score += 10
    if "chatgpt" in missing_platforms:
        score -= 5
    if "claude" in missing_platforms:
        score -= 5
    if cycle.blockers:
        score -= 10
    return max(0, min(score, 100))


def _recommended_action(
    cycle,
    *,
    missing_platforms: list[str],
    feed_effective: bool,
    citation_quality_status: str,
    known_collision_competitors: list[str],
) -> str:
    if cycle.blockers:
        return (
            "Resolve feed blockers, then rerun live readiness before external probes."
        )
    if citation_quality_status == "brand_collision_present":
        return (
            "Strengthen brand disambiguation before the next probe; collision "
            f"domains remain: {', '.join(known_collision_competitors)}."
        )
    if citation_quality_status == "missing_official_citation":
        return "Revise feed assets so answer engines cite official www, docs, GitHub, MCP, or registry sources."
    if cycle.external_probe_ready:
        return "Run unchanged GPT/Claude/Grok probes and record results under the same run group."
    if missing_platforms:
        return f"Complete missing external probes: {', '.join(missing_platforms)}."
    if feed_effective:
        return "Schedule the next stability probe to prove the result holds."
    return "Revise the feed surface, publish, and compare against the previous run."
