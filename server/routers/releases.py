"""Release center API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ReleaseActionRequest, ReleaseCandidateOut, ReleaseDetailOut, ReleaseRollbackRequest
from server.services.releases.service import (
    build_release_detail,
    deploy_release,
    mark_release_no_deploy,
    list_release_candidates,
    open_release_pr,
    prepare_release,
    rollback_release,
)


router = APIRouter(prefix="/api/releases", tags=["releases"])


@router.get("/candidates", response_model=list[ReleaseCandidateOut])
def list_release_candidates_endpoint(db: Session = Depends(get_db)):
    return list_release_candidates(db)


@router.get("/{requirement_id}", response_model=ReleaseDetailOut)
def get_release_detail_endpoint(requirement_id: int, db: Session = Depends(get_db)):
    try:
        return build_release_detail(db, requirement_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{requirement_id}/prepare", response_model=ReleaseDetailOut)
def prepare_release_endpoint(requirement_id: int, body: ReleaseActionRequest, db: Session = Depends(get_db)):
    try:
        return prepare_release(db, requirement_id, actor=body.actor, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/open-pr", response_model=ReleaseDetailOut)
def open_release_pr_endpoint(requirement_id: int, body: ReleaseActionRequest, db: Session = Depends(get_db)):
    try:
        return open_release_pr(db, requirement_id, actor=body.actor, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/deploy/staging", response_model=ReleaseDetailOut)
def deploy_release_staging_endpoint(requirement_id: int, body: ReleaseActionRequest, db: Session = Depends(get_db)):
    try:
        return deploy_release(
            db,
            requirement_id,
            environment="staging",
            actor=body.actor,
            note=body.note,
            source_ref_type=body.source_ref_type,
            source_ref=body.source_ref,
            deploy_scope=body.deploy_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/deploy/production", response_model=ReleaseDetailOut)
def deploy_release_production_endpoint(requirement_id: int, body: ReleaseActionRequest, db: Session = Depends(get_db)):
    try:
        return deploy_release(
            db,
            requirement_id,
            environment="production",
            actor=body.actor,
            note=body.note,
            source_ref_type=body.source_ref_type,
            source_ref=body.source_ref,
            deploy_scope=body.deploy_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/no-deploy", response_model=ReleaseDetailOut)
def mark_release_no_deploy_endpoint(requirement_id: int, body: ReleaseActionRequest, db: Session = Depends(get_db)):
    try:
        return mark_release_no_deploy(
            db,
            requirement_id,
            actor=body.actor,
            note=body.note,
            source_ref_type=body.source_ref_type,
            source_ref=body.source_ref,
            deploy_scope=body.deploy_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{requirement_id}/rollback", response_model=ReleaseDetailOut)
def rollback_release_endpoint(requirement_id: int, body: ReleaseRollbackRequest, db: Session = Depends(get_db)):
    try:
        return rollback_release(
            db,
            requirement_id,
            rollback_target_sha=body.rollback_target_sha,
            actor=body.actor,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
