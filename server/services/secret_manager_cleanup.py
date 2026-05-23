"""Secret Manager version cleanup without reading secret payloads."""

from __future__ import annotations

import json
import re
import subprocess  # nosec B404 - fixed gcloud argv runner, no shell
from datetime import datetime, timezone
from typing import Any, Callable

from server import config
from server.services.result_objects import ServiceObjectResult, service_object_result

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=120)  # noqa: S603 # nosec B603 - fixed gcloud argv, no shell


def _json_loads(raw: str) -> Any:
    try:
        return json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []


def _secret_id(name: str) -> str:
    return str(name or "").rstrip("/").rsplit("/", 1)[-1]


def _version_id(name: str) -> str:
    return str(name or "").rstrip("/").rsplit("/", 1)[-1]


def _version_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    version = _version_id(str(row.get("name") or "0"))
    numeric = int(version) if re.fullmatch(r"\d+", version) else 0
    return numeric, str(row.get("createTime") or "")


def _call_json(command: list[str], *, runner: CommandRunner) -> list[dict[str, Any]]:
    result = runner(command)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(stderr[:1000] or f"command failed: {' '.join(command)}")
    data = _json_loads(result.stdout)
    return data if isinstance(data, list) else []


def _empty_project_result(project: str) -> dict[str, Any]:
    return {
        "project": project,
        "secret_count": 0,  # nosec B105 - count field, not a password
        "version_count": 0,
        "kept_count": 0,
        "candidate_count": 0,
        "destroyed_count": 0,
        "skipped": [],
        "errors": [],
        "candidates": [],
    }


def _destroy_secret_version(
    *,
    project: str,
    secret_name: str,
    version: str,
    runner: CommandRunner,
) -> str | None:
    destroy = runner(
        [
            "gcloud",
            "secrets",
            "versions",
            "destroy",
            version,
            "--secret",
            secret_name,
            "--project",
            project,
            "--quiet",
        ]
    )
    if destroy.returncode == 0:
        return None
    return (destroy.stderr or destroy.stdout or "").strip()[:1000]


def _cleanup_secret_versions(
    *,
    project: str,
    secret_name: str,
    keep_count: int,
    dry_run: bool,
    runner: CommandRunner,
    project_result: dict[str, Any],
) -> None:
    versions = _call_json(
        [
            "gcloud",
            "secrets",
            "versions",
            "list",
            secret_name,
            "--project",
            project,
            "--format=json",
        ],
        runner=runner,
    )
    active_versions = [
        row
        for row in versions
        if str(row.get("state") or "").upper() in {"ENABLED", "DISABLED"}
    ]
    active_versions.sort(key=_version_sort_key, reverse=True)
    keep_versions = active_versions[:keep_count]
    candidates = active_versions[keep_count:]
    project_result["version_count"] += len(active_versions)
    project_result["kept_count"] += len(keep_versions)
    project_result["candidate_count"] += len(candidates)
    if not active_versions:
        project_result["skipped"].append(
            {"secret": secret_name, "reason": "no_active_versions"}
        )
        return
    for candidate in candidates:
        version = _version_id(str(candidate.get("name") or ""))
        project_result["candidates"].append(
            {
                "secret": secret_name,
                "version": version,
                "state": str(candidate.get("state") or ""),
                "createTime": candidate.get("createTime"),
            }
        )
        if dry_run:
            continue
        error = _destroy_secret_version(
            project=project, secret_name=secret_name, version=version, runner=runner
        )
        if error:
            project_result["errors"].append(
                {"secret": secret_name, "version": version, "error": error}
            )
        else:
            project_result["destroyed_count"] += 1


def _cleanup_project_versions(
    *,
    project: str,
    keep_count: int,
    dry_run: bool,
    runner: CommandRunner,
    secret_ids: set[str] | None,
) -> dict[str, Any]:
    project_result = _empty_project_result(project)
    try:
        secrets = _call_json(
            ["gcloud", "secrets", "list", "--project", project, "--format=json"],
            runner=runner,
        )
    except Exception as exc:
        project_result["errors"].append(
            {"scope": "list_secrets", "error": str(exc)[:1000]}
        )
        return project_result
    selected_secrets = _filter_secrets(secrets, secret_ids=secret_ids)
    project_result["secret_count"] = len(selected_secrets)
    for secret in selected_secrets:
        secret_name = _secret_id(str(secret.get("name") or ""))
        if not secret_name:
            project_result["skipped"].append(
                {"secret": "", "reason": "missing_secret_name"}  # nosec B105 - empty secret id marker
            )
            continue
        try:
            _cleanup_secret_versions(
                project=project,
                secret_name=secret_name,
                keep_count=keep_count,
                dry_run=dry_run,
                runner=runner,
                project_result=project_result,
            )
        except Exception as exc:
            project_result["errors"].append(
                {"secret": secret_name, "error": str(exc)[:1000]}
            )
    return project_result


def _filter_secrets(
    secrets: list[dict[str, Any]], *, secret_ids: set[str] | None
) -> list[dict[str, Any]]:
    if not secret_ids:
        return secrets
    return [
        secret
        for secret in secrets
        if _secret_id(str(secret.get("name") or "")) in secret_ids
    ]


def _selected_secret_ids(secret_ids: list[str] | None) -> set[str] | None:
    selected = {str(item).strip() for item in secret_ids or [] if str(item).strip()}
    return selected or None


def _cleanup_totals(project_count: int) -> dict[str, int]:
    return {
        "project_count": project_count,
        "secret_count": 0,  # nosec B105 - count field, not a password
        "version_count": 0,
        "kept_count": 0,
        "candidate_count": 0,
        "destroyed_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }


def _merge_project_totals(
    totals: dict[str, int], project_result: dict[str, Any]
) -> None:
    totals["secret_count"] += int(project_result["secret_count"] or 0)
    totals["version_count"] += int(project_result["version_count"] or 0)
    totals["kept_count"] += int(project_result["kept_count"] or 0)
    totals["candidate_count"] += int(project_result["candidate_count"] or 0)
    totals["destroyed_count"] += int(project_result["destroyed_count"] or 0)
    totals["skipped_count"] += len(project_result["skipped"])
    totals["error_count"] += len(project_result["errors"])


def _cleanup_projects(
    *,
    projects: list[str],
    keep_count: int,
    dry_run: bool,
    runner: CommandRunner,
    secret_ids: set[str] | None,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    totals = _cleanup_totals(len(projects))
    project_results: list[dict[str, Any]] = []
    for project in projects:
        project_result = _cleanup_project_versions(
            project=project,
            keep_count=keep_count,
            dry_run=dry_run,
            runner=runner,
            secret_ids=secret_ids,
        )
        _merge_project_totals(totals, project_result)
        project_results.append(project_result)
    return totals, project_results


@service_object_result
def cleanup_secret_manager_versions(
    *,
    projects: list[str] | None = None,
    secret_ids: list[str] | None = None,
    keep: int | None = None,
    dry_run: bool = True,
    runner: CommandRunner | None = None,
) -> ServiceObjectResult:
    """Destroy old Secret Manager versions while keeping the newest active N.

    Active means ENABLED or DISABLED. DESTROYED versions are ignored because they
    no longer contribute to active-version sprawl and cannot be recovered.
    """

    command_runner = runner or _run_command
    selected_projects = list(projects or config.SECRET_MANAGER_CLEANUP_PROJECTS)
    selected_secret_ids = _selected_secret_ids(secret_ids)
    keep_count = max(1, int(keep or config.SECRET_MANAGER_CLEANUP_KEEP_VERSIONS))
    totals, project_results = _cleanup_projects(
        projects=selected_projects,
        keep_count=keep_count,
        dry_run=dry_run,
        runner=command_runner,
        secret_ids=selected_secret_ids,
    )
    return {
        "dry_run": bool(dry_run),
        "keep": keep_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **totals,
        "projects": project_results,
    }
