"""Release evidence adapter for deployment governance."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import ReleaseRecordRow, RequirementRow


def requirement_delivery_payload(db: Session, requirement_id: int) -> dict[str, Any]:
    release = _latest_release_record(db, requirement_id)
    if release is None:
        return {}
    metadata = _json_load(getattr(release, "metadata_json", None), {})
    return {
        **metadata,
        "latest_remote_sha": str(getattr(release, "commit_sha", "") or "").strip()
        or None,
        "latest_commit_sha": str(getattr(release, "commit_sha", "") or "").strip()
        or None,
        "head_branch": _release_head_branch(release),
        "branch_name": str(getattr(release, "branch_name", "") or "").strip() or None,
    }


def resolve_commit_sha(
    db: Session, requirement: RequirementRow, explicit_commit_sha: str | None = None
) -> str:
    if explicit_commit_sha and explicit_commit_sha.strip():
        return explicit_commit_sha.strip()
    payload = requirement_delivery_payload(db, int(requirement.id))
    commit_sha = (
        str(payload.get("latest_remote_sha") or "").strip()
        or str(payload.get("latest_commit_sha") or "").strip()
    )
    if commit_sha:
        return commit_sha
    raise ValueError(
        "Requirement is missing a deliverable commit SHA. Sync branch delivery before deploy."
    )


def _json_load(
    raw: str | None, fallback: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not raw:
        return dict(fallback or {})
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(fallback or {})
    if not isinstance(data, dict):
        return dict(fallback or {})
    return dict(data)


def _latest_release_record(db: Session, requirement_id: int) -> ReleaseRecordRow | None:
    return (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == requirement_id)
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )


def _release_head_branch(release: ReleaseRecordRow) -> str | None:
    return (
        str(
            getattr(release, "actual_branch_name", "")
            or getattr(release, "branch_name", "")
            or ""
        ).strip()
        or None
    )
