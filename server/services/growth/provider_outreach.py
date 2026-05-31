from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
)
from server.services.growth.serializer import json_dumps


def trusted_contact_email(candidate: dict[str, Any]) -> str:
    for channel in list(candidate.get("contact_channels") or []):
        value = str(channel.get("value") or "").strip()
        confidence = str(channel.get("confidence") or "").strip().lower()
        if not value or "@" not in value:
            continue
        if "noreply.github.com" in value.lower():
            continue
        if confidence in {"high", "medium", "trusted"}:
            return value
    return ""


def create_provider_onboarding_draft(
    db: Session,
    *,
    lead_id: int,
    candidate: dict[str, Any],
    actor: str,
) -> None:
    contact_email = trusted_contact_email(candidate)
    if not contact_email:
        raise ValueError("trusted contact email is required before drafting outreach")
    lead = db.query(GrowthLeadRow).filter(GrowthLeadRow.id == int(lead_id)).first()
    if lead is None:
        raise ValueError("growth lead not found")
    evidence = list(candidate.get("evidence") or [])
    contact_provenance = list(candidate.get("contact_provenance") or [])
    organization = str(candidate["organization"])
    why_this_provider = str(
        candidate.get("why_this_provider", "it exposes agent-ready API functionality")
    ).rstrip(". ")
    body = (
        f"Hi {organization} team,\n\n"
        "I noticed your MCP/API surface for agent workflows and wanted to share a possible provider angle.\n\n"
        "Synapse Network is building payment rails for autonomous agents: agents can discover provider services, call metered APIs with a budget cap, and leave receipt evidence a human operator can inspect later.\n\n"
        f"{organization} looks like a strong fit because {why_this_provider}.\n\n"
        "This is not a request to change your product or a claim about guaranteed revenue. The useful question is whether your API should be available as a Synapse provider service so agent developers can use it with spend limits, metering, and settlement evidence.\n\n"
        "Would it be useful if I sent a short provider onboarding note with the expected service contract and receipt flow?\n"
    )
    row = GrowthOutreachMessageRow(
        lead_id=lead.id,
        campaign_id=None,
        channel="email",
        subject=f"Synapse provider fit for {organization}",
        body=body,
        personalization_evidence_json=json_dumps(evidence),
        status="needs_review",
        metadata_json=json_dumps(
            {
                "source": "growth_provider_source_sweep",
                "draft_kind": "provider_onboarding",
                "send_policy": "manual_gmail_draft_only",
                "contact_email": contact_email,
                "contact_provenance": contact_provenance,
                "gmail_status": "not_created",
                "provider_scorecard": candidate.get("provider_scorecard") or {},
            }
        ),
    )
    db.add(row)
    lead.status = "drafted"
    db.flush()
    db.add(
        GrowthOutreachEventRow(
            lead_id=lead.id,
            message_id=row.id,
            event_type="message_drafted",
            actor=actor,
            to_status="needs_review",
            summary="Provider source run drafted manual-only Gmail outreach message.",
            metadata_json=json_dumps(
                {
                    "source": "growth_provider_source_sweep",
                    "draft_kind": "provider_onboarding",
                    "contact_email": contact_email,
                    "auto_send": False,
                }
            ),
        )
    )
