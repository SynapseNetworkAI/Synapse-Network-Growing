from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import (
    CandidateDecisionRequest,
    CandidateApproveRunResultOut,
    CandidateMaterializeResultOut,
    PlannerSweepOut,
    PlannerSweepRunRequest,
    PlanningArchiveCycleRequest,
    PlanningDropGoalRequest,
    PlanningDropGoalResultOut,
    PlanningGoalRollupOut,
    PlanningMissionControlOut,
    PlanningGoalStatusRequest,
    PlanningManifestHistoryOut,
    PlanningManifestOut,
    PlanningManifestSaveRequest,
    RequirementCandidateOut,
    RequirementCandidatePageOut,
)
from server.services.planning.lifecycle import (
    approve_candidate,
    approve_and_run_candidate,
    archive_and_start_new_cycle,
    candidate_to_dict,
    drop_goal,
    ensure_active_manifest,
    goal_rollup,
    list_candidates,
    list_manifest_history,
    manifest_to_dict,
    materialize_candidate,
    mission_control_snapshot,
    reject_candidate,
    run_planner_sweep,
    save_active_manifest,
    sweep_to_dict,
)


router = APIRouter(prefix="/api/planning", tags=["planning"])


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/mission-control", response_model=PlanningMissionControlOut)
def get_mission_control(db: Session = Depends(get_db)):
    return mission_control_snapshot(db)


@router.get("/manifest/active", response_model=PlanningManifestOut)
def get_active_manifest(db: Session = Depends(get_db)):
    return manifest_to_dict(ensure_active_manifest(db))


@router.put("/manifest/active", response_model=PlanningManifestOut)
def put_active_manifest(body: PlanningManifestSaveRequest, db: Session = Depends(get_db)):
    try:
        row = save_active_manifest(
            db,
            payload=dict(body.payload),
            version_name=body.version_name,
            cycle_label=body.cycle_label,
            operator=body.operator,
        )
        return manifest_to_dict(row)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/manifests/history", response_model=PlanningManifestHistoryOut)
def get_manifest_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
):
    return list_manifest_history(db, page=page, page_size=page_size, status=status, search=search)


@router.post("/manifest/{manifest_id}/archive-and-start-cycle", response_model=PlanningManifestOut)
def post_archive_and_start_cycle(
    manifest_id: int,
    body: PlanningArchiveCycleRequest,
    db: Session = Depends(get_db),
):
    active = ensure_active_manifest(db)
    if int(active.id) != int(manifest_id):
        raise HTTPException(status_code=409, detail="only the active manifest can start a new cycle")
    try:
        row = archive_and_start_new_cycle(
            db,
            version_name=body.version_name,
            cycle_label=body.cycle_label,
            operator=body.operator,
            payload_patch=dict(body.payload_patch or {}),
        )
        return manifest_to_dict(row)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/manifest/{manifest_id}/goals/{goal_key}/drop", response_model=PlanningDropGoalResultOut)
def post_drop_goal(
    manifest_id: int,
    goal_key: str,
    body: PlanningDropGoalRequest,
    db: Session = Depends(get_db),
):
    try:
        return drop_goal(
            db,
            manifest_id=manifest_id,
            goal_key=goal_key,
            reason=body.reason,
            operator=body.operator,
            halt_mode=body.halt_mode,
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/manifest/{manifest_id}/goals/{goal_key}/status", response_model=PlanningDropGoalResultOut)
def post_goal_status(
    manifest_id: int,
    goal_key: str,
    body: PlanningGoalStatusRequest,
    db: Session = Depends(get_db),
):
    if body.status != "dropped":
        raise HTTPException(status_code=400, detail="v1.2 only supports dropped lifecycle transition through this endpoint")
    try:
        return drop_goal(
            db,
            manifest_id=manifest_id,
            goal_key=goal_key,
            reason=body.reason,
            operator=body.operator,
            halt_mode="safe_halt",
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/manifest/{manifest_id}/goals/{goal_key}/rollup", response_model=PlanningGoalRollupOut)
def get_goal_rollup(manifest_id: int, goal_key: str, db: Session = Depends(get_db)):
    try:
        return goal_rollup(db, manifest_id, goal_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sweeps/run", response_model=PlannerSweepOut)
def post_run_planner_sweep(body: PlannerSweepRunRequest, db: Session = Depends(get_db)):
    try:
        return sweep_to_dict(run_planner_sweep(db, dry_run=body.dry_run, triggered_by=body.triggered_by))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.get("/candidates", response_model=RequirementCandidatePageOut)
def get_candidates(
    manifest_id: int | None = None,
    status: str | None = None,
    goal_key: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return list_candidates(db, manifest_id=manifest_id, status=status, goal_key=goal_key, page=page, page_size=page_size)


@router.post("/candidates/{candidate_id}/approve", response_model=RequirementCandidateOut)
def post_approve_candidate(
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    try:
        return candidate_to_dict(approve_candidate(db, candidate_id, operator=body.operator))
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/candidates/{candidate_id}/approve-and-run", response_model=CandidateApproveRunResultOut)
def post_approve_and_run_candidate(
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    try:
        return approve_and_run_candidate(db, candidate_id, operator=body.operator)
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/candidates/{candidate_id}/reject", response_model=RequirementCandidateOut)
def post_reject_candidate(
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    try:
        return candidate_to_dict(
            reject_candidate(
                db,
                candidate_id,
                reason=body.reason,
                operator=body.operator,
                comment=body.comment,
            )
        )
    except ValueError as exc:
        raise _bad_request(exc) from exc


@router.post("/candidates/{candidate_id}/materialize", response_model=CandidateMaterializeResultOut)
def post_materialize_candidate(
    candidate_id: int,
    body: CandidateDecisionRequest,
    db: Session = Depends(get_db),
):
    try:
        return materialize_candidate(db, candidate_id, operator=body.operator)
    except ValueError as exc:
        raise _bad_request(exc) from exc
