"""Shared helpers for SDK package release services."""

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from server.services.releases.sdk_package_catalog import (
    DEFAULT_PACKAGE_ORDER,
    PACKAGE_CATALOG,
    VALID_CHANNELS,
)
from server.services.releases.sdk_package_models import (
    SdkPackageReleaseEventRow,
    SdkPackageReleaseRow,
)
from server.services.releases.sdk_package_schemas import (
    SdkPackageReleaseEventOut,
    SdkPackageReleaseOut,
)


def clean(value: object) -> str:
    return str(value or "").strip()


def json_dump(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def validate_version(value: str, *, field_name: str) -> str:
    version = clean(value)
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", version):
        raise ValueError(f"{field_name} must be a SemVer value, for example 0.1.0.")
    return version


def validate_channel(value: str) -> str:
    channel = clean(value).lower()
    if channel not in VALID_CHANNELS:
        raise ValueError(f"channel must be one of: {', '.join(sorted(VALID_CHANNELS))}")
    return channel


def package_languages(requested: list[str]) -> list[str]:
    if not requested:
        return DEFAULT_PACKAGE_ORDER
    seen: set[str] = set()
    languages: list[str] = []
    for item in requested:
        language = clean(item).lower()
        if language not in PACKAGE_CATALOG:
            raise ValueError(f"Unsupported SDK package language: {item}")
        if language not in seen:
            seen.add(language)
            languages.append(language)
    return languages


def git_tag_for(language: str, package_version: str, release_train_version: str) -> str:
    if language == "go":
        return f"go/v{package_version}"
    return f"sdk/v{release_train_version}"


def package_url_for(row: SdkPackageReleaseRow) -> str | None:
    package = clean(row.package_name)
    version = clean(row.package_version)
    language = clean(row.sdk_language)
    if language == "python":
        return f"https://pypi.org/project/{package}/{version}/"
    if language == "typescript":
        return f"https://www.npmjs.com/package/{package}/v/{version}"
    if language == "go":
        return f"https://pkg.go.dev/{package}@v{version}"
    if language == "java":
        group_path = package.split(":", 1)[0].replace(".", "/")
        artifact = package.split(":", 1)[1] if ":" in package else package
        return f"https://repo1.maven.org/maven2/{group_path}/{artifact}/{version}/"
    if language == "dotnet":
        return f"https://www.nuget.org/packages/{package}/{version}"
    return None


def package_release_to_out(row: SdkPackageReleaseRow) -> SdkPackageReleaseOut:
    return SdkPackageReleaseOut(
        id=int(row.id),
        release_train_version=clean(row.release_train_version),
        sdk_language=clean(row.sdk_language),
        package_name=clean(row.package_name),
        registry=clean(row.registry),
        channel=clean(row.channel) or "preview",
        package_version=clean(row.package_version),
        git_tag=clean(row.git_tag) or None,
        status=clean(row.status) or "planned",
        package_url=clean(row.package_url) or None,
        workflow_run_url=clean(row.workflow_run_url) or None,
        failure_summary=clean(row.failure_summary) or None,
        release_notes=clean(row.release_notes) or None,
        metadata=_json_load(row.metadata_json),
        published_at=row.published_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def package_release_event_to_out(
    row: SdkPackageReleaseEventRow,
) -> SdkPackageReleaseEventOut:
    return SdkPackageReleaseEventOut(
        id=int(row.id),
        sdk_package_release_id=int(row.sdk_package_release_id),
        action=clean(row.action),
        from_status=clean(row.from_status) or None,
        to_status=clean(row.to_status) or None,
        actor=clean(row.actor) or None,
        note=clean(row.note) or None,
        workflow_run_url=clean(row.workflow_run_url) or None,
        error_summary=clean(row.error_summary) or None,
        metadata=_json_load(row.metadata_json),
        created_at=row.created_at,
    )


def record_event(
    db: Session,
    row: SdkPackageReleaseRow,
    *,
    action: str,
    from_status: str | None,
    to_status: str | None,
    actor: str | None = None,
    note: str | None = None,
    workflow_run_url: str | None = None,
    error_summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        SdkPackageReleaseEventRow(
            sdk_package_release_id=int(row.id),
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor=clean(actor) or None,
            note=clean(note) or None,
            workflow_run_url=clean(workflow_run_url) or None,
            error_summary=clean(error_summary) or None,
            metadata_json=json_dump(metadata or {}),
        )
    )
