from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachMessageRow,
    GrowthResearchRunRow,
    GrowthSourceConfigRow,
)
from server.schemas_growth import GrowthLeadCreate, GrowthLeadOut
from server.services.growth import workbench
from server.services.growth.provider_outreach import (
    create_provider_onboarding_draft,
    trusted_contact_email,
)
from server.services.growth.serializer import json_dumps, json_loads


class CandidateApplyOutcome(BaseModel):
    created: int = 0
    reused: int = 0
    drafted: int = 0
    lead_id: int | None = None
    draft_error: str = ""


class ApplyCandidatesResult(BaseModel):
    candidate_count: int = 0
    created_count: int = 0
    reused_count: int = 0
    drafted_count: int = 0
    lead_ids: list[int] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    error_summary: str = ""
    send_policy: str = "manual_gmail_draft_only"


def apply_candidates(
    db: Session,
    *,
    source: GrowthSourceConfigRow,
    run: GrowthResearchRunRow,
    candidates: list[dict[str, Any]],
    dry_run: bool,
    create_score: int,
    draft_score: int,
    create_drafts: bool,
    actor: str,
) -> ApplyCandidatesResult:
    created = reused = drafted = 0
    draft_errors: list[str] = []
    lead_ids: list[int] = []
    for candidate in candidates:
        outcome = _apply_candidate(
            db,
            source=source,
            run=run,
            candidate=candidate,
            dry_run=dry_run,
            create_score=create_score,
            draft_score=draft_score,
            create_drafts=create_drafts,
            actor=actor,
        )
        created += outcome.created
        reused += outcome.reused
        drafted += outcome.drafted
        if outcome.lead_id is not None:
            lead_ids.append(outcome.lead_id)
        if outcome.draft_error:
            draft_errors.append(outcome.draft_error)
    return ApplyCandidatesResult(
        candidate_count=len(candidates),
        created_count=created,
        reused_count=reused,
        drafted_count=drafted,
        lead_ids=lead_ids,
        candidates=candidates,
        error_summary="; ".join(draft_errors)[:1000],
    )


def _apply_candidate(
    db: Session,
    *,
    source: GrowthSourceConfigRow,
    run: GrowthResearchRunRow,
    candidate: dict[str, Any],
    dry_run: bool,
    create_score: int,
    draft_score: int,
    create_drafts: bool,
    actor: str,
) -> CandidateApplyOutcome:
    score = int(candidate["fit_score"])
    if score < create_score or dry_run:
        return CandidateApplyOutcome()
    lead_body = _candidate_to_lead(candidate, source_config_id=source.id, run_id=run.id)
    existing = _existing_lead(db, lead_body)
    lead = _create_or_sync_lead(db, lead_body, existing)
    message = _active_message(db, lead.id)
    if message is not None:
        _sync_existing_message(message, candidate)
    draft_result = _maybe_draft_candidate(
        db,
        lead_id=lead.id,
        candidate=candidate,
        can_draft=create_drafts and score >= draft_score and message is None,
        actor=actor,
    )
    return CandidateApplyOutcome(
        created=0 if existing is not None else 1,
        reused=1 if existing is not None else 0,
        drafted=draft_result.drafted,
        lead_id=lead.id,
        draft_error=draft_result.draft_error,
    )


def _create_or_sync_lead(
    db: Session, lead_body: GrowthLeadCreate, existing: GrowthLeadRow | None
) -> GrowthLeadOut:
    if existing is not None:
        _sync_existing_lead(existing, lead_body)
    return workbench.create_lead(db, lead_body)


def _maybe_draft_candidate(
    db: Session,
    *,
    lead_id: int,
    candidate: dict[str, Any],
    can_draft: bool,
    actor: str,
) -> CandidateApplyOutcome:
    if not can_draft:
        return CandidateApplyOutcome()
    if not trusted_contact_email(candidate):
        return CandidateApplyOutcome(
            draft_error=f"{candidate['name']}: blocked_missing_trusted_contact_email"
        )
    try:
        create_provider_onboarding_draft(
            db,
            lead_id=lead_id,
            candidate=candidate,
            actor=actor,
        )
    except Exception as exc:  # fail closed for draft only
        return CandidateApplyOutcome(
            draft_error=f"{candidate['name']}: {str(exc)[:160]}"
        )
    return CandidateApplyOutcome(drafted=1)


def _candidate_to_lead(
    candidate: dict[str, Any], *, source_config_id: int, run_id: int
) -> GrowthLeadCreate:
    contact_email = trusted_contact_email(candidate)
    metadata = {
        "source_config_id": source_config_id,
        "research_run_id": run_id,
        "provider_scorecard": candidate.get("provider_scorecard") or {},
        "dedupe_key": f"provider:{candidate['source_url']}",
        "why_this_provider": candidate.get("why_this_provider") or "",
        "send_policy": "manual_gmail_draft_only",
        "contact_email": contact_email,
        "contact_provenance": list(candidate.get("contact_provenance") or []),
        "provider_email_confidence": "high" if contact_email else "missing",
    }
    return GrowthLeadCreate(
        lead_type="provider",
        project_key="growing",
        name=str(candidate["name"]),
        organization=str(candidate["organization"]),
        source_kind=str(candidate["source_kind"]),
        source_url=str(candidate["source_url"]),
        status="researched",
        fit_score=int(candidate["fit_score"]),
        confidence_score=int(candidate["confidence_score"]),
        contact_channels=list(candidate.get("contact_channels") or []),
        evidence=list(candidate.get("evidence") or []),
        metadata=metadata,
        next_action=str(candidate["next_action"]),
    )


def _existing_lead(db: Session, body: GrowthLeadCreate) -> GrowthLeadRow | None:
    return (
        db.query(GrowthLeadRow)
        .filter(
            GrowthLeadRow.lead_type == body.lead_type,
            GrowthLeadRow.source_url == body.source_url,
        )
        .first()
    )


def _sync_existing_lead(row: GrowthLeadRow, body: GrowthLeadCreate) -> None:
    metadata = json_loads(row.metadata_json, {})
    metadata.update(body.metadata)
    row.contact_channels_json = json_dumps(body.contact_channels)
    row.evidence_json = json_dumps(body.evidence)
    row.metadata_json = json_dumps(metadata)
    row.fit_score = int(body.fit_score or 0)
    row.confidence_score = int(body.confidence_score or 0)
    row.next_action = body.next_action.strip()
    if row.status in {"new", "researched"}:
        row.status = body.status


def _active_message(db: Session, lead_id: int) -> GrowthOutreachMessageRow | None:
    return (
        db.query(GrowthOutreachMessageRow)
        .filter(
            GrowthOutreachMessageRow.lead_id == int(lead_id),
            GrowthOutreachMessageRow.status.in_(
                ("draft", "needs_review", "approved", "queued")
            ),
        )
        .first()
    )


def _sync_existing_message(
    row: GrowthOutreachMessageRow, candidate: dict[str, Any]
) -> None:
    metadata = json_loads(row.metadata_json, {})
    metadata.update(
        {
            "send_policy": "manual_gmail_draft_only",
            "contact_email": trusted_contact_email(candidate),
            "contact_provenance": list(candidate.get("contact_provenance") or []),
            "gmail_status": metadata.get("gmail_status") or "not_created",
            "provider_scorecard": candidate.get("provider_scorecard") or {},
        }
    )
    row.metadata_json = json_dumps(metadata)
