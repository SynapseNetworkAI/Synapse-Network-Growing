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
    SocialDistributionAccountOut,
    SocialDistributionAccountPatchRequest,
    SocialDistributionGenerateContentPlanRequest,
    SocialDistributionApproveGenerateRequest,
    SocialDistributionGenerateTasksOut,
    SocialDistributionGenerateTasksRequest,
    SocialDistributionMarkLiveRequest,
    SocialDistributionMarkRemovedRequest,
    SocialDistributionPublishXRequest,
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
from server.services.social.distribution_documents import (
    create_content_task,
    generate_content_plan,
)
from server.services.social.distribution_board import (
    social_distribution_board,
)
from server.services.social.distribution_generation import (
    approve_and_generate_distribution_tasks,
    generate_distribution_tasks,
)
from server.services.social.distribution_tasks import (
    mark_distribution_task_live,
    mark_distribution_task_removed,
    publish_distribution_task_to_x,
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


@router.get("/assets", response_model=list[SocialContentAssetOut])
def list_content_assets_endpoint(db: Session = Depends(get_db)):
    return list_content_assets(db)


@router.post("/assets/plan-next", response_model=SocialAssetPlannerRunOut)
def run_social_asset_planner_endpoint(db: Session = Depends(get_db)):
    return run_social_asset_planner_sweep(db)


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
