"""MCP server release center API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.services.releases import mcp_server_schemas as mcp_schema
from server.services.releases import mcp_server_catalog_service as mcp_catalog
from server.services.releases import mcp_surface_config_service as mcp_config
from server.services.releases import mcp_servers as mcp_service

router = APIRouter(prefix="/api/releases/mcp-servers", tags=["mcp-server-releases"])
surface_router = APIRouter(prefix="/api/releases", tags=["mcp-server-releases"])


@surface_router.get(
    "/mcp-surfaces", response_model=list[mcp_schema.McpDiscoverySurfaceOut]
)
def list_mcp_discovery_surfaces_endpoint(db: Session = Depends(get_db)):
    return mcp_catalog.list_discovery_surfaces(db)


@surface_router.get(
    "/mcp-surfaces/{surface_key}/config",
    response_model=mcp_schema.McpSurfaceConfigOut,
)
def get_mcp_surface_config_endpoint(surface_key: str, db: Session = Depends(get_db)):
    try:
        return mcp_config.get_surface_config(db, surface_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@surface_router.patch(
    "/mcp-surfaces/{surface_key}/config",
    response_model=mcp_schema.McpSurfaceConfigOut,
)
def patch_mcp_surface_config_endpoint(
    surface_key: str,
    body: mcp_schema.McpSurfaceConfigPatchRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_config.patch_surface_config(db, surface_key, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@surface_router.post(
    "/mcp-surfaces/{surface_key}/config/verify",
    response_model=mcp_schema.McpSurfaceConfigVerifyOut,
)
def verify_mcp_surface_config_endpoint(
    surface_key: str, db: Session = Depends(get_db)
):
    try:
        return mcp_config.verify_surface_config(db, surface_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/catalog", response_model=mcp_schema.McpServerPageOut)
def list_mcp_server_catalog_endpoint(
    search: str | None = None,
    transport_kind: str | None = None,
    status: str | None = None,
    surface_category: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    return mcp_catalog.list_mcp_servers(
        db,
        search=search,
        transport_kind=transport_kind,
        status=status,
        surface_category=surface_category,
        page=page,
        page_size=page_size,
    )


@router.post("/catalog", response_model=mcp_schema.McpServerOut, status_code=201)
def create_mcp_server_catalog_endpoint(
    body: mcp_schema.McpServerCreateRequest, db: Session = Depends(get_db)
):
    try:
        return mcp_catalog.create_mcp_server(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/catalog/{server_id}", response_model=mcp_schema.McpServerOut)
def get_mcp_server_catalog_endpoint(server_id: int, db: Session = Depends(get_db)):
    try:
        return mcp_catalog.get_mcp_server(db, server_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/catalog/{server_id}/releases",
    response_model=mcp_schema.McpServerReleaseOut,
    status_code=201,
)
def create_mcp_server_catalog_release_endpoint(
    server_id: int,
    body: mcp_schema.McpServerReleaseCreateRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_catalog.create_release_for_server(db, server_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "/{server_id}/submission-readiness",
    response_model=mcp_schema.McpSubmissionReadinessOut,
)
def get_mcp_server_submission_readiness_endpoint(
    server_id: int, db: Session = Depends(get_db)
):
    try:
        return mcp_config.get_submission_readiness(db, server_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=mcp_schema.McpServerReleasePageOut)
def list_mcp_server_releases_endpoint(
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    return mcp_service.list_mcp_server_releases(
        db,
        status=status,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=mcp_schema.McpServerReleaseOut, status_code=201)
def create_mcp_server_release_endpoint(
    body: mcp_schema.McpServerReleaseCreateRequest, db: Session = Depends(get_db)
):
    try:
        return mcp_service.create_mcp_server_release(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync-statuses", response_model=mcp_schema.McpServerReleaseSyncResult)
def sync_mcp_server_release_statuses_endpoint(
    max_records: int = 50, db: Session = Depends(get_db)
):
    return mcp_service.sync_mcp_server_release_statuses(db, max_records=max_records)


@router.get("/{release_id}", response_model=mcp_schema.McpServerReleaseOut)
def get_mcp_server_release_endpoint(release_id: int, db: Session = Depends(get_db)):
    try:
        return mcp_service.get_mcp_server_release(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{release_id}/events", response_model=list[mcp_schema.McpServerReleaseEventOut]
)
def list_mcp_server_release_events_endpoint(
    release_id: int, db: Session = Depends(get_db)
):
    try:
        return mcp_service.list_mcp_server_release_events(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{release_id}/readiness", response_model=mcp_schema.McpServerReleaseOut)
def run_mcp_server_readiness_endpoint(
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
    db: Session = Depends(get_db),
):
    return _mcp_action(mcp_service.run_mcp_release_readiness, db, release_id, body)


@router.post("/{release_id}/publish-npm", response_model=mcp_schema.McpServerReleaseOut)
def publish_mcp_server_npm_endpoint(
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
    db: Session = Depends(get_db),
):
    return _mcp_action(mcp_service.publish_mcp_npm_release, db, release_id, body)


@router.post(
    "/{release_id}/submit-registry", response_model=mcp_schema.McpServerReleaseOut
)
def submit_mcp_server_registry_endpoint(
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
    db: Session = Depends(get_db),
):
    return _mcp_action(mcp_service.submit_mcp_registry_release, db, release_id, body)


@router.post("/{release_id}/prod-smoke", response_model=mcp_schema.McpServerReleaseOut)
def run_mcp_server_prod_smoke_endpoint(
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
    db: Session = Depends(get_db),
):
    return _mcp_action(mcp_service.run_mcp_prod_smoke, db, release_id, body)


@router.post("/{release_id}/deploy-remote-prod", response_model=mcp_schema.McpServerReleaseOut)
def deploy_mcp_server_remote_prod_endpoint(
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
    db: Session = Depends(get_db),
):
    return _mcp_action(mcp_service.deploy_mcp_remote_prod, db, release_id, body)


@router.post("/{release_id}/complete", response_model=mcp_schema.McpServerReleaseOut)
def complete_mcp_server_release_endpoint(
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_service.mark_mcp_release_completed(db, release_id, actor=body.actor)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.patch(
    "/{release_id}/surfaces/{surface_key}",
    response_model=mcp_schema.McpServerSurfaceOut,
)
def patch_mcp_server_surface_endpoint(
    release_id: int,
    surface_key: str,
    body: mcp_schema.McpServerSurfacePatchRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_service.patch_mcp_surface(db, release_id, surface_key, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post(
    "/{release_id}/surface-sync", response_model=mcp_schema.McpServerReleaseOut
)
def sync_mcp_release_surfaces_endpoint(release_id: int, db: Session = Depends(get_db)):
    try:
        return mcp_service.sync_mcp_release_surface_statuses(db, release_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/{release_id}/surface-live-check",
    response_model=mcp_schema.McpSurfaceLiveCheckOut,
)
def live_check_mcp_release_surface_endpoint(
    release_id: int,
    body: mcp_schema.McpServerSurfaceSubmitRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_config.live_check_surface(db, release_id, body.surface_key)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post(
    "/{release_id}/submit-surface", response_model=mcp_schema.McpServerSurfaceOut
)
def submit_mcp_release_surface_with_readiness_endpoint(
    release_id: int,
    body: mcp_schema.McpServerSurfaceSubmitRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_config.submit_surface_with_readiness(
            db, release_id, body.surface_key, actor=body.actor, note=body.note
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post(
    "/{release_id}/submit-directory", response_model=mcp_schema.McpServerSurfaceOut
)
def submit_mcp_release_surface_endpoint(
    release_id: int,
    body: mcp_schema.McpServerSurfaceSubmitRequest,
    db: Session = Depends(get_db),
):
    try:
        return mcp_service.submit_mcp_directory_surface(db, release_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


def _mcp_action(
    action: Callable[
        [Session, int, mcp_schema.McpServerReleaseActionRequest],
        mcp_schema.McpServerReleaseOut,
    ],
    db: Session,
    release_id: int,
    body: mcp_schema.McpServerReleaseActionRequest,
):
    try:
        return action(db, release_id, body)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
