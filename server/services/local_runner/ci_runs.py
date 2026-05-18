"""Local CI run persistence and event helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from server.database import LocalCiEventRow, LocalCiRunRow, utcnow
from server.services.local_runner.ci_schemas import (
    LocalCiRunCreateRequest,
    LocalCiRunOut,
    LocalCiRunResetRequest,
)
from server.services.local_runner.json_utils import json_dump, _json_load_dict

CI_EVENT_TYPES = {
    "stdout",
    "stderr",
    "step_started",
    "step_finished",
    "runner_status",
    "local_ci_force_reset",
}
DEFAULT_EVENT_LIMIT = 200
MAX_EVENT_LIMIT = 1000
VALID_CI_STATUSES = {"requested", "running", "passed", "failed", "cancelled"}
VALID_CI_SCOPES = {"auto", "full", "scoped"}


@dataclass(frozen=True)
class LocalCiEventsPage:
    items: list[LocalCiEventRow]
    next_sequence: int
    has_more: bool


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_event_type(event_type: str) -> str:
    normalized = _clean(event_type).lower()
    return normalized if normalized in CI_EVENT_TYPES else "runner_status"


def ci_run_to_out(row: LocalCiRunRow) -> LocalCiRunOut:
    return LocalCiRunOut(
        id=int(row.id),
        repo_path=_clean(row.repo_path),
        branch_name=_clean(row.branch_name),
        commit_sha=_clean(row.commit_sha),
        base_ref=_clean(row.base_ref) or "origin/main",
        scope=_clean(row.scope) or "auto",
        status=_clean(row.status) or "requested",
        actor=_clean(row.actor) or "operator",
        exit_code=int(row.exit_code) if row.exit_code is not None else None,
        summary=_clean(row.summary) or None,
        metadata=_json_load_dict(row.metadata_json),
        started_at=row.started_at,
        finished_at=row.finished_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def create_local_ci_run(db: Session, body: LocalCiRunCreateRequest) -> LocalCiRunRow:
    scope = _clean(body.scope).lower() or "auto"
    if scope not in VALID_CI_SCOPES:
        raise ValueError("scope must be one of: auto, scoped, full")
    repo_path = _clean(body.repo_path)
    branch_name = _clean(body.branch_name)
    commit_sha = _clean(body.commit_sha)
    if not repo_path:
        raise ValueError("repo_path is required.")
    if not branch_name:
        raise ValueError("branch_name is required.")
    if not commit_sha:
        raise ValueError("commit_sha is required.")
    row = LocalCiRunRow(
        repo_path=repo_path,
        branch_name=branch_name,
        commit_sha=commit_sha,
        base_ref=_clean(body.base_ref) or "origin/main",
        scope=scope,
        status="requested",
        actor=_clean(body.actor) or "operator",
        metadata_json=json_dump(dict(body.metadata or {})),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_local_ci_runs(
    db: Session,
    *,
    status: str | None = None,
    repo_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[LocalCiRunRow], int, int, int]:
    bounded_limit = max(1, min(int(limit or 50), 100))
    bounded_offset = max(0, int(offset or 0))
    query = db.query(LocalCiRunRow)
    if _clean(status):
        query = query.filter(LocalCiRunRow.status == _clean(status).lower())
    if _clean(repo_path):
        query = query.filter(LocalCiRunRow.repo_path == _clean(repo_path))
    total = int(query.count())
    rows = (
        query.order_by(LocalCiRunRow.created_at.desc(), LocalCiRunRow.id.desc())
        .offset(bounded_offset)
        .limit(bounded_limit)
        .all()
    )
    return rows, total, bounded_limit, bounded_offset


def get_local_ci_run(db: Session, run_id: int) -> LocalCiRunRow:
    row = db.get(LocalCiRunRow, int(run_id))
    if row is None:
        raise ValueError("Local CI run not found.")
    return row


def append_local_ci_event(
    db: Session,
    *,
    ci_run_id: int,
    event_type: str,
    message: str,
    step_key: str | None = None,
) -> LocalCiEventRow:
    row = get_local_ci_run(db, ci_run_id)
    next_sequence = (
        db.query(func.coalesce(func.max(LocalCiEventRow.sequence), 0))
        .filter(LocalCiEventRow.ci_run_id == int(row.id))
        .scalar()
        or 0
    ) + 1
    event = LocalCiEventRow(
        ci_run_id=int(row.id),
        sequence=int(next_sequence),
        event_type=_normalize_event_type(event_type),
        step_key=_clean(step_key) or None,
        message=str(message or ""),
    )
    db.add(event)
    db.flush()
    return event


def list_local_ci_events(
    db: Session,
    *,
    ci_run_id: int,
    after_sequence: int = 0,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> LocalCiEventsPage:
    get_local_ci_run(db, ci_run_id)
    bounded_limit = max(1, min(int(limit or DEFAULT_EVENT_LIMIT), MAX_EVENT_LIMIT))
    cursor = max(0, int(after_sequence or 0))
    rows = (
        db.query(LocalCiEventRow)
        .filter(
            LocalCiEventRow.ci_run_id == int(ci_run_id),
            LocalCiEventRow.sequence > cursor,
        )
        .order_by(LocalCiEventRow.sequence.asc(), LocalCiEventRow.id.asc())
        .limit(bounded_limit + 1)
        .all()
    )
    has_more = len(rows) > bounded_limit
    items = rows[:bounded_limit]
    next_sequence = int(items[-1].sequence) if items else cursor
    return LocalCiEventsPage(
        items=items, next_sequence=next_sequence, has_more=has_more
    )


def reset_local_ci_run(
    db: Session, run_id: int, body: LocalCiRunResetRequest
) -> LocalCiRunRow:
    row = get_local_ci_run(db, run_id)
    if _clean(body.confirm_phrase) != "RESET_LOCAL_CI":
        raise ValueError("Reset requires confirm_phrase=RESET_LOCAL_CI.")
    if _clean(row.status) in {"passed", "cancelled"}:
        raise ValueError("Passed or cancelled local CI runs cannot be reset.")
    reason = _clean(body.reason) or "Operator reset local CI run."
    row.status = "requested"
    row.exit_code = None
    row.summary = reason
    row.started_at = None
    row.finished_at = None
    row.updated_at = utcnow()
    append_local_ci_event(
        db,
        ci_run_id=int(row.id),
        event_type="local_ci_force_reset",
        step_key="reset",
        message=f"Local CI force reset by {_clean(body.actor) or 'operator'}: {reason}",
    )
    db.commit()
    db.refresh(row)
    return row


def claim_local_ci_run(db: Session, run_id: int | None = None) -> LocalCiRunRow | None:
    query = db.query(LocalCiRunRow).filter(LocalCiRunRow.status == "requested")
    if run_id is not None:
        query = query.filter(LocalCiRunRow.id == int(run_id))
    row = (
        query.order_by(LocalCiRunRow.created_at.asc(), LocalCiRunRow.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if row is None:
        return None
    row.status = "running"
    row.started_at = utcnow()
    row.updated_at = utcnow()
    db.flush()
    append_local_ci_event(
        db,
        ci_run_id=int(row.id),
        event_type="runner_status",
        step_key="claim",
        message="Local CI runner claimed this run.\n",
    )
    db.commit()
    db.refresh(row)
    return row


def finish_local_ci_run(
    db: Session,
    run_id: int,
    *,
    exit_code: int,
    summary: str | None = None,
) -> LocalCiRunRow:
    row = get_local_ci_run(db, run_id)
    row.exit_code = int(exit_code)
    row.status = "passed" if int(exit_code) == 0 else "failed"
    row.summary = _clean(summary) or (
        "Local CI passed." if int(exit_code) == 0 else "Local CI failed."
    )
    row.finished_at = utcnow()
    row.updated_at = utcnow()
    append_local_ci_event(
        db,
        ci_run_id=int(row.id),
        event_type="runner_status",
        step_key="finish",
        message=f"{row.summary}\n",
    )
    db.commit()
    db.refresh(row)
    return row
