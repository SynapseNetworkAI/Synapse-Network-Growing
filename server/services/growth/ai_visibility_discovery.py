from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database_growth import GrowthAIVisibilityCheckRow
from server.schemas_growth import (
    GrowthAIVisibilityCheckCreate,
    GrowthAIVisibilityCheckListOut,
    GrowthAIVisibilityCheckOut,
    GrowthAIVisibilityComparisonListOut,
    GrowthAIVisibilityNextCycleOut,
    GrowthAIVisibilityWeeklyReportOut,
)
from server.services.growth.serializer import ai_check_out, json_dumps
from server.services.growth.ai_visibility_comparison_helpers import (
    _comparison_collision_mentions,
    _comparison_out,
    _feed_report,
    _latest_comparison_by_feed,
    _latest_validation_blockers,
    _previous_comparison_by_key,
    _probe_template_command,
    _recommended_feed_key,
    _stable_positive_runs,
    _utcnow,
    _weekly_blockers,
    _weekly_next_actions,
)
from server.services.growth.ai_visibility_official_sources import (
    is_official_citation_url,
)

AI_VISIBILITY_TARGET_PLATFORMS = ["chatgpt", "claude", "grok", "gemini"]
AI_VISIBILITY_REQUIRED_STABLE_RUNS = 3


def _limit(value: int) -> int:
    return min(max(int(value or 50), 1), 100)


def create_ai_check(
    db: Session, body: GrowthAIVisibilityCheckCreate
) -> GrowthAIVisibilityCheckOut:
    if not body.query.strip() or not body.platform.strip():
        raise ValueError("query and platform are required")
    if (
        body.synapse_cited
        and body.cited_urls
        and not _has_official_citation(body.cited_urls)
    ):
        raise ValueError(
            "synapse_cited=true requires at least one official Synapse cited_url"
        )
    row = GrowthAIVisibilityCheckRow(
        query=body.query.strip(),
        platform=body.platform.strip(),
        answer_summary=body.answer_summary.strip(),
        synapse_mentioned=1 if body.synapse_mentioned else 0,
        synapse_cited=1 if body.synapse_cited else 0,
        cited_urls_json=json_dumps(body.cited_urls),
        competitor_mentions_json=json_dumps(body.competitor_mentions),
        missing_facts_json=json_dumps(body.missing_facts),
        next_action=body.next_action.strip(),
        feed_key=body.feed_key.strip(),
        run_group=body.run_group.strip(),
        result_rank=max(int(body.result_rank or 0), 0),
        evidence_url=body.evidence_url.strip(),
        metadata_json=json_dumps(body.metadata),
    )
    db.add(row)
    db.commit()
    return ai_check_out(row)


def _has_official_citation(urls: list[str]) -> bool:
    return any(is_official_citation_url(url) for url in urls)


def list_ai_checks(
    db: Session,
    *,
    q: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GrowthAIVisibilityCheckListOut:
    query = db.query(GrowthAIVisibilityCheckRow)
    if platform:
        query = query.filter(GrowthAIVisibilityCheckRow.platform == platform)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                GrowthAIVisibilityCheckRow.query.ilike(pattern),
                GrowthAIVisibilityCheckRow.answer_summary.ilike(pattern),
            )
        )
    total = int(query.count())
    items = (
        query.order_by(
            GrowthAIVisibilityCheckRow.run_at.desc(),
            GrowthAIVisibilityCheckRow.id.desc(),
        )
        .offset(max(offset, 0))
        .limit(_limit(limit))
        .all()
    )
    return GrowthAIVisibilityCheckListOut(
        items=[ai_check_out(item) for item in items],
        total=total,
        limit=_limit(limit),
        offset=max(offset, 0),
    )


def list_ai_comparisons(
    db: Session,
    *,
    feed_key: str | None = None,
    run_group: str | None = None,
    limit: int = 20,
) -> GrowthAIVisibilityComparisonListOut:
    query = db.query(GrowthAIVisibilityCheckRow)
    if feed_key:
        query = query.filter(GrowthAIVisibilityCheckRow.feed_key == feed_key.strip())
    rows = (
        query.order_by(
            GrowthAIVisibilityCheckRow.run_at.desc(),
            GrowthAIVisibilityCheckRow.id.desc(),
        )
        .limit(_limit(limit) * 12)
        .all()
    )
    grouped: dict[tuple[str, str], list[GrowthAIVisibilityCheckRow]] = {}
    for row in rows:
        key = (row.feed_key or "unassigned", row.run_group or "manual")
        grouped.setdefault(key, []).append(row)
    previous_by_key = _previous_comparison_by_key(grouped)
    comparisons = [
        _comparison_out(key, value, previous=previous_by_key.get(key))
        for key, value in grouped.items()
    ]
    if run_group:
        clean_run_group = run_group.strip()
        comparisons = [
            item for item in comparisons if item.run_group == clean_run_group
        ]
    comparisons.sort(key=lambda item: item.latest_run_at or datetime.min, reverse=True)
    return GrowthAIVisibilityComparisonListOut(
        items=comparisons[: _limit(limit)],
        total=len(comparisons),
    )


def ai_visibility_weekly_report(db: Session) -> GrowthAIVisibilityWeeklyReportOut:
    comparisons = list_ai_comparisons(db, limit=100).items
    validation_blockers = _latest_validation_blockers(db)
    latest_by_feed = _latest_comparison_by_feed(comparisons)
    feed_reports = [_feed_report(item) for item in latest_by_feed]
    covered_platforms, missing_platforms = _platform_coverage(comparisons)
    stable_positive_runs = _stable_positive_runs(comparisons)
    latest = _latest_comparison(comparisons)
    blockers = _weekly_blockers(
        comparisons=comparisons,
        missing_platforms=missing_platforms,
        stable_positive_runs=stable_positive_runs,
        validation_blockers=validation_blockers,
    )
    collision_mentions = _comparison_collision_mentions(latest_by_feed)
    goal_achieved = not blockers
    recommended_feed_key = _recommended_feed_key(feed_reports)
    return GrowthAIVisibilityWeeklyReportOut(
        generated_at=_utcnow(),
        goal_status="achieved" if goal_achieved else "optimizing",
        goal_achieved=goal_achieved,
        required_stable_runs=AI_VISIBILITY_REQUIRED_STABLE_RUNS,
        stable_positive_runs=stable_positive_runs,
        target_platforms=AI_VISIBILITY_TARGET_PLATFORMS,
        covered_platforms=covered_platforms,
        missing_platforms=missing_platforms,
        total_external_checks=sum(item.external_checks_count for item in comparisons),
        total_mentioned_count=sum(item.mentioned_count for item in comparisons),
        total_cited_count=sum(item.cited_count for item in comparisons),
        latest_feed_key=latest.feed_key if latest else "",
        latest_run_group=latest.run_group if latest else "",
        latest_comparison_status=latest.comparison_status
        if latest
        else "needs_external_probe",
        feed_reports=feed_reports,
        blockers=blockers,
        next_actions=_weekly_next_actions(
            feed_reports,
            missing_platforms,
            validation_blockers=validation_blockers,
            collision_mentions=collision_mentions,
        ),
        recommended_feed_key=recommended_feed_key,
        recommended_probe_template_command=_probe_template_command(
            recommended_feed_key
        ),
    )


def _platform_coverage(comparisons) -> tuple[list[str], list[str]]:
    covered_platforms = sorted(
        {
            platform
            for item in comparisons
            for platform in item.external_platforms
            if platform in AI_VISIBILITY_TARGET_PLATFORMS
        }
    )
    missing_platforms = [
        platform
        for platform in AI_VISIBILITY_TARGET_PLATFORMS
        if platform not in covered_platforms
    ]
    return covered_platforms, missing_platforms


def _latest_comparison(comparisons):
    return comparisons[0] if comparisons else None


def ai_visibility_next_cycle(db: Session) -> GrowthAIVisibilityNextCycleOut:
    from server.services.growth.ai_visibility_plan import ai_visibility_feed_packages

    report = ai_visibility_weekly_report(db)
    feed_key = report.recommended_feed_key or "agent_payment_category_pages"
    run_group = f"{_utcnow().date().isoformat()}-{feed_key}-weekly"
    output_path = f"docs/archive/evidence/growth/ai-visibility/{run_group}.jsonl"
    matrix_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-probe-matrix.json"
    )
    cycle_summary_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-cycle-summary.json"
    )
    operator_brief_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-operator-brief.md"
    )
    goal_audit_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-goal-audit.json"
    )
    validation_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/{run_group}-feed-validation.jsonl"
    )
    external_gate_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/"
        f"{run_group}-external-probe-gate.json"
    )
    public_search_snapshot_path = (
        f"docs/archive/evidence/growth/ai-visibility/"
        f"{run_group}-public-web-search-snapshot.json"
    )
    public_search_output_path = (
        f"docs/archive/evidence/growth/ai-visibility/"
        f"{run_group}-public-web-search.jsonl"
    )
    packages = ai_visibility_feed_packages(feed_key).items
    validation_commands = packages[0].validation_commands if packages else []
    manual_command = (
        _probe_template_command(feed_key)
        .replace("YYYY-MM-DD-weekly", run_group)
        .replace(
            "docs/archive/evidence/growth/ai-visibility/YYYY-MM-DD-weekly.jsonl",
            output_path,
        )
    )
    api_base = (
        "python scripts/growth/run_ai_visibility_api_probe.py "
        f"--feed-key {feed_key} "
        f"--run-group {run_group} "
        "--platforms chatgpt,claude,grok,gemini"
    )
    return GrowthAIVisibilityNextCycleOut(
        feed_key=feed_key,
        run_group=run_group,
        output_path=output_path,
        missing_platforms=report.missing_platforms,
        blockers=report.blockers,
        next_actions=report.next_actions,
        validation_commands=validation_commands,
        feed_validation_command=(
            "python scripts/growth/run_ai_visibility_feed_validation.py "
            f"--feed-key {feed_key} "
            f"--run-group {run_group} "
            f"--output {validation_output_path}"
        ),
        manual_probe_template_command=manual_command,
        external_probe_gate_command=(
            "python scripts/growth/generate_ai_visibility_external_probe_gate.py "
            f"--feed-key {feed_key} "
            f"--run-group {run_group} "
            f"--output {external_gate_output_path}"
        ),
        api_readiness_command=api_base,
        api_execute_command=f"{api_base} --output {output_path} --execute",
        public_web_search_import_command=(
            "python scripts/growth/import_ai_visibility_public_search_snapshot.py "
            f"{public_search_snapshot_path} "
            f"--output {public_search_output_path}"
        ),
        apply_command=(
            f"python scripts/growth/record_ai_visibility_probe.py {output_path} --apply"
        ),
        probe_matrix_command=(
            "python scripts/growth/generate_ai_visibility_probe_matrix.py "
            f"--output {matrix_output_path}"
        ),
        validate_matrix_command=(
            "python scripts/growth/validate_ai_visibility_probe_matrix.py "
            f"{output_path} "
            f"--matrix-file {matrix_output_path} "
            f"--feed-key {feed_key} "
            f"--run-group {run_group}"
        ),
        cycle_summary_command=(
            "python scripts/growth/summarize_ai_visibility_cycle.py "
            f"{output_path} "
            f"--output {cycle_summary_output_path}"
        ),
        operator_brief_command=(
            "python scripts/growth/generate_ai_visibility_operator_brief.py "
            f"--feed-key {feed_key} "
            f"--cycle-summary {cycle_summary_output_path} "
            f"--output {operator_brief_output_path}"
        ),
        goal_audit_command=(
            "python scripts/growth/generate_ai_visibility_goal_audit.py "
            f"--output {goal_audit_output_path}"
        ),
        compare_command=(
            "curl -fsS "
            f"'http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key={feed_key}&run_group={run_group}' "
            "| python -m json.tool"
        ),
        weekly_report_command=(
            "python scripts/growth/export_ai_visibility_weekly_report.py "
            "--output docs/archive/evidence/growth/ai-visibility/"
            f"{run_group}-weekly-report.json"
        ),
    )
