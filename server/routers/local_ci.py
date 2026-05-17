"""Local CI runner API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.services.local_runner.ci_runs import (
    ci_run_to_out,
    create_local_ci_run,
    get_local_ci_run,
    list_local_ci_events,
    list_local_ci_runs,
    reset_local_ci_run,
)
from server.services.local_runner.ci_schemas import (
    LocalCiEventOut,
    LocalCiEventsPageOut,
    LocalCiRunCreateRequest,
    LocalCiRunOut,
    LocalCiRunResetRequest,
    LocalCiRunsPageOut,
)

router = APIRouter(prefix="/api/ci", tags=["local-ci"])


@router.post("/runs", response_model=LocalCiRunOut)
def create_local_ci_run_endpoint(
    body: LocalCiRunCreateRequest, db: Session = Depends(get_db)
):
    try:
        return ci_run_to_out(create_local_ci_run(db, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs", response_model=LocalCiRunsPageOut)
def list_local_ci_runs_endpoint(
    status: str | None = None,
    repo_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    rows, total, bounded_limit, bounded_offset = list_local_ci_runs(
        db, status=status, repo_path=repo_path, limit=limit, offset=offset
    )
    return LocalCiRunsPageOut(
        items=[ci_run_to_out(row) for row in rows],
        total=total,
        limit=bounded_limit,
        offset=bounded_offset,
    )


@router.get("/runs/{run_id}", response_model=LocalCiRunOut)
def get_local_ci_run_endpoint(run_id: int, db: Session = Depends(get_db)):
    try:
        return ci_run_to_out(get_local_ci_run(db, run_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/events", response_model=LocalCiEventsPageOut)
def list_local_ci_events_endpoint(
    run_id: int,
    after_sequence: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    try:
        page = list_local_ci_events(
            db, ci_run_id=run_id, after_sequence=after_sequence, limit=limit
        )
        return LocalCiEventsPageOut(
            items=[LocalCiEventOut.model_validate(row) for row in page.items],
            next_sequence=page.next_sequence,
            has_more=page.has_more,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/reset", response_model=LocalCiRunOut)
def reset_local_ci_run_endpoint(
    run_id: int,
    body: LocalCiRunResetRequest,
    db: Session = Depends(get_db),
):
    try:
        return ci_run_to_out(reset_local_ci_run(db, run_id, body))
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
