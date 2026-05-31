"""Agent-native bug backlog and fix-attempt workflow helpers."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from server.database import (
    BugEventRow,
    BugFixAttemptRow,
    BugRecordRow,
)
from server.schemas import BugRecordOut
from server.schemas_bugs import (
    BugAgentQueueOut,
    BugClaimResultOut,
    BugDetailOut,
    BugListOut,
)
from server.services.bugs import automation as bug_automation
from server.services.bugs.intake import serialize_bug_record
from server.services.bugs.policy import (
    allowed_next_actions,
    ensure_close_evidence,
    verification_status,
)
from server.services.bugs.serializer import (
    build_agent_context,
    json_loads,
    serialize_bug_event,
    serialize_fix_attempt,
)
from server.services.requirements.sources import materialize_bug_backlog
from server.services.requirements import service as requirement_service

project_attempt_from_workflow = bug_automation.project_attempt_from_workflow
requirement_workflow_binding = bug_automation.requirement_workflow_binding
run_claim_and_run_bug = bug_automation.run_claim_and_run_bug
start_requirement_workflow = requirement_service.start_requirement_workflow

ACTIVE_ATTEMPT_STATUSES = {"claimed", "fixing", "fixed_pending_verification"}
AGENT_QUEUE_STATUSES = {"open", "triaged", "ready_for_agent", "reopened"}
BUG_STATUSES = {
    "open",
    "triaged",
    "ready_for_agent",
    "fixing",
    "fixed_pending_verification",
    "verified",
    "closed",
    "reopened",
    "failed",
    "duplicate",
    "wontfix",
    "converted",
}
FIX_STATUSES = {
    "claimed",
    "fixing",
    "fixed_pending_verification",
    "verified",
    "failed",
    "abandoned",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bug_or_404(db: Session, bug_id: int) -> BugRecordRow:
    row = db.query(BugRecordRow).filter(BugRecordRow.id == int(bug_id)).first()
    if row is None:
        raise ValueError("bug not found")
    return row


def _event(
    db: Session,
    row: BugRecordRow,
    event_type: str,
    *,
    actor: str = "agent",
    from_status: str | None = None,
    to_status: str | None = None,
    message: str = "",
    metadata: dict[str, object] | None = None,
) -> None:
    db.add(
        BugEventRow(
            bug_id=int(row.id),
            event_type=event_type,
            actor=str(actor or "agent"),
            from_status=from_status,
            to_status=to_status,
            message=str(message or ""),
            metadata_json=_json_dumps(metadata or {}),
        )
    )


def latest_fix_attempt(db: Session, bug_id: int) -> BugFixAttemptRow | None:
    return (
        db.query(BugFixAttemptRow)
        .filter(BugFixAttemptRow.bug_id == int(bug_id))
        .order_by(BugFixAttemptRow.updated_at.desc(), BugFixAttemptRow.id.desc())
        .first()
    )


def active_fix_attempt(db: Session, bug_id: int) -> BugFixAttemptRow | None:
    return (
        db.query(BugFixAttemptRow)
        .filter(
            BugFixAttemptRow.bug_id == int(bug_id),
            BugFixAttemptRow.status.in_(tuple(ACTIVE_ATTEMPT_STATUSES)),
        )
        .order_by(BugFixAttemptRow.updated_at.desc(), BugFixAttemptRow.id.desc())
        .first()
    )


def _editable_fix_attempt(db: Session, bug_id: int) -> BugFixAttemptRow | None:
    active = active_fix_attempt(db, bug_id)
    if active is not None:
        return active
    return latest_fix_attempt(db, bug_id)


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _payload_text(
    payload: dict[str, object], key: str, current: object = None
) -> str | None:
    value = payload.get(key)
    if value is None:
        value = current
    return _clean_text(value)


def _payload_value(
    payload: dict[str, object], key: str, current: object = None
) -> object:
    value = payload.get(key)
    if value is None:
        return current
    return value


def _payload_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return value


def _sync_attempts(db: Session, rows: list[BugRecordRow]) -> None:
    changed = False
    for row in rows:
        attempt = latest_fix_attempt(db, int(row.id))
        if attempt is None:
            continue
        if project_attempt_from_workflow(db, row, attempt):
            db.add(attempt)
            db.add(row)
            changed = True
    if changed:
        db.commit()


def bug_detail(db: Session, bug_id: int) -> BugDetailOut:
    row = _bug_or_404(db, bug_id)
    _sync_attempts(db, [row])
    row = _bug_or_404(db, bug_id)
    attempts = (
        db.query(BugFixAttemptRow)
        .filter(BugFixAttemptRow.bug_id == int(row.id))
        .order_by(BugFixAttemptRow.updated_at.desc(), BugFixAttemptRow.id.desc())
        .all()
    )
    events = (
        db.query(BugEventRow)
        .filter(BugEventRow.bug_id == int(row.id))
        .order_by(BugEventRow.created_at.desc(), BugEventRow.id.desc())
        .all()
    )
    return BugDetailOut(
        bug=BugRecordOut(**serialize_bug_record(row)),
        latest_fix_attempt=serialize_fix_attempt(attempts[0]) if attempts else None,
        fix_attempts=[serialize_fix_attempt(item) for item in attempts],
        events=[serialize_bug_event(item) for item in events],
        agent_context=build_agent_context(
            db,
            row,
            allowed_next_actions=allowed_next_actions(
                row, attempts[0] if attempts else None
            ),
        ),
    )


def list_bugs(
    db: Session,
    *,
    project_key: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    source_key: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> BugListOut:
    query = db.query(BugRecordRow)
    if project_key:
        query = query.filter(BugRecordRow.project_key == project_key)
    if status:
        query = query.filter(BugRecordRow.status == status)
    if severity:
        query = query.filter(BugRecordRow.severity == severity)
    if source_key:
        query = query.filter(BugRecordRow.source_key == source_key)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            or_(
                BugRecordRow.title.ilike(needle),
                BugRecordRow.summary.ilike(needle),
                BugRecordRow.bug_key.ilike(needle),
                BugRecordRow.fingerprint.ilike(needle),
            )
        )
    total = query.count()
    severity_order = case(
        (BugRecordRow.severity == "critical", 0),
        (BugRecordRow.severity == "high", 1),
        (BugRecordRow.severity == "normal", 2),
        else_=3,
    )
    limit = max(1, min(int(limit or 50), 100))
    offset = max(0, int(offset or 0))
    rows = (
        query.order_by(
            severity_order.asc(),
            BugRecordRow.last_seen_at.desc(),
            BugRecordRow.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    _sync_attempts(db, rows)
    return BugListOut(
        items=[BugRecordOut(**serialize_bug_record(row)) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        status_counts=_count_by(query, BugRecordRow.status),
        severity_counts=_count_by(query, BugRecordRow.severity),
    )


def _count_by(query: Any, column: Any) -> dict[str, int]:
    return {
        str(key): int(count)
        for key, count in query.with_entities(column, func.count(BugRecordRow.id))
        .group_by(column)
        .all()
    }


def agent_queue(db: Session, *, limit: int = 20, offset: int = 0) -> BugAgentQueueOut:
    rows = (
        db.query(BugRecordRow)
        .filter(BugRecordRow.status.in_(tuple(AGENT_QUEUE_STATUSES)))
        .order_by(BugRecordRow.last_seen_at.desc(), BugRecordRow.id.desc())
        .offset(max(0, int(offset or 0)))
        .limit(max(1, min(int(limit or 20), 50)))
        .all()
    )
    return BugAgentQueueOut(
        items=[bug_detail(db, int(row.id)) for row in rows],
        total=db.query(BugRecordRow)
        .filter(BugRecordRow.status.in_(tuple(AGENT_QUEUE_STATUSES)))
        .count(),
        limit=max(1, min(int(limit or 20), 50)),
        offset=max(0, int(offset or 0)),
    )


def claim_bug(
    db: Session, bug_id: int, *, agent_id: str, lease_minutes: int = 120
) -> BugClaimResultOut:
    row = _bug_or_404(db, bug_id)
    active = active_fix_attempt(db, int(row.id))
    if active is not None:
        raise ValueError("bug already has an active fix attempt")
    now = _utcnow()
    from_status = str(row.status or "open")
    row.status = "fixing"
    attempt = BugFixAttemptRow(
        bug_id=int(row.id),
        status="claimed",
        agent_id=str(agent_id or "agent"),
        requirement_id=row.converted_requirement_id,
        lease_token=secrets.token_urlsafe(16),
        lease_expires_at=now
        + timedelta(minutes=max(15, min(int(lease_minutes or 120), 24 * 60))),
    )
    db.add(attempt)
    _event(
        db,
        row,
        "claimed",
        actor=attempt.agent_id,
        from_status=from_status,
        to_status=row.status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    db.refresh(attempt)
    return BugClaimResultOut(
        bug=BugRecordOut(**serialize_bug_record(row)),
        fix_attempt=serialize_fix_attempt(attempt),
        agent_context=build_agent_context(
            db, row, allowed_next_actions=allowed_next_actions(row, attempt)
        ),
    )


def materialize_bug_requirement(db: Session, bug_id: int) -> BugDetailOut:
    row = _bug_or_404(db, bug_id)
    previous = row.converted_requirement_id
    result = materialize_bug_backlog(
        db,
        refresh=False,
        auto_start=True,
        min_score=0.0,
        max_created=1,
        bug_ids=[int(row.id)],
    )
    db.refresh(row)
    if row.converted_requirement_id is None:
        raise ValueError("bug could not be materialized into a requirement")
    if previous != row.converted_requirement_id:
        _event(
            db,
            row,
            "requirement_created",
            actor="agent",
            message=f"Created requirement #{row.converted_requirement_id}",
            metadata={"materialize_result": result},
        )
        db.commit()
    return bug_detail(db, int(row.id))


def claim_and_run_bug(
    db: Session, bug_id: int, *, agent_id: str, lease_minutes: int = 120
) -> BugDetailOut:
    return run_claim_and_run_bug(
        db, bug_id, agent_id=agent_id, lease_minutes=lease_minutes
    )


def link_bug_fix(db: Session, bug_id: int, payload: dict[str, object]) -> BugDetailOut:
    row = _bug_or_404(db, bug_id)
    attempt = _editable_fix_attempt(db, int(row.id))
    if attempt is None:
        raise ValueError("claim the bug before linking a fix")
    attempt.branch_name = _payload_text(payload, "branch_name", attempt.branch_name)
    attempt.commit_sha = _payload_text(payload, "commit_sha", attempt.commit_sha)
    attempt.pr_url = _payload_text(payload, "pr_url", attempt.pr_url)
    attempt.workflow_run_id = _payload_value(
        payload, "workflow_run_id", attempt.workflow_run_id
    )
    attempt.requirement_id = _payload_value(
        payload,
        "requirement_id",
        attempt.requirement_id or row.converted_requirement_id,
    )
    attempt.status = "fixing"
    row.status = "fixing"
    metadata = json_loads(row.metadata_json, {})
    metadata["latest_fix"] = {
        "branch_name": attempt.branch_name,
        "commit_sha": attempt.commit_sha,
        "pr_url": attempt.pr_url,
        "workflow_run_id": attempt.workflow_run_id,
        "requirement_id": attempt.requirement_id,
    }
    row.metadata_json = _json_dumps(metadata)
    _event(
        db,
        row,
        "commit_linked",
        actor=_payload_text(payload, "agent_id", attempt.agent_id) or "agent",
        to_status=row.status,
        metadata=metadata["latest_fix"],
    )
    db.add(attempt)
    db.add(row)
    db.commit()
    return bug_detail(db, int(row.id))


def add_bug_verification(
    db: Session, bug_id: int, payload: dict[str, object]
) -> BugDetailOut:
    row = _bug_or_404(db, bug_id)
    attempt = _editable_fix_attempt(db, int(row.id))
    if attempt is None:
        raise ValueError("claim the bug before adding verification")
    target_status = verification_status(
        {"status": _payload_text(payload, "status", "fixed_pending_verification")}
    )
    summary = _payload_text(payload, "summary")
    if summary is None:
        raise ValueError("verification summary is required")
    attempt.verification_summary = summary
    attempt.verification_commands_json = _json_dumps(_payload_list(payload, "commands"))
    attempt.verification_screenshots_json = _json_dumps(
        _payload_list(payload, "screenshots")
    )
    attempt.status = target_status
    if target_status == "verified":
        attempt.verified_at = _utcnow()
    previous = str(row.status or "open")
    row.status = "verified" if target_status == "verified" else target_status
    _event(
        db,
        row,
        "verification_added",
        actor=_payload_text(payload, "agent_id", attempt.agent_id) or "agent",
        from_status=previous,
        to_status=row.status,
    )
    db.add(attempt)
    db.add(row)
    db.commit()
    return bug_detail(db, int(row.id))


def close_bug(db: Session, bug_id: int, *, actor: str, resolution: str) -> BugDetailOut:
    row = _bug_or_404(db, bug_id)
    attempt = latest_fix_attempt(db, int(row.id))
    ensure_close_evidence(row, attempt)
    previous = str(row.status or "verified")
    row.status = "closed"
    _event(
        db,
        row,
        "closed",
        actor=actor,
        from_status=previous,
        to_status="closed",
        metadata={"resolution": resolution},
    )
    db.add(row)
    db.commit()
    return bug_detail(db, int(row.id))


def reopen_bug(db: Session, bug_id: int, *, actor: str, reason: str) -> BugDetailOut:
    row = _bug_or_404(db, bug_id)
    previous = str(row.status or "open")
    row.status = "reopened"
    metadata = json_loads(row.metadata_json, {})
    metadata["last_reopen_reason"] = str(reason or "").strip()
    row.metadata_json = _json_dumps(metadata)
    _event(
        db,
        row,
        "reopened",
        actor=actor,
        from_status=previous,
        to_status="reopened",
        message=str(reason or ""),
    )
    db.add(row)
    db.commit()
    return bug_detail(db, int(row.id))
