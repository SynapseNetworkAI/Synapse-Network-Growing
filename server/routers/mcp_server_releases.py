"""MCP server release center API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.services.releases import mcp_server_schemas as mcp_schema
from server.services.releases import mcp_servers as mcp_service

router = APIRouter(prefix="/api/releases/mcp-servers", tags=["mcp-server-releases"])


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
