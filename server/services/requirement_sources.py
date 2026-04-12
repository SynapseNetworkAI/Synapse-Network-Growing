"""Requirement source registry and unified intake entrypoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database import CompanyOperatingReviewRow, OptimizationSignalRow, RequirementRow
from server.schemas import OptimizationSignalAutoIntakeRequest


DEFAULT_INTAKE_CONFIDENCE_BY_SOURCE = {
    "manual": 1.0,
    "optimization_signal": 0.85,
    "company_review_bundle": 0.75,
    "automation_candidate": 0.8,
    "optimization_template": 0.7,
    "bugfix_circuit_breaker": 0.95,
}

FOLLOWUP_SOURCES = {"bugfix_circuit_breaker"}


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
        "intake_mode": str(raw.get("intake_mode") or ("automatic" if source_key in {"optimization_signal", "incident_followup"} else "operator")),
    }
    for key in ("upstream_status", "trigger", "registry_hint", "bundle_item_key", "signal_id", "review_id"):
        value = raw.get(key)
        if value is not None:
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
    from server.services.company_review import (
        latest_company_operating_review,
        materialize_company_review_automation_candidates,
        materialize_company_review_bundle,
        refresh_company_operating_review,
    )
    from server.services.optimization_signals import (
        auto_intake_optimization_signals,
        refresh_optimization_signals,
    )

    requested = str(source_key or "all").strip() or "all"
    if requested not in {"all", "optimization_signal", "company_review_bundle", "automation_candidate"}:
        raise ValueError("source_key must be one of: all, optimization_signal, company_review_bundle, automation_candidate")

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

    return {
        "executed_sources": executed_sources,
        "created_requirement_ids": sorted({int(item) for item in created_requirement_ids}),
        "reused_requirement_ids": sorted({int(item) for item in reused_requirement_ids}),
        "skipped": skipped,
        "items": items,
    }
