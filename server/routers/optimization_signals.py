"""Optimization signals API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import (
    OptimizationSignalAutoIntakeRequest,
    OptimizationSignalAutoIntakeResultOut,
    OptimizationSignalCreateRequirementRequest,
    OptimizationSignalOut,
    RequirementDetailOut,
)
from server.services.optimization_signals import (
    _project_map,
    auto_intake_optimization_signals,
    create_requirement_from_signal,
    dismiss_optimization_signal,
    list_optimization_signals,
    optimization_signal_to_dict,
    refresh_optimization_signals,
)


router = APIRouter(prefix="/api/optimization-signals", tags=["optimization-signals"])


@router.get("", response_model=list[OptimizationSignalOut])
def list_optimization_signals_endpoint(
    status: Optional[str] = Query(None),
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    rows = refresh_optimization_signals(db) if refresh else list_optimization_signals(db, status=status)
    if status:
        rows = [row for row in rows if row.status == status]
    project_map = _project_map(db)
    return [OptimizationSignalOut(**optimization_signal_to_dict(row, project_map=project_map)) for row in rows]


@router.post("/refresh", response_model=list[OptimizationSignalOut])
def refresh_optimization_signals_endpoint(db: Session = Depends(get_db)):
    project_map = _project_map(db)
    return [OptimizationSignalOut(**optimization_signal_to_dict(row, project_map=project_map)) for row in refresh_optimization_signals(db)]


@router.post("/auto-intake", response_model=OptimizationSignalAutoIntakeResultOut)
def auto_intake_optimization_signals_endpoint(
    body: OptimizationSignalAutoIntakeRequest,
    db: Session = Depends(get_db),
):
    return OptimizationSignalAutoIntakeResultOut(**auto_intake_optimization_signals(
        db,
        min_score=body.min_score,
        max_created=body.max_created,
        auto_start=body.auto_start,
    ))


@router.post("/{signal_id}/dismiss", response_model=OptimizationSignalOut)
def dismiss_optimization_signal_endpoint(signal_id: int, db: Session = Depends(get_db)):
    try:
        row = dismiss_optimization_signal(db, signal_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OptimizationSignalOut(**optimization_signal_to_dict(row, project_map=_project_map(db)))


@router.post("/{signal_id}/create-requirement", response_model=RequirementDetailOut)
def create_requirement_from_signal_endpoint(
    signal_id: int,
    body: OptimizationSignalCreateRequirementRequest,
    db: Session = Depends(get_db),
):
    try:
        _row, detail = create_requirement_from_signal(
            db,
            signal_id=signal_id,
            title=body.title,
            auto_start=body.auto_start,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return detail
