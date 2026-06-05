from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilityProbeMatrixOut,
    GrowthAIVisibilityProbeMatrixRowOut,
)
from server.services.growth.ai_visibility_cycles import ai_visibility_feed_cycles
from server.services.growth.ai_visibility_official_sources import (
    ai_visibility_official_sources,
)
from server.services.growth.ai_visibility_plan import ai_visibility_feed_packages


def ai_visibility_probe_matrix(db: Session) -> GrowthAIVisibilityProbeMatrixOut:
    cycles = ai_visibility_feed_cycles(db)
    packages = {item.feed_key: item for item in ai_visibility_feed_packages().items}
    source_urls_by_feed = _source_urls_by_feed()
    rows: list[GrowthAIVisibilityProbeMatrixRowOut] = []
    for cycle in cycles.items:
        package = packages.get(cycle.feed_key)
        if not package:
            continue
        run_group = _run_group_from_command(cycle.manual_probe_template_command)
        for platform in cycles.target_platforms:
            rows.append(
                GrowthAIVisibilityProbeMatrixRowOut(
                    feed_key=cycle.feed_key,
                    platform=platform,
                    status=_row_status(cycle=cycle, platform=platform),
                    run_group=run_group,
                    queries=list(package.target_queries),
                    official_source_urls=source_urls_by_feed.get(cycle.feed_key, []),
                    success_decision_rule=(
                        "Success requires the answer to mention Synapse Network and "
                        "cite at least one official_source_urls host. Brand collision "
                        "domains are competitor mentions, not Synapse success."
                    ),
                    manual_probe_template_command=cycle.manual_probe_template_command,
                    record_probe_command=(
                        "python scripts/growth/record_ai_visibility_probe.py "
                        f"{_output_path(run_group)} --apply"
                    ),
                    compare_command=cycle.compare_command,
                    evidence_directory=(
                        f"docs/archive/evidence/growth/ai-visibility/{run_group}"
                    ),
                    blockers=list(cycle.blockers),
                    next_actions=_next_actions(cycle=cycle, platform=platform),
                )
            )
    return GrowthAIVisibilityProbeMatrixOut(
        generated_at=datetime.now(UTC),
        target_platforms=cycles.target_platforms,
        recommended_feed_key=cycles.recommended_feed_key,
        rows=rows,
        total=len(rows),
    )


def _source_urls_by_feed() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for source in ai_visibility_official_sources().items:
        for feed_key in source.feed_keys:
            grouped.setdefault(feed_key, []).append(source.canonical_url)
    return {key: sorted(set(value)) for key, value in grouped.items()}


def _row_status(*, cycle, platform: str) -> str:
    if cycle.blockers:
        return "blocked_until_feed_ready"
    if platform in cycle.external_platforms:
        return "covered"
    if platform in cycle.missing_platforms:
        return "ready_to_probe"
    return "needs_review"


def _next_actions(*, cycle, platform: str) -> list[str]:
    if cycle.blockers:
        return cycle.next_actions[:4]
    if platform in cycle.external_platforms:
        return [
            "Keep the same query phrasing and rerun this platform in the next stability window."
        ]
    return [
        f"Run the {platform} probe with unchanged query wording.",
        "Capture screenshot evidence, cited URLs, competitors, and missing facts.",
        "Record the result with the generated JSONL template before comparing runs.",
    ]


def _run_group_from_command(command: str) -> str:
    match = re.search(r"--run-group\s+([^\s]+)", command)
    return match.group(1) if match else "ai-visibility-probe"


def _output_path(run_group: str) -> str:
    return f"docs/archive/evidence/growth/ai-visibility/{run_group}.jsonl"
