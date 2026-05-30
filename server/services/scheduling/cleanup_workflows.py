from __future__ import annotations

from collections.abc import Callable
from typing import Any

from server import config
from server.database import RecurringWorkflowRow
from server.services.artifact_registry_cleanup import cleanup_artifact_registry_versions


def run_cleanup_workflow(
    row: RecurringWorkflowRow, *, workflow_key: str, dry_run: bool
) -> Any | None:
    handler = _cleanup_handler(row, workflow_key=workflow_key)
    return handler(row, dry_run) if handler else None


def _cleanup_handler(
    row: RecurringWorkflowRow, *, workflow_key: str
) -> Callable[[RecurringWorkflowRow, bool], Any] | None:
    output_kind = str(_json_object(row.output_action_json).get("kind") or "")
    if workflow_key == "artifact_registry_cleanup_sweep":
        return _run_artifact_cleanup
    if output_kind == "cleanup_artifact_registry_versions":
        return _run_artifact_cleanup
    return None


def _run_artifact_cleanup(row: RecurringWorkflowRow, dry_run: bool) -> Any:
    input_query = _json_object(row.input_query_json)
    return cleanup_artifact_registry_versions(
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
            input_query.get("older_than_days")
            or config.ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS
        ),
        dry_run=dry_run,
    )


def _string_list(value: Any) -> list[str] | None:
    return [str(item) for item in value] if isinstance(value, list) else None


def _json_object(raw: str | None) -> dict[str, Any]:
    import json

    try:
        value = json.loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
