"""Recurring COO workflow registry API."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.logging_utils import timed_operation
from server.schemas import RecurringWorkflowOut, RecurringWorkflowRunRequest, RecurringWorkflowRunResultOut
from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    recurring_workflow_to_dict,
    run_recurring_workflow,
    sync_recurring_workflows,
)

router = APIRouter(prefix="/api/recurring-workflows", tags=["recurring-workflows"])
logger = logging.getLogger("ops-dashboard.recurring_workflows_api")


@router.get("", response_model=list[RecurringWorkflowOut])
def list_recurring_workflows_endpoint(db: Session = Depends(get_db)):
    with timed_operation(logger, "recurring_workflows_list", slow_ms=1000):
        rows = sync_recurring_workflows(db)
        return [RecurringWorkflowOut(**recurring_workflow_to_dict(row)) for row in rows]


@router.get("/{workflow_key}", response_model=RecurringWorkflowOut)
def get_recurring_workflow_endpoint(workflow_key: str, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "recurring_workflows_get", workflow_key=workflow_key, slow_ms=1000):
            row = get_recurring_workflow(db, workflow_key)
            return RecurringWorkflowOut(**recurring_workflow_to_dict(row))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sync", response_model=list[RecurringWorkflowOut])
def sync_recurring_workflows_endpoint(db: Session = Depends(get_db)):
    with timed_operation(logger, "recurring_workflows_sync", slow_ms=1000):
        rows = sync_recurring_workflows(db)
        return [RecurringWorkflowOut(**recurring_workflow_to_dict(row)) for row in rows]


@router.post("/{workflow_key}/run", response_model=RecurringWorkflowRunResultOut)
def run_recurring_workflow_endpoint(
    workflow_key: str,
    body: RecurringWorkflowRunRequest,
    db: Session = Depends(get_db),
):
    try:
        with timed_operation(logger, "recurring_workflows_run", workflow_key=workflow_key, slow_ms=1200):
            return RecurringWorkflowRunResultOut(
                **run_recurring_workflow(
                    db,
                    workflow_key=workflow_key,
                    dry_run=body.dry_run,
                    auto_start=body.auto_start,
                    intake_min_score=body.intake_min_score,
                    intake_max_created=body.intake_max_created,
                    acceptance_limit=body.acceptance_limit,
                    auto_dispatch_acceptance=body.auto_dispatch_acceptance,
                )
            )
    except ValueError as exc:
        raise HTTPException(status_code=400 if "not active" in str(exc).lower() or "unsupported" in str(exc).lower() else 404, detail=str(exc)) from exc
