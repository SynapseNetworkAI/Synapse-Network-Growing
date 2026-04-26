"""Social publishing API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import (
    SocialAccountOut,
    SocialPostCreateRequest,
    SocialPostDraftOut,
    SocialPostGenerateDraftRequest,
    SocialPostPatchRequest,
    SocialPostPublishRequest,
    SocialPostRewriteRequest,
)
from server.services.social.publishing import (
    create_social_post,
    generate_social_post_draft,
    list_social_accounts,
    list_social_posts,
    publish_social_post_to_x,
    request_social_post_rewrite,
    update_social_post,
)


router = APIRouter(prefix="/api/social", tags=["social"])


def _http_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = 404 if "not found" in detail.lower() else 400
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/accounts", response_model=list[SocialAccountOut])
def list_social_accounts_endpoint(db: Session = Depends(get_db)):
    return list_social_accounts(db)


@router.get("/posts", response_model=list[SocialPostDraftOut])
def list_social_posts_endpoint(status: str | None = None, db: Session = Depends(get_db)):
    return list_social_posts(db, status=status)


@router.post("/posts", response_model=SocialPostDraftOut)
def create_social_post_endpoint(body: SocialPostCreateRequest, db: Session = Depends(get_db)):
    try:
        return create_social_post(db, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts/generate-draft", response_model=SocialPostDraftOut)
def generate_social_post_draft_endpoint(body: SocialPostGenerateDraftRequest, db: Session = Depends(get_db)):
    try:
        return generate_social_post_draft(db, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.patch("/posts/{post_id}", response_model=SocialPostDraftOut)
def update_social_post_endpoint(post_id: int, body: SocialPostPatchRequest, db: Session = Depends(get_db)):
    try:
        return update_social_post(db, post_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts/{post_id}/request-rewrite", response_model=SocialPostDraftOut)
def request_social_post_rewrite_endpoint(post_id: int, body: SocialPostRewriteRequest, db: Session = Depends(get_db)):
    try:
        return request_social_post_rewrite(db, post_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts/{post_id}/publish-x", response_model=SocialPostDraftOut)
def publish_social_post_to_x_endpoint(post_id: int, body: SocialPostPublishRequest, db: Session = Depends(get_db)):
    try:
        return publish_social_post_to_x(db, post_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc
