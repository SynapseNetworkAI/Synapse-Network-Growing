"""Company operating review API."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.logging_utils import timed_operation
from server.schemas import (
    CompanyOperatingReviewOut,
    CompanyReviewBundleMaterializeRequest,
    CompanyReviewBundleMaterializeResultOut,
)
from server.services.company_review import (
    company_review_to_dict,
    latest_company_operating_review,
    materialize_company_review_bundle,
    refresh_company_operating_review,
)

router = APIRouter(prefix="/api/company-review", tags=["company-review"])
logger = logging.getLogger("ops-dashboard.company_review_api")


@router.get("", response_model=CompanyOperatingReviewOut)
def get_company_operating_review(db: Session = Depends(get_db)):
    with timed_operation(logger, "company_review_get", slow_ms=1000):
        return CompanyOperatingReviewOut(**company_review_to_dict(latest_company_operating_review(db)))


@router.post("/refresh", response_model=CompanyOperatingReviewOut)
def refresh_company_review_endpoint(db: Session = Depends(get_db)):
    with timed_operation(logger, "company_review_refresh", slow_ms=1200):
        return CompanyOperatingReviewOut(**company_review_to_dict(refresh_company_operating_review(db)))


@router.post("/{review_id}/materialize-bundle", response_model=CompanyReviewBundleMaterializeResultOut)
def materialize_company_review_bundle_endpoint(
    review_id: int,
    body: CompanyReviewBundleMaterializeRequest,
    db: Session = Depends(get_db),
):
    try:
        with timed_operation(
            logger,
            "company_review_materialize_bundle",
            review_id=review_id,
            requested_items=len(body.bundle_item_keys or []),
            auto_start=body.auto_start,
            slow_ms=1500,
        ):
            return materialize_company_review_bundle(
                db,
                review_id=review_id,
                bundle_item_keys=body.bundle_item_keys,
                auto_start=body.auto_start,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
