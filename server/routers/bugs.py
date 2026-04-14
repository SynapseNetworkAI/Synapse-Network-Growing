"""Bug source registry API."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
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
from server.services.bugs.intake import intake_bug
from server.services.bugs.external_adapter import intake_external_log_center_batch
from server.services.bugs.sources import list_bug_source_registry

router = APIRouter(prefix="/api/bugs", tags=["bugs"])
logger = logging.getLogger("ops-dashboard.bugs")


@router.get("/sources", response_model=BugSourceRegistryOut)
def get_bug_source_registry(db: Session = Depends(get_db)):
    with timed_operation(logger, "bug_source_registry_get", slow_ms=1000):
        return BugSourceRegistryOut(**list_bug_source_registry(db))


@router.post("/intake", response_model=BugIntakeResultOut, status_code=201)
def intake_bug_endpoint(body: BugIntakeRequest, db: Session = Depends(get_db)):
    try:
        with timed_operation(logger, "bug_intake_post", source_key=body.source_key, slow_ms=1000):
            return BugIntakeResultOut(**intake_bug(db, body))
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
