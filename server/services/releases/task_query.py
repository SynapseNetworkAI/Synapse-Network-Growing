"""Paginated release task query for high-volume release lists."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow
from server.services.releases.task_query_schemas import ReleaseTaskPageOut
from server.services.releases.tasks import (
    _clean,
    _release_task_to_out,
)


def _filtered_query(
    db: Session,
    *,
    project_key: str | None,
    environment: str | None,
    status: str | None,
    source_type: str | None,
    q: str | None,
):
    query = db.query(ReleaseTaskRow)
    filters = {
        ReleaseTaskRow.project_key: _clean(project_key),
        ReleaseTaskRow.environment: _clean(environment).lower(),
        ReleaseTaskRow.status: _clean(status).lower(),
        ReleaseTaskRow.source_type: _clean(source_type).lower(),
    }
    for column, value in filters.items():
        if value:
            query = query.filter(column == value)
    needle = _clean(q)
    if not needle:
        return query
    like = f"%{needle}%"
    return query.filter(
        or_(
            ReleaseTaskRow.project_key.ilike(like),
            ReleaseTaskRow.project_display_name.ilike(like),
            ReleaseTaskRow.service_key.ilike(like),
            ReleaseTaskRow.branch_name.ilike(like),
            ReleaseTaskRow.status.ilike(like),
            ReleaseTaskRow.actor.ilike(like),
            ReleaseTaskRow.operator.ilike(like),
            ReleaseTaskRow.note.ilike(like),
        )
    )


def query_release_tasks(
    db: Session,
    *,
    project_key: str | None = None,
    environment: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    q: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> ReleaseTaskPageOut:
    query = _filtered_query(
        db,
        project_key=project_key,
        environment=environment,
        status=status,
        source_type=source_type,
        q=q,
    )
    total = int(query.count())
    safe_limit = min(max(1, int(limit)), 100)
    safe_offset = max(0, int(offset))
    rows = (
        query.order_by(
            ReleaseTaskRow.updated_at.desc(),
            ReleaseTaskRow.id.desc(),
        )
        .limit(safe_limit)
        .offset(safe_offset)
        .all()
    )
    items = [_release_task_to_out(row) for row in rows]
    return ReleaseTaskPageOut(
        items=items, total=total, limit=safe_limit, offset=safe_offset
    )
