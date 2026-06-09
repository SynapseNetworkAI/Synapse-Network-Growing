"""Fail-closed completion audit for the AI visibility goal."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from server.schemas_growth import (
    GrowthAIVisibilityGoalAuditOut,
    GrowthAIVisibilityGoalAuditRequirementOut,
)
from server.services.growth.ai_visibility_cycles import ai_visibility_feed_cycles
from server.services.growth.ai_visibility_discovery import (
    AI_VISIBILITY_TARGET_PLATFORMS,
    ai_visibility_weekly_report,
)
from server.services.growth.ai_visibility_docs_blueprint import (
    ai_agent_payments_docs_blueprint,
)
from server.services.growth.ai_visibility_design_handoff import (
    ai_agent_payments_design_handoff,
)
from server.services.growth.ai_visibility_plan import ai_visibility_optimization_plan
from server.services.growth.ai_visibility_scorecard import ai_visibility_feed_scorecard
from server.services.growth.ai_visibility_source_host_audit import (
    REQUIRED_DIRECTORY_HOSTS,
    SOURCE_HOST_FRAME,
    merge_source_host_audit_facts,
    missing_hosts,
    source_host_audit_facts,
    source_host_checklist_facts,
)
from server.services.growth.ai_visibility_source_host_feed import (
    ai_visibility_source_host_execution_checklist,
)
from server.services.growth.ai_visibility_text import unique_strings

OFFICIAL_HOMEPAGE = "https://www.synapse-network.ai/"
MCP_DISCOVERY_FEED_KEY = "mcp_paid_api_discovery"


def ai_visibility_goal_audit(
    db: Session,
    *,
    live_readiness: dict[str, Any] | None = None,
    external_gate: dict[str, Any] | None = None,
) -> GrowthAIVisibilityGoalAuditOut:
    context = _audit_context(db)
    requirements = _audit_requirements(
        context,
        live_readiness=live_readiness,
        external_gate=external_gate,
    )
    blockers = _audit_blockers(requirements, context["weekly"].blockers)
    next_actions = _audit_next_actions(requirements, context["weekly"].next_actions)
    completed_count = _completed_count(requirements)
    achieved = not blockers and completed_count == len(requirements)
    return GrowthAIVisibilityGoalAuditOut(
        generated_at=datetime.now(UTC),
        status="achieved" if achieved else "incomplete",
        goal_achieved=achieved,
        official_homepage=OFFICIAL_HOMEPAGE,
        target_platforms=AI_VISIBILITY_TARGET_PLATFORMS,
        completed_count=completed_count,
        total_required=len(requirements),
        requirements=requirements,
        blockers=blockers,
        next_actions=next_actions,
        export_command=(
            "python scripts/growth/generate_ai_visibility_goal_audit.py "
            "--output docs/archive/evidence/growth/ai-visibility/goal-audit.json"
        ),
    )


def _audit_context(db: Session) -> dict[str, Any]:
    plan = ai_visibility_optimization_plan()
    checklist = ai_visibility_source_host_execution_checklist(
        db,
        feed_key=MCP_DISCOVERY_FEED_KEY,
    )
    source_host_facts = merge_source_host_audit_facts(
        source_host_checklist_facts(checklist),
        source_host_audit_facts(),
    )
    return {
        "plan": plan,
        "docs": ai_agent_payments_docs_blueprint(),
        "handoff": ai_agent_payments_design_handoff(),
        "source_host_facts": source_host_facts,
        "weekly": ai_visibility_weekly_report(db),
        "cycles": ai_visibility_feed_cycles(db),
        "scorecard": ai_visibility_feed_scorecard(db),
    }


def _audit_requirements(
    context: dict[str, Any],
    *,
    live_readiness: dict[str, Any] | None,
    external_gate: dict[str, Any] | None,
) -> list[GrowthAIVisibilityGoalAuditRequirementOut]:
    plan = context["plan"]
    docs = context["docs"]
    handoff = context["handoff"]
    source_host_facts = context["source_host_facts"]
    cycles = context["cycles"]
    scorecard = context["scorecard"]
    weekly = context["weekly"]
    return [
        _static_requirement(
            "strategy",
            "Agent optimization strategy",
            _strategy_complete(plan),
            f"{len(plan.feed_experiments)} feed experiments and "
            f"{len(plan.success_criteria)} success criteria are defined.",
            "Define feed experiments, success criteria, and answer-engine target queries.",
        ),
        _static_requirement(
            "product_docs",
            "Product docs design",
            _product_docs_complete(docs),
            f"{docs.category} blueprint has {len(docs.pages)} page(s).",
            "Export AI Agent Payments docs blueprint with answer-ready blocks.",
        ),
        _static_requirement(
            "stitch_figma",
            "Stitch to Figma handoff",
            _handoff_complete(handoff),
            f"{handoff.figma_file_name} has {len(handoff.frames)} frame prompt(s).",
            "Generate Stitch/Figma handoff with frames, components, and import steps.",
        ),
        _static_requirement(
            "growing_module",
            "Growing AI Visibility module",
            _growing_module_complete(plan, cycles, scorecard),
            f"{len(cycles.items)} feed cycle(s) and {len(scorecard.items)} score row(s).",
            "Expose feed cycles, scorecard, matrix, gates, and weekly report in Growing.",
        ),
        _static_requirement(
            "feed_experiments",
            "Different feed experiments",
            len(plan.feed_experiments) >= 3,
            ", ".join(item.feed_key for item in plan.feed_experiments),
            "Define brand, category-page, and MCP discovery feed experiments.",
        ),
        _source_host_handoff_requirement(source_host_facts),
        _source_host_submission_requirement(source_host_facts),
        _source_host_live_requirement(source_host_facts),
        _feed_readiness_requirement(cycles, live_readiness, external_gate),
        _external_probe_requirement(weekly),
        _stable_runs_requirement(weekly),
    ]


def _audit_blockers(
    requirements: list[GrowthAIVisibilityGoalAuditRequirementOut],
    weekly_blockers: list[str],
) -> list[str]:
    return unique_strings(
        [item.blocker for item in requirements if item.required and item.blocker]
        + list(weekly_blockers)
    )


def _audit_next_actions(
    requirements: list[GrowthAIVisibilityGoalAuditRequirementOut],
    weekly_next_actions: list[str],
) -> list[str]:
    return unique_strings(
        [item.next_action for item in requirements if item.next_action]
        + list(weekly_next_actions)
    )


def _completed_count(
    requirements: list[GrowthAIVisibilityGoalAuditRequirementOut],
) -> int:
    return len([item for item in requirements if item.status == "completed"])


def _strategy_complete(plan) -> bool:
    return all([plan.feed_experiments, plan.success_criteria])


def _product_docs_complete(docs) -> bool:
    return all([docs.pages, docs.shared_components])


def _handoff_complete(handoff) -> bool:
    return all([handoff.frames, handoff.import_steps])


def _growing_module_complete(plan, cycles, scorecard) -> bool:
    return all([plan.growing_workflows, cycles.items, scorecard.items])


def _static_requirement(
    key: str,
    title: str,
    passed: bool,
    evidence: str,
    next_action: str,
) -> GrowthAIVisibilityGoalAuditRequirementOut:
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key=key,
        title=title,
        status="completed" if passed else "blocked",
        evidence=evidence if passed else "",
        blocker="" if passed else next_action,
        next_action="" if passed else next_action,
    )


def _source_host_handoff_requirement(
    facts,
) -> GrowthAIVisibilityGoalAuditRequirementOut:
    missing_frame = missing_hosts(facts.framed_checklist_hosts)
    missing_command = missing_hosts(facts.submission_command_hosts)
    passed = not missing_frame and not missing_command
    blocker = (
        "Source-host checklist is missing AIToolNet/AlternativeTo design frame or "
        "submission-confirmation commands."
    )
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key="source_host_handoff",
        title="Directory source-host handoff",
        status="completed" if passed else "blocked",
        evidence=(
            f"{SOURCE_HOST_FRAME} covers {', '.join(REQUIRED_DIRECTORY_HOSTS)}."
            if passed
            else ""
        ),
        blocker="" if passed else blocker,
        next_action=""
        if passed
        else "Regenerate the source-host checklist and design handoff package.",
    )


def _source_host_submission_requirement(
    facts,
) -> GrowthAIVisibilityGoalAuditRequirementOut:
    missing = missing_hosts(facts.submitted_or_live_surfaces)
    passed = not missing
    blocker = (
        "Missing source-host submission confirmation evidence for "
        f"{', '.join(missing)}."
    )
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key="source_host_submission_evidence",
        title="Directory submission evidence",
        status="completed" if passed else "blocked",
        evidence=(
            f"Submitted or live surfaces: {', '.join(facts.submitted_or_live_surfaces)}."
            if passed
            else ""
        ),
        blocker="" if passed else blocker,
        next_action=""
        if passed
        else "Submit AIToolNet/AlternativeTo forms and record confirmation evidence.",
    )


def _source_host_live_requirement(
    facts,
) -> GrowthAIVisibilityGoalAuditRequirementOut:
    missing = missing_hosts(facts.live_surfaces)
    passed = not missing
    blocker = (
        "Directory submission is not enough; live listing evidence is missing for "
        f"{', '.join(missing)}."
    )
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key="source_host_live_evidence",
        title="Directory live listing evidence",
        status="completed" if passed else "blocked",
        evidence=(
            f"Live source-host listings verified: {', '.join(facts.live_surfaces)}."
            if passed
            else ""
        ),
        blocker="" if passed else blocker,
        next_action=""
        if passed
        else "Verify published listings, then rerun unchanged GPT/Claude/Grok/Gemini probes.",
    )


def _feed_readiness_requirement(
    cycles,
    live_readiness: dict[str, Any] | None,
    external_gate: dict[str, Any] | None,
) -> GrowthAIVisibilityGoalAuditRequirementOut:
    ready_cycles = _ready_cycle_keys(cycles)
    passed = _feed_readiness_passed(
        live_readiness=live_readiness,
        external_gate=external_gate,
        ready_cycles=ready_cycles,
    )
    blocker = "Run and pass live feed readiness before external GPT/Claude/Grok/Gemini probes."
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key="feed_readiness",
        title="Live feed readiness",
        status="completed" if passed else "blocked",
        evidence=(
            f"Ready feeds: {', '.join(ready_cycles) or 'live/external gate ready'}"
            if passed
            else ""
        ),
        blocker="" if passed else blocker,
        next_action="" if passed else "Run live readiness and fix feed blockers.",
    )


def _ready_cycle_keys(cycles) -> list[str]:
    return [item.feed_key for item in cycles.items if item.feed_ready]


def _feed_readiness_passed(
    *,
    live_readiness: dict[str, Any] | None,
    external_gate: dict[str, Any] | None,
    ready_cycles: list[str],
) -> bool:
    return any(
        [
            _live_readiness_ready(live_readiness),
            _external_gate_feed_ready(external_gate),
            bool(ready_cycles),
        ]
    )


def _live_readiness_ready(live_readiness: dict[str, Any] | None) -> bool:
    return bool(live_readiness) and live_readiness.get("status") != "blocked"


def _external_gate_feed_ready(external_gate: dict[str, Any] | None) -> bool:
    return bool(external_gate) and external_gate.get("feed_ready") is True


def _external_probe_requirement(weekly) -> GrowthAIVisibilityGoalAuditRequirementOut:
    covered = set(weekly.covered_platforms)
    missing = unique_strings(
        [item for item in AI_VISIBILITY_TARGET_PLATFORMS if item not in covered]
        + _latest_feed_missing_platforms(weekly)
    )
    cited = weekly.total_cited_count
    passed = not missing and cited >= len(AI_VISIBILITY_TARGET_PLATFORMS)
    blocker = (
        "Missing real external GPT/Claude/Grok/Gemini evidence: "
        f"{', '.join(missing) or 'official citations are still insufficient'}."
    )
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key="external_search_evidence",
        title="GPT/Claude/Grok/Gemini search evidence",
        status="completed" if passed else "blocked",
        evidence=(
            f"Covered {', '.join(weekly.covered_platforms)} with "
            f"{weekly.total_cited_count} official citation(s)."
            if passed
            else ""
        ),
        blocker="" if passed else blocker,
        next_action="" if passed else "Run full external probes and record evidence.",
    )


def _latest_feed_missing_platforms(weekly) -> list[str]:
    latest_feed_key = getattr(weekly, "latest_feed_key", "")
    latest_run_group = getattr(weekly, "latest_run_group", "")
    for report in weekly.feed_reports:
        if (
            report.feed_key == latest_feed_key
            and report.latest_run_group == latest_run_group
        ):
            return list(report.missing_platforms)
    return []


def _stable_runs_requirement(weekly) -> GrowthAIVisibilityGoalAuditRequirementOut:
    passed = weekly.goal_achieved
    blocker = (
        f"Stable positive runs {weekly.stable_positive_runs}/"
        f"{weekly.required_stable_runs}; keep optimizing until the weekly gate passes."
    )
    return GrowthAIVisibilityGoalAuditRequirementOut(
        key="stable_positive_runs",
        title="Continuous optimization proof",
        status="completed" if passed else "blocked",
        evidence=(
            f"{weekly.stable_positive_runs}/{weekly.required_stable_runs} stable runs."
            if passed
            else ""
        ),
        blocker="" if passed else blocker,
        next_action=""
        if passed
        else "Repeat feed, probe, compare, and weekly report cycles.",
    )
