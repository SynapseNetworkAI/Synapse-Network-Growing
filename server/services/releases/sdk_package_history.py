"""Paginated SDK package release result history."""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.services.releases.sdk_package_catalog import SDK_REPO_FULL_NAME
from server.services.releases.sdk_package_helpers import clean, package_url_for
from server.services.releases.sdk_package_models import SdkPackageReleaseRow
from server.services.releases.sdk_package_schemas import (
    SdkPackageReleaseHistoryItemOut,
    SdkPackageReleaseHistoryPageOut,
)


SDK_REPO_URL = f"https://github.com/{SDK_REPO_FULL_NAME}"


def _require_anchor(db: Session, release_id: int) -> SdkPackageReleaseRow:
    row = (
        db.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == int(release_id))
        .first()
    )
    if row is None:
        raise ValueError("SDK package release not found.")
    return row


def _git_tag_url(row: SdkPackageReleaseRow) -> str | None:
    tag = clean(row.git_tag)
    return f"{SDK_REPO_URL}/tree/{tag}" if tag else None


def _history_item(row: SdkPackageReleaseRow) -> SdkPackageReleaseHistoryItemOut:
    return SdkPackageReleaseHistoryItemOut(
        id=int(row.id),
        release_train_version=clean(row.release_train_version),
        sdk_language=clean(row.sdk_language),
        package_name=clean(row.package_name),
        registry=clean(row.registry),
        channel=clean(row.channel) or "preview",
        package_version=clean(row.package_version),
        status=clean(row.status) or "planned",
        package_url=clean(row.package_url) or package_url_for(row),
        repo_url=SDK_REPO_URL,
        git_tag=clean(row.git_tag) or None,
        git_tag_url=_git_tag_url(row),
        workflow_run_url=clean(row.workflow_run_url) or None,
        failure_summary=clean(row.failure_summary) or None,
        published_at=row.published_at,
        updated_at=row.updated_at,
    )


def query_sdk_package_release_history(
    db: Session,
    release_id: int,
    *,
    q: str | None = None,
    status: str | None = None,
    channel: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> SdkPackageReleaseHistoryPageOut:
    anchor = _require_anchor(db, release_id)
    query = db.query(SdkPackageReleaseRow).filter(
        SdkPackageReleaseRow.sdk_language == clean(anchor.sdk_language),
        SdkPackageReleaseRow.registry == clean(anchor.registry),
        SdkPackageReleaseRow.package_name == clean(anchor.package_name),
    )
    if clean(status):
        query = query.filter(SdkPackageReleaseRow.status == clean(status).lower())
    if clean(channel):
        query = query.filter(SdkPackageReleaseRow.channel == clean(channel).lower())
    needle = clean(q)
    if needle:
        like = f"%{needle}%"
        query = query.filter(
            or_(
                SdkPackageReleaseRow.release_train_version.ilike(like),
                SdkPackageReleaseRow.sdk_language.ilike(like),
                SdkPackageReleaseRow.package_name.ilike(like),
                SdkPackageReleaseRow.registry.ilike(like),
                SdkPackageReleaseRow.channel.ilike(like),
                SdkPackageReleaseRow.package_version.ilike(like),
                SdkPackageReleaseRow.git_tag.ilike(like),
                SdkPackageReleaseRow.status.ilike(like),
                SdkPackageReleaseRow.failure_summary.ilike(like),
            )
        )
    safe_limit = max(1, min(int(limit or 10), 100))
    safe_offset = max(0, int(offset or 0))
    total = int(query.count())
    rows = (
        query.order_by(
            SdkPackageReleaseRow.updated_at.desc(), SdkPackageReleaseRow.id.desc()
        )
        .limit(safe_limit)
        .offset(safe_offset)
        .all()
    )
    return SdkPackageReleaseHistoryPageOut(
        items=[_history_item(row) for row in rows],
        total=total,
        limit=safe_limit,
        offset=safe_offset,
    )
