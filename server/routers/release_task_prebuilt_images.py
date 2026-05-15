"""Release task prebuilt image endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow, get_db
from server.schemas import ReleaseTaskOut
from server.services.releases.prebuilt_images import attach_prebuilt_image_to_task
from server.services.releases.tasks import _clean, _release_task_to_out

router = APIRouter(prefix="/api/releases", tags=["releases"])


class ReleaseTaskAttachPrebuiltImageRequest(BaseModel):
    service_key: str
    image_digest: str
    source_commit_sha: str
    image_source: str = "ephemeral_worktree_local_build"
    build_evidence: dict[str, Any] = Field(default_factory=dict)


@router.post("/tasks/{task_id}/attach-prebuilt-image", response_model=ReleaseTaskOut)
def attach_release_task_prebuilt_image_endpoint(
    task_id: int,
    body: ReleaseTaskAttachPrebuiltImageRequest,
    db: Session = Depends(get_db),
):
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Release task not found.")
    if _clean(row.status).lower() != "requested":
        raise HTTPException(
            status_code=400,
            detail="Only requested release tasks can attach a prebuilt image.",
        )
    if row.deployment_record_id is not None:
        raise HTTPException(
            status_code=400, detail="Release task already has a deployment record."
        )
    try:
        return _release_task_to_out(attach_prebuilt_image_to_task(db, row, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
