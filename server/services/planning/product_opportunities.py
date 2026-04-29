"""Product planning opportunities for Goal Mission Lanes.

The product planner is intentionally proposal-only: it can surface product
gaps and goal ideas, but it never creates official goals or starts workflows
without an operator action.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Session

from server.database import (
    Base,
    OperatingManifestRow,
    PlanningGoalRow,
    RequirementCandidateRow,
    utcnow,
)
from server.services.planning.lifecycle import (
    create_goal,
    ensure_active_manifest,
    goal_to_dict,
)
from server.services.result_objects import ServiceObjectResult, service_object_result

OPPORTUNITY_STATUSES = {"proposed", "goal_created", "rejected", "deferred"}
RECOMMENDED_LANES = {"growth_lead", "software_engineer", "both"}


class ProductOpportunityRow(Base):
    __tablename__ = "product_opportunities"
    __table_args__ = (
        Index("ix_product_opportunities_manifest_status", "manifest_id", "status"),
        Index("ix_product_opportunities_lane_status", "recommended_lane", "status"),
        Index("ix_product_opportunities_goal_key", "manifest_id", "suggested_goal_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    manifest_id = Column(Integer, ForeignKey("operating_manifests.id"), nullable=False)
    converted_goal_id = Column(Integer, ForeignKey("planning_goals.id"), nullable=True)
    title = Column(Text, nullable=False)
    problem = Column(Text, nullable=False)
    why_now = Column(Text, nullable=False, default="")
    evidence_json = Column(Text, nullable=False, default="[]")
    suggested_goal_key = Column(Text, nullable=False)
    recommended_lane = Column(Text, nullable=False, default="growth_lead")
    risk_level = Column(Text, nullable=False, default="normal")
    success_metric = Column(Text, nullable=False, default="")
    next_action = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="proposed")
    source = Column(Text, nullable=False, default="product_planning_sweep")
    created_by = Column(Text, nullable=False, default="product_planner")
    reviewed_by = Column(Text, nullable=True)
    review_note = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


def ensure_product_opportunity_table(db: Session) -> None:
    ProductOpportunityRow.__table__.create(bind=db.get_bind(), checkfirst=True)


def _json_loads(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _json_dumps(payload: Any) -> str:
    def _default(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    return json.dumps(payload, ensure_ascii=False, default=_default)


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return text[:80] or "product_opportunity"


def _text(value: Any, default: str = "") -> str:
    text = str(value or "")
    return text if text else default


def _optional_text(value: Any) -> str | None:
    return _text(value) or None


@service_object_result
def product_opportunity_to_dict(row: ProductOpportunityRow) -> ServiceObjectResult:
    return {
        "id": int(row.id),
        "manifest_id": int(row.manifest_id),
        "converted_goal_id": int(row.converted_goal_id)
        if row.converted_goal_id
        else None,
        "title": _text(row.title),
        "problem": _text(row.problem),
        "why_now": _text(row.why_now),
        "evidence": _json_loads(row.evidence_json, []),
        "suggested_goal_key": _text(row.suggested_goal_key),
        "recommended_lane": _text(row.recommended_lane, "growth_lead"),
        "risk_level": _text(row.risk_level, "normal"),
        "success_metric": _text(row.success_metric),
        "next_action": _text(row.next_action),
        "status": _text(row.status, "proposed"),
        "source": _text(row.source, "product_planning_sweep"),
        "created_by": _text(row.created_by, "product_planner"),
        "reviewed_by": _optional_text(row.reviewed_by),
        "review_note": _optional_text(row.review_note),
        "metadata": _json_loads(row.metadata_json, {}),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _company_signal_counts(db: Session, manifest_id: int) -> dict[str, int]:
    return {
        "active_goals": db.query(PlanningGoalRow)
        .filter(
            PlanningGoalRow.manifest_id == manifest_id,
            PlanningGoalRow.status == "active",
        )
        .count(),
        "pending_candidates": db.query(RequirementCandidateRow)
        .filter(
            RequirementCandidateRow.manifest_id == manifest_id,
            RequirementCandidateRow.status.in_(("pending", "validation_failed")),
        )
        .count(),
    }


def _default_opportunity_specs(
    db: Session, manifest: OperatingManifestRow
) -> list[dict[str, Any]]:
    counts = _company_signal_counts(db, int(manifest.id))
    shared_evidence = [
        f"Active planning goals: {counts['active_goals']}",
        f"Pending or blocked candidates: {counts['pending_candidates']}",
        "Synapse has live staging/release automation and X Social Ops data, but public-preview traction still needs product-line proof.",
    ]
    return [
        {
            "title": "Core Gateway & Settlement public-preview proof",
            "problem": "The core product must prove an agent can discover a service, invoke it, pay safely, and receive an auditable receipt in staging.",
            "why_now": "Public-preview messaging is already going out on X; the product must provide a reproducible proof path behind that story.",
            "evidence": [
                *shared_evidence,
                "Synapse positioning promises agent-native settlement, budget control, and receipt evidence.",
            ],
            "suggested_goal_key": "core_gateway_settlement_preview",
            "recommended_lane": "software_engineer",
            "risk_level": "normal",
            "success_metric": "A staging smoke proves discover -> invoke -> pay -> receipt with bounded budget and visible evidence.",
            "next_action": "Create an engineering goal that turns the end-to-end payment path into an evidence-bound requirement.",
        },
        {
            "title": "Provider Runtime self-serve onboarding path",
            "problem": "A new API provider still needs a clear path from docs to service registration, staging health, Cloud Run release, and Gateway marketplace visibility.",
            "why_now": "Provider staging deployment is now connected to the release control plane, so onboarding is the next supply-side bottleneck.",
            "evidence": [
                *shared_evidence,
                "Synapse-Network-Provider is a first-class release target with successful staging DeploymentRecords.",
            ],
            "suggested_goal_key": "provider_self_serve_onboarding",
            "recommended_lane": "software_engineer",
            "risk_level": "normal",
            "success_metric": "A provider can follow docs, register/update a service, pass staging health, and see it through Gateway discovery without operator handholding.",
            "next_action": "Create a provider onboarding goal and route missing docs/API/health checks into software_engineer.",
        },
        {
            "title": "SDK & Developer Experience quickstart",
            "problem": "Developers need a 5-minute Python/TypeScript quickstart, MCP/agent demo, receipt example, and failure troubleshooting path.",
            "why_now": "Staging SDK docs exist, but public-preview conversion depends on a fast proof that a real agent can call paid/free services safely.",
            "evidence": [
                *shared_evidence,
                "Synapse-Network-Sdk positions staging as the default public preview environment.",
            ],
            "suggested_goal_key": "sdk_developer_quickstart",
            "recommended_lane": "both",
            "risk_level": "normal",
            "success_metric": "A new developer can complete SDK install, service search, invocation, and receipt verification in under 5 minutes.",
            "next_action": "Create a cross-lane goal: growth_lead frames the developer story and software_engineer fills the runnable demo gaps.",
        },
        {
            "title": "Growth / Social Ops conversion loop",
            "problem": "X publishing can create reach, but the system must connect daily content, trend radar, repost/reply actions, and docs/staging/GitHub conversion signals.",
            "why_now": "The official X account is already publishing, reposting, and tracking candidates; the next step is proving downstream product interest.",
            "evidence": [
                *shared_evidence,
                "Existing social_post_drafts, social_repost_candidates, and social_reply_items show the growth loop is active.",
            ],
            "suggested_goal_key": "growth_social_conversion_loop",
            "recommended_lane": "growth_lead",
            "risk_level": "normal",
            "success_metric": "Daily X content, trend radar, repost/reply candidates, and published-effect metrics feed Planning with docs/staging/GitHub conversion evidence.",
            "next_action": "Create a growth goal that improves content cadence, source quality, and conversion attribution without automatic public actions.",
        },
        {
            "title": "Ops Control Plane stabilization",
            "problem": "The control plane must make Mission Board, Planning Queues, Release sync, Quality Gates, and Product Planner proposals understandable and reliable.",
            "why_now": "The operator experience has moved from debug screens to business lanes; reliability now determines whether autonomous work can be trusted.",
            "evidence": [
                *shared_evidence,
                "Mission Board and top-navigation changes are in place, but old dogfood data still obscures the company operating view.",
            ],
            "suggested_goal_key": "ops_control_plane_stabilization",
            "recommended_lane": "software_engineer",
            "risk_level": "normal",
            "success_metric": "Command Center shows clean active goals, lane queues, release sync status, quality gates, and unassigned red lights without raw-debug noise.",
            "next_action": "Create an engineering goal for remaining control-plane reliability, tests, and operator UX gaps.",
        },
        {
            "title": "Trust / Production Readiness governance",
            "problem": "Production promotion needs clear Human Gate rules, rollback policy, auth/secret handling, observability, and public trust documentation.",
            "why_now": "Staging releases are working; production cannot be allowed to inherit staging shortcuts or ambiguous social/release automation.",
            "evidence": [
                *shared_evidence,
                "Existing release tasks and DeploymentRecords prove staging flow; production remains intentionally gated.",
            ],
            "suggested_goal_key": "trust_production_readiness",
            "recommended_lane": "both",
            "risk_level": "high",
            "success_metric": "Production deploy/rollback, X public actions, OAuth/secret flows, and observability have documented Human Gate boundaries and audit evidence.",
            "next_action": "Create a trust/governance goal before enabling production promotion or higher-risk automation.",
        },
    ]


@service_object_result
def run_product_planning_sweep(
    db: Session, *, dry_run: bool = False
) -> ServiceObjectResult:
    ensure_product_opportunity_table(db)
    manifest = ensure_active_manifest(db)
    specs = _default_opportunity_specs(db, manifest)
    existing = {
        str(row.suggested_goal_key)
        for row in db.query(ProductOpportunityRow)
        .filter(ProductOpportunityRow.manifest_id == int(manifest.id))
        .all()
    }
    created_ids: list[int] = []
    skipped_keys: list[str] = []
    proposals: list[dict[str, Any]] = []
    for spec in specs:
        key = str(spec["suggested_goal_key"])
        if key in existing:
            skipped_keys.append(key)
            continue
        proposals.append(spec)
        if dry_run:
            continue
        row = ProductOpportunityRow(
            manifest_id=int(manifest.id),
            title=spec["title"],
            problem=spec["problem"],
            why_now=spec["why_now"],
            evidence_json=_json_dumps(spec["evidence"]),
            suggested_goal_key=key,
            recommended_lane=spec["recommended_lane"],
            risk_level=spec["risk_level"],
            success_metric=spec["success_metric"],
            next_action=spec["next_action"],
            metadata_json=_json_dumps({"generated_by": "product_planner_v1"}),
        )
        db.add(row)
        db.flush()
        created_ids.append(int(row.id))
    if not dry_run:
        db.commit()
    return {
        "workflow_key": "product_planning_sweep",
        "dry_run": bool(dry_run),
        "auto_create_goal": False,
        "created_opportunity_ids": created_ids,
        "created_count": len(created_ids),
        "skipped_existing_keys": skipped_keys,
        "proposals": proposals,
    }


@service_object_result
def list_product_opportunities(
    db: Session, *, status: str | None = None, limit: int = 50
) -> ServiceObjectResult:
    ensure_product_opportunity_table(db)
    query = db.query(ProductOpportunityRow)
    if status and status != "all":
        query = query.filter(ProductOpportunityRow.status == status)
    rows = (
        query.order_by(
            ProductOpportunityRow.updated_at.desc(), ProductOpportunityRow.id.desc()
        )
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return {
        "items": [product_opportunity_to_dict(row) for row in rows],
        "total": query.count(),
    }


def get_product_opportunity(db: Session, opportunity_id: int) -> ProductOpportunityRow:
    ensure_product_opportunity_table(db)
    row = db.get(ProductOpportunityRow, int(opportunity_id))
    if row is None:
        raise ValueError("product opportunity not found")
    return row


@service_object_result
def reject_product_opportunity(
    db: Session, opportunity_id: int, *, operator: str, reason: str
) -> ServiceObjectResult:
    row = get_product_opportunity(db, opportunity_id)
    if str(row.status) == "goal_created":
        raise ValueError("converted opportunities cannot be rejected")
    row.status = "rejected"
    row.reviewed_by = operator or "operator"
    row.review_note = reason or "operator_rejected"
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return product_opportunity_to_dict(row)


@service_object_result
def defer_product_opportunity(
    db: Session, opportunity_id: int, *, operator: str, reason: str
) -> ServiceObjectResult:
    row = get_product_opportunity(db, opportunity_id)
    if str(row.status) == "goal_created":
        raise ValueError("converted opportunities cannot be deferred")
    row.status = "deferred"
    row.reviewed_by = operator or "operator"
    row.review_note = reason or "operator_deferred"
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return product_opportunity_to_dict(row)


def _existing_goal_response(
    db: Session, row: ProductOpportunityRow
) -> dict[str, Any] | None:
    if not row.converted_goal_id:
        return None
    goal = db.get(PlanningGoalRow, int(row.converted_goal_id))
    if goal is None:
        return None
    return {
        "opportunity": product_opportunity_to_dict(row),
        "goal": goal_to_dict(goal, include_intent=True),
        "already_created": True,
    }


def _workflow_key_for_lane(lane: str) -> str:
    if lane in {"software_engineer", "both"}:
        return "agent_self_repair"
    return "x_social_daily_content_planner"


def _project_key_for_opportunity(row: ProductOpportunityRow) -> str:
    goal_key = str(row.suggested_goal_key or "").strip().lower()
    title = str(row.title or "").strip().lower()
    problem = str(row.problem or "").strip().lower()
    haystack = f"{goal_key} {title} {problem}"
    if "sdk" in haystack or "developer experience" in haystack:
        return "synapse-network-sdk"
    if "provider" in haystack:
        return "synapse-network-provider"
    if "gateway" in haystack or "settlement" in haystack:
        return "synapse-network"
    return "synapse-network-growing"


def _goal_payload_from_opportunity(
    row: ProductOpportunityRow, *, operator: str
) -> dict[str, Any]:
    evidence = "\n".join(f"- {item}" for item in _json_loads(row.evidence_json, []))
    lane = str(row.recommended_lane or "")
    return {
        "manifest_id": int(row.manifest_id),
        "goal_key": str(row.suggested_goal_key or _slug(row.title)),
        "title": str(row.title),
        "intent_markdown": (
            f"# {row.title}\n\n"
            f"## Problem\n{row.problem}\n\n"
            f"## Why now\n{row.why_now}\n\n"
            f"## Evidence\n{evidence or '- product planner signal'}\n\n"
            f"## Next action\n{row.next_action}\n"
        ),
        "success_metric": str(row.success_metric or ""),
        "domain": "product",
        "workflow_key": _workflow_key_for_lane(lane),
        "project_key": _project_key_for_opportunity(row),
        "priority": "normal",
        "risk_level": str(row.risk_level or "normal"),
        "weight": 0.1,
        "acceptance_kind": "business",
        "metadata": {
            "source": "product_opportunity",
            "product_opportunity_id": int(row.id),
            "recommended_lane": lane,
            "created_by_operator": operator or "operator",
        },
    }


def _mark_goal_created(
    row: ProductOpportunityRow, goal: dict[str, Any], *, operator: str
) -> None:
    row.status = "goal_created"
    row.converted_goal_id = int(goal["id"])
    row.reviewed_by = operator or "operator"
    row.review_note = "created_goal"
    row.updated_at = utcnow()


@service_object_result
def create_goal_from_product_opportunity(
    db: Session, opportunity_id: int, *, operator: str
) -> ServiceObjectResult:
    row = get_product_opportunity(db, opportunity_id)
    existing = _existing_goal_response(db, row)
    if existing is not None:
        return existing
    if str(row.status) in {"rejected", "deferred"}:
        raise ValueError("rejected or deferred opportunities cannot create goals")
    goal = create_goal(db, _goal_payload_from_opportunity(row, operator=operator))
    _mark_goal_created(row, goal, operator=operator)
    db.commit()
    db.refresh(row)
    return {
        "opportunity": product_opportunity_to_dict(row),
        "goal": goal,
        "already_created": False,
    }


@service_object_result
def product_opportunity_summary(db: Session) -> ServiceObjectResult:
    ensure_product_opportunity_table(db)
    rows = db.query(ProductOpportunityRow).all()
    counts: dict[str, int] = {status: 0 for status in OPPORTUNITY_STATUSES}
    for row in rows:
        counts[str(row.status or "proposed")] = (
            counts.get(str(row.status or "proposed"), 0) + 1
        )
    return {
        "counts": counts,
        "pending_review": counts.get("proposed", 0),
        "total": len(rows),
    }
