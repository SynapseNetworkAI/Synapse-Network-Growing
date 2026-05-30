"""Template-based Schedule Center services."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from server.database import RecurringWorkflowRow, utcnow
from server.services.result_objects import ServiceListResult, ServiceObjectResult
from server.services.scheduling.artifact_registry_workflows import (
    ARTIFACT_REGISTRY_CLEANUP_INPUT_QUERY,
    ARTIFACT_REGISTRY_CLEANUP_SCHEDULE,
)
from server.services.scheduling.recurring_workflows import (
    get_recurring_workflow,
    list_recurring_workflow_runs,
    recurring_workflow_run_to_dict,
    recurring_workflow_to_dict,
    run_recurring_workflow,
    sync_recurring_workflows,
)

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,80}$")


SCHEDULE_TEMPLATES: dict[str, dict[str, Any]] = {
    "artifact_registry_cleanup": {
        "template_key": "artifact_registry_cleanup",
        "display_name": "Artifact Registry Cleanup",
        "description": "Clean stale Docker image versions by metadata, with dry-run first.",
        "category": "infra_cleanup",
        "risk_level": "high",
        "handler_key": "cleanup_artifact_registry_versions",
        "schedule": ARTIFACT_REGISTRY_CLEANUP_SCHEDULE,
        "input_query": ARTIFACT_REGISTRY_CLEANUP_INPUT_QUERY,
        "output_action": {
            "kind": "cleanup_artifact_registry_versions",
            "read_image_payload": False,
        },
        "validation_signal": {"success_metric": "deleted_count", "min_expected": 0},
    },
}

_ALLOWED_HANDLER_KEYS = {
    str(item["handler_key"]) for item in SCHEDULE_TEMPLATES.values()
}


def list_schedule_templates() -> ServiceListResult:
    return ServiceListResult(list(SCHEDULE_TEMPLATES.values()))


def list_schedules(db: Session) -> ServiceListResult:
    rows = sync_recurring_workflows(db)
    return ServiceListResult([schedule_to_dict(row).root for row in rows])


def get_schedule(db: Session, schedule_key: str) -> ServiceObjectResult:
    return schedule_to_dict(get_recurring_workflow(db, schedule_key))


def list_schedule_runs(
    db: Session, schedule_key: str, *, limit: int = 50
) -> ServiceListResult:
    return ServiceListResult(
        [
            recurring_workflow_run_to_dict(row).root
            for row in list_recurring_workflow_runs(db, schedule_key, limit=limit)
        ]
    )


def run_schedule(
    db: Session, *, schedule_key: str, dry_run: bool, triggered_by: str = "operator"
) -> ServiceObjectResult:
    return run_recurring_workflow(
        db, workflow_key=schedule_key, dry_run=dry_run, triggered_by=triggered_by
    )


def schedule_to_dict(row: RecurringWorkflowRow) -> ServiceObjectResult:
    payload = dict(recurring_workflow_to_dict(row))
    output_action = (
        payload.get("output_action")
        if isinstance(payload.get("output_action"), dict)
        else {}
    )
    payload["handler_key"] = str(output_action.get("kind") or "")
    payload["category"] = _category_for(payload)
    payload["risk_level"] = _risk_level_for(payload)
    payload["editable"] = not bool(payload.get("is_builtin"))
    payload["deletable"] = not bool(payload.get("is_builtin"))
    return ServiceObjectResult(payload)


def create_schedule(db: Session, *, payload: dict[str, Any]) -> ServiceObjectResult:
    template_key, template = _template_for_payload(payload)
    workflow_key = _validated_new_workflow_key(db, payload)
    row = _build_custom_schedule_row(
        payload,
        template_key=template_key,
        template=template,
        workflow_key=workflow_key,
    )
    _validate_handler(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return schedule_to_dict(row)


def update_schedule(
    db: Session, schedule_key: str, *, payload: dict[str, Any]
) -> ServiceObjectResult:
    row = get_recurring_workflow(db, schedule_key)
    if "status" in payload:
        status = str(payload["status"])
        if status not in {"active", "paused", "disabled"}:
            raise ValueError("status must be active, paused, or disabled")
        row.status = status
    if row.is_builtin:
        db.commit()
        db.refresh(row)
        return schedule_to_dict(row)
    for attr in ("display_name", "description", "owner_role"):
        if attr in payload:
            setattr(row, attr, str(payload[attr]).strip())
    if "schedule" in payload:
        row.schedule_json = _json_dumps(_dict(payload["schedule"]))
    if "input_query" in payload:
        row.input_query_json = _json_dumps(_dict(payload["input_query"]))
    row.updated_at = utcnow()
    _validate_handler(row)
    db.commit()
    db.refresh(row)
    return schedule_to_dict(row)


def delete_schedule(db: Session, schedule_key: str) -> ServiceObjectResult:
    row = get_recurring_workflow(db, schedule_key)
    if row.is_builtin:
        raise ValueError("Built-in schedules cannot be deleted; disable them instead")
    payload = schedule_to_dict(row)
    db.delete(row)
    db.commit()
    return ServiceObjectResult({"deleted": True, "schedule": payload.root})


def _validate_handler(row: RecurringWorkflowRow) -> None:
    output_action = _dict(_json_loads(row.output_action_json, {}))
    handler_key = str(output_action.get("kind") or "")
    if handler_key not in _ALLOWED_HANDLER_KEYS:
        raise ValueError("Schedule handler is not allowlisted")


def _build_custom_schedule_row(
    payload: dict[str, Any],
    *,
    template_key: str,
    template: dict[str, Any],
    workflow_key: str,
) -> RecurringWorkflowRow:
    display_name = str(payload.get("display_name") or template["display_name"]).strip()
    return RecurringWorkflowRow(
        workflow_key=workflow_key,
        display_name=display_name,
        description=str(payload.get("description") or template["description"]),
        status=str(payload.get("status") or "active"),
        trigger_type="scheduled",
        owner_role=str(payload.get("owner_role") or "runtime_reliability_engineer"),
        schedule_json=_json_dumps(payload.get("schedule") or template["schedule"]),
        input_query_json=_json_dumps(
            {**template["input_query"], **_dict(payload.get("input_query"))}
        ),
        output_action_json=_json_dumps(template["output_action"]),
        escalation_rule_json=_json_dumps(
            {"on_failure": "notify_portfolio_operator", "template_key": template_key}
        ),
        validation_signal_json=_json_dumps(template["validation_signal"]),
        is_builtin=False,
    )


def _template_for_payload(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    template_key = str(payload.get("template_key") or "").strip()
    template = SCHEDULE_TEMPLATES.get(template_key)
    if template is None:
        raise ValueError("Unknown schedule template")
    return template_key, template


def _validated_new_workflow_key(db: Session, payload: dict[str, Any]) -> str:
    workflow_key = str(payload.get("workflow_key") or "").strip()
    if not _KEY_PATTERN.fullmatch(workflow_key):
        raise ValueError("workflow_key must be snake_case and 3-80 chars")
    if _schedule_exists(db, workflow_key):
        raise ValueError("Schedule key already exists")
    return workflow_key


def _schedule_exists(db: Session, workflow_key: str) -> bool:
    return (
        db.query(RecurringWorkflowRow)
        .filter(RecurringWorkflowRow.workflow_key == workflow_key)
        .first()
        is not None
    )


def _category_for(payload: dict[str, Any]) -> str:
    key = str(payload.get("workflow_key") or "")
    handler = str(payload.get("handler_key") or "")
    for category, matcher in _CATEGORY_MATCHERS:
        if matcher(key, handler):
            return category
    return "system_health"


_CATEGORY_MATCHERS = (
    ("infra_cleanup", lambda key, handler: "cleanup" in key or "cleanup" in handler),
    ("growth", lambda key, _handler: key.startswith(("x_social", "social_"))),
    ("release_runner", lambda key, _handler: key.startswith(("release", "ci_"))),
    (
        "planning",
        lambda key, _handler: any(
            token in key for token in ("planner", "review", "planning")
        ),
    ),
)


def _risk_level_for(payload: dict[str, Any]) -> str:
    handler = str(payload.get("handler_key") or "")
    if handler in {
        "cleanup_artifact_registry_versions",
        "destroy_old_secret_manager_versions",
    }:
        return "high"
    if bool(payload.get("is_builtin")) and str(
        payload.get("workflow_key") or ""
    ).startswith("x_social"):
        return "medium"
    return "low"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_loads(raw: str | None, default: Any) -> Any:
    import json

    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _json_dumps(payload: Any) -> str:
    import json

    return json.dumps(payload or {}, ensure_ascii=False, default=str)
