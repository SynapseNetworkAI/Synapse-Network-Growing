from __future__ import annotations

"""Scoped session registry for Codex CLI thread reuse."""

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from server import config
from server.database import CodexSessionRow, utcnow


def build_session_key(*, role_key: str, project_root: str, requirement_id: int | None) -> str:
    raw = f"{role_key.strip().lower()}|{project_root.strip()}|{int(requirement_id or 0)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def find_reusable_session(
    db: Session,
    *,
    role_key: str,
    project_root: str,
    requirement_id: int | None,
) -> CodexSessionRow | None:
    session_key = build_session_key(role_key=role_key, project_root=project_root, requirement_id=requirement_id)
    row = (
        db.query(CodexSessionRow)
        .filter(CodexSessionRow.session_key == session_key)
        .order_by(CodexSessionRow.updated_at.desc(), CodexSessionRow.id.desc())
        .first()
    )
    if row is None or not str(row.thread_id or "").strip():
        return None
    if str(row.status or "") not in {"completed", "resumable"}:
        return None
    ttl = max(60, int(config.CODEX_CLI_SESSION_REUSE_TTL_SECONDS))
    last_used = row.last_used_at or row.updated_at or row.created_at
    if last_used is None:
        return None
    if utcnow() > last_used + timedelta(seconds=ttl):
        row.status = "expired"
        db.commit()
        return None
    return row


def upsert_session_launch(
    db: Session,
    *,
    role_key: str,
    project_root: str,
    requirement_id: int | None,
    workflow_run_id: int | None,
    task_id: int,
    thread_id: str | None,
    status: str,
    resume_count: int = 0,
    metadata: dict[str, Any] | None = None,
) -> CodexSessionRow:
    session_key = build_session_key(role_key=role_key, project_root=project_root, requirement_id=requirement_id)
    row = db.query(CodexSessionRow).filter(CodexSessionRow.session_key == session_key).first()
    if row is None:
        row = CodexSessionRow(
            session_key=session_key,
            role_key=role_key,
            project_root=project_root,
            requirement_id=requirement_id,
            workflow_run_id=workflow_run_id,
        )
        db.add(row)
    row.current_task_id = task_id
    row.thread_id = thread_id or row.thread_id
    row.status = status
    row.last_used_at = utcnow()
    row.last_heartbeat_at = row.last_heartbeat_at or utcnow()
    row.resume_count = int(resume_count)
    row.metadata_json = json.dumps(metadata or {}, default=str)
    db.flush()
    return row


def update_session_state(
    db: Session,
    *,
    role_key: str,
    project_root: str,
    requirement_id: int | None,
    thread_id: str | None = None,
    status: str | None = None,
    heartbeat: bool = False,
    current_task_id: int | None = None,
    resume_count: int | None = None,
    metadata_patch: dict[str, Any] | None = None,
) -> CodexSessionRow | None:
    session_key = build_session_key(role_key=role_key, project_root=project_root, requirement_id=requirement_id)
    row = db.query(CodexSessionRow).filter(CodexSessionRow.session_key == session_key).first()
    if row is None:
        return None
    if thread_id:
        row.thread_id = thread_id
    if status:
        row.status = status
    if heartbeat:
        row.last_heartbeat_at = utcnow()
    row.last_used_at = utcnow()
    if current_task_id is not None:
        row.current_task_id = current_task_id
    if resume_count is not None:
        row.resume_count = int(resume_count)
    if metadata_patch:
        try:
            payload = json.loads(str(row.metadata_json or "{}"))
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        payload.update(metadata_patch)
        row.metadata_json = json.dumps(payload, default=str)
    db.flush()
    return row

