"""Manual release task surface.

Release tasks represent release intent and human closure. They do not trigger
deployment workflows in v1.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import ProjectPolicyRow, ReleaseTaskRow, RequirementRow, utcnow
from server.schemas import ReleaseTaskOut

VALID_SOURCE_TYPES = {"manual", "requirement_flow"}
VALID_ENVIRONMENTS = {"staging", "production"}
VALID_STATUSES = {"requested", "completed", "failed", "cancelled"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _release_task_to_out(row: ReleaseTaskRow) -> ReleaseTaskOut:
    return ReleaseTaskOut(
        id=int(row.id),
        source_type=str(row.source_type or "manual"),
        requirement_id=int(row.requirement_id) if row.requirement_id is not None else None,
        deployment_record_id=int(row.deployment_record_id) if row.deployment_record_id is not None else None,
        project_key=str(row.project_key or ""),
        project_display_name=_clean(row.project_display_name) or None,
        branch_name=str(row.branch_name or ""),
        environment=str(row.environment or ""),
        status=str(row.status or "requested"),
        actor=_clean(row.actor) or None,
        operator=_clean(row.operator) or None,
        note=_clean(row.note) or None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _project_display_name(db: Session, project_key: str, explicit: str | None) -> str | None:
    if _clean(explicit):
        return _clean(explicit)
    policy = (
        db.query(ProjectPolicyRow)
        .filter(ProjectPolicyRow.project_key == project_key)
        .order_by(ProjectPolicyRow.id.desc())
        .first()
    )
    return _clean(getattr(policy, "display_name", None)) or None


def list_release_tasks(
    db: Session,
    *,
    project_key: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
) -> list[ReleaseTaskOut]:
    query = db.query(ReleaseTaskRow)
    if _clean(project_key):
        query = query.filter(ReleaseTaskRow.project_key == _clean(project_key))
    if _clean(environment):
        query = query.filter(ReleaseTaskRow.environment == _clean(environment).lower())
    if _clean(status):
        query = query.filter(ReleaseTaskRow.status == _clean(status).lower())
    if _clean(source_type):
        query = query.filter(ReleaseTaskRow.source_type == _clean(source_type).lower())
    rows = query.order_by(ReleaseTaskRow.updated_at.desc(), ReleaseTaskRow.id.desc()).all()
    return [_release_task_to_out(row) for row in rows]


def create_release_task(db: Session, body: Any) -> ReleaseTaskOut:
    source_type = _clean(getattr(body, "source_type", "manual")).lower() or "manual"
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError("source_type must be manual or requirement_flow")
    environment = _clean(getattr(body, "environment", "")).lower()
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError("environment must be staging or production")
    project_key = _clean(getattr(body, "project_key", ""))
    if not project_key:
        raise ValueError("project_key is required")
    branch_name = _clean(getattr(body, "branch_name", ""))
    if not branch_name:
        raise ValueError("branch_name is required")
    requirement_id = int(getattr(body, "requirement_id", 0) or 0) or None
    if source_type == "manual":
        requirement_id = None
    elif requirement_id is not None and db.get(RequirementRow, requirement_id) is None:
        raise ValueError("Requirement not found.")
    row = ReleaseTaskRow(
        source_type=source_type,
        requirement_id=requirement_id,
        deployment_record_id=None,
        project_key=project_key,
        project_display_name=_project_display_name(db, project_key, getattr(body, "project_display_name", None)),
        branch_name=branch_name,
        environment=environment,
        status="requested",
        actor=_clean(getattr(body, "actor", "operator")) or "operator",
        operator=None,
        note=_clean(getattr(body, "note", None)) or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _release_task_to_out(row)


def update_release_task(db: Session, task_id: int, body: Any) -> ReleaseTaskOut:
    row = db.get(ReleaseTaskRow, int(task_id))
    if row is None:
        raise ValueError("Release task not found.")
    current_status = _clean(row.status).lower() or "requested"
    if current_status in TERMINAL_STATUSES:
        raise ValueError("Terminal release task cannot be changed.")
    next_status = _clean(getattr(body, "status", "")).lower()
    if next_status not in TERMINAL_STATUSES:
        raise ValueError("status must be completed, failed, or cancelled")
    row.status = next_status
    row.operator = _clean(getattr(body, "operator", "operator")) or "operator"
    if getattr(body, "note", None) is not None:
        row.note = _clean(getattr(body, "note", None)) or None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _release_task_to_out(row)
