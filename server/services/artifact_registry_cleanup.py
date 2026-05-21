"""Artifact Registry cleanup by metadata only."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - fixed gcloud argv runner, no shell
from datetime import datetime, timezone
from typing import Any, Callable

from server import config
from server.services.result_objects import ServiceObjectResult, service_object_result

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

PROTECTED_TAG_PREFIXES = ("prod-", "production-", "promoted-", "release-")


def _run_command(
    cmd: list[str],
) -> subprocess.CompletedProcess[
    str
]:  # pragma: no cover - fixed gcloud subprocess adapter
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=180)  # noqa: S603 # nosec B603


def _json_loads(raw: str) -> Any:  # pragma: no cover - defensive gcloud JSON parser
    try:
        return json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []


def _call_json(
    command: list[str], *, runner: CommandRunner
) -> list[dict[str, Any]]:  # pragma: no cover - thin command adapter
    result = runner(command)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(stderr[:1000] or f"command failed: {' '.join(command)}")
    payload = _json_loads(result.stdout)
    return payload if isinstance(payload, list) else []


def _parse_time(value: Any) -> datetime:  # pragma: no cover - defensive metadata parser
    raw = str(value or "").strip()
    if not raw:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _image_name(
    row: dict[str, Any], *, location: str, project: str, repository: str
) -> str:
    raw = str(row.get("name") or row.get("uri") or row.get("package") or "")
    fallback = f"{location}-docker.pkg.dev/{project}/{repository}/unknown"
    return raw or _image_name_from_digest(row) or fallback


def _image_name_from_digest(
    row: dict[str, Any],
) -> str:  # pragma: no cover - fallback for alternate gcloud payloads
    digest = str(row.get("version") or row.get("digest") or "")
    image = str(row.get("image") or row.get("packageName") or "")
    if not image or not digest:
        return ""
    prefix = "" if digest.startswith("sha256:") else "sha256:"
    return f"{image}@{prefix}{digest}"


def _digest_key(row: dict[str, Any]) -> str:
    raw = str(row.get("version") or row.get("digest") or row.get("name") or "")
    match = re.search(r"sha256[:/][a-fA-F0-9]{16,}", raw)
    if match:
        return match.group(0).replace("/", ":")
    return raw.rsplit("/", 1)[-1] or raw


def _tags(row: dict[str, Any]) -> list[str]:
    value = row.get("tags") or row.get("tag") or []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _protected(tags: list[str]) -> bool:
    return any(tag.startswith(PROTECTED_TAG_PREFIXES) for tag in tags)


def _delete_image(
    image: str, *, runner: CommandRunner
) -> str | None:  # pragma: no cover - fixed gcloud delete adapter
    result = runner(
        [
            "gcloud",
            "artifacts",
            "docker",
            "images",
            "delete",
            image,
            "--delete-tags",
            "--quiet",
        ]
    )
    if result.returncode == 0:
        return None
    return (result.stderr or result.stdout or "").strip()[:1000]


def _cleanup_row(
    row: dict[str, Any],
    *,
    project: str,
    region: str,
    repository: str,
    protected_or_recent: set[str],
    cutoff: float,
):
    tags = _tags(row)
    digest = _digest_key(row)
    image = _image_name(row, location=region, project=project, repository=repository)
    updated = _parse_time(row.get("updateTime") or row.get("createTime"))
    item = {
        "image": image,
        "digest": digest,
        "tags": tags,
        "updated_at": updated.isoformat(),
    }
    if digest in protected_or_recent or _protected(tags):
        return "kept", {**item, "reason": "recent_or_promoted"}
    if updated.timestamp() > cutoff:
        return "skipped", {**item, "reason": "newer_than_cutoff"}
    return "candidate", item


def _cleanup_project(
    *,
    project: str,
    region: str,
    repository: str,
    keep_count: int,
    cutoff: float,
    dry_run: bool,
    runner: CommandRunner,
):
    project_result = _empty_project_result(
        project=project, region=region, repository=repository
    )
    totals = _empty_totals()
    try:
        rows = _list_images(
            project=project, region=region, repository=repository, runner=runner
        )
    except Exception as exc:
        project_result["errors"].append(
            {"scope": "list_images", "error": str(exc)[:1000]}
        )
        totals["error_count"] += 1
        return project_result, totals
    rows.sort(
        key=lambda row: _parse_time(
            row.get("updateTime") or row.get("createTime")
        ).timestamp(),
        reverse=True,
    )
    protected_or_recent = {_digest_key(row) for row in rows[:keep_count]}
    for row in rows:
        action, item = _cleanup_row(
            row,
            project=project,
            region=region,
            repository=repository,
            protected_or_recent=protected_or_recent,
            cutoff=cutoff,
        )
        totals["image_count"] += 1
        if action == "kept":
            project_result["kept"].append(item)
            totals["kept_count"] += 1
            continue
        if action == "skipped":
            project_result["skipped"].append(item)
            totals["skipped_count"] += 1
            continue
        project_result["candidates"].append(item)
        totals["candidate_count"] += 1
        if dry_run:
            continue
        error = _delete_image(str(item["image"]), runner=runner)
        if error:
            project_result["errors"].append({**item, "error": error})
            totals["error_count"] += 1
        else:
            project_result["deleted_count"] += 1
            totals["deleted_count"] += 1
    return project_result, totals


def _empty_project_result(
    *, project: str, region: str, repository: str
) -> dict[str, Any]:
    return {
        "project": project,
        "region": region,
        "repository": repository,
        "kept": [],
        "candidates": [],
        "skipped": [],
        "errors": [],
        "deleted_count": 0,
    }


def _empty_totals() -> dict[str, int]:
    return {
        "image_count": 0,
        "kept_count": 0,
        "candidate_count": 0,
        "deleted_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }


def _list_images(
    *, project: str, region: str, repository: str, runner: CommandRunner
) -> list[dict[str, Any]]:
    image_root = f"{region}-docker.pkg.dev/{project}/{repository}"
    return _call_json(
        [
            "gcloud",
            "artifacts",
            "docker",
            "images",
            "list",
            image_root,
            "--include-tags",
            "--format=json",
        ],
        runner=runner,
    )


@service_object_result
def cleanup_artifact_registry_versions(
    *,
    projects: list[str] | None = None,
    region: str | None = None,
    repository: str | None = None,
    keep: int | None = None,
    older_than_days: int | None = None,
    dry_run: bool = True,
    runner: CommandRunner | None = None,
) -> ServiceObjectResult:
    """Delete old Artifact Registry Docker images while preserving recent/promoted versions."""

    command_runner = runner or _run_command
    selected_projects = list(projects or config.ARTIFACT_REGISTRY_CLEANUP_PROJECTS)
    selected_region = str(region or config.ARTIFACT_REGISTRY_CLEANUP_REGION)
    selected_repository = str(repository or config.ARTIFACT_REGISTRY_CLEANUP_REPOSITORY)
    keep_count = max(1, int(keep or config.ARTIFACT_REGISTRY_CLEANUP_KEEP_VERSIONS))
    age_days = max(
        0,
        int(
            older_than_days
            if older_than_days is not None
            else config.ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS
        ),
    )
    cutoff = datetime.now(timezone.utc).timestamp() - (age_days * 86400)
    totals = {
        "project_count": len(selected_projects),
        "image_count": 0,
        "kept_count": 0,
        "candidate_count": 0,
        "deleted_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }
    project_results: list[dict[str, Any]] = []
    for project in selected_projects:
        project_result, project_totals = _cleanup_project(
            project=project,
            region=selected_region,
            repository=selected_repository,
            keep_count=keep_count,
            cutoff=cutoff,
            dry_run=dry_run,
            runner=command_runner,
        )
        for key, value in project_totals.items():
            totals[key] += int(value)
        project_results.append(project_result)
    return {
        "dry_run": bool(dry_run),
        "keep": keep_count,
        "older_than_days": age_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **totals,
        "projects": project_results,
    }
