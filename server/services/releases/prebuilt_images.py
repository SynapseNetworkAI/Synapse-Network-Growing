"""Prebuilt release image policy for frontend release tasks."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow, utcnow
from server.services.delivery.deployment_governance import _json_dump

PREBUILT_FRONTEND_SERVICES = {"admin-front", "user-front", "docs-front"}
PREBUILT_FRONTEND_WORKFLOWS = {"local_deploy_runner"}
PREBUILT_IMAGE_SOURCE = "ephemeral_worktree_local_build"
SYNAPSE_NETWORK_PROJECT_KEY = "synapse-network"


class PrebuiltDeployPlan(BaseModel):
    digest: str = ""
    commit: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, str] = Field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        return bool(self.digest)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _json_load(
    value: str | None, fallback: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not value:
        return fallback or {}
    try:
        import json

        payload = json.loads(value)
    except Exception:  # noqa: BLE001
        return fallback or {}
    return payload if isinstance(payload, dict) else (fallback or {})


def prebuilt_image_metadata(row: ReleaseTaskRow) -> dict[str, Any]:
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    return metadata if _clean(metadata.get("prebuiltImageDigest")) else {}


def prebuilt_deploy_plan(
    row: ReleaseTaskRow, *, service_key: str, workflow_file: str
) -> PrebuiltDeployPlan:
    metadata = prebuilt_image_metadata(row)
    digest = _clean(metadata.get("prebuiltImageDigest"))
    if not digest:
        return PrebuiltDeployPlan()
    commit = _clean(metadata.get("sourceCommitSha")).lower()
    if workflow_file not in PREBUILT_FRONTEND_WORKFLOWS:
        raise ValueError(
            "Prebuilt image deploy is only supported by the local frontend deploy runner."
        )
    validate_prebuilt_image_for_task(
        row,
        service_key=service_key,
        image_digest=digest,
        source_commit_sha=commit,
        image_source=_clean(metadata.get("imageSource")) or PREBUILT_IMAGE_SOURCE,
    )
    return PrebuiltDeployPlan(
        digest=digest,
        commit=commit,
        metadata={
            "prebuiltImageDigest": digest,
            "imageSource": "prebuilt_digest",
            "sourceCommitSha": commit,
            "buildService": service_key,
            "buildEvidence": metadata.get("buildEvidence")
            if isinstance(metadata.get("buildEvidence"), dict)
            else {},
        },
        inputs={
            "commit_sha": commit,
            "source_ref_type": "commit",
            "source_ref": commit,
            "prebuilt_image_digest": digest,
        },
    )


def _validate_task_scope(row: ReleaseTaskRow, row_service: str, service_key: str) -> None:
    environment = _clean(row.environment).lower()
    if environment not in {"staging", "production"}:
        raise ValueError(
            "Prebuilt image attach is only allowed for staging or production release tasks."
        )
    if _clean(row.project_key) != SYNAPSE_NETWORK_PROJECT_KEY:
        raise ValueError(
            "Prebuilt image attach is only allowed for Synapse-Network frontend tasks."
        )
    if row_service not in PREBUILT_FRONTEND_SERVICES:
        raise ValueError(
            "Prebuilt image attach is only allowed for admin-front/user-front/docs-front release tasks."
        )
    if service_key != row_service:
        raise ValueError(
            "Prebuilt image service_key must match the release task service."
        )


def validate_prebuilt_image_for_task(
    row: ReleaseTaskRow,
    *,
    service_key: str,
    image_digest: str,
    source_commit_sha: str,
    image_source: str,
) -> None:
    row_service = _clean(getattr(row, "service_key", None)).lower()
    service_key = _clean(service_key).lower()
    image_digest = _clean(image_digest)
    source_commit_sha = _clean(source_commit_sha).lower()
    _validate_task_scope(row, row_service, service_key)
    if not image_digest:
        raise ValueError("prebuilt image digest is required.")
    if not source_commit_sha:
        raise ValueError("source_commit_sha is required.")


def attach_prebuilt_image_to_task(
    db: Session, row: ReleaseTaskRow, body: Any
) -> ReleaseTaskRow:
    service_key = _clean(getattr(body, "service_key", "")).lower()
    image_digest = _clean(getattr(body, "image_digest", ""))
    source_commit_sha = _clean(getattr(body, "source_commit_sha", "")).lower()
    image_source = (
        _clean(getattr(body, "image_source", PREBUILT_IMAGE_SOURCE))
        or PREBUILT_IMAGE_SOURCE
    )
    validate_prebuilt_image_for_task(
        row,
        service_key=service_key,
        image_digest=image_digest,
        source_commit_sha=source_commit_sha,
        image_source=image_source,
    )
    build_evidence = getattr(body, "build_evidence", {}) or {}
    if not isinstance(build_evidence, dict):
        build_evidence = {}
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    metadata.update(
        {
            "prebuiltImageDigest": image_digest,
            "imageSource": image_source,
            "sourceCommitSha": source_commit_sha,
            "buildService": service_key,
            "buildEvidence": build_evidence,
            "prebuiltImageAttachedAt": utcnow().isoformat(),
        }
    )
    row.metadata_json = _json_dump(metadata)
    row.target_commit_sha = source_commit_sha
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row
