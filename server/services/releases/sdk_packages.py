"""SDK package release records for the release center."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from server.database import utcnow
from server.services.releases.sdk_package_catalog import (
    PACKAGE_CATALOG,
    SDK_PACKAGE_STATUSES,
    TERMINAL_STATUSES,
)
from server.services.releases.sdk_package_helpers import (
    clean,
    git_tag_for,
    json_dump,
    package_languages,
    package_release_event_to_out,
    package_release_to_out,
    record_event,
    validate_channel,
    validate_version,
)
from server.services.releases.sdk_package_models import (
    SdkPackageReleaseEventRow,
    SdkPackageReleaseRow,
)
from server.services.releases.sdk_package_platforms import require_enabled_platform
from server.services.releases.sdk_package_schemas import (
    SdkPackageReleaseActionRequest,
    SdkPackageReleaseEventOut,
    SdkPackageReleaseInitializeRequest,
    SdkPackageReleaseOut,
    SdkPackageReleasePageOut,
    SdkPackageReleaseSyncResult,
    SdkReleaseTrainOut,
)
LOCAL_SDK_RUN_PREFIX = "local-sdk-run:"
SDK_PUBLISH_CONFIRM_PREFIX = "PUBLISH_SDK_"


def list_sdk_package_releases(
    db: Session,
    *,
    release_train_version: str | None = None,
    sdk_language: str | None = None,
    registry: str | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> SdkPackageReleasePageOut:
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
    if clean(registry):
        query = query.filter(SdkPackageReleaseRow.registry == clean(registry).lower())
    if clean(search):
        needle = f"%{clean(search).lower()}%"
        query = query.filter(
            or_(
                SdkPackageReleaseRow.release_train_version.ilike(needle),
                SdkPackageReleaseRow.sdk_language.ilike(needle),
                SdkPackageReleaseRow.package_name.ilike(needle),
                SdkPackageReleaseRow.registry.ilike(needle),
                SdkPackageReleaseRow.channel.ilike(needle),
                SdkPackageReleaseRow.package_version.ilike(needle),
                SdkPackageReleaseRow.git_tag.ilike(needle),
                SdkPackageReleaseRow.status.ilike(needle),
                SdkPackageReleaseRow.failure_summary.ilike(needle),
            )
        )
    safe_page = max(1, page)
    safe_page_size = max(1, min(page_size, 100))
    total = query.count()
    rows = (
        query.order_by(
            SdkPackageReleaseRow.updated_at.desc(),
            SdkPackageReleaseRow.created_at.desc(),
            SdkPackageReleaseRow.id.desc(),
        )
        .offset((safe_page - 1) * safe_page_size)
        .limit(safe_page_size)
        .all()
    )
    total_pages = (total + safe_page_size - 1) // safe_page_size if total else 0
    return SdkPackageReleasePageOut(
        items=[package_release_to_out(row) for row in rows],
        total=total,
        page=safe_page,
        page_size=safe_page_size,
        total_pages=total_pages,
    )


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


def _local_sdk_publish_reference(row: SdkPackageReleaseRow, *, dry_run: bool) -> str:
    mode = "dry-run" if dry_run else "publish"
    return f"{LOCAL_SDK_RUN_PREFIX}{mode}:{int(row.id)}"


def _merge_metadata(row: SdkPackageReleaseRow, patch: dict[str, object]) -> None:
    import json

    try:
        current = json.loads(row.metadata_json or "{}")
    except json.JSONDecodeError:
        current = {}
    if not isinstance(current, dict):
        current = {}
    current.update(patch)
    row.metadata_json = json_dump(current)


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
    platform = require_enabled_platform(db, clean(row.sdk_language))
    from_status = clean(row.status) or "planned"
    _bump_package_version(row, body.package_version)
    if body.channel:
        row.channel = validate_channel(body.channel)
    row.status = "dry_running"
    row.workflow_run_url = _local_sdk_publish_reference(row, dry_run=True)
    row.failure_summary = None
    _merge_metadata(
        row,
        {
            "platform_key": platform.platform_key,
            "registry_url": platform.registry_url,
            "package_url_template": platform.package_url_template,
            "local_runner_mode": "dry_run",
        },
    )
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
    expected_phrase = f"{SDK_PUBLISH_CONFIRM_PREFIX}{clean(row.package_version)}"
    if clean(body.confirm_phrase) != expected_phrase:
        raise ValueError(f"confirm_phrase must be {expected_phrase} to publish immutable SDK packages.")
    platform = require_enabled_platform(db, clean(row.sdk_language))
    if not platform.credential_present:
        raise ValueError(f"credential_missing: runner env {platform.credential_env_var} is required for {platform.platform_key}.")
    from_status = clean(row.status) or "planned"
    _bump_package_version(row, body.package_version)
    if body.channel:
        row.channel = validate_channel(body.channel)
    row.status = "publishing"
    row.workflow_run_url = _local_sdk_publish_reference(row, dry_run=False)
    row.failure_summary = None
    _merge_metadata(
        row,
        {
            "platform_key": platform.platform_key,
            "registry_url": platform.registry_url,
            "package_url_template": platform.package_url_template,
            "local_runner_mode": "publish",
        },
    )
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
    target_status = "ready_to_publish" if clean(row.package_url) else "dry_running"
    row.status = target_status
    row.workflow_run_url = _local_sdk_publish_reference(row, dry_run=target_status == "dry_running")
    row.failure_summary = None
    _record_action_event(db, row, action="retry", from_status=from_status, body=body)
    db.commit()
    db.refresh(row)
    return package_release_to_out(row)


def sync_sdk_package_release_statuses(
    db: Session, *, max_records: int = 50
) -> SdkPackageReleaseSyncResult:
    rows = (
        db.query(SdkPackageReleaseRow)
        .filter(SdkPackageReleaseRow.status.in_(["dry_running", "building", "publishing"]))
        .order_by(SdkPackageReleaseRow.updated_at.asc())
        .limit(max(1, min(max_records, 200)))
        .all()
    )
    result = SdkPackageReleaseSyncResult(processed_count=len(rows))
    for row in rows:
        status = clean(row.status)
        if status not in SDK_PACKAGE_STATUSES and status != "building":
            result.error_ids.append(int(row.id))
            continue
        if status in {"dry_running", "building"}:
            result.ready_ids.append(int(row.id))
        elif status == "publishing":
            result.publishing_ids.append(int(row.id))
        record_event(
            db,
            row,
            action="sync_status",
            from_status=status,
            to_status=clean(row.status),
            workflow_run_url=row.workflow_run_url,
            metadata={"local_runner": True, "message": "Status is owned by local SDK publish worker."},
        )
        row.updated_at = utcnow().astimezone(timezone.utc)
    db.commit()
    return result
