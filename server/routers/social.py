"""Social publishing API."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import (
    SocialAccountOut,
    SocialCampaignGoalCreateRequest,
    SocialCampaignGoalOut,
    SocialOpsOverviewOut,
    SocialPostCreateRequest,
    SocialPostDraftOut,
    SocialPostGenerateDraftRequest,
    SocialPostMetricOut,
    SocialPostPatchRequest,
    SocialPostPublishRequest,
    SocialPostRewriteRequest,
    SocialRepostPublishRequest,
    SocialXOAuthCallbackOut,
    SocialXOAuthStartOut,
    SocialReplyItemOut,
    SocialRepostCandidateOut,
    SocialTrendItemOut,
    SocialWatchlistAccountOut,
)
from server.services.social.publishing import (
    create_social_campaign_goal,
    create_social_post,
    complete_x_oauth_authorization,
    generate_social_post_draft,
    get_social_post,
    get_social_media_preview_path,
    list_social_campaign_goals,
    list_social_accounts,
    list_social_post_metrics,
    list_social_posts,
    list_social_replies,
    list_social_repost_candidates,
    list_social_trends,
    list_social_watchlist,
    publish_social_post_to_x,
    publish_social_repost_candidate_to_x,
    regenerate_social_post_image,
    remove_social_post_media,
    request_social_post_rewrite,
    social_ops_overview,
    start_x_oauth_authorization,
    update_social_post,
    upload_social_post_image,
)


router = APIRouter(prefix="/api/social", tags=["social"])


def _http_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = 404 if "not found" in detail.lower() else 400
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/accounts", response_model=list[SocialAccountOut])
def list_social_accounts_endpoint(db: Session = Depends(get_db)):
    return list_social_accounts(db)


@router.get("/x/oauth/start", response_model=SocialXOAuthStartOut)
def start_x_oauth_endpoint(account_id: int | None = None, db: Session = Depends(get_db)):
    try:
        return start_x_oauth_authorization(db, account_id=account_id)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/x/oauth/callback", response_model=SocialXOAuthCallbackOut)
def complete_x_oauth_endpoint(state: str, code: str, db: Session = Depends(get_db)):
    try:
        return complete_x_oauth_authorization(db, state=state, code=code)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/ops/overview", response_model=SocialOpsOverviewOut)
def social_ops_overview_endpoint(db: Session = Depends(get_db)):
    return social_ops_overview(db)


@router.get("/campaign-goals", response_model=list[SocialCampaignGoalOut])
def list_social_campaign_goals_endpoint(db: Session = Depends(get_db)):
    return list_social_campaign_goals(db)


@router.post("/campaign-goals", response_model=SocialCampaignGoalOut)
def create_social_campaign_goal_endpoint(body: SocialCampaignGoalCreateRequest, db: Session = Depends(get_db)):
    try:
        return create_social_campaign_goal(db, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/trends", response_model=list[SocialTrendItemOut])
def list_social_trends_endpoint(db: Session = Depends(get_db)):
    return list_social_trends(db)


@router.get("/watchlist", response_model=list[SocialWatchlistAccountOut])
def list_social_watchlist_endpoint(db: Session = Depends(get_db)):
    return list_social_watchlist(db)


@router.get("/replies", response_model=list[SocialReplyItemOut])
def list_social_replies_endpoint(db: Session = Depends(get_db)):
    return list_social_replies(db)


@router.get("/repost-candidates", response_model=list[SocialRepostCandidateOut])
def list_social_repost_candidates_endpoint(db: Session = Depends(get_db)):
    return list_social_repost_candidates(db)


@router.post("/repost-candidates/{candidate_id}/publish-x", response_model=SocialRepostCandidateOut)
def publish_social_repost_candidate_to_x_endpoint(candidate_id: int, body: SocialRepostPublishRequest, db: Session = Depends(get_db)):
    try:
        return publish_social_repost_candidate_to_x(db, candidate_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/post-metrics", response_model=list[SocialPostMetricOut])
def list_social_post_metrics_endpoint(db: Session = Depends(get_db)):
    return list_social_post_metrics(db)


@router.get("/posts", response_model=list[SocialPostDraftOut])
def list_social_posts_endpoint(status: str | None = None, db: Session = Depends(get_db)):
    return list_social_posts(db, status=status)


@router.get("/posts/{post_id}", response_model=SocialPostDraftOut)
def get_social_post_endpoint(post_id: int, db: Session = Depends(get_db)):
    try:
        return get_social_post(db, post_id)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts", response_model=SocialPostDraftOut)
def create_social_post_endpoint(body: SocialPostCreateRequest, db: Session = Depends(get_db)):
    try:
        return create_social_post(db, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts/generate-draft", response_model=SocialPostDraftOut)
def generate_social_post_draft_endpoint(
    body: SocialPostGenerateDraftRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        return generate_social_post_draft(db, body, background_tasks=background_tasks)
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


@router.get("/media/{media_id}/preview")
def social_media_preview_endpoint(media_id: int, db: Session = Depends(get_db)):
    try:
        return FileResponse(get_social_media_preview_path(db, media_id))
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts/{post_id}/regenerate-image", response_model=SocialPostDraftOut)
def regenerate_social_post_image_endpoint(post_id: int, body: SocialPostPublishRequest, db: Session = Depends(get_db)):
    try:
        return regenerate_social_post_image(db, post_id, actor=body.actor)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.delete("/posts/{post_id}/media/{media_id}", response_model=SocialPostDraftOut)
def remove_social_post_media_endpoint(post_id: int, media_id: int, db: Session = Depends(get_db)):
    try:
        return remove_social_post_media(db, post_id, media_id, actor="operator")
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/posts/{post_id}/media/upload", response_model=SocialPostDraftOut)
async def upload_social_post_image_endpoint(
    post_id: int,
    file: UploadFile = File(...),
    alt_text: str | None = Form(default=None),
    actor: str = Form(default="operator"),
    db: Session = Depends(get_db),
):
    try:
        payload = await file.read()
        return upload_social_post_image(
            db,
            post_id,
            filename=file.filename,
            content_type=file.content_type,
            payload=payload,
            alt_text=alt_text,
            actor=actor or "operator",
        )
    except ValueError as exc:
        raise _http_error(exc) from exc
