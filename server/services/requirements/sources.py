"""Requirement source registry and unified intake entrypoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import BugRecordRow, CompanyOperatingReviewRow, OptimizationSignalRow, ProjectPolicyRow, RequirementRow
from server.schemas import RequirementCreate
from server.schemas import OptimizationSignalAutoIntakeRequest


DEFAULT_INTAKE_CONFIDENCE_BY_SOURCE = {
    "manual": 1.0,
    "optimization_signal": 0.85,
    "company_review_bundle": 0.75,
    "automation_candidate": 0.8,
    "bug_intake": 0.9,
    "optimization_template": 0.7,
    "bugfix_circuit_breaker": 0.95,
}

FOLLOWUP_SOURCES = {"bugfix_circuit_breaker"}
ACTIVE_BUG_REQUIREMENT_STATUSES = {
    "draft",
    "pending_approval",
    "approved",
    "planning",
    "plan_failed",
    "ready",
    "in_progress",
    "blocked",
    "paused",
    "needs_revision",
}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_source_key(source: str | None, source_ref: str | None = None) -> str:
    normalized = str(source or "manual").strip() or "manual"
    source_ref_text = str(source_ref or "").strip()
    if normalized in FOLLOWUP_SOURCES or source_ref_text.startswith("bugfix-circuit-breaker:"):
        return "incident_followup"
    return normalized


def normalize_requirement_intake_metadata(
    source: str | None,
    source_ref: str | None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    source_key = _normalize_source_key(source, source_ref)
    raw = dict(metadata or {})
    intake_reason = str(raw.get("intake_reason") or "").strip()
    if not intake_reason:
        intake_reason = {
            "manual": "operator_created_requirement",
            "optimization_signal": "auto_or_operator_intake_from_runtime_signal",
            "company_review_bundle": "materialized_from_company_review_bundle",
            "automation_candidate": "materialized_from_company_review_automation_candidate",
            "bug_intake": "materialized_from_bug_backlog",
            "optimization_template": "operator_created_from_template",
            "incident_followup": "auto_created_from_incident_followup",
        }.get(source_key, "source_driven_requirement")
    try:
        confidence = float(raw.get("confidence")) if raw.get("confidence") is not None else None
    except (TypeError, ValueError):
        confidence = None
    if confidence is None:
        confidence = float(DEFAULT_INTAKE_CONFIDENCE_BY_SOURCE.get(str(source or source_key), 0.6))
    confidence = max(0.0, min(confidence, 1.0))
    normalized: dict[str, object] = {
        "source_key": source_key,
        "source": str(source or source_key),
        "source_ref": str(source_ref or "").strip() or None,
        "intake_reason": intake_reason,
        "confidence": round(confidence, 2),
        "intake_mode": str(raw.get("intake_mode") or ("automatic" if source_key in {"optimization_signal", "incident_followup", "bug_intake"} else "operator")),
    }
    for key in (
        "upstream_status",
        "trigger",
        "registry_hint",
        "bundle_item_key",
        "signal_id",
        "review_id",
        "bug_id",
        "scorecard_priority",
        "blocker_flags",
        "affected_project_keys",
        "cross_project_recovery",
    ):
        value = raw.get(key)
        if value is not None:
            normalized[key] = value
    for key, value in raw.items():
        if key in normalized or value is None:
            continue
        normalized[key] = value
    return normalized


def requirement_intake_metadata_for_requirement(requirement: RequirementRow) -> dict[str, object]:
    raw = _json_loads(getattr(requirement, "intake_metadata_json", None), {})
    return normalize_requirement_intake_metadata(requirement.source, requirement.source_ref, raw)


def _latest_review_payload(db: Session) -> tuple[CompanyOperatingReviewRow | None, dict[str, Any]]:
    row = db.query(CompanyOperatingReviewRow).order_by(
        CompanyOperatingReviewRow.created_at.desc(),
        CompanyOperatingReviewRow.id.desc(),
    ).first()
    payload = _json_loads(getattr(row, "payload_json", None), {}) if row is not None else {}
    return row, payload


def _bug_score_total(row: BugRecordRow) -> float:
    payload = _json_loads(getattr(row, "scorecard_json", None), {})
    try:
        return float(payload.get("total") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _bug_auto_intake_eligible(row: BugRecordRow) -> bool:
    payload = _json_loads(getattr(row, "scorecard_json", None), {})
    return bool(payload.get("auto_intake_eligible", False))


def _bug_priority(row: BugRecordRow) -> str:
    payload = _json_loads(getattr(row, "scorecard_json", None), {})
    priority = str(payload.get("priority") or row.severity or "normal").strip().lower()
    if priority == "critical":
        return "high"
    if priority in {"high", "normal", "low"}:
        return priority
    return "normal"


def _bug_target_project_path(db: Session, row: BugRecordRow) -> str | None:
    root = str(getattr(row, "project_root_path", "") or "").strip()
    metadata = _json_loads(getattr(row, "metadata_json", None), {})
    roots: list[str] = []
    raw_paths = list(metadata.get("affected_project_root_paths") or []) if isinstance(metadata, dict) else []
    for item in raw_paths:
        value = str(item or "").strip()
        if value and value not in roots:
            roots.append(value)
    raw_keys = list(metadata.get("affected_project_keys") or []) if isinstance(metadata, dict) else []
    for item in raw_keys:
        project_key = str(item or "").strip().lower()
        if not project_key:
            continue
        policy = db.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == project_key).first()
        root_path = str(getattr(policy, "root_path", "") or "").strip()
        if root_path and root_path not in roots:
            roots.append(root_path)
    if root and root not in roots:
        roots.insert(0, root)
    if roots:
        return "\n".join(roots)
    project_key = str(getattr(row, "project_key", "") or "").strip().lower()
    if not project_key:
        return None
    policy = db.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == project_key).first()
    return str(getattr(policy, "root_path", "") or "").strip() or None


def _bug_affected_project_keys(row: BugRecordRow) -> list[str]:
    metadata = _json_loads(getattr(row, "metadata_json", None), {})
    project_keys: list[str] = []
    primary = str(getattr(row, "project_key", "") or "").strip()
    if primary:
        project_keys.append(primary)
    if isinstance(metadata, dict):
        for item in list(metadata.get("affected_project_keys") or []):
            value = str(item or "").strip()
            if value and value not in project_keys:
                project_keys.append(value)
    return project_keys


def _bug_is_cross_project(row: BugRecordRow, db: Session) -> bool:
    target = _bug_target_project_path(db, row)
    if target:
        paths = [item.strip() for item in str(target).splitlines() if item.strip()]
        if len(paths) > 1:
            return True
    return len(_bug_affected_project_keys(row)) > 1


def _bug_blocker_flags(row: BugRecordRow) -> list[str]:
    payload = _json_loads(getattr(row, "scorecard_json", None), {})
    return [str(item).strip() for item in list(payload.get("blocker_flags") or []) if str(item).strip()]


def _bug_requires_human_approval(row: BugRecordRow) -> bool:
    source_key = str(getattr(row, "source_key", "") or "").strip().lower()
    if source_key in {"workflow_incident", "delivery_blocker_bug"}:
        return True
    blocker_flags = set(_bug_blocker_flags(row))
    return bool(blocker_flags & {"delivery_blocker", "workflow_incident"})


def _bug_is_high_value(row: BugRecordRow, *, min_score: float) -> bool:
    priority = str(_json_loads(getattr(row, "scorecard_json", None), {}).get("priority") or "").strip().lower()
    if priority in {"high", "critical"}:
        return True
    return _bug_score_total(row) >= float(min_score)


def _bug_approval_contract(db: Session, row: BugRecordRow) -> dict[str, object]:
    requires_human = _bug_requires_human_approval(row) or _bug_is_cross_project(row, db)
    if requires_human:
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


def _bug_description_markdown(row: BugRecordRow) -> str:
    scorecard = _json_loads(getattr(row, "scorecard_json", None), {})
    evidence = list(_json_loads(getattr(row, "evidence_json", None), []))
    latest = dict(evidence[0]) if evidence else {}
    lines = [
        f"# Bug Intake: {row.title}",
        "",
        f"- source: `{row.source_key}`",
        f"- severity: `{row.severity}`",
        f"- occurrence_count: `{int(row.occurrence_count or 0)}`",
        f"- priority: `{scorecard.get('priority') or _bug_priority(row)}`",
        f"- total_score: `{scorecard.get('total') or 0}`",
        "",
        "## Summary",
        str(row.summary or "").strip() or "Bug backlog item created from automated intake.",
    ]
    blockers = list(scorecard.get("blocker_flags") or [])
    if blockers:
        lines.extend(["", "## Blockers"])
        lines.extend(f"- `{item}`" for item in blockers)
    if latest:
        lines.extend(["", "## Latest Evidence"])
        if latest.get("source_ref"):
            lines.append(f"- source_ref: `{latest.get('source_ref')}`")
        if latest.get("environment"):
            lines.append(f"- environment: `{latest.get('environment')}`")
        if latest.get("log_excerpt"):
            lines.extend(["", "```text", str(latest.get("log_excerpt")), "```"])
        if latest.get("stack_trace"):
            lines.extend(["", "## Stack Snippet", "", "```text", str(latest.get("stack_trace")), "```"])
    return "\n".join(lines)


def _normalize_bug_signature(value: str | None) -> str:
    text = " ".join(str(value or "").strip().lower().split())
    if not text:
        return ""
    text = "".join("#" if ch.isdigit() else ch for ch in text)
    return text[:220]


def _bug_signature(row: BugRecordRow) -> str:
    evidence = list(_json_loads(getattr(row, "evidence_json", None), []))
    latest = dict(evidence[0]) if evidence else {}
    return _normalize_bug_signature(
        latest.get("summary")
        or latest.get("log_excerpt")
        or getattr(row, "summary", None)
        or getattr(row, "title", None)
    )


def _target_project_path_set(value: str | None) -> set[str]:
    return {item.strip() for item in str(value or "").splitlines() if item.strip()}


def _find_reusable_bug_requirement(db: Session, row: BugRecordRow) -> RequirementRow | None:
    target_paths = _target_project_path_set(_bug_target_project_path(db, row))
    bug_fingerprint = str(getattr(row, "fingerprint", "") or "").strip()
    bug_signature = _bug_signature(row)
    rows = (
        db.query(RequirementRow)
        .filter(
            RequirementRow.source == "bug_intake",
            RequirementRow.title == f"Bug Fix: {row.title}",
            RequirementRow.status.in_(tuple(ACTIVE_BUG_REQUIREMENT_STATUSES)),
        )
        .order_by(RequirementRow.id.desc())
        .all()
    )
    for requirement in rows:
        metadata = requirement_intake_metadata_for_requirement(requirement)
        existing_target_paths = _target_project_path_set(getattr(requirement, "target_project_path", None))
        if target_paths and existing_target_paths and not (target_paths & existing_target_paths):
            continue
        existing_fingerprint = str(metadata.get("bug_fingerprint") or "").strip()
        if bug_fingerprint and existing_fingerprint and existing_fingerprint == bug_fingerprint:
            return requirement
        existing_signature = _normalize_bug_signature(str(metadata.get("bug_signature") or ""))
        if bug_signature and existing_signature and existing_signature == bug_signature:
            return requirement
        description_signature = _normalize_bug_signature(getattr(requirement, "description_markdown", None))
        if bug_signature and description_signature and bug_signature in description_signature:
            return requirement
    return None


def materialize_bug_backlog(
    db: Session,
    *,
    refresh: bool = True,
    auto_start: bool = False,
    min_score: float = 60.0,
    max_created: int = 1,
) -> dict[str, Any]:
    from server.services.bugs.log_sweep import run_bug_log_sweep
    from server.services.workflows.orchestrator import create_requirement

    if refresh:
        run_bug_log_sweep(db)

    rows = (
        db.query(BugRecordRow)
        .filter(BugRecordRow.status == "open")
        .order_by(BugRecordRow.last_seen_at.desc(), BugRecordRow.id.desc())
        .all()
    )
    rows.sort(key=lambda row: (-_bug_score_total(row), -(int(getattr(row, "id", 0) or 0))))

    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped: list[str] = []
    items: list[dict[str, Any]] = []
    limit = max(1, min(int(max_created or 1), 10))

    for row in rows:
        bug_id = int(row.id)
        scorecard = _json_loads(getattr(row, "scorecard_json", None), {})
        total = _bug_score_total(row)
        if not _bug_auto_intake_eligible(row):
            skipped.append(f"bug #{bug_id} not auto-intake eligible")
            continue
        if not _bug_is_high_value(row, min_score=min_score):
            skipped.append(f"bug #{bug_id} not high value enough")
            continue
        if total < float(min_score):
            skipped.append(f"bug #{bug_id} below threshold")
            continue

        source_ref = f"bug-intake:{bug_id}"
        if row.converted_requirement_id is not None:
            existing = db.query(RequirementRow).filter(RequirementRow.id == int(row.converted_requirement_id)).first()
            if existing is not None:
                reused_requirement_ids.append(int(existing.id))
                items.append(
                    {
                        "source_key": "bug_intake",
                        "status": "linked_existing",
                        "action": "reuse_existing",
                        "bug_id": bug_id,
                        "requirement_id": int(existing.id),
                        "source_ref": source_ref,
                    }
                )
                continue
        existing = db.query(RequirementRow).filter(RequirementRow.source_ref == source_ref).first()
        if existing is not None:
            row.converted_requirement_id = int(existing.id)
            row.status = "converted"
            db.add(row)
            db.commit()
            reused_requirement_ids.append(int(existing.id))
            items.append(
                {
                    "source_key": "bug_intake",
                    "status": "already_exists",
                    "action": "reuse_existing",
                    "bug_id": bug_id,
                    "requirement_id": int(existing.id),
                    "source_ref": source_ref,
                }
            )
            continue
        reusable = _find_reusable_bug_requirement(db, row)
        if reusable is not None:
            row.converted_requirement_id = int(reusable.id)
            row.status = "converted"
            db.add(row)
            db.commit()
            reused_requirement_ids.append(int(reusable.id))
            items.append(
                {
                    "source_key": "bug_intake",
                    "status": "deduped_to_active_requirement",
                    "action": "reuse_existing",
                    "bug_id": bug_id,
                    "requirement_id": int(reusable.id),
                    "source_ref": source_ref,
                }
            )
            continue

        confidence = round(max(0.6, min(0.98, total / 100.0)), 2)
        body = RequirementCreate(
            title=f"Bug Fix: {row.title}",
            description_markdown=_bug_description_markdown(row),
            priority=_bug_priority(row),
            source="bug_intake",
            source_ref=source_ref,
            intake_metadata=normalize_requirement_intake_metadata(
                "bug_intake",
                source_ref,
                {
                    "intake_reason": "materialized_from_bug_backlog",
                    "confidence": confidence,
                    "intake_mode": "automatic" if auto_start else "operator",
                    "registry_hint": "bug_intake",
                    "trigger": "bug_backlog_materialize",
                    "bug_id": bug_id,
                    "bug_fingerprint": str(getattr(row, "fingerprint", "") or "").strip() or None,
                    "bug_signature": _bug_signature(row) or None,
                    "scorecard_priority": str(scorecard.get("priority") or _bug_priority(row)),
                    "blocker_flags": _bug_blocker_flags(row),
                    "affected_project_keys": _bug_affected_project_keys(row),
                    "cross_project_recovery": _bug_is_cross_project(row, db),
                },
            ),
            target_project_path=_bug_target_project_path(db, row),
            auto_start=auto_start,
            approval_contract=_bug_approval_contract(db, row),
        )
        detail = create_requirement(db, body)
        row.converted_requirement_id = int(detail.requirement.id)
        row.status = "converted"
        db.add(row)
        db.commit()
        family_action = str((detail.requirement.intake_metadata or {}).get("family_recommendation", {}).get("action") or "")
        if family_action in {"reuse_existing", "archive_experiment"} or str(detail.requirement.source_ref or "") != source_ref:
            reused_requirement_ids.append(int(detail.requirement.id))
            items.append(
                {
                    "source_key": "bug_intake",
                    "status": "deduped_to_active_requirement",
                    "action": "reuse_existing",
                    "bug_id": bug_id,
                    "requirement_id": int(detail.requirement.id),
                    "source_ref": source_ref,
                }
            )
            continue
        created_requirement_ids.append(int(detail.requirement.id))
        items.append(
            {
                "source_key": "bug_intake",
                "status": "created",
                "action": "create_requirement",
                "bug_id": bug_id,
                "requirement_id": int(detail.requirement.id),
                "source_ref": source_ref,
            }
        )
        if len(created_requirement_ids) >= limit:
            break

    return {
        "created_requirement_ids": created_requirement_ids,
        "reused_requirement_ids": sorted(set(reused_requirement_ids)),
        "skipped": skipped,
        "items": items,
    }


def list_requirement_source_registry(db: Session) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=7)
    requirements = db.query(RequirementRow).all()

    grouped_requirements: dict[str, list[RequirementRow]] = {}
    for row in requirements:
        source_key = _normalize_source_key(getattr(row, "source", None), getattr(row, "source_ref", None))
        grouped_requirements.setdefault(source_key, []).append(row)

    open_signal_count = db.query(OptimizationSignalRow).filter(OptimizationSignalRow.status == "open").count()
    latest_review, latest_review_payload = _latest_review_payload(db)
    bundle_items = list(latest_review_payload.get("next_cycle_requirement_bundle") or [])
    automation_candidates = list(latest_review_payload.get("automation_candidates") or [])
    open_bug_candidates = db.query(BugRecordRow).filter(BugRecordRow.status == "open").count()

    registry_definitions = [
        {
            "source_key": "manual",
            "display_name": "Manual Intake",
            "description": "Operator or strategist directly creates a requirement.",
            "source_types": ["manual"],
            "intake_supported": False,
            "open_candidate_count": 0,
        },
        {
            "source_key": "optimization_signal",
            "display_name": "Optimization Signals",
            "description": "Runtime signals, delivery blockers, manual overrides, and incidents converted into backlog items.",
            "source_types": ["optimization_signal"],
            "intake_supported": True,
            "open_candidate_count": int(open_signal_count),
        },
        {
            "source_key": "company_review_bundle",
            "display_name": "Company Review Bundle",
            "description": "Next-cycle bundle items materialized from company operating review.",
            "source_types": ["company_review_bundle"],
            "intake_supported": True,
            "open_candidate_count": len(bundle_items),
        },
        {
            "source_key": "automation_candidate",
            "display_name": "Automation Candidates",
            "description": "Weekly review automation opportunities materialized into backlog items.",
            "source_types": ["automation_candidate"],
            "intake_supported": True,
            "open_candidate_count": len(automation_candidates),
        },
        {
            "source_key": "bug_intake",
            "display_name": "Bug Backlog",
            "description": "High-value bugs materialized from bug intake, log sweep, and incident evidence.",
            "source_types": ["bug_intake"],
            "intake_supported": True,
            "open_candidate_count": int(open_bug_candidates),
        },
        {
            "source_key": "incident_followup",
            "display_name": "Incident Follow-Up",
            "description": "Auto-created follow-up requirements from circuit breakers and workflow incidents.",
            "source_types": sorted(FOLLOWUP_SOURCES),
            "intake_supported": False,
            "open_candidate_count": 0,
        },
        {
            "source_key": "optimization_template",
            "display_name": "Optimization Templates",
            "description": "Operator-created requirements from standard optimization templates.",
            "source_types": ["optimization_template"],
            "intake_supported": False,
            "open_candidate_count": 0,
        },
    ]

    items: list[dict[str, Any]] = []
    for definition in registry_definitions:
        rows = grouped_requirements.get(definition["source_key"], [])
        latest = max(
            (_ensure_utc(row.created_at or row.updated_at) for row in rows if (row.created_at or row.updated_at) is not None),
            default=None,
        )
        recent_count = sum(
            1
            for row in rows
            if (_ensure_utc(row.created_at or row.updated_at) or now) >= recent_cutoff
        )
        sample_refs = [
            str(getattr(row, "source_ref", "") or f"requirement:{int(row.id)}")
            for row in rows[-3:]
        ]
        item = {
            **definition,
            "requirement_count": len(rows),
            "recent_requirement_count": recent_count,
            "last_requirement_at": latest,
            "sample_source_refs": sample_refs,
        }
        if definition["source_key"] == "company_review_bundle":
            item["latest_review_id"] = int(latest_review.id) if latest_review is not None else None
        if definition["source_key"] == "automation_candidate":
            item["latest_review_id"] = int(latest_review.id) if latest_review is not None else None
        items.append(item)

    return {
        "generated_at": now,
        "total_requirements": len(requirements),
        "sources": items,
    }


def intake_requirement_sources(
    db: Session,
    *,
    source_key: str = "all",
    refresh: bool = True,
    auto_start: bool = False,
    min_score: float = 60.0,
    max_created: int = 1,
    bundle_item_keys: list[str] | None = None,
) -> dict[str, Any]:
    from server.services.reviews.company_review import (
        latest_company_operating_review,
        materialize_company_review_automation_candidates,
        materialize_company_review_bundle,
        refresh_company_operating_review,
    )
    from server.services.signals.optimization_signals import (
        auto_intake_optimization_signals,
        refresh_optimization_signals,
    )

    requested = str(source_key or "all").strip() or "all"
    if requested not in {"all", "optimization_signal", "company_review_bundle", "automation_candidate", "bug_intake"}:
        raise ValueError("source_key must be one of: all, optimization_signal, company_review_bundle, automation_candidate, bug_intake")

    items: list[dict[str, Any]] = []
    executed_sources: list[str] = []
    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped: list[str] = []
    review = None

    if requested in {"all", "optimization_signal"}:
        if refresh:
            refresh_optimization_signals(db)
        signal_result = auto_intake_optimization_signals(
            db,
            **OptimizationSignalAutoIntakeRequest(
                min_score=min_score,
                max_created=max_created,
                auto_start=auto_start,
            ).model_dump(),
        )
        executed_sources.append("optimization_signal")
        signal_created_ids = [int(item["requirement_id"]) for item in signal_result.get("created", [])]
        created_requirement_ids.extend(signal_created_ids)
        signal_skipped = list(signal_result.get("skipped", []))
        skipped.extend(signal_skipped)
        items.append(
            {
                "source_key": "optimization_signal",
                "action": "auto_intake",
                "status": "completed",
                "created_requirement_ids": signal_created_ids,
                "reused_requirement_ids": [],
                "skipped": signal_skipped,
                "details": signal_result,
            }
        )

    if requested in {"all", "company_review_bundle"}:
        review = review or (refresh_company_operating_review(db) if refresh else latest_company_operating_review(db))
        materialize_result = materialize_company_review_bundle(
            db,
            review_id=int(review.id),
            bundle_item_keys=list(bundle_item_keys or []),
            auto_start=auto_start,
        )
        executed_sources.append("company_review_bundle")
        created_requirement_ids.extend(list(materialize_result.created_requirement_ids))
        reused_requirement_ids.extend(list(materialize_result.reused_requirement_ids))
        skipped.extend(list(materialize_result.skipped_bundle_item_keys))
        items.append(
            {
                "source_key": "company_review_bundle",
                "action": "materialize_bundle",
                "status": "completed",
                "created_requirement_ids": list(materialize_result.created_requirement_ids),
                "reused_requirement_ids": list(materialize_result.reused_requirement_ids),
                "skipped": list(materialize_result.skipped_bundle_item_keys),
                "details": materialize_result.model_dump(),
            }
        )

    if requested in {"all", "automation_candidate"}:
        review = review or (refresh_company_operating_review(db) if refresh else latest_company_operating_review(db))
        materialize_result = materialize_company_review_automation_candidates(
            db,
            review_id=int(review.id),
            candidate_keys=[],
            auto_start=auto_start,
        )
        executed_sources.append("automation_candidate")
        created_requirement_ids.extend(list(materialize_result.created_requirement_ids))
        reused_requirement_ids.extend(list(materialize_result.reused_requirement_ids))
        skipped.extend(list(materialize_result.skipped_bundle_item_keys))
        items.append(
            {
                "source_key": "automation_candidate",
                "action": "materialize_automation_candidates",
                "status": "completed",
                "created_requirement_ids": list(materialize_result.created_requirement_ids),
                "reused_requirement_ids": list(materialize_result.reused_requirement_ids),
                "skipped": list(materialize_result.skipped_bundle_item_keys),
                "details": materialize_result.model_dump(),
            }
        )

    if requested in {"all", "bug_intake"}:
        materialize_result = materialize_bug_backlog(
            db,
            refresh=refresh,
            auto_start=auto_start,
            min_score=min_score,
            max_created=max_created,
        )
        executed_sources.append("bug_intake")
        created_requirement_ids.extend(list(materialize_result.get("created_requirement_ids") or []))
        reused_requirement_ids.extend(list(materialize_result.get("reused_requirement_ids") or []))
        skipped.extend(list(materialize_result.get("skipped") or []))
        items.append(
            {
                "source_key": "bug_intake",
                "action": "materialize_bug_backlog",
                "status": "completed",
                "created_requirement_ids": list(materialize_result.get("created_requirement_ids") or []),
                "reused_requirement_ids": list(materialize_result.get("reused_requirement_ids") or []),
                "skipped": list(materialize_result.get("skipped") or []),
                "details": materialize_result,
            }
        )

    return {
        "executed_sources": executed_sources,
        "created_requirement_ids": sorted({int(item) for item in created_requirement_ids}),
        "reused_requirement_ids": sorted({int(item) for item in reused_requirement_ids}),
        "skipped": skipped,
        "items": items,
    }
