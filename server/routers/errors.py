"""Error log and fingerprint API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ErrorFingerprintDetailOut, ErrorFingerprintOut, ErrorIntakeRequest
from server.services.bugs.error_loop import build_error_fingerprint_detail, intake_error_event, list_error_fingerprints


router = APIRouter(prefix="/api/errors", tags=["errors"])


@router.post("/intake", response_model=ErrorFingerprintDetailOut, status_code=201)
def intake_error_event_endpoint(body: ErrorIntakeRequest, db: Session = Depends(get_db)):
    try:
        return intake_error_event(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[ErrorFingerprintOut])
def list_error_fingerprints_endpoint(db: Session = Depends(get_db)):
    return list_error_fingerprints(db)


@router.get("/{fingerprint_key}", response_model=ErrorFingerprintDetailOut)
def get_error_fingerprint_endpoint(fingerprint_key: str, db: Session = Depends(get_db)):
    try:
        return build_error_fingerprint_detail(db, fingerprint_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
