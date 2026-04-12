"""Bug intake normalization and dedupe service."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import BugRecordRow
from server.schemas import BugIntakeRequest
from server.services.bug_sources import get_bug_source_definition

_MAX_EVIDENCE_ITEMS = 5
_MAX_EXCERPT_LENGTH = 500
_SEVERITY_RANK = {"low": 0, "normal": 1, "high": 2, "critical": 3}
_SEVERITY_BASE_SCORE = {"low": 5.0, "normal": 15.0, "high": 35.0, "critical": 50.0}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _clean_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_severity(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"critical", "high", "normal", "low"}:
        return normalized
    if normalized in {"medium", ""}:
        return "normal"
    raise ValueError("severity must be one of critical|high|normal|low")


def _merge_severity(current: str | None, incoming: str) -> str:
    current_normalized = _normalize_severity(current)
    return incoming if _SEVERITY_RANK[incoming] > _SEVERITY_RANK[current_normalized] else current_normalized


def _freshness_score(last_seen_at: datetime | None, now: datetime) -> float:
    if last_seen_at is None:
        return 8.0
    seen = last_seen_at if last_seen_at.tzinfo else last_seen_at.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (now - seen).total_seconds() / 3600.0)
    if age_hours <= 1:
        return 20.0
    if age_hours <= 6:
        return 16.0
    if age_hours <= 24:
        return 12.0
    if age_hours <= 72:
        return 7.0
    return 3.0


def _blocker_score(source_key: str, severity: str, metadata: dict[str, object]) -> tuple[float, list[str]]:
    blockers: list[str] = []
    score = 0.0
    lowered_source = str(source_key or "").strip().lower()
    lowered_metadata = json.dumps(metadata or {}, ensure_ascii=False).lower()
    if lowered_source == "delivery_blocker_bug":
        blockers.append("delivery_blocker")
        score += 25.0
    if lowered_source == "workflow_incident":
        blockers.append("workflow_incident")
        score += 18.0
    if "publish_block" in lowered_metadata or "release_block" in lowered_metadata:
        blockers.append("publish_blocked")
        score += 20.0
    if "blocking" in lowered_metadata or "blocker" in lowered_metadata:
        blockers.append("explicit_blocker")
        score += 15.0
    if severity == "critical":
        blockers.append("critical_severity")
        score += 12.0
    return min(score, 30.0), sorted(set(blockers))


def _priority_from_total(total: float, severity: str, blockers: list[str]) -> str:
    if severity == "critical" or total >= 85 or "delivery_blocker" in blockers:
        return "critical"
    if total >= 60:
        return "high"
    if total >= 30:
        return "normal"
    return "low"


def _score_bug_record(
    *,
    source: dict[str, Any],
    severity: str,
    occurrence_count: int,
    last_seen_at: datetime | None,
    metadata: dict[str, object],
    now: datetime,
) -> dict[str, object]:
    severity_score = _SEVERITY_BASE_SCORE[severity]
    recurrence_score = min(max(int(occurrence_count) - 1, 0) * 8.0, 24.0)
    freshness_score = _freshness_score(last_seen_at, now)
    blocker_score, blocker_flags = _blocker_score(str(source.get("source_key") or ""), severity, metadata)
    total = min(100.0, severity_score + recurrence_score + freshness_score + blocker_score)
    priority = _priority_from_total(total, severity, blocker_flags)
    policy = dict(source.get("auto_requirement_policy") or {})
    auto_allowed = bool(policy.get("allowed", False))
    auto_intake_eligible = auto_allowed and (priority in {"critical", "high"} or total >= 65.0)
    return {
        "severity_score": round(severity_score, 2),
        "recurrence_score": round(recurrence_score, 2),
        "freshness_score": round(freshness_score, 2),
        "blocker_score": round(blocker_score, 2),
        "blocker_flags": blocker_flags,
        "total": round(total, 2),
        "priority": priority,
        "auto_intake_eligible": auto_intake_eligible,
        "intake_reason": (
            "blocking_bug_candidate"
            if blocker_flags
            else "high_value_recurrent_bug"
            if auto_intake_eligible
            else "needs_additional_review"
        ),
        "scored_at": now.isoformat(),
    }


def _normalize_project_scope(project_key: str | None, project_root_path: str | None) -> tuple[str | None, str | None, str]:
    key = str(project_key or "").strip().lower() or None
    root = str(project_root_path or "").strip() or None
    scope = key or root or "global"
    return key, root, scope


def _derive_fingerprint(body: BugIntakeRequest) -> str:
    if str(body.fingerprint or "").strip():
        seed = _clean_text(body.fingerprint)
    else:
        pieces = [
            _clean_text(body.title).lower(),
            _clean_text(body.summary).lower(),
            _clean_text(body.log_excerpt).lower(),
            _clean_text(body.stack_trace).lower(),
        ]
        metadata = body.metadata or {}
        if metadata:
            pieces.append(_clean_text(_json_dumps(metadata)).lower())
        seed = " | ".join(piece for piece in pieces if piece)
    if not seed:
        raise ValueError("fingerprint could not be derived from the intake payload")
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"fp_{digest}"


def _build_bug_key(source_key: str, scope: str, fingerprint: str) -> str:
    return f"{source_key}::{scope}::{fingerprint}"


def _build_evidence_entry(body: BugIntakeRequest, fingerprint: str) -> dict[str, object]:
    log_excerpt = str(body.log_excerpt or "").strip()
    stack_trace = str(body.stack_trace or "").strip()
    return {
        "captured_at": _utcnow().isoformat(),
        "source_ref": str(body.source_ref or "").strip() or None,
        "environment": str(body.environment or "").strip() or None,
        "fingerprint": fingerprint,
        "log_excerpt": log_excerpt[:_MAX_EXCERPT_LENGTH] or None,
        "stack_trace": stack_trace[:_MAX_EXCERPT_LENGTH] or None,
        "title": _clean_text(body.title) or None,
        "summary": _clean_text(body.summary) or None,
    }


def _merge_evidence(existing: list[dict[str, object]], incoming: dict[str, object]) -> tuple[list[dict[str, object]], bool]:
    evidence_key = (
        str(incoming.get("source_ref") or ""),
        str(incoming.get("environment") or ""),
        str(incoming.get("log_excerpt") or ""),
        str(incoming.get("stack_trace") or ""),
        str(incoming.get("title") or ""),
        str(incoming.get("summary") or ""),
    )
    for item in existing:
        item_key = (
            str(item.get("source_ref") or ""),
            str(item.get("environment") or ""),
            str(item.get("log_excerpt") or ""),
            str(item.get("stack_trace") or ""),
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
        )
        if item_key == evidence_key:
            item["captured_at"] = incoming.get("captured_at")
            return existing[:_MAX_EVIDENCE_ITEMS], True
    merged = [incoming, *existing]
    return merged[:_MAX_EVIDENCE_ITEMS], False


def serialize_bug_record(row: BugRecordRow) -> dict[str, object]:
    return {
        "id": int(row.id),
        "bug_key": str(row.bug_key or ""),
        "source_key": str(row.source_key or ""),
        "source_kind": str(row.source_kind or ""),
        "status": str(row.status or "open"),
        "title": str(row.title or ""),
        "summary": str(row.summary or ""),
        "severity": str(row.severity or "normal"),
        "fingerprint": str(row.fingerprint or ""),
        "project_key": str(row.project_key or "") or None,
        "project_root_path": str(row.project_root_path or "") or None,
        "source_ref": str(row.source_ref or "") or None,
        "environment": str(row.environment or "") or None,
        "occurrence_count": int(row.occurrence_count or 0),
        "evidence": _json_loads(row.evidence_json, []),
        "metadata": _json_loads(row.metadata_json, {}),
        "scorecard": _json_loads(row.scorecard_json, {}),
        "converted_requirement_id": row.converted_requirement_id,
        "first_seen_at": row.first_seen_at,
        "last_seen_at": row.last_seen_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def intake_bug(db: Session, body: BugIntakeRequest) -> dict[str, object]:
    source = get_bug_source_definition(body.source_key)
    title = _clean_text(body.title)
    if not title:
        raise ValueError("title is required")
    severity = _normalize_severity(body.severity)
    project_key, project_root_path, project_scope = _normalize_project_scope(body.project_key, body.project_root_path)
    fingerprint = _derive_fingerprint(body)
    bug_key = _build_bug_key(str(source["source_key"]), project_scope, fingerprint)
    evidence_entry = _build_evidence_entry(body, fingerprint)
    summary = str(body.summary or "").strip()
    source_ref = str(body.source_ref or "").strip() or None
    environment = str(body.environment or "").strip() or None
    metadata = dict(body.metadata or {})
    metadata["source_display_name"] = source.get("display_name")

    existing = db.query(BugRecordRow).filter(BugRecordRow.bug_key == bug_key).first()
    now = _utcnow()
    if existing is None:
        scorecard = _score_bug_record(
            source=source,
            severity=severity,
            occurrence_count=1,
            last_seen_at=now,
            metadata=metadata,
            now=now,
        )
        row = BugRecordRow(
            bug_key=bug_key,
            source_key=str(source["source_key"]),
            source_kind=str(source["source_kind"]),
            status="open",
            title=title,
            summary=summary,
            severity=severity,
            fingerprint=fingerprint,
            project_key=project_key,
            project_root_path=project_root_path,
            source_ref=source_ref,
            environment=environment,
            occurrence_count=1,
            evidence_json=_json_dumps([evidence_entry]),
            metadata_json=_json_dumps(metadata),
            scorecard_json=_json_dumps(scorecard),
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"result": "created", "bug": serialize_bug_record(row)}

    evidence_items = _json_loads(existing.evidence_json, [])
    merged_evidence, deduped = _merge_evidence(evidence_items, evidence_entry)
    existing.title = existing.title or title
    existing.summary = summary or existing.summary
    existing.severity = _merge_severity(existing.severity, severity)
    existing.project_key = existing.project_key or project_key
    existing.project_root_path = existing.project_root_path or project_root_path
    existing.source_ref = source_ref or existing.source_ref
    existing.environment = environment or existing.environment
    existing.occurrence_count = int(existing.occurrence_count or 0) + 1
    existing.last_seen_at = now
    existing.evidence_json = _json_dumps(merged_evidence)
    merged_metadata = {**_json_loads(existing.metadata_json, {}), **metadata}
    existing.metadata_json = _json_dumps(merged_metadata)
    existing.scorecard_json = _json_dumps(
        _score_bug_record(
            source=source,
            severity=existing.severity,
            occurrence_count=existing.occurrence_count,
            last_seen_at=existing.last_seen_at,
            metadata=merged_metadata,
            now=now,
        )
    )
    db.add(existing)
    db.commit()
    db.refresh(existing)
    return {
        "result": "deduped" if deduped else "updated",
        "bug": serialize_bug_record(existing),
    }
