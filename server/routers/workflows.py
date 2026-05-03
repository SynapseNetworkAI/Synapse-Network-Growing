"""Declarative workflow factory API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.database import RequirementRow, get_db
from server.services.workflows.declarative import (
    WorkflowRuntimeError,
    WorkflowSpecError,
    archive_workflow_run,
    create_workflow_followup_requirement,
    create_declarative_workflow_run,
    decide_human_gate,
    list_workflow_definitions,
    list_workflow_runs,
    request_workflow_business_followup,
    set_workflow_business_outcome,
    supersede_workflow_and_retry_planner,
    workflow_runs_summary,
    workflow_definition_detail,
    workflow_run_detail,
)
from server.services.runtime.workspace_recovery import (
    mark_workflow_workspace_killed,
    recover_workspace_before_retry,
    workspace_recovery_summary_for_workflow,
)


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowRunCreateRequest(BaseModel):
    """Request body for creating a declarative workflow run."""

    requirement_id: int
    workflow_key: str
    triggered_by: str = "operator"
    initial_blackboard: dict[str, Any] = Field(default_factory=dict)
    run_immediately: bool = True


class HumanGateDecisionRequest(BaseModel):
    """Operator decision for a pending human gate."""

    decision: str
    reviewer: str = "operator"
    comment: str = ""


class WorkflowRunArchiveRequest(BaseModel):
    archived_by: str = "operator"
    reason: str = ""


class WorkflowRunFollowupRequest(BaseModel):
    title: str | None = None
    description_markdown: str | None = None
    operator: str = "operator"


class BusinessOutcomeRequest(BaseModel):
    operator: str = "operator"
    note: str = ""
    title: str | None = None
    description_markdown: str | None = None


class WorkflowSupersedeRetryRequest(BaseModel):
    operator: str = "operator"
    comment: str = ""


class WorkflowRuntimeKillRequest(BaseModel):
    kill_signal: str = "SIGKILL"


def _detail_with_workspace_recovery(db: Session, workflow_run_id: int):
    detail = workflow_run_detail(db, workflow_run_id)
    detail["workspace_recovery"] = workspace_recovery_summary_for_workflow(db, workflow_run_id).model_dump()
    return detail


@router.get("/definitions")
def list_workflow_definitions_endpoint(db: Session = Depends(get_db)):
    return list_workflow_definitions(db)


@router.get("/definitions/{workflow_key}")
def get_workflow_definition_endpoint(workflow_key: str, db: Session = Depends(get_db)):
    try:
        return workflow_definition_detail(db, workflow_key)
    except WorkflowRuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs")
def list_workflow_runs_endpoint(
    limit: int = 100,
    page: int | None = None,
    page_size: int | None = None,
    tab: str | None = None,
    include_archived: bool = False,
    status: str | None = None,
    workflow_key: str | None = None,
    goal_key: str | None = None,
    current_state: str | None = None,
    risk_level: str | None = None,
    pending_human_gate: bool | None = None,
    requirement_id: int | None = None,
    db: Session = Depends(get_db),
):
    return list_workflow_runs(
        db,
        limit=limit,
        page=page or 1,
        page_size=page_size,
        tab=tab,
        status=status,
        workflow_key=workflow_key,
        goal_key=goal_key,
        current_state=current_state,
        risk_level=risk_level,
        pending_human_gate=pending_human_gate,
        requirement_id=requirement_id,
        include_archived=include_archived,
    )


@router.get("/runs/summary")
def workflow_runs_summary_endpoint(db: Session = Depends(get_db)):
    return workflow_runs_summary(db)


@router.post("/runs", status_code=201)
def create_workflow_run_endpoint(body: WorkflowRunCreateRequest, db: Session = Depends(get_db)):
    requirement = db.query(RequirementRow).filter(RequirementRow.id == int(body.requirement_id)).first()
    if requirement is None:
        raise HTTPException(status_code=404, detail=f"requirement not found: {body.requirement_id}")
    try:
        run = create_declarative_workflow_run(
            db,
            requirement=requirement,
            workflow_key=body.workflow_key,
            triggered_by=body.triggered_by,
            initial_blackboard=body.initial_blackboard,
            run_immediately=body.run_immediately,
        )
        db.commit()
        return _detail_with_workspace_recovery(db, int(run.id))
    except (WorkflowRuntimeError, WorkflowSpecError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/archive")
def archive_workflow_run_endpoint(
    workflow_run_id: int,
    body: WorkflowRunArchiveRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = archive_workflow_run(db, workflow_run_id, archived_by=body.archived_by, reason=body.reason)
        db.commit()
        return payload
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/create-followup", status_code=201)
def create_workflow_followup_endpoint(
    workflow_run_id: int,
    body: WorkflowRunFollowupRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = create_workflow_followup_requirement(
            db,
            workflow_run_id,
            title=body.title,
            description_markdown=body.description_markdown,
            operator=body.operator,
        )
        db.commit()
        return payload
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/supersede-and-retry-planner")
def supersede_and_retry_planner_endpoint(
    workflow_run_id: int,
    body: WorkflowSupersedeRetryRequest | None = None,
    db: Session = Depends(get_db),
):
    try:
        payload = supersede_workflow_and_retry_planner(
            db,
            workflow_run_id=workflow_run_id,
            operator=(body.operator if body is not None else "operator"),
            comment=(body.comment if body is not None else ""),
        )
        db.commit()
        return payload
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/business-outcome/confirm")
def confirm_workflow_business_outcome_endpoint(
    workflow_run_id: int,
    body: BusinessOutcomeRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = set_workflow_business_outcome(
            db,
            workflow_run_id,
            status="confirmed",
            operator=body.operator,
            note=body.note,
        )
        db.commit()
        return payload
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/business-outcome/reject")
def reject_workflow_business_outcome_endpoint(
    workflow_run_id: int,
    body: BusinessOutcomeRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = set_workflow_business_outcome(
            db,
            workflow_run_id,
            status="rejected",
            operator=body.operator,
            note=body.note,
        )
        db.commit()
        return payload
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/business-outcome/follow-up", status_code=201)
def followup_workflow_business_outcome_endpoint(
    workflow_run_id: int,
    body: BusinessOutcomeRequest,
    db: Session = Depends(get_db),
):
    try:
        payload = request_workflow_business_followup(
            db,
            workflow_run_id,
            title=body.title,
            description_markdown=body.description_markdown,
            operator=body.operator,
            note=body.note,
        )
        db.commit()
        return payload
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{workflow_run_id}")
def get_workflow_run_endpoint(workflow_run_id: int, db: Session = Depends(get_db)):
    try:
        return _detail_with_workspace_recovery(db, workflow_run_id)
    except WorkflowRuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/runtime/mark-killed")
def mark_workflow_runtime_killed_endpoint(
    workflow_run_id: int,
    body: WorkflowRuntimeKillRequest | None = None,
    db: Session = Depends(get_db),
):
    try:
        mark_workflow_workspace_killed(
            db,
            workflow_run_id,
            kill_signal=(body.kill_signal if body is not None else "SIGKILL"),
        )
        db.commit()
        return _detail_with_workspace_recovery(db, workflow_run_id)
    except (WorkflowRuntimeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{workflow_run_id}/events")
def list_workflow_run_events_endpoint(workflow_run_id: int, db: Session = Depends(get_db)):
    try:
        return workflow_run_detail(db, workflow_run_id)["events"]
    except WorkflowRuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{workflow_run_id}/human-gates/{gate_id}/decide")
def decide_workflow_human_gate_endpoint(
    workflow_run_id: int,
    gate_id: int,
    body: HumanGateDecisionRequest,
    db: Session = Depends(get_db),
):
    try:
        if str(body.decision or "").strip().lower() == "continue_retry":
            recovery = recover_workspace_before_retry(db, workflow_run_id)
            if recovery.recovery_status in {"failed", "human_review"}:
                db.commit()
                detail = recovery.model_dump()
                detail["message"] = recovery.root_cause or "workspace_recovery_failed"
                raise HTTPException(status_code=409, detail=detail)
        gate = decide_human_gate(
            db,
            gate_id=gate_id,
            decision=body.decision,
            reviewer=body.reviewer,
            comment=body.comment,
        )
        if int(gate.workflow_run_id) != int(workflow_run_id):
            db.rollback()
            raise HTTPException(status_code=404, detail="human gate does not belong to workflow run")
        db.commit()
        detail = _detail_with_workspace_recovery(db, workflow_run_id)
        detail.update(getattr(gate, "_resume_result", {}) or {})
        return detail
    except HTTPException:
        raise
    except WorkflowRuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
