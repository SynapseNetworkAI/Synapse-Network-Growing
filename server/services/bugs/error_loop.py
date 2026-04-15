"""Error intake, fingerprint dedupe, requirement auto-loop, and stability views."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    ErrorEventRow,
    ErrorFingerprintRow,
    ExecutionRunRow,
    ProjectPolicyRow,
    ReleaseRecordRow,
    RequirementRow,
    utcnow,
)
from server.schemas import (
    AgentFirstRequirementOut,
    ErrorEventOut,
    ErrorFingerprintDetailOut,
    ErrorFingerprintOut,
    ErrorIntakeRequest,
    NotificationDeliveryOut,
    ReleaseRecordSlimOut,
    ExecutionRunOut,
    RequirementCreate,
)
from server.logging_utils import get_logger, log_event
from server.services.requirements.sources import ACTIVE_BUG_REQUIREMENT_STATUSES, normalize_requirement_intake_metadata
from server.services.runtime.alerting import build_ops_url, deliver_lark_notification, notification_service_label
from server.services.bugs.discovery import (
    build_error_discovery_recommendation,
    resolve_or_create_signal_project,
    update_error_discovery_state,
)
from server.services.projects.project_center import ensure_projects_materialized
from server.services.workflows.agent_first import (
    build_execution_detail,
    build_release_detail,
    build_requirement_detail,
    create_requirement,
    submit_requirement,
)

ALLOWED_ERROR_SOURCE_KINDS = {"runtime_log_error", "task_failure", "workflow_incident"}
_SEVERITY_RANK = {"low": 0, "normal": 1, "warning": 1, "high": 2, "critical": 3}
logger = get_logger("ops-dashboard.error_loop")


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_text(value: str | None, *, collapse_digits: bool = False, limit: int = 240) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    if collapse_digits:
        text = "".join("#" if ch.isdigit() else ch for ch in text)
    return text[:limit]


def _stack_signature(stack_trace: str | None) -> str:
    lines = [line.strip() for line in str(stack_trace or "").splitlines() if line.strip()]
    reduced = []
    for line in lines[:5]:
        line = re.sub(r":\d+", ":#", line)
        reduced.append(_normalize_text(line, collapse_digits=True, limit=120))
    return " | ".join(item for item in reduced if item)


def _fingerprint_key(body: ErrorIntakeRequest) -> tuple[str, str, str]:
    incident_code = _normalize_text(body.incident_code or "", collapse_digits=True, limit=80)
    normalized_message = _normalize_text(body.message, collapse_digits=True, limit=200)
    stack_sig = _stack_signature(body.stack_trace)
    root_scope = _normalize_text(body.project_key or body.project_root_path or "", collapse_digits=True, limit=120)
    payload = "|".join(
        [
            _normalize_text(body.source_kind, limit=40),
            root_scope,
            incident_code,
            normalized_message,
            stack_sig,
        ]
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{body.source_kind}:{digest}", normalized_message, stack_sig


def _severity(value: str | None) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in _SEVERITY_RANK:
        return "normal"
    return "normal" if normalized == "warning" else normalized


def _priority_for_severity(value: str) -> str:
    return "high" if _SEVERITY_RANK.get(value, 1) >= _SEVERITY_RANK["high"] else "normal"


def _ensure_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _policy_target(db: Session, *, project_key: str | None, project_root_path: str | None) -> tuple[ProjectPolicyRow | None, str | None]:
    cleaned_key = str(project_key or "").strip().lower()
    cleaned_root = str(project_root_path or "").strip()
    policy = None
    if cleaned_key:
        policy = db.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == cleaned_key).first()
    if policy is None and cleaned_root:
        policy = db.query(ProjectPolicyRow).filter(ProjectPolicyRow.root_path == cleaned_root).first()
    target = cleaned_root or (str(getattr(policy, "root_path", "") or "").strip() or None)
    return policy, target


def _active_requirement_for_fingerprint(db: Session, fingerprint_key: str) -> RequirementRow | None:
    return (
        db.query(RequirementRow)
        .filter(
            RequirementRow.source == "bug_intake",
            RequirementRow.source_ref == f"error-fingerprint:{fingerprint_key}",
            RequirementRow.status.in_(tuple(ACTIVE_BUG_REQUIREMENT_STATUSES)),
        )
        .order_by(RequirementRow.id.desc())
        .first()
    )


def _notification_deliveries_for_fingerprint(db: Session, fingerprint_key: str) -> list[NotificationDeliveryOut]:
    from server.database import NotificationDeliveryRow

    rows = (
        db.query(NotificationDeliveryRow)
        .filter(
            NotificationDeliveryRow.object_type == "error_fingerprint",
            NotificationDeliveryRow.object_key == fingerprint_key,
        )
        .order_by(NotificationDeliveryRow.id.desc())
        .all()
    )
    return [
        NotificationDeliveryOut(
            id=int(row.id),
            channel=str(row.channel or ""),
            event_type=str(row.event_type or ""),
            event_key=str(row.event_key or ""),
            object_type=str(row.object_type or ""),
            object_key=str(row.object_key or ""),
            service_name=str(row.service_name or "").strip() or None,
            status=str(row.status or ""),
            payload=_json_load(getattr(row, "payload_json", None), {}),
            response_excerpt=str(row.response_excerpt or "").strip() or None,
            delivered_at=row.delivered_at,
            created_at=row.created_at,
        )
        for row in rows
    ]


def _release_to_out(requirement_id: int, db: Session) -> ReleaseRecordSlimOut | None:
    try:
        return build_release_detail(db, requirement_id).release
    except Exception:
        return None


def _execution_to_out(execution_run_id: int | None, db: Session) -> ExecutionRunOut | None:
    if execution_run_id is None:
        return None
    try:
        return build_execution_detail(db, execution_run_id).execution
    except Exception:
        return None


def _requirement_to_out(requirement_id: int | None, db: Session) -> AgentFirstRequirementOut | None:
    if requirement_id is None:
        return None
    try:
        return build_requirement_detail(db, requirement_id).requirement
    except Exception:
        return None


def _event_to_out(row: ErrorEventRow) -> ErrorEventOut:
    return ErrorEventOut(
        id=int(row.id),
        fingerprint_key=str(row.fingerprint_key or ""),
        source_kind=str(row.source_kind or ""),
        service_name=str(row.service_name or ""),
        project_key=str(row.project_key or "").strip() or None,
        project_root_path=str(row.project_root_path or "").strip() or None,
        incident_code=str(row.incident_code or "").strip() or None,
        severity=str(row.severity or "normal"),
        summary=str(row.summary or ""),
        message=str(row.message or ""),
        stack_trace=str(row.stack_trace or "").strip() or None,
        source_ref=str(row.source_ref or "").strip() or None,
        environment=str(row.environment or "").strip() or None,
        metadata=_json_load(getattr(row, "metadata_json", None), {}),
        occurred_at=row.occurred_at,
        created_at=row.created_at,
    )


def _fingerprint_to_out(row: ErrorFingerprintRow, db: Session) -> ErrorFingerprintOut:
    requirement = _requirement_to_out(int(row.linked_requirement_id), db) if row.linked_requirement_id is not None else None
    latest_execution_id = requirement.latest_execution_run_id if requirement is not None else None
    discovery = _json_load(getattr(row, "discovery_recommendation_json", None), {})
    return ErrorFingerprintOut(
        fingerprint_key=str(row.fingerprint_key or ""),
        source_kind=str(row.source_kind or ""),
        service_name=str(row.service_name or ""),
        project_key=str(row.project_key or "").strip() or None,
        project_root_path=str(row.project_root_path or "").strip() or None,
        incident_code=str(row.incident_code or "").strip() or None,
        severity=str(row.severity or "normal"),
        summary=str(row.summary or ""),
        evidence_excerpt=str(row.evidence_excerpt or "").strip() or None,
        status=str(row.status or "open"),
        occurrence_count=int(row.occurrence_count or 0),
        first_seen_at=row.first_seen_at,
        latest_seen_at=row.latest_seen_at,
        latest_error_event_id=int(row.latest_error_event_id) if row.latest_error_event_id is not None else None,
        linked_requirement_id=int(row.linked_requirement_id) if row.linked_requirement_id is not None else None,
        materialized_requirement_id=int(row.linked_requirement_id) if row.linked_requirement_id is not None else None,
        latest_execution_run_id=latest_execution_id,
        discovery_status=str(getattr(row, "discovery_status", None) or "pending"),
        discovery_recommendation=discovery or None,
        last_discovery_at=getattr(row, "last_discovery_at", None),
    )


def _error_description_markdown(
    *,
    body: ErrorIntakeRequest,
    fingerprint_key: str,
    evidence_excerpt: str,
    error_page_url: str | None,
) -> str:
    lines = [
        f"# Error Recovery: {body.summary.strip()}",
        "",
        f"- source_kind: `{body.source_kind}`",
        f"- service_name: `{body.service_name.strip()}`",
        f"- severity: `{_severity(body.severity)}`",
        f"- fingerprint: `{fingerprint_key}`",
    ]
    if body.project_key:
        lines.append(f"- project_key: `{body.project_key.strip()}`")
    if body.incident_code:
        lines.append(f"- incident_code: `{body.incident_code.strip()}`")
    if error_page_url:
        lines.append(f"- error_page: {error_page_url}")
    lines.extend(
        [
            "",
            "## Summary",
            body.summary.strip(),
            "",
            "## Latest Evidence",
            "",
            "```text",
            evidence_excerpt,
            "```",
        ]
    )
    if str(body.stack_trace or "").strip():
        lines.extend(["", "## Stack Trace", "", "```text", str(body.stack_trace).strip()[:2200], "```"])
    return "\n".join(lines)


def _error_acceptance_markdown(service_name: str) -> str:
    return "\n".join(
        [
            "- 找到并修复该错误的根因或缺失的保护逻辑",
            "- 保留最小必要变更，不扩散到无关项目",
            f"- 为 `{service_name}` 补充足够证据，使 validate 能确认错误已被处理",
            "- 若不能立即修复，至少给出可执行的隔离或恢复方案",
        ]
    )


def _error_approval_contract(body: ErrorIntakeRequest, *, project_count: int) -> dict[str, object]:
    if _severity(_severity(body.severity)) == "high" and body.source_kind == "workflow_incident":
        manual = True
    else:
        manual = _severity(body.severity) == "critical" or project_count > 1
    if manual:
        return {
            "approval_mode": "manual_required",
            "required_approver_roles": ["request_owner", "reviewer", "tester", "operator"],
            "fallback_reviewer": "operator",
            "auto_approve": {
                "enabled": False,
                "max_priority": "normal",
                "max_complexity_tier": "standard",
                "single_project_only": True,
                "allow_incident_recovery": False,
            },
        }
    return {
        "approval_mode": "auto_or_human",
        "required_approver_roles": ["request_owner", "reviewer", "tester"],
        "fallback_reviewer": "operator",
        "auto_approve": {
            "enabled": True,
            "max_priority": "normal",
            "max_complexity_tier": "standard",
            "single_project_only": True,
            "allow_incident_recovery": False,
        },
    }


def _notify_error_logged(
    db: Session,
    *,
    fingerprint_key: str,
    body: ErrorIntakeRequest,
    event_id: int,
    requirement_id: int | None,
    execution_id: int | None,
    error_page_url: str | None,
) -> None:
    service = notification_service_label(service_name=body.service_name, project_key=body.project_key)
    deliver_lark_notification(
        db,
        channel="alert",
        event_type="error_logged",
        event_key=f"alert:error_logged:event:{event_id}",
        object_type="error_fingerprint",
        object_key=fingerprint_key,
        service_name=service,
        status_or_severity=_severity(body.severity),
        summary=body.summary.strip() or body.message.strip()[:120],
        next_action="查看错误日志页与关联 requirement，确认是否需要人工审批或等待自动执行完成。",
        actor_or_source=body.source_kind,
        occurred_at=_ensure_utc(body.occurred_at),
        object_refs={
            "fingerprint_key": fingerprint_key,
            "requirement_id": requirement_id,
            "execution_id": execution_id,
            "project_key": body.project_key,
        },
        links={
            "错误页": error_page_url or "",
            "需求": build_ops_url(f"/requirements/{requirement_id}") or "" if requirement_id else "",
            "执行": build_ops_url(f"/executions/{execution_id}") or "" if execution_id else "",
        },
    )


def _refresh_requirement_intake_metadata(
    requirement: RequirementRow,
    *,
    fingerprint_key: str,
    body: ErrorIntakeRequest,
    event: ErrorEventRow,
    occurrence_count: int,
    error_page_url: str | None,
) -> None:
    metadata = normalize_requirement_intake_metadata(
        "bug_intake",
        f"error-fingerprint:{fingerprint_key}",
        _json_load(getattr(requirement, "intake_metadata_json", None), {}),
    )
    metadata.update(
        {
            "fingerprint_key": fingerprint_key,
            "source_kind": body.source_kind,
            "service_name": body.service_name.strip(),
            "project_key": body.project_key,
            "severity": _severity(body.severity),
            "occurrence_count": occurrence_count,
            "latest_error_event_id": int(event.id),
            "latest_seen_at": _ensure_utc(body.occurred_at).isoformat(),
            "evidence_excerpt": str(body.message or "").strip()[:600],
            "linked_error_page_url": error_page_url,
        }
    )
    requirement.intake_metadata_json = _json_dump(metadata)
    requirement.updated_at = utcnow()


def list_error_fingerprints(db: Session) -> list[ErrorFingerprintOut]:
    rows = (
        db.query(ErrorFingerprintRow)
        .order_by(ErrorFingerprintRow.latest_seen_at.desc(), ErrorFingerprintRow.id.desc())
        .all()
    )
    return [_fingerprint_to_out(row, db) for row in rows]


def build_error_fingerprint_detail(db: Session, fingerprint_key: str) -> ErrorFingerprintDetailOut:
    row = db.query(ErrorFingerprintRow).filter(ErrorFingerprintRow.fingerprint_key == fingerprint_key).first()
    if row is None:
        raise ValueError("Error fingerprint not found.")
    events = (
        db.query(ErrorEventRow)
        .filter(ErrorEventRow.fingerprint_key == fingerprint_key)
        .order_by(ErrorEventRow.occurred_at.desc(), ErrorEventRow.id.desc())
        .all()
    )
    requirement = _requirement_to_out(int(row.linked_requirement_id), db) if row.linked_requirement_id is not None else None
    latest_execution = _execution_to_out(requirement.latest_execution_run_id if requirement is not None else None, db)
    release = _release_to_out(int(requirement.id), db) if requirement is not None else None
    return ErrorFingerprintDetailOut(
        fingerprint=_fingerprint_to_out(row, db),
        requirement=requirement,
        latest_execution=latest_execution,
        release=release,
        events=[_event_to_out(event) for event in events],
        notifications=_notification_deliveries_for_fingerprint(db, fingerprint_key),
    )


def intake_error_event(db: Session, body: ErrorIntakeRequest) -> ErrorFingerprintDetailOut:
    ensure_projects_materialized(db)
    source_kind = str(body.source_kind or "").strip()
    if source_kind not in ALLOWED_ERROR_SOURCE_KINDS:
        raise ValueError("source_kind must be one of runtime_log_error|task_failure|workflow_incident")
    if not str(body.service_name or "").strip():
        raise ValueError("service_name is required.")
    if not str(body.summary or "").strip():
        raise ValueError("summary is required.")
    if not str(body.message or "").strip():
        raise ValueError("message is required.")

    fingerprint_key, normalized_message, stack_signature = _fingerprint_key(body)
    occurred_at = _ensure_utc(body.occurred_at)
    policy, target_project_path = _policy_target(db, project_key=body.project_key, project_root_path=body.project_root_path)
    error_page_url = build_ops_url(f"/errors/{fingerprint_key}")
    evidence_excerpt = str(body.message or "").strip()[:800]

    fingerprint = db.query(ErrorFingerprintRow).filter(ErrorFingerprintRow.fingerprint_key == fingerprint_key).first()
    severity = _severity(body.severity)
    if fingerprint is None:
        fingerprint = ErrorFingerprintRow(
            fingerprint_key=fingerprint_key,
            source_kind=source_kind,
            service_name=body.service_name.strip(),
            project_key=str(body.project_key or "").strip() or str(getattr(policy, "project_key", "") or "").strip() or None,
            project_root_path=str(target_project_path or body.project_root_path or "").strip() or None,
            incident_code=str(body.incident_code or "").strip() or None,
            severity=severity,
            summary=body.summary.strip(),
            normalized_message=normalized_message,
            stack_signature=stack_signature,
            evidence_excerpt=evidence_excerpt,
            occurrence_count=0,
            metadata_json=_json_dump({"environment": body.environment, **(body.metadata or {})}),
            first_seen_at=occurred_at,
            latest_seen_at=occurred_at,
        )
        db.add(fingerprint)
        db.flush()
    else:
        if _SEVERITY_RANK.get(severity, 1) > _SEVERITY_RANK.get(str(fingerprint.severity or "normal"), 1):
            fingerprint.severity = severity
        fingerprint.summary = body.summary.strip() or str(fingerprint.summary or "")
        fingerprint.service_name = body.service_name.strip() or str(fingerprint.service_name or "")
        fingerprint.project_key = str(body.project_key or fingerprint.project_key or "").strip() or None
        fingerprint.project_root_path = str(target_project_path or fingerprint.project_root_path or "").strip() or None
        fingerprint.incident_code = str(body.incident_code or fingerprint.incident_code or "").strip() or None
        fingerprint.normalized_message = normalized_message or str(fingerprint.normalized_message or "")
        fingerprint.stack_signature = stack_signature or str(fingerprint.stack_signature or "")
        fingerprint.evidence_excerpt = evidence_excerpt or str(fingerprint.evidence_excerpt or "")
        fingerprint.latest_seen_at = occurred_at

    event = ErrorEventRow(
        fingerprint_key=fingerprint_key,
        source_kind=source_kind,
        service_name=body.service_name.strip(),
        project_key=str(body.project_key or getattr(policy, "project_key", "") or "").strip() or None,
        project_root_path=str(target_project_path or body.project_root_path or "").strip() or None,
        incident_code=str(body.incident_code or "").strip() or None,
        severity=severity,
        summary=body.summary.strip(),
        message=body.message.strip(),
        stack_trace=str(body.stack_trace or "").strip() or None,
        source_ref=str(body.source_ref or "").strip() or None,
        environment=str(body.environment or "").strip() or None,
        metadata_json=_json_dump(body.metadata or {}),
        occurred_at=occurred_at,
    )
    db.add(event)
    db.flush()

    fingerprint.latest_error_event_id = int(event.id)
    fingerprint.occurrence_count = int(fingerprint.occurrence_count or 0) + 1
    log_event(
        logger,
        "error_event_ingested",
        fingerprint_key=fingerprint_key,
        source_kind=source_kind,
        service_name=body.service_name.strip(),
        project_key=str(body.project_key or getattr(policy, "project_key", "") or "").strip() or None,
        severity=severity,
        error_event_id=int(event.id),
        occurrence_count=int(fingerprint.occurrence_count or 1),
    )

    source_ref = f"error-fingerprint:{fingerprint_key}"
    requirement = _active_requirement_for_fingerprint(db, fingerprint_key)
    created_requirement = False
    recommendation = build_error_discovery_recommendation(fingerprint)
    log_event(
        logger,
        "error_discovery_recommendation",
        fingerprint_key=fingerprint_key,
        discovery_action=str(recommendation.get("discovery_action") or ""),
        confidence=recommendation.get("confidence"),
        severity=severity,
        occurrence_count=int(fingerprint.occurrence_count or 1),
    )
    if requirement is not None:
        update_error_discovery_state(fingerprint, recommendation=recommendation, status="linked_active_requirement")
    elif str(recommendation.get("discovery_action") or "") == "auto_materialize":
        project = resolve_or_create_signal_project(
            db,
            project_key=str(body.project_key or getattr(policy, "project_key", "") or "").strip() or None,
            project_root_path=target_project_path,
            display_name=str(body.project_key or getattr(policy, "project_key", "") or body.service_name or "").strip() or None,
        )
        if project is None:
            update_error_discovery_state(fingerprint, recommendation=recommendation, status="queued_for_operator")
            db.add(fingerprint)
            db.commit()
            requirement = None
        else:
            update_error_discovery_state(fingerprint, recommendation=recommendation, status="recommended")
            body_payload = RequirementCreate(
                title=str(recommendation.get("suggested_title") or f"Error Recovery: {body.summary.strip()[:96]}"),
                description_markdown=_error_description_markdown(
                    body=body,
                    fingerprint_key=fingerprint_key,
                    evidence_excerpt=evidence_excerpt,
                    error_page_url=error_page_url,
                ),
                acceptance_criteria_markdown=_error_acceptance_markdown(body.service_name.strip()),
                priority=_priority_for_severity(severity),
                source="bug_intake",
                source_ref=source_ref,
                project_id=int(project.id),
                intake_metadata=normalize_requirement_intake_metadata(
                    "bug_intake",
                    source_ref,
                    {
                        "intake_reason": "materialized_from_error_event",
                        "confidence": 0.93,
                        "intake_mode": "automatic",
                        "registry_hint": "error_auto_loop",
                        "trigger": "error_events_intake",
                        "fingerprint_key": fingerprint_key,
                        "source_kind": source_kind,
                        "service_name": body.service_name.strip(),
                        "project_key": str(body.project_key or getattr(policy, "project_key", "") or "").strip() or None,
                        "severity": severity,
                        "discovery_action": str(recommendation.get("discovery_action") or ""),
                        "discovery_confidence": recommendation.get("confidence"),
                        "discovery_reason": str(recommendation.get("reason") or ""),
                        "occurrence_count": int(fingerprint.occurrence_count or 1),
                        "first_seen_at": occurred_at.isoformat(),
                        "latest_seen_at": occurred_at.isoformat(),
                        "latest_error_event_id": int(event.id),
                        "evidence_excerpt": evidence_excerpt,
                        "linked_error_page_url": error_page_url,
                        "affected_project_keys": [str(body.project_key or getattr(policy, "project_key", "") or "").strip()] if str(body.project_key or getattr(policy, "project_key", "") or "").strip() else [],
                    },
                ),
                target_project_path=target_project_path,
                approval_contract=_error_approval_contract(
                    body,
                    project_count=len([item for item in str(target_project_path or "").splitlines() if item.strip()]) or 1,
                ),
            )
            requirement = create_requirement(db, body_payload).requirement
            requirement = db.query(RequirementRow).filter(RequirementRow.id == requirement.id).first()
            created_requirement = requirement is not None
            if requirement is not None:
                update_error_discovery_state(fingerprint, recommendation=recommendation, status="materialized")
                log_event(
                    logger,
                    "error_requirement_materialized",
                    fingerprint_key=fingerprint_key,
                    requirement_id=int(requirement.id),
                    source_kind=source_kind,
                    severity=severity,
                    created_from_error=True,
                )
    elif str(recommendation.get("discovery_action") or "") == "queue_for_operator":
        update_error_discovery_state(fingerprint, recommendation=recommendation, status="queued_for_operator")
    else:
        update_error_discovery_state(fingerprint, recommendation=recommendation, status="ignored_as_noise")

    if requirement is not None:
        fingerprint.linked_requirement_id = int(requirement.id)
        _refresh_requirement_intake_metadata(
            requirement,
            fingerprint_key=fingerprint_key,
            body=body,
            event=event,
            occurrence_count=int(fingerprint.occurrence_count or 1),
            error_page_url=error_page_url,
        )
    db.add(fingerprint)
    db.commit()

    execution_id: int | None = None
    active_status = str(requirement.status or "") if requirement is not None else ""
    latest_execution = (
        db.query(ExecutionRunRow)
        .filter(ExecutionRunRow.requirement_id == int(requirement.id))
        .order_by(ExecutionRunRow.id.desc())
        .first()
        if requirement is not None
        else None
    )
    latest_execution_id = int(latest_execution.id) if latest_execution is not None else 0
    should_submit_requirement = requirement is not None and (
        created_requirement
        or latest_execution_id <= 0
        or active_status in {"draft", "needs_revision"}
    )
    if should_submit_requirement:
        detail = submit_requirement(db, int(requirement.id))
        execution_id = detail.approval.execution_run_id
        log_event(
            logger,
            "error_requirement_submitted",
            fingerprint_key=fingerprint_key,
            requirement_id=int(requirement.id),
            execution_id=execution_id,
            approval_status=str(detail.requirement.approval_status or ""),
            requirement_status=str(detail.requirement.status or ""),
        )
    elif requirement is not None:
        detail = build_requirement_detail(db, int(requirement.id))
        execution_id = detail.latest_execution_id

    _notify_error_logged(
        db,
        fingerprint_key=fingerprint_key,
        body=body,
        event_id=int(event.id),
        requirement_id=int(requirement.id) if requirement is not None else None,
        execution_id=execution_id,
        error_page_url=error_page_url,
    )
    db.commit()
    return build_error_fingerprint_detail(db, fingerprint_key)
