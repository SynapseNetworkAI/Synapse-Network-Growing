"""Schedule Center API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from server.database import get_db
from server.logging_utils import timed_operation
from server.schemas import (
    RecurringWorkflowOut,
    RecurringWorkflowRunOut,
    RecurringWorkflowRunRequest,
    RecurringWorkflowRunResultOut,
)
from server.schemas_schedules import (
    ScheduleCreateRequest,
    ScheduleDeleteResultOut,
    ScheduleTemplateOut,
    ScheduleUpdateRequest,
)
from server.services.scheduling.schedules import (
    create_schedule,
    delete_schedule,
    get_schedule,
    list_schedule_runs,
    list_schedule_templates,
    list_schedules,
    run_schedule,
    update_schedule,
)

router = APIRouter(prefix="/api/schedules", tags=["schedules"])
logger = logging.getLogger("ops-dashboard.schedules_api")


@router.get("", response_model=list[RecurringWorkflowOut])
def list_schedules_endpoint(db: Session = Depends(get_db)):
    with timed_operation(logger, "schedules_list", slow_ms=1000):
        return [RecurringWorkflowOut(**item) for item in list_schedules(db)]


@router.get("/templates", response_model=list[ScheduleTemplateOut])
def list_schedule_templates_endpoint():
    return [ScheduleTemplateOut(**item) for item in list_schedule_templates()]


@router.post("", response_model=RecurringWorkflowOut)
def create_schedule_endpoint(
    body: ScheduleCreateRequest, db: Session = Depends(get_db)
):
    try:
        return RecurringWorkflowOut(
            **create_schedule(db, payload=body.model_dump(exclude_none=True))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{schedule_key}", response_model=RecurringWorkflowOut)
def get_schedule_endpoint(schedule_key: str, db: Session = Depends(get_db)):
    try:
        return RecurringWorkflowOut(**get_schedule(db, schedule_key))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{schedule_key}", response_model=RecurringWorkflowOut)
def update_schedule_endpoint(
    schedule_key: str, body: ScheduleUpdateRequest, db: Session = Depends(get_db)
):
    try:
        return RecurringWorkflowOut(
            **update_schedule(
                db, schedule_key, payload=body.model_dump(exclude_unset=True)
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{schedule_key}", response_model=ScheduleDeleteResultOut)
def delete_schedule_endpoint(schedule_key: str, db: Session = Depends(get_db)):
    try:
        return ScheduleDeleteResultOut(**delete_schedule(db, schedule_key))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{schedule_key}/runs", response_model=list[RecurringWorkflowRunOut])
def list_schedule_runs_endpoint(
    schedule_key: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        return [
            RecurringWorkflowRunOut(**item)
            for item in list_schedule_runs(db, schedule_key, limit=limit)
        ]
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{schedule_key}/run", response_model=RecurringWorkflowRunResultOut)
def run_schedule_endpoint(
    schedule_key: str, body: RecurringWorkflowRunRequest, db: Session = Depends(get_db)
):
    try:
        return RecurringWorkflowRunResultOut(
            **run_schedule(
                db,
                schedule_key=schedule_key,
                dry_run=body.dry_run,
                triggered_by="operator",
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
