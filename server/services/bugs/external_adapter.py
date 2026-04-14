"""External log center adapter for bug intake."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.schemas import (
    BugIntakeRequest,
    ExternalLogCenterBatchRequest,
)
from server.services.bugs.intake import intake_bug


def _normalize_severity(value: str | None) -> str:
    lowered = str(value or "").strip().lower()
    if lowered in {"fatal", "critical", "sev0", "sev1"}:
        return "critical"
    if lowered in {"error", "high", "sev2"}:
        return "high"
    if lowered in {"warning", "warn", "medium"}:
        return "normal"
    if lowered in {"info", "low", "debug"}:
        return "low"
    return "high"


def intake_external_log_center_batch(db: Session, body: ExternalLogCenterBatchRequest) -> dict[str, Any]:
    created_bug_ids: list[int] = []
    updated_bug_ids: list[int] = []
    deduped_bug_ids: list[int] = []
    results: list[dict[str, object]] = []

    for event in list(body.events or []):
        metadata = dict(event.metadata or {})
        metadata["source_system"] = str(body.source_system or "log_center")
        if event.service_name:
            metadata["service_name"] = str(event.service_name)
        result = intake_bug(
            db,
            BugIntakeRequest(
                source_key="external_log_center_error",
                project_key=event.project_key,
                project_root_path=event.project_root_path,
                title=str(event.title or event.message[:120] or "External log error"),
                summary=str(event.message or "")[:500],
                severity=_normalize_severity(event.severity),
                fingerprint=event.fingerprint,
                source_ref=event.source_ref,
                environment=event.environment,
                log_excerpt=event.log_excerpt or event.message,
                stack_trace=event.stack_trace,
                metadata=metadata,
            ),
        )
        bug = dict(result.get("bug") or {})
        bug_id = int(bug.get("id") or 0)
        if result["result"] == "created":
            created_bug_ids.append(bug_id)
        elif result["result"] == "updated":
            updated_bug_ids.append(bug_id)
        else:
            deduped_bug_ids.append(bug_id)
        results.append(result)

    return {
        "source_system": str(body.source_system or "log_center"),
        "accepted_count": len(results),
        "created_bug_ids": sorted(set(created_bug_ids)),
        "updated_bug_ids": sorted(set(updated_bug_ids)),
        "deduped_bug_ids": sorted(set(deduped_bug_ids)),
        "results": results,
    }
