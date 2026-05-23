"""Staging deployment evidence helpers for production promotion gates."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow
from server.services.releases.tasks import _clean, _json_load


def deployment_commit_sha(row: DeploymentRecordRow) -> str:
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    return (
        _clean(getattr(row, "commit_sha", None))
        or _clean(metadata.get("resolvedCommitSha"))
        or _clean(metadata.get("resolved_commit_sha"))
        or _clean(metadata.get("githubHeadSha"))
        or _clean(metadata.get("headSha"))
        or _clean(metadata.get("commitSha"))
        or _clean(metadata.get("commit_sha"))
    )


def deployment_service_key(row: DeploymentRecordRow) -> str:
    metadata = _json_load(getattr(row, "metadata_json", None), {})
    return _clean(
        metadata.get("service_key")
        or metadata.get("serviceKey")
        or metadata.get("deployScope")
        or metadata.get("deploy_scope")
    )


def successful_staging_deployment_for_commit(
    db: Session,
    *,
    project_key: str,
    service_key: str,
    commit_sha: str,
) -> DeploymentRecordRow | None:
    rows = _successful_staging_rows(db, project_key=project_key, branch_name=None)
    for row in rows:
        if deployment_service_key(row) != service_key:
            continue
        if deployment_commit_sha(row) == commit_sha:
            return row
    return None


def latest_successful_staging_deployment(
    db: Session,
    *,
    project_key: str,
    service_key: str,
) -> DeploymentRecordRow | None:
    rows = _successful_staging_rows(db, project_key=project_key, branch_name="main")
    for row in rows:
        if deployment_service_key(row) == service_key and deployment_commit_sha(row):
            return row
    return None


def _successful_staging_rows(
    db: Session,
    *,
    project_key: str,
    branch_name: str | None,
) -> list[DeploymentRecordRow]:
    query = db.query(DeploymentRecordRow).filter(
        DeploymentRecordRow.project_key == project_key,
        DeploymentRecordRow.environment == "staging",
        DeploymentRecordRow.status == "succeeded",
        DeploymentRecordRow.health_status.in_(["passed", "healthy", "manual_verified"]),
    )
    if branch_name is not None:
        query = query.filter(DeploymentRecordRow.branch_name == branch_name)
    return query.order_by(DeploymentRecordRow.id.desc()).limit(50).all()
