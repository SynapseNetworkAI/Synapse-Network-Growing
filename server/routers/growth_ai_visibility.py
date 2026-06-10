"""AI visibility growth API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas_growth import (
    GrowthAIVisibilityCheckCreate,
    GrowthAIVisibilityCheckListOut,
    GrowthAIVisibilityCheckOut,
    GrowthAIVisibilityComparisonListOut,
    GrowthAIVisibilityDesignHandoffOut,
    GrowthAIVisibilityDocsBlueprintOut,
    GrowthAIVisibilityExternalProbeGateOut,
    GrowthAIVisibilityFeedCycleListOut,
    GrowthAIVisibilityFeedPackageListOut,
    GrowthAIVisibilityFeedScorecardOut,
    GrowthAIVisibilityGoalAuditOut,
    GrowthAIVisibilityHandoffBundleOut,
    GrowthAIVisibilityLiveReadinessOut,
    GrowthAIVisibilityNextCycleOut,
    GrowthAIVisibilityOptimizationBriefOut,
    GrowthAIVisibilityOfficialSourceListOut,
    GrowthAIVisibilityOptimizationPlanOut,
    GrowthAIVisibilityPresencePlanOut,
    GrowthAIVisibilityProbeMatrixOut,
    GrowthAIVisibilityReleaseSnapshotOut,
    GrowthAIVisibilityReleaseUnblockPlanOut,
    GrowthAIVisibilitySourceHostExecutionChecklistOut,
    GrowthAIVisibilitySourceHostFeedPackageOut,
    GrowthAIVisibilitySourceHostLiveSpotCheckOut,
    GrowthAIVisibilityWeeklyReportOut,
)
from server.services.growth import (
    ai_visibility_brief,
    ai_visibility_cycles,
    ai_visibility_design_handoff,
    ai_visibility_docs_blueprint,
    ai_visibility_external_probe_gate,
    ai_visibility_goal_audit,
    ai_visibility_handoff_bundle,
    ai_visibility_live_readiness,
    ai_visibility_official_sources,
    ai_visibility_plan,
    ai_visibility_presence_plan,
    ai_visibility_probe_matrix,
    ai_visibility_release_snapshot,
    ai_visibility_release_unblock,
    ai_visibility_scorecard,
    ai_visibility_source_host_feed,
    ai_visibility_source_host_live_spot_check,
    ai_visibility_discovery,
)

router = APIRouter(prefix="/api/growth", tags=["growth"])


@router.get(
    "/ai-visibility/optimization-plan",
    response_model=GrowthAIVisibilityOptimizationPlanOut,
)
def get_ai_visibility_optimization_plan():
    return ai_visibility_plan.ai_visibility_optimization_plan()


@router.get(
    "/ai-visibility/feed-package",
    response_model=GrowthAIVisibilityFeedPackageListOut,
)
def get_ai_visibility_feed_package(feed_key: str | None = None):
    return ai_visibility_plan.ai_visibility_feed_packages(feed_key=feed_key)


@router.get(
    "/ai-visibility/docs-blueprint",
    response_model=GrowthAIVisibilityDocsBlueprintOut,
)
def get_ai_visibility_docs_blueprint():
    return ai_visibility_docs_blueprint.ai_agent_payments_docs_blueprint()


@router.get(
    "/ai-visibility/design-handoff",
    response_model=GrowthAIVisibilityDesignHandoffOut,
)
def get_ai_visibility_design_handoff():
    return ai_visibility_design_handoff.ai_agent_payments_design_handoff()


@router.get(
    "/ai-visibility/weekly-report",
    response_model=GrowthAIVisibilityWeeklyReportOut,
)
def get_ai_visibility_weekly_report(db: Session = Depends(get_db)):
    return ai_visibility_discovery.ai_visibility_weekly_report(db)


@router.get(
    "/ai-visibility/next-cycle",
    response_model=GrowthAIVisibilityNextCycleOut,
)
def get_ai_visibility_next_cycle(db: Session = Depends(get_db)):
    return ai_visibility_discovery.ai_visibility_next_cycle(db)


@router.get(
    "/ai-visibility/goal-audit",
    response_model=GrowthAIVisibilityGoalAuditOut,
)
def get_ai_visibility_goal_audit(db: Session = Depends(get_db)):
    return ai_visibility_goal_audit.ai_visibility_goal_audit(db)


@router.get(
    "/ai-visibility/release-unblock-plan",
    response_model=GrowthAIVisibilityReleaseUnblockPlanOut,
)
def get_ai_visibility_release_unblock_plan(
    target_commit: str | None = None,
    actor: str = ai_visibility_release_unblock.DEFAULT_ACTOR,
):
    return ai_visibility_release_unblock.build_release_unblock_plan(
        target_commit=target_commit
        or ai_visibility_release_unblock.DEFAULT_TARGET_COMMIT,
        actor=actor,
    )


@router.get(
    "/ai-visibility/release-snapshot",
    response_model=GrowthAIVisibilityReleaseSnapshotOut,
)
def get_ai_visibility_release_snapshot(
    target_commit: str | None = None,
    actor: str = ai_visibility_release_unblock.DEFAULT_ACTOR,
    feed_key: str = "mcp_paid_api_discovery",
    run_group: str | None = None,
):
    return ai_visibility_release_snapshot.build_snapshot(
        target_commit=target_commit
        or ai_visibility_release_unblock.DEFAULT_TARGET_COMMIT,
        actor=actor,
        feed_key=feed_key,
        run_group=run_group or "",
    )


@router.get(
    "/ai-visibility/handoff-bundle",
    response_model=GrowthAIVisibilityHandoffBundleOut,
)
def get_ai_visibility_handoff_bundle(
    feed_key: str = ai_visibility_handoff_bundle.DEFAULT_FEED_KEY,
    run_group: str | None = None,
    target_commit: str | None = None,
    actor: str = ai_visibility_release_unblock.DEFAULT_ACTOR,
    db: Session = Depends(get_db),
):
    payloads = ai_visibility_handoff_bundle.build_handoff_payloads(
        feed_key=feed_key,
        run_group=run_group or "",
        target_commit=target_commit
        or ai_visibility_release_unblock.DEFAULT_TARGET_COMMIT,
        actor=actor,
        output_dir=None,
        db=db,
    )
    return payloads["manifest"]


@router.get(
    "/ai-visibility/feed-cycles",
    response_model=GrowthAIVisibilityFeedCycleListOut,
)
def get_ai_visibility_feed_cycles(db: Session = Depends(get_db)):
    return ai_visibility_cycles.ai_visibility_feed_cycles(db)


@router.get(
    "/ai-visibility/feed-scorecard",
    response_model=GrowthAIVisibilityFeedScorecardOut,
)
def get_ai_visibility_feed_scorecard(db: Session = Depends(get_db)):
    return ai_visibility_scorecard.ai_visibility_feed_scorecard(db)


@router.get(
    "/ai-visibility/live-readiness",
    response_model=GrowthAIVisibilityLiveReadinessOut,
)
def get_ai_visibility_live_readiness(
    feed_key: list[str] | None = Query(default=None),
    run_group: str | None = None,
):
    try:
        return ai_visibility_live_readiness.ai_visibility_live_readiness(
            feed_keys=feed_key,
            run_group=run_group,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/ai-visibility/external-probe-gate",
    response_model=GrowthAIVisibilityExternalProbeGateOut,
)
def get_ai_visibility_external_probe_gate(
    feed_key: str = ai_visibility_external_probe_gate.DEFAULT_FEED_KEY,
    run_group: str | None = None,
):
    try:
        return ai_visibility_external_probe_gate.ai_visibility_external_probe_gate(
            feed_key=feed_key,
            run_group=run_group,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/ai-visibility/official-sources",
    response_model=GrowthAIVisibilityOfficialSourceListOut,
)
def get_ai_visibility_official_sources():
    return ai_visibility_official_sources.ai_visibility_official_sources()


@router.get(
    "/ai-visibility/probe-matrix",
    response_model=GrowthAIVisibilityProbeMatrixOut,
)
def get_ai_visibility_probe_matrix(db: Session = Depends(get_db)):
    return ai_visibility_probe_matrix.ai_visibility_probe_matrix(db)


@router.get(
    "/ai-visibility/presence-plan",
    response_model=GrowthAIVisibilityPresencePlanOut,
)
def get_ai_visibility_presence_plan(
    feed_key: str = ai_visibility_presence_plan.DEFAULT_FEED_KEY,
    run_group: str | None = None,
    db: Session = Depends(get_db),
):
    return ai_visibility_presence_plan.ai_visibility_presence_plan(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )


@router.get(
    "/ai-visibility/source-host-feed-package",
    response_model=GrowthAIVisibilitySourceHostFeedPackageOut,
)
def get_ai_visibility_source_host_feed_package(
    feed_key: str = ai_visibility_presence_plan.DEFAULT_FEED_KEY,
    run_group: str | None = None,
    db: Session = Depends(get_db),
):
    return ai_visibility_source_host_feed.ai_visibility_source_host_feed_package(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )


@router.get(
    "/ai-visibility/source-host-execution-checklist",
    response_model=GrowthAIVisibilitySourceHostExecutionChecklistOut,
)
def get_ai_visibility_source_host_execution_checklist(
    feed_key: str = ai_visibility_presence_plan.DEFAULT_FEED_KEY,
    run_group: str | None = None,
    db: Session = Depends(get_db),
):
    return ai_visibility_source_host_feed.ai_visibility_source_host_execution_checklist(
        db,
        feed_key=feed_key,
        run_group=run_group,
    )


@router.get(
    "/ai-visibility/source-host-live-spot-check",
    response_model=GrowthAIVisibilitySourceHostLiveSpotCheckOut,
)
def get_ai_visibility_source_host_live_spot_check(
    feed_key: str = ai_visibility_presence_plan.DEFAULT_FEED_KEY,
    run_group: str | None = None,
    execute: bool = False,
    db: Session = Depends(get_db),
):
    return ai_visibility_source_host_live_spot_check.ai_visibility_source_host_live_spot_check(
        db,
        feed_key=feed_key,
        run_group=run_group,
        execute=execute,
    )


@router.get(
    "/ai-visibility/optimization-brief",
    response_model=GrowthAIVisibilityOptimizationBriefOut,
)
def get_ai_visibility_optimization_brief(
    run_group: str | None = None,
    db: Session = Depends(get_db),
):
    return ai_visibility_brief.ai_visibility_optimization_brief(
        db,
        run_group=run_group,
    )


@router.get(
    "/ai-visibility/comparisons",
    response_model=GrowthAIVisibilityComparisonListOut,
)
def list_ai_visibility_comparisons(
    feed_key: str | None = None,
    run_group: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    return ai_visibility_discovery.list_ai_comparisons(
        db, feed_key=feed_key, run_group=run_group, limit=limit
    )


@router.get("/ai-visibility/checks", response_model=GrowthAIVisibilityCheckListOut)
def list_ai_visibility_checks(
    q: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return ai_visibility_discovery.list_ai_checks(
        db, q=q, platform=platform, limit=limit, offset=offset
    )


@router.post(
    "/ai-visibility/checks",
    response_model=GrowthAIVisibilityCheckOut,
    status_code=201,
)
def create_ai_visibility_check(
    body: GrowthAIVisibilityCheckCreate, db: Session = Depends(get_db)
):
    try:
        return ai_visibility_discovery.create_ai_check(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
