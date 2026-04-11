"""Company operating review API."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import CompanyOperatingReviewOut
from server.services.company_review import (
    company_review_to_dict,
    latest_company_operating_review,
    refresh_company_operating_review,
)

router = APIRouter(prefix="/api/company-review", tags=["company-review"])


@router.get("", response_model=CompanyOperatingReviewOut)
def get_company_operating_review(db: Session = Depends(get_db)):
    return CompanyOperatingReviewOut(**company_review_to_dict(latest_company_operating_review(db)))


@router.post("/refresh", response_model=CompanyOperatingReviewOut)
def refresh_company_review_endpoint(db: Session = Depends(get_db)):
    return CompanyOperatingReviewOut(**company_review_to_dict(refresh_company_operating_review(db)))
