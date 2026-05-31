from __future__ import annotations

from collections.abc import Callable
from typing import Any

from server import config
from sqlalchemy.orm import Session

from server.database import RecurringWorkflowRow
from server.services.artifact_registry_cleanup import cleanup_artifact_registry_versions
from server.services.secret_manager_cleanup import cleanup_secret_manager_versions
from server.services.staging_environment_shutdown import shutdown_staging_environment
from server.services.scheduling.growth_workflows import GROWTH_PROVIDER_SOURCE_WORKFLOW, run_growth_provider_source_workflow


def run_cleanup_workflow(
    row: RecurringWorkflowRow, *, workflow_key: str, dry_run: bool, db: Session | None = None
) -> Any | None:
    handler = _cleanup_handler(row, workflow_key=workflow_key)
    return handler(row, dry_run, db) if handler else None


def _cleanup_handler(
    row: RecurringWorkflowRow, *, workflow_key: str
) -> Callable[[RecurringWorkflowRow, bool, Session | None], Any] | None:
    output_kind = str(_json_object(row.output_action_json).get("kind") or "")
    if workflow_key == "artifact_registry_cleanup_sweep":
        return _run_artifact_cleanup
    if workflow_key == "secret_manager_version_cleanup_sweep":
        return _run_secret_manager_cleanup
    if workflow_key == "staging_environment_shutdown_sweep":
        return _run_staging_environment_shutdown
    if workflow_key == "growth_provider_source_sweep":
        return _run_growth_provider_source
    if output_kind == "cleanup_artifact_registry_versions":
        return _run_artifact_cleanup
    if output_kind == "destroy_old_secret_manager_versions":
        return _run_secret_manager_cleanup
    if output_kind == "shutdown_staging_environment":
        return _run_staging_environment_shutdown
    return None


def _run_growth_provider_source(
    row: RecurringWorkflowRow, dry_run: bool, db: Session | None
) -> Any:
    if db is None:
        raise ValueError("growth provider source workflow requires a database session")
    return run_growth_provider_source_workflow(db, dry_run=dry_run)


def _run_artifact_cleanup(
    row: RecurringWorkflowRow, dry_run: bool, db: Session | None = None
) -> Any:
    input_query = _json_object(row.input_query_json)
    return cleanup_artifact_registry_versions(
        targets=_dict_list(input_query.get("targets")),
        projects=_string_list(input_query.get("projects")),
        region=str(
            input_query.get("region") or config.ARTIFACT_REGISTRY_CLEANUP_REGION
        ),
        repository=str(
            input_query.get("repository") or config.ARTIFACT_REGISTRY_CLEANUP_REPOSITORY
        ),
        keep=int(
            input_query.get("keep") or config.ARTIFACT_REGISTRY_CLEANUP_KEEP_VERSIONS
        ),
        older_than_days=int(
            input_query["older_than_days"]
            if "older_than_days" in input_query
            else config.ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS
        ),
        dry_run=dry_run,
    )


def _run_secret_manager_cleanup(
    row: RecurringWorkflowRow, dry_run: bool, db: Session | None = None
) -> Any:
    input_query = _json_object(row.input_query_json)
    return cleanup_secret_manager_versions(
        projects=_string_list(input_query.get("projects")),
        secret_ids=_string_list(input_query.get("secret_ids")),
        keep=int(input_query.get("keep") or config.SECRET_MANAGER_CLEANUP_KEEP_VERSIONS),
        dry_run=dry_run,
    )


def _run_staging_environment_shutdown(
    row: RecurringWorkflowRow, dry_run: bool, db: Session | None = None
) -> Any:
    input_query = _json_object(row.input_query_json)
    return shutdown_staging_environment(
        project=str(input_query.get("project") or config.STAGING_ENVIRONMENT_PROJECT),
        region=str(input_query.get("region") or config.STAGING_ENVIRONMENT_REGION),
        cloud_run_services=_string_list(input_query.get("cloud_run_services")),
        scheduler_jobs=_string_list(input_query.get("scheduler_jobs")),
        cloud_sql_instance=str(
            input_query.get("cloud_sql_instance") or config.STAGING_CLOUD_SQL_INSTANCE
        ),
        dry_run=dry_run,
    )


def _string_list(value: Any) -> list[str] | None:
    return [str(item) for item in value] if isinstance(value, list) else None


def _dict_list(value: Any) -> list[dict[str, Any]] | None:
    return [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else None


def _json_object(raw: str | None) -> dict[str, Any]:
    import json

    try:
        value = json.loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
