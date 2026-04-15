"""Execution console API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ExecutionCreateRequest, ExecutionFilePreviewOut, ExecutionOperationResultOut, ExecutionRunDetailOut, ExecutionRunOut
from server.services.workflows.agent_first import (
    _execution_file_preview,
    build_execution_detail,
    create_execution_run,
    list_execution_runs,
    pause_execution_run,
    retry_execution_run,
    start_execution_command,
    validate_execution_run,
)


router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get("", response_model=list[ExecutionRunOut])
def list_execution_runs_endpoint(db: Session = Depends(get_db)):
    return list_execution_runs(db)


@router.post("", response_model=ExecutionRunDetailOut, status_code=201)
def create_execution_endpoint(body: ExecutionCreateRequest, db: Session = Depends(get_db)):
    try:
        return create_execution_run(db, body.requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{execution_run_id}", response_model=ExecutionRunDetailOut)
def get_execution_endpoint(execution_run_id: int, db: Session = Depends(get_db)):
    try:
        return build_execution_detail(db, execution_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{execution_run_id}/files/{file_path:path}", response_model=ExecutionFilePreviewOut)
def get_execution_file_preview_endpoint(execution_run_id: int, file_path: str, db: Session = Depends(get_db)):
    try:
        return _execution_file_preview(db, execution_run_id, file_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{execution_run_id}/start", response_model=ExecutionOperationResultOut)
def start_execution_endpoint(execution_run_id: int, db: Session = Depends(get_db)):
    return start_execution_command(db, execution_run_id)


@router.post("/{execution_run_id}/pause", response_model=ExecutionRunDetailOut)
def pause_execution_endpoint(execution_run_id: int, db: Session = Depends(get_db)):
    try:
        return pause_execution_run(db, execution_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{execution_run_id}/resume", response_model=ExecutionOperationResultOut)
def resume_execution_endpoint(execution_run_id: int, db: Session = Depends(get_db)):
    return start_execution_command(db, execution_run_id)


@router.post("/{execution_run_id}/retry", response_model=ExecutionRunDetailOut)
def retry_execution_endpoint(execution_run_id: int, db: Session = Depends(get_db)):
    try:
        return retry_execution_run(db, execution_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{execution_run_id}/validate", response_model=ExecutionRunDetailOut)
def validate_execution_endpoint(execution_run_id: int, db: Session = Depends(get_db)):
    try:
        return validate_execution_run(db, execution_run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
