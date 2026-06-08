"""Markdown operator brief for the AI visibility optimization loop."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from server.schemas_growth import GrowthAIVisibilityOptimizationBriefOut
from server.services.growth.ai_visibility_cycles import ai_visibility_feed_cycles
from server.services.growth.ai_visibility_design_handoff import (
    ai_agent_payments_design_handoff,
)
from server.services.growth.ai_visibility_docs_blueprint import (
    ai_agent_payments_docs_blueprint,
)
from server.services.growth.ai_visibility_external_probe_gate import (
    ai_visibility_external_probe_gate,
)
from server.services.growth.ai_visibility_plan import (
    CANONICAL_HOMEPAGE,
    ai_visibility_optimization_plan,
)
from server.services.growth.ai_visibility_release_snapshot import build_snapshot
from server.services.growth.ai_visibility_release_unblock import (
    DEFAULT_ACTOR,
    DEFAULT_TARGET_COMMIT,
    build_release_unblock_plan,
)
from server.services.growth.ai_visibility_discovery import ai_visibility_weekly_report
from server.services.growth.ai_visibility_text import unique_strings


def ai_visibility_optimization_brief(
    db: Session,
    *,
    run_group: str | None = None,
) -> GrowthAIVisibilityOptimizationBriefOut:
    generated_at = _utcnow()
    safe_run_group = (
        run_group or f"{generated_at.date().isoformat()}-operator-brief"
    ).strip()
    report = ai_visibility_weekly_report(db)
    cycles = ai_visibility_feed_cycles(db)
    release_plan = build_release_unblock_plan(
        target_commit=DEFAULT_TARGET_COMMIT,
        actor="codex/ai-visibility-operator-brief",
    )
    release_snapshot = build_snapshot(
        target_commit=DEFAULT_TARGET_COMMIT,
        actor=DEFAULT_ACTOR,
        feed_key="mcp_paid_api_discovery",
        run_group=f"{safe_run_group}-release-snapshot",
    )
    external_gate = ai_visibility_external_probe_gate(
        feed_key=release_snapshot["feed_key"],
        run_group=f"{safe_run_group}-external-probe",
    )
    plan = ai_visibility_optimization_plan()
    docs = ai_agent_payments_docs_blueprint()
    handoff = ai_agent_payments_design_handoff()
    blockers = _brief_blockers(
        report,
        cycles,
        release_plan,
        release_snapshot,
        external_gate,
    )
    next_actions = _brief_next_actions(report, cycles, release_snapshot)
    artifact_path = (
        "docs/archive/evidence/growth/ai-visibility/"
        f"{safe_run_group}-optimization-brief.md"
    )
    markdown = _render_markdown(
        generated_at=generated_at,
        plan_objective=plan.objective,
        report=report,
        cycles=cycles,
        release_plan=release_plan,
        release_snapshot=release_snapshot,
        external_gate=external_gate,
        docs_category=docs.category,
        figma_file_name=handoff.figma_file_name,
        blockers=blockers,
        next_actions=next_actions,
    )
    return GrowthAIVisibilityOptimizationBriefOut(
        title="Synapse AI Visibility Optimization Brief",
        status="blocked" if blockers else "ready_for_external_probe",
        generated_at=generated_at,
        official_homepage=CANONICAL_HOMEPAGE,
        recommended_feed_key=cycles.recommended_feed_key or report.recommended_feed_key,
        target_platforms=cycles.target_platforms,
        blockers=blockers,
        next_actions=next_actions,
        artifact_path=artifact_path,
        export_command=(
            "python scripts/growth/generate_ai_visibility_optimization_brief.py "
            f"--run-group {safe_run_group} "
            f"--output {artifact_path}"
        ),
        markdown=markdown,
    )


def _brief_blockers(
    report,
    cycles,
    release_plan: dict,
    release_snapshot: dict,
    external_gate,
) -> list[str]:
    return unique_strings(
        report.blockers
        + [blocker for item in cycles.items for blocker in item.blockers]
        + list(release_plan.get("known_blockers") or [])
        + list(release_snapshot.get("blockers") or [])
        + list(external_gate.blockers)
    )[:12]


def _brief_next_actions(report, cycles, release_snapshot: dict) -> list[str]:
    return unique_strings(
        report.next_actions
        + [action for item in cycles.items for action in item.next_actions]
        + list(release_snapshot.get("next_actions") or [])
    )[:12]


def _render_markdown(
    *,
    generated_at: datetime,
    plan_objective: str,
    report,
    cycles,
    release_plan: dict,
    release_snapshot: dict,
    external_gate,
    docs_category: str,
    figma_file_name: str,
    blockers: list[str],
    next_actions: list[str],
) -> str:
    lines = [
        "# Synapse AI Visibility Optimization Brief",
        "",
        f"Generated: {generated_at.isoformat()}",
        f"Official homepage: {CANONICAL_HOMEPAGE}",
        f"Objective: {plan_objective}",
        "",
        "## Current Gate",
        "",
        f"- Status: {report.goal_status}",
        f"- Stable positive runs: {report.stable_positive_runs}/{report.required_stable_runs}",
        f"- Target platforms: {', '.join(cycles.target_platforms)}",
        f"- Recommended feed: {cycles.recommended_feed_key or report.recommended_feed_key}",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(_bullets(blockers or ["No blockers recorded."]))
    lines.extend(["", "## Next Actions", ""])
    lines.extend(_bullets(next_actions or ["Run the next weekly external probe."]))
    lines.extend(["", "## Operator Execution Sequence", ""])
    lines.extend(
        _execution_sequence_markdown_lines(
            feed_key=(
                release_snapshot.get("feed_key")
                or cycles.recommended_feed_key
                or report.recommended_feed_key
            ),
        )
    )
    lines.extend(["", "## Fail-Closed Success Rules", ""])
    lines.extend(_fail_closed_markdown_lines())
    lines.extend(["", "## Feed Cycle Matrix", ""])
    lines.extend(_cycle_markdown_lines(cycles.items))
    lines.extend(
        [
            "## Product Docs And Design",
            "",
            f"- Docs category: {docs_category}",
            f"- Stitch/Figma file: {figma_file_name}",
            "- Product docs and Figma handoff remain source-backed by the Growing AI Visibility module.",
            "",
            "## Release Unblock",
            "",
            f"- Status: {release_plan.get('status')}",
            f"- Target commit: {release_plan.get('target_commit_sha')}",
            f"- Services: {', '.join(release_plan.get('services') or [])}",
            f"- Release snapshot: {release_snapshot.get('status')}",
            f"- Release readiness: {release_snapshot.get('deploy_readiness_status')}",
            f"- External probe gate: {external_gate.status}",
            f"- Ready platforms: {', '.join(external_gate.ready_platforms) or '-'}",
            f"- Missing platforms: {', '.join(external_gate.missing_platforms) or '-'}",
            f"- Partial probe command: `{external_gate.partial_api_readiness_command or '-'}`",
            "- Production feed validation must pass before GPT/Claude/Grok probes count as success evidence.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _cycle_markdown_lines(items) -> list[str]:
    lines: list[str] = []
    for item in items:
        lines.extend(
            [
                f"### {item.feed_key}",
                "",
                f"- Status: {item.status}",
                f"- Latest run: {item.latest_run_group or 'none'}",
                f"- External platforms: {', '.join(item.external_platforms) or '-'}",
                f"- Missing platforms: {', '.join(item.missing_platforms) or '-'}",
                f"- Mention/citation count: {item.mentioned_count}/{item.cited_count}",
                f"- Feed validation: `{item.feed_validation_command}`",
                f"- API readiness: `{item.api_readiness_command}`",
                f"- Compare: `{item.compare_command}`",
                "",
            ]
        )
    return lines


def _execution_sequence_markdown_lines(*, feed_key: str) -> list[str]:
    return [
        (
            "- Validate production feed readiness: "
            f"`python scripts/growth/run_ai_visibility_feed_validation.py --feed-key {feed_key}`."
        ),
        (
            "- Export the GPT/Claude/Grok/Gemini probe matrix: "
            f"`python scripts/growth/generate_ai_visibility_probe_matrix.py --feed-key {feed_key}`."
        ),
        (
            "- Generate the feed-specific manual or API probe payloads; do not replace "
            "the matrix with one-off `--query` diagnostics."
        ),
        (
            "- Record every external probe with screenshot or artifact evidence before "
            "running comparison."
        ),
        (
            "- Validate matrix coverage: "
            f"`python scripts/growth/validate_ai_visibility_probe_matrix.py --feed-key {feed_key}`."
        ),
        "- Run comparison and weekly report only after the matrix validator passes.",
    ]


def _fail_closed_markdown_lines() -> list[str]:
    return [
        (
            f"- The canonical product homepage is {CANONICAL_HOMEPAGE}; "
            "bare-domain results only count as redirect evidence, not as the canonical citation."
        ),
        (
            "- Successful GPT/Claude/Grok/Gemini evidence must cite an official source prefix "
            "from the official source map."
        ),
        (
            "- Stable positive runs require complete matrix coverage, external platform "
            "evidence URLs, official citations, and no known brand-collision competitor."
        ),
        (
            "- Partial API readiness is diagnostic only; it cannot close the AI visibility "
            "goal or count as full cross-platform success."
        ),
    ]


def _bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items if str(item).strip()]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
