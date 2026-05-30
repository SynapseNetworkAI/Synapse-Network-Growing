"""Delete migrated X refresh-token Secret Manager resources after local verification."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed gcloud argv runner, no shell
from dataclasses import dataclass
from typing import Any, Callable

from server import config
from server.database_local_secrets import LocalSecretVersionRow
from server.database import SessionLocal
from server.services.local_secrets import latest_local_secret_version
from server.services.result_objects import (
    ServiceObjectResult,
    dump_service_result,
    service_object_result,
)
from server.services.social.publishing import (
    SecretValueStore,
    SocialPublishError,
    XOAuth2TokenProvider,
)

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

DEFAULT_PROJECTS = ("fabled-archive-494108-k5", "synapse-network-prod")
DELETE_CONFIRMATION = "DELETE_X_REFRESH_SECRET_AFTER_LOCAL_DB_VERIFIED"


@dataclass(frozen=True)
class LocalXRefreshVerification:
    local_key: str
    active_version_count: int
    verified_refresh: bool
    rotated: bool


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=120)  # noqa: S603 # nosec B603 - fixed gcloud argv, no shell


def _bounded(raw: str, *, limit: int = 1000) -> str:
    return str(raw or "").strip()[:limit]


def _active_local_version_count(local_key: str) -> int:
    with SessionLocal() as db:
        row = latest_local_secret_version(db, local_key)
        if row is None:
            return 0
        return (
            db.query(LocalSecretVersionRow)
            .filter(
                LocalSecretVersionRow.secret_key == local_key,
                LocalSecretVersionRow.status == "active",
            )
            .count()
        )


def verify_local_x_refresh_token(
    *,
    local_key: str | None = None,
    provider: XOAuth2TokenProvider | None = None,
) -> LocalXRefreshVerification:
    """Verify local DB has an active token and X OAuth can refresh it."""

    key = str(local_key or config.X_OAUTH_REFRESH_TOKEN_LOCAL_KEY).strip()
    active_count = _active_local_version_count(key)
    if active_count <= 0:
        raise SocialPublishError(
            "x_auth_failed", f"Local secret {key!r} has no active version."
        )
    token_provider = provider or XOAuth2TokenProvider(SecretValueStore())
    token = token_provider.get_access_token()
    if not token.access_token:
        raise SocialPublishError(
            "x_refresh_failed", "X OAuth local DB refresh did not return access token."
        )
    return LocalXRefreshVerification(
        local_key=key,
        active_version_count=active_count,
        verified_refresh=True,
        rotated=bool(token.refresh_token_rotated),
    )


def _delete_secret(
    *, project: str, secret_id: str, dry_run: bool, runner: CommandRunner
) -> dict[str, Any]:
    describe = runner(
        [
            "gcloud",
            "secrets",
            "describe",
            secret_id,
            "--project",
            project,
            "--format=json",
        ]
    )
    if describe.returncode != 0:
        detail = _bounded(describe.stderr or describe.stdout)
        if "not found" in detail.lower() or "not_found" in detail.lower():
            return {"project": project, "secret_id": secret_id, "status": "not_found"}
        return {
            "project": project,
            "secret_id": secret_id,
            "status": "describe_failed",
            "error": detail,
        }
    if dry_run:
        return {"project": project, "secret_id": secret_id, "status": "would_delete"}
    delete = runner(
        [
            "gcloud",
            "secrets",
            "delete",
            secret_id,
            "--project",
            project,
            "--quiet",
        ]
    )
    if delete.returncode != 0:
        return {
            "project": project,
            "secret_id": secret_id,
            "status": "delete_failed",
            "error": _bounded(delete.stderr or delete.stdout),
        }
    return {"project": project, "secret_id": secret_id, "status": "deleted"}


def _ensure_delete_confirmation(*, dry_run: bool, confirmation: str) -> None:
    if not dry_run and confirmation != DELETE_CONFIRMATION:
        raise ValueError(f"confirmation must be {DELETE_CONFIRMATION!r}")


def _selected_projects(projects: list[str] | None) -> list[str]:
    return [
        item.strip() for item in (projects or list(DEFAULT_PROJECTS)) if item.strip()
    ]


def _delete_project_results(
    *,
    projects: list[str],
    secret_id: str,
    dry_run: bool,
    runner: CommandRunner,
) -> list[dict[str, Any]]:
    return [
        _delete_secret(
            project=project,
            secret_id=secret_id,
            dry_run=dry_run,
            runner=runner,
        )
        for project in projects
    ]


def _result_count(results: list[dict[str, Any]], status: str) -> int:
    return sum(1 for item in results if item["status"] == status)


def _error_count(results: list[dict[str, Any]]) -> int:
    return sum(1 for item in results if str(item["status"]).endswith("_failed"))


@service_object_result
def delete_x_refresh_token_secret_manager(
    *,
    projects: list[str] | None = None,
    secret_id: str | None = None,
    confirmation: str,
    dry_run: bool = True,
    runner: CommandRunner | None = None,
    provider: XOAuth2TokenProvider | None = None,
) -> ServiceObjectResult:
    """Delete the X refresh-token secret resource from selected GCP projects."""

    _ensure_delete_confirmation(dry_run=dry_run, confirmation=confirmation)
    verification = verify_local_x_refresh_token(provider=provider)
    command_runner = runner or _run_command
    selected_secret_id = str(secret_id or config.X_OAUTH_REFRESH_TOKEN_LOCAL_KEY).strip()
    results = _delete_project_results(
        projects=_selected_projects(projects),
        secret_id=selected_secret_id,
        dry_run=dry_run,
        runner=command_runner,
    )
    return {
        "dry_run": bool(dry_run),
        "secret_id": selected_secret_id,
        "local_verification": verification.__dict__,
        "projects": results,
        "deleted_count": _result_count(results, "deleted"),
        "not_found_count": _result_count(results, "not_found"),
        "error_count": _error_count(results),
    }


def dump_delete_result(payload: dict[str, Any] | ServiceObjectResult) -> str:
    return json.dumps(
        dump_service_result(payload), ensure_ascii=False, indent=2, sort_keys=True
    )
