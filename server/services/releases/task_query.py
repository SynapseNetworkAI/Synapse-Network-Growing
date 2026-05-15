"""Paginated release task query for high-volume release lists."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import ReleaseTaskRow
from server.schemas import ReleaseTaskPrGateOut
from server.services.releases.task_query_schemas import ReleaseTaskPageOut
from server.services.releases.tasks import (
    _clean,
    _policy_for_project,
    _release_task_deploy_repo,
    _release_task_pr_gate_for,
    _release_task_pr_gate_with_row_actions,
    _release_task_to_out,
)
from server.services.releases.production_tasks import release_task_production_gate


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


def _pr_gate_for_row(
    db: Session,
    row: ReleaseTaskRow,
    *,
    repo_cache: dict[str, str],
    gate_cache: dict[tuple[str, str], ReleaseTaskPrGateOut],
) -> ReleaseTaskPrGateOut | None:
    project_key_value = _clean(row.project_key)
    branch_name = _clean(row.branch_name)
    environment = _clean(row.environment).lower()
    if environment not in {"staging", "production"} or not branch_name:
        return None
    try:
        repo_full_name = repo_cache.get(project_key_value)
        if repo_full_name is None:
            policy = _policy_for_project(db, project_key_value)
            repo_full_name = _release_task_deploy_repo(policy, project_key_value)
            repo_cache[project_key_value] = repo_full_name
        if environment == "production":
            return release_task_production_gate(db, row, repo_full_name)
        cache_key = (repo_full_name, branch_name)
        pr_gate = gate_cache.get(cache_key)
        if pr_gate is None:
            pr_gate = _release_task_pr_gate_for(row, repo_full_name)
            gate_cache[cache_key] = pr_gate
        return _release_task_pr_gate_with_row_actions(row, pr_gate)
    except ValueError as exc:
        return ReleaseTaskPrGateOut(blocked_reason=str(exc))


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
    repo_cache: dict[str, str] = {}
    gate_cache: dict[tuple[str, str], ReleaseTaskPrGateOut] = {}
    items = []
    for row in rows:
        pr_gate = _pr_gate_for_row(
            db, row, repo_cache=repo_cache, gate_cache=gate_cache
        )
        items.append(_release_task_to_out(row, pr_gate=pr_gate))
    return ReleaseTaskPageOut(
        items=items, total=total, limit=safe_limit, offset=safe_offset
    )
