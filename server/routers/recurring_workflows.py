"""Recurring COO workflow registry API."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from server.database import get_db
from server.logging_utils import timed_operation
from server.schemas import (
    RecurringWorkflowHealthOut,
    RecurringWorkflowOut,
    RecurringWorkflowRunOut,
    RecurringWorkflowRunRequest,
    RecurringWorkflowRunResultOut,
)
from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    list_recurring_workflow_runs,
    recurring_workflow_to_dict,
    recurring_workflow_health,
    recurring_workflow_run_to_dict,
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


@router.get("/health", response_model=RecurringWorkflowHealthOut)
def recurring_workflow_health_endpoint(request: Request, db: Session = Depends(get_db)):
    bug_scheduler = getattr(request.app.state, "bug_log_scheduler", None)
    goal_planner_scheduler = getattr(request.app.state, "goal_planner_scheduler", None)
    ci_status_scheduler = getattr(request.app.state, "ci_status_scheduler", None)
    release_pr_status_scheduler = getattr(
        request.app.state, "release_pr_status_scheduler", None
    )
    release_deployment_status_scheduler = getattr(
        request.app.state, "release_deployment_status_scheduler", None
    )
    x_social_scheduler = getattr(request.app.state, "x_social_scheduler", None)
    cost_control_scheduler = getattr(request.app.state, "cost_control_scheduler", None)
    notification_dispatcher = getattr(
        request.app.state, "notification_dispatcher", None
    )
    return RecurringWorkflowHealthOut(
        **recurring_workflow_health(
            db,
            bug_scheduler_status=bug_scheduler.status_snapshot()
            if bug_scheduler is not None
            else None,
            goal_planner_scheduler_status=goal_planner_scheduler.status_snapshot()
            if goal_planner_scheduler is not None
            else None,
            ci_status_scheduler_status=ci_status_scheduler.status_snapshot()
            if ci_status_scheduler is not None
            else None,
            release_pr_status_scheduler_status=release_pr_status_scheduler.status_snapshot()
            if release_pr_status_scheduler is not None
            else None,
            release_deployment_status_scheduler_status=(
                release_deployment_status_scheduler.status_snapshot()
                if release_deployment_status_scheduler is not None
                else None
            ),
            x_social_scheduler_status=x_social_scheduler.status_snapshot()
            if x_social_scheduler is not None
            else None,
            cost_control_scheduler_status=cost_control_scheduler.status_snapshot()
            if cost_control_scheduler is not None
            else None,
            notification_dispatcher_status=notification_dispatcher.status_snapshot(db)
            if notification_dispatcher is not None
            else None,
        )
    )


@router.get("/{workflow_key}", response_model=RecurringWorkflowOut)
def get_recurring_workflow_endpoint(workflow_key: str, db: Session = Depends(get_db)):
    try:
        with timed_operation(
            logger, "recurring_workflows_get", workflow_key=workflow_key, slow_ms=1000
        ):
            row = get_recurring_workflow(db, workflow_key)
            return RecurringWorkflowOut(**recurring_workflow_to_dict(row))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{workflow_key}/runs", response_model=list[RecurringWorkflowRunOut])
def list_recurring_workflow_runs_endpoint(
    workflow_key: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        rows = list_recurring_workflow_runs(db, workflow_key, limit=limit)
        return [
            RecurringWorkflowRunOut(**recurring_workflow_run_to_dict(row))
            for row in rows
        ]
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
        with timed_operation(
            logger, "recurring_workflows_run", workflow_key=workflow_key, slow_ms=1200
        ):
            sync_recurring_workflows(db)
            return RecurringWorkflowRunResultOut(
                **run_recurring_workflow(
                    db,
                    workflow_key=workflow_key,
                    dry_run=body.dry_run,
                    triggered_by="operator",
                    auto_start=body.auto_start,
                    intake_min_score=body.intake_min_score,
                    intake_max_created=body.intake_max_created,
                    acceptance_limit=body.acceptance_limit,
                    auto_dispatch_acceptance=body.auto_dispatch_acceptance,
                )
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=400
            if "not active" in str(exc).lower() or "unsupported" in str(exc).lower()
            else 404,
            detail=str(exc),
        ) from exc
