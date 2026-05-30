"""Bug source registry API."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.logging_utils import timed_operation
from server.schemas import (
    BugIntakeRequest,
    BugIntakeResultOut,
    BugSourceRegistryOut,
    ExternalLogCenterBatchRequest,
    ExternalLogCenterBatchResultOut,
)
from server.schemas_bugs import (
    BugAgentQueueOut,
    BugClaimRequest,
    BugClaimResultOut,
    BugCloseRequest,
    BugDetailOut,
    BugLinkFixRequest,
    BugListOut,
    BugReopenRequest,
    BugVerificationRequest,
)
from server.services.bugs.intake import intake_bug
from server.services.bugs.agent_auth import require_agent_bug_token
from server.services.bugs.external_adapter import intake_external_log_center_batch
from server.services.bugs.sources import list_bug_source_registry
from server.services.bugs.workbench import (
    add_bug_verification,
    agent_queue,
    bug_detail,
    claim_bug,
    close_bug,
    link_bug_fix,
    list_bugs,
    materialize_bug_requirement,
    reopen_bug,
)

router = APIRouter(prefix="/api/bugs", tags=["bugs"])
logger = logging.getLogger("ops-dashboard.bugs")


@router.get("", response_model=BugListOut)
def list_bugs_endpoint(
    project_key: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    source_key: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    with timed_operation(logger, "bug_list_get", slow_ms=1000):
        return list_bugs(
            db,
            project_key=project_key,
            status=status,
            severity=severity,
            source_key=source_key,
            q=q,
            limit=limit,
            offset=offset,
        )


@router.get("/agent-queue", response_model=BugAgentQueueOut)
def get_bug_agent_queue(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    with timed_operation(logger, "bug_agent_queue_get", slow_ms=1000):
        return agent_queue(db, limit=limit, offset=offset)


@router.get("/sources", response_model=BugSourceRegistryOut)
def get_bug_source_registry(db: Session = Depends(get_db)):
    with timed_operation(logger, "bug_source_registry_get", slow_ms=1000):
        return BugSourceRegistryOut(**list_bug_source_registry(db))


@router.post("/intake", response_model=BugIntakeResultOut, status_code=201)
def intake_bug_endpoint(body: BugIntakeRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_intake_post", source_key=body.source_key, slow_ms=1000):
            return intake_bug(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/intake/log-center", response_model=ExternalLogCenterBatchResultOut, status_code=201)
def intake_log_center_endpoint(body: ExternalLogCenterBatchRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(
            logger,
            "bug_log_center_intake_post",
            source_system=body.source_system,
            event_count=len(body.events or []),
            slow_ms=1000,
        ):
            return ExternalLogCenterBatchResultOut(**intake_external_log_center_batch(db, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/agent-actions/intake", response_model=BugIntakeResultOut, status_code=201)
def agent_intake_bug_endpoint(
    body: BugIntakeRequest,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return intake_bug_endpoint(body, db)


@router.post("/agent-actions/{bug_id}/claim", response_model=BugClaimResultOut)
def agent_claim_bug_endpoint(
    bug_id: int,
    body: BugClaimRequest,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return claim_bug_endpoint(bug_id, body, db)


@router.post("/agent-actions/{bug_id}/materialize-requirement", response_model=BugDetailOut)
def agent_materialize_bug_requirement_endpoint(
    bug_id: int,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return materialize_bug_requirement_endpoint(bug_id, db)


@router.post("/agent-actions/{bug_id}/link-fix", response_model=BugDetailOut)
def agent_link_bug_fix_endpoint(
    bug_id: int,
    body: BugLinkFixRequest,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return link_bug_fix_endpoint(bug_id, body, db)


@router.post("/agent-actions/{bug_id}/verification", response_model=BugDetailOut)
def agent_add_bug_verification_endpoint(
    bug_id: int,
    body: BugVerificationRequest,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return add_bug_verification_endpoint(bug_id, body, db)


@router.post("/agent-actions/{bug_id}/close", response_model=BugDetailOut)
def agent_close_bug_endpoint(
    bug_id: int,
    body: BugCloseRequest,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return close_bug_endpoint(bug_id, body, db)


@router.post("/agent-actions/{bug_id}/reopen", response_model=BugDetailOut)
def agent_reopen_bug_endpoint(
    bug_id: int,
    body: BugReopenRequest,
    db: Session = Depends(get_db),
    x_growing_agent_bug_token: str | None = Header(default=None),
):
    require_agent_bug_token(x_growing_agent_bug_token)
    return reopen_bug_endpoint(bug_id, body, db)


@router.get("/{bug_id}", response_model=BugDetailOut)
def get_bug_detail_endpoint(bug_id: int, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_detail_get", bug_id=bug_id, slow_ms=1000):
            return bug_detail(db, bug_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{bug_id}/claim", response_model=BugClaimResultOut)
def claim_bug_endpoint(bug_id: int, body: BugClaimRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_claim_post", bug_id=bug_id, slow_ms=1000):
            return claim_bug(db, bug_id, agent_id=body.agent_id, lease_minutes=body.lease_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "active fix" in str(exc) else 400, detail=str(exc)) from exc


@router.post("/{bug_id}/materialize-requirement", response_model=BugDetailOut)
def materialize_bug_requirement_endpoint(bug_id: int, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_materialize_requirement_post", bug_id=bug_id, slow_ms=1000):
            return materialize_bug_requirement(db, bug_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{bug_id}/link-fix", response_model=BugDetailOut)
def link_bug_fix_endpoint(bug_id: int, body: BugLinkFixRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_link_fix_post", bug_id=bug_id, slow_ms=1000):
            return link_bug_fix(db, bug_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{bug_id}/verification", response_model=BugDetailOut)
def add_bug_verification_endpoint(bug_id: int, body: BugVerificationRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_verification_post", bug_id=bug_id, slow_ms=1000):
            return add_bug_verification(db, bug_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{bug_id}/close", response_model=BugDetailOut)
def close_bug_endpoint(bug_id: int, body: BugCloseRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_close_post", bug_id=bug_id, slow_ms=1000):
            return close_bug(db, bug_id, actor=body.actor, resolution=body.resolution)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{bug_id}/reopen", response_model=BugDetailOut)
def reopen_bug_endpoint(bug_id: int, body: BugReopenRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_reopen_post", bug_id=bug_id, slow_ms=1000):
            return reopen_bug(db, bug_id, actor=body.actor, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
