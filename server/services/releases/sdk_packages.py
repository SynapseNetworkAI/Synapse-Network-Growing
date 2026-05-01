"""SDK package release records for the release center."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy.orm import Session

from server.database import utcnow
from server.services.releases.sdk_package_catalog import (
    PACKAGE_CATALOG,
    SDK_PUBLISH_REF,
    SDK_PUBLISH_WORKFLOW_FILE,
    SDK_REPO_FULL_NAME,
    TERMINAL_STATUSES,
)
from server.services.releases.sdk_package_helpers import (
    clean,
    git_tag_for,
    json_dump,
    package_languages,
    package_release_event_to_out,
    package_release_to_out,
    package_url_for,
    record_event,
    validate_channel,
    validate_version,
)
from server.services.releases.sdk_package_models import (
    SdkPackageReleaseEventRow,
    SdkPackageReleaseRow,
)
from server.services.releases.sdk_package_schemas import (
    SdkPackageReleaseActionRequest,
    SdkPackageReleaseEventOut,
    SdkPackageReleaseInitializeRequest,
    SdkPackageReleaseOut,
    SdkPackageReleaseSyncResult,
    SdkReleaseTrainOut,
)
from server.services.delivery.deployment_governance import _dispatch_github_workflow
from server.services.releases.tasks import (
    _github_actions_run_id_from_url,
    _github_actions_run_view,
)


def list_sdk_package_releases(
    db: Session,
    *,
    release_train_version: str | None = None,
    sdk_language: str | None = None,
    status: str | None = None,
) -> list[SdkPackageReleaseOut]:
    query = db.query(SdkPackageReleaseRow)
    if clean(release_train_version):
        query = query.filter(
            SdkPackageReleaseRow.release_train_version == clean(release_train_version)
        )
    if clean(sdk_language):
        query = query.filter(
            SdkPackageReleaseRow.sdk_language == clean(sdk_language).lower()
        )
    if clean(status):
        query = query.filter(SdkPackageReleaseRow.status == clean(status).lower())
    rows = query.order_by(
        SdkPackageReleaseRow.release_train_version.desc(), SdkPackageReleaseRow.id.asc()
    ).all()
    return [package_release_to_out(row) for row in rows]


def get_sdk_package_release(db: Session, release_id: int) -> SdkPackageReleaseOut:
    return package_release_to_out(_require_sdk_package_release(db, release_id))


def list_sdk_package_release_events(
    db: Session, release_id: int
) -> list[SdkPackageReleaseEventOut]:
    _require_sdk_package_release(db, release_id)
    rows = (
        db.query(SdkPackageReleaseEventRow)
        .filter(SdkPackageReleaseEventRow.sdk_package_release_id == release_id)
        .order_by(SdkPackageReleaseEventRow.id.asc())
        .all()
    )
    return [package_release_event_to_out(row) for row in rows]


def _status_counts(rows: list[SdkPackageReleaseRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = clean(row.status) or "planned"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _min_datetime(values: list[datetime | None]) -> datetime | None:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _max_datetime(values: list[datetime | None]) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _train_to_out(version: str, rows: list[SdkPackageReleaseRow]) -> SdkReleaseTrainOut:
    return SdkReleaseTrainOut(
        release_train_version=version,
        channel=clean(rows[0].channel) if rows else "preview",
        package_count=len(rows),
        status_counts=_status_counts(rows),
        packages=[package_release_to_out(row) for row in rows],
        created_at=_min_datetime([row.created_at for row in rows]),
        updated_at=_max_datetime([row.updated_at for row in rows]),
    )


def list_sdk_release_trains(db: Session) -> list[SdkReleaseTrainOut]:
    rows = (
        db.query(SdkPackageReleaseRow)
        .order_by(
            SdkPackageReleaseRow.release_train_version.desc(),
            SdkPackageReleaseRow.id.asc(),
        )
        .all()
    )
    grouped: dict[str, list[SdkPackageReleaseRow]] = {}
    for row in rows:
        grouped.setdefault(clean(row.release_train_version), []).append(row)
    return [
        _train_to_out(version, train_rows) for version, train_rows in grouped.items()
    ]


def get_sdk_release_train(db: Session, version: str) -> SdkReleaseTrainOut:
    train_version = validate_version(version, field_name="release_train_version")
    rows = (
        db.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.release_train_version == train_version)
        .order_by(SdkPackageReleaseRow.id.asc())
        .all()
    )
    if not rows:
        raise ValueError("SDK release train not found.")
    return _train_to_out(train_version, rows)


def initialize_sdk_release_train(
    db: Session, body: SdkPackageReleaseInitializeRequest
) -> list[SdkPackageReleaseOut]:
    train_version = validate_version(
        body.release_train_version, field_name="release_train_version"
    )
    channel = validate_channel(body.channel)
    languages = package_languages(body.packages)
    created: list[SdkPackageReleaseRow] = []
    for language in languages:
        catalog = PACKAGE_CATALOG[language]
        existing = (
            db.query(SdkPackageReleaseRow)
            .filter(
                SdkPackageReleaseRow.sdk_language == language,
                SdkPackageReleaseRow.registry == catalog["registry"],
                SdkPackageReleaseRow.package_version == train_version,
            )
            .first()
        )
        if existing is not None:
            created.append(existing)
            continue
        row = SdkPackageReleaseRow(
            release_train_version=train_version,
            sdk_language=language,
            package_name=catalog["package_name"],
            registry=catalog["registry"],
            channel=channel,
            package_version=train_version,
            git_tag=git_tag_for(language, train_version, train_version),
            status="planned",
            release_notes=clean(body.release_notes) or None,
            metadata_json=json_dump(
                {"release_train_version": train_version, "channel": channel}
            ),
        )
        db.add(row)
        db.flush()
        record_event(
            db,
            row,
            action="initialize_train",
            from_status=None,
            to_status="planned",
            actor="operator",
            note=clean(body.release_notes) or None,
            metadata={
                "release_train_version": train_version,
                "channel": channel,
                "sdk_language": language,
            },
        )
        created.append(row)
    db.commit()
    for row in created:
        db.refresh(row)
    return [package_release_to_out(row) for row in created]


def _require_sdk_package_release(db: Session, release_id: int) -> SdkPackageReleaseRow:
    row = (
        db.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.id == release_id)
        .first()
    )
    if row is None:
        raise ValueError("SDK package release not found.")
    return row


def _bump_package_version(
    row: SdkPackageReleaseRow, package_version: str | None
) -> None:
    if package_version is None or not clean(package_version):
        return
    if clean(row.status) == "published":
        raise ValueError(
            "Published package versions are immutable. Initialize a new patch record instead."
        )
    next_version = validate_version(package_version, field_name="package_version")
    row.package_version = next_version
    row.git_tag = git_tag_for(
        clean(row.sdk_language), next_version, clean(row.release_train_version)
    )


def _dispatch_sdk_publish_workflow(row: SdkPackageReleaseRow, *, dry_run: bool) -> str:
    return _dispatch_github_workflow(
        repo_full_name=SDK_REPO_FULL_NAME,
        workflow_file=SDK_PUBLISH_WORKFLOW_FILE,
        ref=SDK_PUBLISH_REF,
        inputs={
            "release_train_version": clean(row.release_train_version),
            "package": clean(row.sdk_language),
            "package_version": clean(row.package_version),
            "channel": clean(row.channel) or "preview",
            "dry_run": "true" if dry_run else "false",
        },
    )


def _record_action_event(
    db: Session,
    row: SdkPackageReleaseRow,
    *,
    action: str,
    from_status: str,
    body: SdkPackageReleaseActionRequest,
) -> None:
    record_event(
        db,
        row,
        action=action,
        from_status=from_status,
        to_status=clean(row.status),
        actor=body.actor,
        note=body.note,
        workflow_run_url=row.workflow_run_url,
        error_summary=row.failure_summary,
        metadata={
            "package_version": clean(row.package_version),
            "channel": clean(row.channel),
        },
    )


def dry_run_sdk_package_release(
    db: Session, release_id: int, body: SdkPackageReleaseActionRequest
) -> SdkPackageReleaseOut:
    row = _require_sdk_package_release(db, release_id)
    if clean(row.status) in TERMINAL_STATUSES:
        raise ValueError("Terminal SDK package releases cannot be dry-run.")
    from_status = clean(row.status) or "planned"
    _bump_package_version(row, body.package_version)
    if body.channel:
        row.channel = validate_channel(body.channel)
    row.status = "building"
    try:
        row.workflow_run_url = _dispatch_sdk_publish_workflow(row, dry_run=True)
        row.failure_summary = None
    except ValueError as exc:
        row.status = "failed"
        row.failure_summary = str(exc)
    _record_action_event(db, row, action="dry_run", from_status=from_status, body=body)
    db.commit()
    db.refresh(row)
    return package_release_to_out(row)


def publish_sdk_package_release(
    db: Session, release_id: int, body: SdkPackageReleaseActionRequest
) -> SdkPackageReleaseOut:
    row = _require_sdk_package_release(db, release_id)
    if clean(row.status) == "published":
        raise ValueError(
            "SDK package release is already published. Publish a higher patch version instead."
        )
    if clean(row.status) == "cancelled":
        raise ValueError("Cancelled SDK package releases cannot be published.")
    if clean(row.status) != "ready_to_publish":
        raise ValueError("SDK package release must pass dry-run before publish.")
    from_status = clean(row.status) or "planned"
    _bump_package_version(row, body.package_version)
    if body.channel:
        row.channel = validate_channel(body.channel)
    row.status = "publishing"
    try:
        row.workflow_run_url = _dispatch_sdk_publish_workflow(row, dry_run=False)
        row.failure_summary = None
    except ValueError as exc:
        row.status = "failed"
        row.failure_summary = str(exc)
    _record_action_event(db, row, action="publish", from_status=from_status, body=body)
    db.commit()
    db.refresh(row)
    return package_release_to_out(row)


def retry_sdk_package_release(
    db: Session, release_id: int, body: SdkPackageReleaseActionRequest
) -> SdkPackageReleaseOut:
    row = _require_sdk_package_release(db, release_id)
    if clean(row.status) != "failed":
        raise ValueError("Only failed SDK package releases can be retried.")
    from_status = clean(row.status)
    _bump_package_version(row, body.package_version)
    if body.channel:
        row.channel = validate_channel(body.channel)
    row.status = "publishing"
    try:
        row.workflow_run_url = _dispatch_sdk_publish_workflow(row, dry_run=False)
        row.failure_summary = None
    except ValueError as exc:
        row.status = "failed"
        row.failure_summary = str(exc)
    _record_action_event(db, row, action="retry", from_status=from_status, body=body)
    db.commit()
    db.refresh(row)
    return package_release_to_out(row)


def sync_sdk_package_release_statuses(
    db: Session, *, max_records: int = 50
) -> SdkPackageReleaseSyncResult:
    rows = (
        db.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.status.in_(["building", "publishing"]))
        .order_by(SdkPackageReleaseRow.updated_at.asc())
        .limit(max(1, min(max_records, 200)))
        .all()
    )
    result = SdkPackageReleaseSyncResult(processed_count=len(rows))
    for row in rows:
        run_id = _github_actions_run_id_from_url(clean(row.workflow_run_url))
        if not run_id:
            result.publishing_ids.append(int(row.id))
            continue
        payload, error = _github_actions_run_view(SDK_REPO_FULL_NAME, run_id)
        if error or not payload:
            result.error_ids.append(int(row.id))
            continue
        if clean(payload.get("status")).lower() != "completed":
            result.publishing_ids.append(int(row.id))
            continue
        conclusion = clean(payload.get("conclusion")).lower()
        if conclusion == "success":
            was_publish = clean(row.status) == "publishing"
            from_status = clean(row.status)
            row.status = "published" if was_publish else "ready_to_publish"
            if was_publish:
                row.package_url = package_url_for(row)
                row.published_at = utcnow()
                result.published_ids.append(int(row.id))
            else:
                result.ready_ids.append(int(row.id))
            row.failure_summary = None
            record_event(
                db,
                row,
                action="sync_status",
                from_status=from_status,
                to_status=clean(row.status),
                workflow_run_url=row.workflow_run_url,
                metadata={"github_conclusion": conclusion, "run_id": run_id},
            )
        else:
            from_status = clean(row.status)
            row.status = "failed"
            row.failure_summary = (
                f"GitHub Actions concluded with {conclusion or 'unknown'}."
            )
            record_event(
                db,
                row,
                action="sync_status",
                from_status=from_status,
                to_status="failed",
                workflow_run_url=row.workflow_run_url,
                error_summary=row.failure_summary,
                metadata={"github_conclusion": conclusion, "run_id": run_id},
            )
            result.failed_ids.append(int(row.id))
        row.updated_at = utcnow().astimezone(timezone.utc)
    db.commit()
    return result
