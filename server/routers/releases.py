"""Release center API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import (
    ReleaseActionRequest,
    ReleaseBranchOptionOut,
    ReleaseCandidateOut,
    ReleaseDetailOut,
    ReleaseRollbackRequest,
    ReleaseTaskCreateRequest,
    ReleaseTaskDeployRequest,
    ReleaseTaskOut,
    ReleaseTaskPatchRequest,
    OnlineReleaseRecordOut,
)
from server.services.delivery.deployment_governance import list_online_release_records
from server.services.releases.service import (
    build_release_detail,
    deploy_release,
    mark_release_no_deploy,
    list_release_candidates,
    open_release_pr,
    prepare_release,
    rollback_release,
)
from server.services.releases.sdk_packages import (
    dry_run_sdk_package_release,
    get_sdk_package_release,
    get_sdk_release_train,
    initialize_sdk_release_train,
    list_sdk_package_release_events,
    list_sdk_package_releases,
    list_sdk_release_trains,
    publish_sdk_package_release,
    retry_sdk_package_release,
    sync_sdk_package_release_statuses,
)
from server.services.releases.sdk_package_schemas import (
    SdkPackageReleaseActionRequest,
    SdkPackageReleaseEventOut,
    SdkPackageReleaseInitializeRequest,
    SdkPackageReleaseOut,
    SdkPackageReleaseSyncResult,
    SdkReleaseTrainOut,
)
from server.services.releases.tasks import (
    create_release_task,
    create_release_task_pr,
    deploy_release_task_to_staging,
    list_release_task_branch_options,
    list_release_tasks,
    sync_release_task_deployment_statuses,
    update_release_task,
)


router = APIRouter(prefix="/api/releases", tags=["releases"])


@router.get("/candidates", response_model=list[ReleaseCandidateOut])
def list_release_candidates_endpoint(db: Session = Depends(get_db)):
    return list_release_candidates(db)


@router.get("/tasks", response_model=list[ReleaseTaskOut])
def list_release_tasks_endpoint(
    project_key: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    db: Session = Depends(get_db),
):
    return list_release_tasks(
        db,
        project_key=project_key,
        environment=environment,
        status=status,
        source_type=source_type,
    )


@router.get("/branch-options", response_model=list[ReleaseBranchOptionOut])
def list_release_branch_options_endpoint(
    project_key: str,
    service_key: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        return list_release_task_branch_options(db, project_key=project_key, service_key=service_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/online-records", response_model=list[OnlineReleaseRecordOut])
def list_online_release_records_endpoint(
    project_key: str | None = None,
    environment: str | None = None,
    service_key: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return list_online_release_records(
        db,
        project_key=project_key,
        environment=environment,
        service_key=service_key,
        limit=limit,
    )


@router.post("/tasks/sync-deployment-statuses")
def sync_release_task_deployment_statuses_endpoint(max_records: int = 50, db: Session = Depends(get_db)):
    return sync_release_task_deployment_statuses(db, max_records=max_records)


@router.get("/sdk-packages", response_model=list[SdkPackageReleaseOut])
def list_sdk_package_releases_endpoint(
    release_train_version: str | None = None,
    sdk_language: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    return list_sdk_package_releases(
        db,
        release_train_version=release_train_version,
        sdk_language=sdk_language,
        status=status,
    )


@router.post("/sdk-packages/initialize-train", response_model=list[SdkPackageReleaseOut])
def initialize_sdk_release_train_endpoint(body: SdkPackageReleaseInitializeRequest, db: Session = Depends(get_db)):
    try:
        return initialize_sdk_release_train(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sdk-packages/sync-statuses", response_model=SdkPackageReleaseSyncResult)
def sync_sdk_package_release_statuses_endpoint(max_records: int = 50, db: Session = Depends(get_db)):
    return sync_sdk_package_release_statuses(db, max_records=max_records)


@router.get("/sdk-trains", response_model=list[SdkReleaseTrainOut])
def list_sdk_release_trains_endpoint(db: Session = Depends(get_db)):
    return list_sdk_release_trains(db)


@router.get("/sdk-trains/{version}", response_model=SdkReleaseTrainOut)
def get_sdk_release_train_endpoint(version: str, db: Session = Depends(get_db)):
    try:
        return get_sdk_release_train(db, version)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get("/sdk-packages/{release_id}", response_model=SdkPackageReleaseOut)
def get_sdk_package_release_endpoint(release_id: int, db: Session = Depends(get_db)):
    try:
        return get_sdk_package_release(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sdk-packages/{release_id}/events", response_model=list[SdkPackageReleaseEventOut])
def list_sdk_package_release_events_endpoint(release_id: int, db: Session = Depends(get_db)):
    try:
        return list_sdk_package_release_events(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sdk-packages/{release_id}/dry-run", response_model=SdkPackageReleaseOut)
def dry_run_sdk_package_release_endpoint(
    release_id: int,
    body: SdkPackageReleaseActionRequest,
    db: Session = Depends(get_db),
):
    try:
        return dry_run_sdk_package_release(db, release_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/sdk-packages/{release_id}/publish", response_model=SdkPackageReleaseOut)
def publish_sdk_package_release_endpoint(
    release_id: int,
    body: SdkPackageReleaseActionRequest,
    db: Session = Depends(get_db),
):
    try:
        return publish_sdk_package_release(db, release_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/sdk-packages/{release_id}/retry", response_model=SdkPackageReleaseOut)
def retry_sdk_package_release_endpoint(
    release_id: int,
    body: SdkPackageReleaseActionRequest,
    db: Session = Depends(get_db),
):
    try:
        return retry_sdk_package_release(db, release_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/tasks", response_model=ReleaseTaskOut)
def create_release_task_endpoint(body: ReleaseTaskCreateRequest, db: Session = Depends(get_db)):
    try:
        return create_release_task(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/tasks/{task_id}", response_model=ReleaseTaskOut)
def update_release_task_endpoint(task_id: int, body: ReleaseTaskPatchRequest, db: Session = Depends(get_db)):
    try:
        return update_release_task(db, task_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/tasks/{task_id}/create-pr", response_model=ReleaseTaskOut)
def create_release_task_pr_endpoint(task_id: int, body: ReleaseTaskDeployRequest, db: Session = Depends(get_db)):
    try:
        return create_release_task_pr(db, task_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/tasks/{task_id}/deploy-staging", response_model=ReleaseTaskOut)
def deploy_release_task_staging_endpoint(task_id: int, body: ReleaseTaskDeployRequest, db: Session = Depends(get_db)):
    try:
        return deploy_release_task_to_staging(db, task_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


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
