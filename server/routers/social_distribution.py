"""Social distribution API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas_social_distribution import (
    SocialAssetPlannerRunOut,
    SocialContentAssetCreateRequest,
    SocialContentAssetDetailOut,
    SocialContentAssetOut,
    SocialContentAssetPatchRequest,
    SocialContentTaskCreateRequest,
    SocialDistributionBoardOut,
    SocialDistributionAccountAuthStatusListOut,
    SocialDistributionAccountOut,
    SocialDistributionAccountPatchRequest,
    SocialDistributionApproveCanonicalArticleRequest,
    SocialDistributionCampaignTemplateOut,
    SocialDistributionGenerateContentPlanRequest,
    SocialDistributionExpandCanonicalArticleRequest,
    SocialDistributionApproveGenerateRequest,
    SocialDistributionAuditPublishedPageRequest,
    SocialDistributionGenerateTasksOut,
    SocialDistributionGenerateTasksRequest,
    SocialDistributionGenerateXArticlePackOut,
    SocialDistributionGenerateXArticlePackRequest,
    SocialDailyXContentPlannerRequest,
    SocialDailyXContentPlannerRunOut,
    SocialDistributionMarkLiveRequest,
    SocialDistributionMarkRemovedRequest,
    SocialDistributionPublishXRequest,
    SocialXReplyBlockGenerateRequest,
    SocialXReplyBlockGenerateOut,
    SocialDistributionXAuthStatusOut,
    SocialDistributionTaskListOut,
    SocialDistributionTaskOut,
    SocialDistributionTaskPatchRequest,
)
from server.services.social.distribution import (
    create_content_asset,
    get_content_asset,
    list_content_assets,
    list_distribution_accounts,
    list_distribution_tasks,
    update_content_asset,
    update_distribution_account,
)
from server.services.social.distribution_asset_planner import (
    run_social_asset_planner_sweep,
)
from server.services.social.daily_content_task_planner import (
    run_x_social_daily_content_task_planner,
)
from server.services.social.distribution_article_packs import generate_x_article_pack
from server.services.social.distribution_board import social_distribution_board
from server.services.social.distribution_account_auth import (
    distribution_account_auth_statuses,
)
from server.services.social.distribution_campaign_templates import (
    create_x_brand_week_template,
)
from server.services.social.distribution_content_tasks import create_content_task
from server.services.social.distribution_documents import (
    approve_canonical_article,
    expand_canonical_article,
    generate_content_plan,
)
from server.services.social.distribution_generation import (
    approve_and_generate_distribution_tasks,
    generate_distribution_tasks,
)
from server.services.social.distribution_publish_audit import (
    audit_distribution_task_published_page,
    mark_distribution_task_live,
    mark_distribution_task_removed,
)
from server.services.social.distribution_reply_blocks import (
    DEFAULT_REPLY_BLOCK_MAX_SECONDS,
    DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS,
    generate_x_reply_block_candidates,
)
from server.services.social.distribution_tasks import (
    publish_distribution_task_to_x,
    validate_distribution_task_x_auth,
    update_distribution_task,
)

router = APIRouter(prefix="/distribution")


def _http_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    status_code = 404 if "not found" in detail.lower() else 400
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/accounts", response_model=list[SocialDistributionAccountOut])
def list_distribution_accounts_endpoint(db: Session = Depends(get_db)):
    return list_distribution_accounts(db)


@router.get(
    "/accounts/auth-status",
    response_model=SocialDistributionAccountAuthStatusListOut,
)
def list_distribution_account_auth_status_endpoint(
    platform: str | None = None,
    account_id: int | None = None,
    db: Session = Depends(get_db),
):
    return distribution_account_auth_statuses(
        db,
        platform=platform,
        account_id=account_id,
    )


@router.patch("/accounts/{account_id}", response_model=SocialDistributionAccountOut)
def update_distribution_account_endpoint(
    account_id: int,
    body: SocialDistributionAccountPatchRequest,
    db: Session = Depends(get_db),
):
    try:
        return update_distribution_account(db, account_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/board", response_model=SocialDistributionBoardOut)
def social_distribution_board_endpoint(db: Session = Depends(get_db)):
    return social_distribution_board(db)


@router.post("/assets", response_model=SocialContentAssetDetailOut)
def create_content_asset_endpoint(
    body: SocialContentAssetCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        return create_content_asset(db, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/content-tasks", response_model=SocialContentAssetDetailOut)
def create_content_task_endpoint(
    body: SocialContentTaskCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        return create_content_task(db, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/campaign-templates/x-brand-week-technical-builders",
    response_model=SocialDistributionCampaignTemplateOut,
)
def create_x_brand_week_template_endpoint(db: Session = Depends(get_db)):
    return create_x_brand_week_template(db, created_by="operator")


@router.get("/assets", response_model=list[SocialContentAssetOut])
def list_content_assets_endpoint(db: Session = Depends(get_db)):
    return list_content_assets(db)


@router.post("/assets/plan-next", response_model=SocialAssetPlannerRunOut)
def run_social_asset_planner_endpoint(db: Session = Depends(get_db)):
    return run_social_asset_planner_sweep(db)


@router.post(
    "/assets/plan-daily-x-content",
    response_model=SocialDailyXContentPlannerRunOut,
)
def run_daily_x_content_task_planner_endpoint(
    body: SocialDailyXContentPlannerRequest,
    db: Session = Depends(get_db),
):
    return run_x_social_daily_content_task_planner(
        db,
        strategy_key=body.strategy_key,
        strategy_summary=body.strategy_summary,
        local_date=body.local_date,
        actor=body.actor,
    )


@router.get("/assets/{asset_id}", response_model=SocialContentAssetDetailOut)
def get_content_asset_endpoint(asset_id: int, db: Session = Depends(get_db)):
    try:
        return get_content_asset(db, asset_id)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.patch("/assets/{asset_id}", response_model=SocialContentAssetDetailOut)
def update_content_asset_endpoint(
    asset_id: int,
    body: SocialContentAssetPatchRequest,
    db: Session = Depends(get_db),
):
    try:
        return update_content_asset(db, asset_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/generate-content-plan",
    response_model=SocialContentAssetDetailOut,
)
def generate_content_plan_endpoint(
    asset_id: int,
    body: SocialDistributionGenerateContentPlanRequest,
    db: Session = Depends(get_db),
):
    try:
        return generate_content_plan(db, asset_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/expand-canonical-article",
    response_model=SocialContentAssetDetailOut,
)
def expand_canonical_article_endpoint(
    asset_id: int,
    body: SocialDistributionExpandCanonicalArticleRequest,
    db: Session = Depends(get_db),
):
    try:
        return expand_canonical_article(db, asset_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/approve-canonical-article",
    response_model=SocialContentAssetDetailOut,
)
def approve_canonical_article_endpoint(
    asset_id: int,
    body: SocialDistributionApproveCanonicalArticleRequest,
    db: Session = Depends(get_db),
):
    try:
        return approve_canonical_article(db, asset_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/generate-tasks",
    response_model=SocialDistributionGenerateTasksOut,
)
def generate_distribution_tasks_endpoint(
    asset_id: int,
    body: SocialDistributionGenerateTasksRequest,
    db: Session = Depends(get_db),
):
    try:
        return generate_distribution_tasks(db, asset_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/approve-and-generate-tasks",
    response_model=SocialDistributionGenerateTasksOut,
)
def approve_and_generate_distribution_tasks_endpoint(
    asset_id: int,
    body: SocialDistributionApproveGenerateRequest,
    db: Session = Depends(get_db),
):
    try:
        return approve_and_generate_distribution_tasks(db, asset_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/generate-x-reply-block",
    response_model=SocialXReplyBlockGenerateOut,
)
def generate_x_reply_block_endpoint(
    asset_id: int,
    body: SocialXReplyBlockGenerateRequest,
    db: Session = Depends(get_db),
):
    try:
        return generate_x_reply_block_candidates(
            db,
            asset_id=asset_id,
            source_posts=[item.model_dump() for item in body.source_posts],
            target_count=body.target_count,
            actor=body.actor,
            agent_review=body.agent_review,
            max_seconds=body.max_seconds or DEFAULT_REPLY_BLOCK_MAX_SECONDS,
            per_reply_timeout_seconds=(
                body.per_reply_timeout_seconds
                or DEFAULT_REPLY_BLOCK_PER_REPLY_TIMEOUT_SECONDS
            ),
            auto_publish=body.auto_publish,
            force_regenerate=body.force_regenerate,
        )
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/assets/{asset_id}/generate-x-article-pack",
    response_model=SocialDistributionGenerateXArticlePackOut,
)
def generate_x_article_pack_endpoint(
    asset_id: int,
    body: SocialDistributionGenerateXArticlePackRequest,
    db: Session = Depends(get_db),
):
    try:
        return generate_x_article_pack(db, asset_id=asset_id, body=body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get("/tasks", response_model=SocialDistributionTaskListOut)
def list_distribution_tasks_endpoint(
    platform: str | None = None,
    channel_key: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return list_distribution_tasks(
        db,
        platform=platform,
        channel_key=channel_key,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.patch("/tasks/{task_id}", response_model=SocialDistributionTaskOut)
def update_distribution_task_endpoint(
    task_id: int,
    body: SocialDistributionTaskPatchRequest,
    db: Session = Depends(get_db),
):
    try:
        return update_distribution_task(db, task_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/mark-live", response_model=SocialDistributionTaskOut)
def mark_distribution_task_live_endpoint(
    task_id: int,
    body: SocialDistributionMarkLiveRequest,
    db: Session = Depends(get_db),
):
    try:
        return mark_distribution_task_live(db, task_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/mark-removed", response_model=SocialDistributionTaskOut)
def mark_distribution_task_removed_endpoint(
    task_id: int,
    body: SocialDistributionMarkRemovedRequest,
    db: Session = Depends(get_db),
):
    try:
        return mark_distribution_task_removed(db, task_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post(
    "/tasks/{task_id}/audit-published-page",
    response_model=SocialDistributionTaskOut,
)
def audit_distribution_task_published_page_endpoint(
    task_id: int,
    body: SocialDistributionAuditPublishedPageRequest,
    db: Session = Depends(get_db),
):
    try:
        return audit_distribution_task_published_page(db, task_id, body)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/tasks/{task_id}/x-auth-status",
    response_model=SocialDistributionXAuthStatusOut,
)
def validate_distribution_task_x_auth_endpoint(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        return validate_distribution_task_x_auth(db, task_id)
    except ValueError as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{task_id}/publish-x", response_model=SocialDistributionTaskOut)
def publish_distribution_task_to_x_endpoint(
    task_id: int,
    body: SocialDistributionPublishXRequest,
    db: Session = Depends(get_db),
):
    try:
        return publish_distribution_task_to_x(db, task_id, actor=body.actor)
    except ValueError as exc:
        raise _http_error(exc) from exc
