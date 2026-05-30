"""Serialization helpers for the agent-native bug workbench."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    BugEventRow,
    BugFixAttemptRow,
    BugRecordRow,
    ProjectPolicyRow,
)
from server.schemas_bugs import BugAgentContextOut, BugEventOut, BugFixAttemptOut


def json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _text_or_default(value: object, default: str) -> str:
    text = _text_or_none(value)
    if text is None:
        return default
    return text


def target_project_path(db: Session, row: BugRecordRow) -> str | None:
    root = str(getattr(row, "project_root_path", "") or "").strip()
    if root:
        return root
    project_key = str(getattr(row, "project_key", "") or "").strip()
    if not project_key:
        return None
    policy = (
        db.query(ProjectPolicyRow)
        .filter(ProjectPolicyRow.project_key == project_key)
        .first()
    )
    return str(getattr(policy, "root_path", "") or "").strip() or None


def serialize_fix_attempt(row: BugFixAttemptRow) -> BugFixAttemptOut:
    return BugFixAttemptOut(
        id=int(row.id),
        bug_id=int(row.bug_id),
        status=_text_or_default(row.status, "claimed"),
        agent_id=_text_or_default(row.agent_id, "agent"),
        branch_name=_text_or_none(row.branch_name),
        commit_sha=_text_or_none(row.commit_sha),
        pr_url=_text_or_none(row.pr_url),
        workflow_run_id=row.workflow_run_id,
        requirement_id=row.requirement_id,
        lease_expires_at=row.lease_expires_at,
        verification_summary=_text_or_none(row.verification_summary),
        verification_commands=json_loads(row.verification_commands_json, []),
        verification_screenshots=json_loads(row.verification_screenshots_json, []),
        failure_reason=_text_or_none(row.failure_reason),
        created_at=row.created_at,
        updated_at=row.updated_at,
        verified_at=row.verified_at,
    )


def serialize_bug_event(row: BugEventRow) -> BugEventOut:
    return BugEventOut(
        id=int(row.id),
        bug_id=int(row.bug_id),
        event_type=str(row.event_type or ""),
        actor=str(row.actor or "agent"),
        from_status=str(row.from_status or "") or None,
        to_status=str(row.to_status or "") or None,
        message=str(row.message or ""),
        metadata=json_loads(row.metadata_json, {}),
        created_at=row.created_at,
    )


def build_agent_context(db: Session, row: BugRecordRow) -> BugAgentContextOut:
    evidence = json_loads(row.evidence_json, [])
    metadata = json_loads(row.metadata_json, {})
    return BugAgentContextOut(
        bug_id=int(row.id),
        bug_key=str(row.bug_key or ""),
        project_key=str(row.project_key or "") or None,
        target_project_path=target_project_path(db, row),
        title=str(row.title or ""),
        summary=str(row.summary or ""),
        repro_steps=list(metadata.get("repro_steps") or []),
        expected_behavior=metadata.get("expected_behavior"),
        actual_behavior=metadata.get("actual_behavior"),
        evidence=evidence,
        acceptance_checks=list(metadata.get("acceptance_checks") or []),
        linked_requirement_id=row.converted_requirement_id,
        allowed_next_actions=[
            "claim",
            "materialize_requirement",
            "link_fix",
            "verify",
            "reopen",
        ],
    )
