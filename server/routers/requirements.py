"""Requirements and workflow orchestration API."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import RequirementRow, get_db
from server.logging_utils import timed_operation
from server.schemas import (
    AcceptanceDispatchRequest,
    AcceptanceDispatchResultOut,
    RequirementCreate,
    RequirementDependencyUpdate,
    RequirementDetailOut,
    RequirementOut,
    RequirementPatch,
    RequirementSourceIntakeRequest,
    RequirementSourceIntakeResultOut,
    RequirementSourceRegistryOut,
    RequirementPublishRequest,
    RequirementRevisionRequest,
    SchedulerPlanOut,
)
from server.services.project_intelligence import build_requirement_serialization_context, serialize_requirement
from server.services.portfolio_scheduler import build_portfolio_schedule, execute_portfolio_rebalance
from server.services.requirement_sources import intake_requirement_sources, list_requirement_source_registry
from server.services.workflow_orchestrator import (
    _normalize_target_project_path,
    advance_requirement_queue,
    build_requirement_detail,
    close_requirement,
    create_requirement,
    delete_requirement,
    dispatch_acceptance_sweep,
    patch_requirement,
    pause_requirement,
    plan_requirement,
    publish_requirement,
    revise_requirement,
    start_requirement,
    update_requirement_dependencies,
)

router = APIRouter(prefix="/api/requirements", tags=["requirements"])
logger = logging.getLogger("ops-dashboard.requirements")

_DEFAULT_STATUS_SORT_RANK = {"in_progress": 0, "deleted": 2}


def _requirement_default_sort_key(row: RequirementRow) -> tuple[int, float, int]:
    rank = _DEFAULT_STATUS_SORT_RANK.get(str(row.status), 1)
    updated = row.updated_at or row.created_at or datetime.min.replace(tzinfo=timezone.utc)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (rank, -(updated - epoch).total_seconds(), -(row.id or 0))


@router.get("", response_model=list[RequirementOut])
def list_requirements(
    status: Optional[str] = Query(None),
    sort: Optional[str] = Query(None, description="Sort mode: 'score' for priority+aging scoring, default is created_at desc"),
    search: Optional[str] = Query(None, description="Search by requirement id, title, description, source ref, or target path"),
    db: Session = Depends(get_db),
):
    with timed_operation(
        logger,
        "requirements_list",
        status_filter=status or "all",
        sort=sort or "default",
        search=search or "",
        slow_ms=1200,
    ) as op:
        query = db.query(RequirementRow)
        if status:
            query = query.filter(RequirementRow.status == status)
        if search:
            raw = search.strip()
            pattern = f"%{raw}%"
            conditions = [
                RequirementRow.title.ilike(pattern),
                RequirementRow.description_markdown.ilike(pattern),
                RequirementRow.source_ref.ilike(pattern),
                RequirementRow.target_project_path.ilike(pattern),
            ]
            if raw.isdigit():
                conditions.append(RequirementRow.id == int(raw))
            query = query.filter(or_(*conditions))
        rows = query.all()
        changed = False
        for row in rows:
            normalized_target = _normalize_target_project_path(row.target_project_path)
            if normalized_target != row.target_project_path:
                row.target_project_path = normalized_target
                changed = True
        score_map, stored_routing, project_catalog, signal_contexts = build_requirement_serialization_context(db, rows)
        if sort == "score":
            rows.sort(
                key=lambda row: (
                    _DEFAULT_STATUS_SORT_RANK.get(str(row.status), 1),
                    -(float(score_map[int(row.id)].get("total") or 0.0)),
                    -(int(row.id or 0)),
                )
            )
        else:
            rows.sort(key=_requirement_default_sort_key)
        if changed:
            db.commit()
        op["count"] = len(rows)
        return [
            RequirementOut(
                **serialize_requirement(
                    db,
                    row,
                    score=score_map.get(int(row.id)),
                    stored_routing=stored_routing.get(int(row.id)),
                    project_catalog=project_catalog,
                    signal_contexts=signal_contexts,
                )
            )
            for row in rows
        ]


@router.post("", response_model=RequirementDetailOut, status_code=201)
def create_requirement_endpoint(body: RequirementCreate, db: Session = Depends(get_db)):
    if body.priority not in {"low", "normal", "high"}:
        raise HTTPException(status_code=400, detail="priority must be low|normal|high")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required")
    if not body.description_markdown.strip():
        raise HTTPException(status_code=400, detail="description_markdown is required")
    return create_requirement(db, body)


@router.get("/scheduler", response_model=SchedulerPlanOut)
def get_requirement_scheduler(db: Session = Depends(get_db)):
    return build_portfolio_schedule(db)


@router.post("/scheduler/rebalance", response_model=SchedulerPlanOut)
def rebalance_requirement_scheduler(db: Session = Depends(get_db)):
    return execute_portfolio_rebalance(db)


@router.get("/sources", response_model=RequirementSourceRegistryOut)
def get_requirement_source_registry(db: Session = Depends(get_db)):
    return RequirementSourceRegistryOut(**list_requirement_source_registry(db))


@router.post("/intake", response_model=RequirementSourceIntakeResultOut)
def intake_requirements_endpoint(body: RequirementSourceIntakeRequest, db: Session = Depends(get_db)):
    try:
        return RequirementSourceIntakeResultOut(
            **intake_requirement_sources(
                db,
                source_key=body.source_key,
                refresh=body.refresh,
                auto_start=body.auto_start,
                min_score=body.min_score,
                max_created=body.max_created,
                bundle_item_keys=body.bundle_item_keys,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{requirement_id}", response_model=RequirementDetailOut)
def get_requirement(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return build_requirement_detail(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{requirement_id}", response_model=RequirementDetailOut)
def patch_requirement_endpoint(requirement_id: int, body: RequirementPatch, db: Session = Depends(get_db)):
    try:
        return patch_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/close", response_model=RequirementDetailOut)
def close_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return close_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{requirement_id}", response_model=RequirementDetailOut)
def delete_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return delete_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/plan", response_model=RequirementDetailOut)
def plan_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return plan_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/start", response_model=RequirementDetailOut)
def start_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return start_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/pause", response_model=RequirementDetailOut)
def pause_requirement_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return pause_requirement(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/publish", response_model=RequirementDetailOut)
def publish_requirement_endpoint(
    requirement_id: int,
    body: RequirementPublishRequest,
    db: Session = Depends(get_db),
):
    try:
        return publish_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/queue/advance")
def queue_advance_endpoint(db: Session = Depends(get_db)):
    """Advance the requirement queue: start the next ready requirement if nothing is in_progress."""
    return advance_requirement_queue(db)


@router.post("/acceptance/dispatch", response_model=AcceptanceDispatchResultOut)
def dispatch_acceptance_endpoint(body: AcceptanceDispatchRequest, db: Session = Depends(get_db)):
    return dispatch_acceptance_sweep(db, limit=body.limit, auto_dispatch=body.auto_dispatch)


@router.put("/{requirement_id}/dependencies", response_model=RequirementDetailOut)
def update_requirement_dependencies_endpoint(
    requirement_id: int,
    body: RequirementDependencyUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_requirement_dependencies(db, requirement_id, body.depends_on_requirement_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/revise", response_model=RequirementDetailOut)
def revise_requirement_endpoint(
    requirement_id: int,
    body: RequirementRevisionRequest,
    db: Session = Depends(get_db),
):
    if not body.description_markdown.strip():
        raise HTTPException(status_code=400, detail="description_markdown is required")
    if body.title is not None and not body.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be blank")
    try:
        return revise_requirement(db, requirement_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
