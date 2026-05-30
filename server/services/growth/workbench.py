from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
)
from server.schemas_growth import (
    GrowthLeadCreate,
    GrowthLeadDetailOut,
    GrowthLeadImportOut,
    GrowthLeadListOut,
    GrowthLeadOut,
    GrowthOutreachMessageOut,
)
from server.services.growth.draft_agent import generate_outreach_draft
from server.services.growth.serializer import (
    event_out,
    json_dumps,
    lead_out,
    message_out,
)

LEAD_TYPES = {"investor", "provider"}
LEAD_STATUSES = {
    "new",
    "researched",
    "drafted",
    "approved",
    "queued",
    "sent",
    "replied",
    "interested",
    "not_interested",
    "do_not_contact",
    "invalid",
}
MESSAGE_STATUSES = {
    "draft",
    "needs_review",
    "approved",
    "queued",
    "sent",
    "failed",
    "skipped",
}


def list_leads(
    db: Session,
    *,
    lead_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GrowthLeadListOut:
    limit = _limit(limit)
    query = db.query(GrowthLeadRow)
    if lead_type:
        query = query.filter(GrowthLeadRow.lead_type == lead_type)
    if status:
        query = query.filter(GrowthLeadRow.status == status)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                GrowthLeadRow.name.ilike(pattern),
                GrowthLeadRow.organization.ilike(pattern),
                GrowthLeadRow.source_url.ilike(pattern),
            )
        )
    total = int(query.count())
    items = (
        query.order_by(GrowthLeadRow.updated_at.desc(), GrowthLeadRow.id.desc())
        .offset(max(offset, 0))
        .limit(limit)
        .all()
    )
    return GrowthLeadListOut(
        items=[lead_out(item) for item in items],
        total=total,
        limit=limit,
        offset=max(offset, 0),
        status_counts=_count_by(db, GrowthLeadRow, GrowthLeadRow.status),
        lead_type_counts=_count_by(db, GrowthLeadRow, GrowthLeadRow.lead_type),
    )


def create_lead(db: Session, body: GrowthLeadCreate) -> GrowthLeadOut:
    _validate_lead(body)
    existing = _find_existing_lead(db, body)
    if existing is not None:
        return lead_out(existing)
    row = GrowthLeadRow(**_lead_values(body))
    db.add(row)
    db.flush()
    _event(
        db,
        lead_id=row.id,
        event_type="lead_imported",
        to_status=row.status,
        summary="Lead created.",
    )
    db.commit()
    return lead_out(row)


def import_leads(db: Session, leads: list[GrowthLeadCreate]) -> GrowthLeadImportOut:
    created = 0
    reused = 0
    items: list[GrowthLeadOut] = []
    for lead in leads:
        _validate_lead(lead)
        existing = _find_existing_lead(db, lead)
        if existing is not None:
            reused += 1
            items.append(lead_out(existing))
            continue
        row = GrowthLeadRow(**_lead_values(lead))
        db.add(row)
        db.flush()
        _event(
            db,
            lead_id=row.id,
            event_type="lead_imported",
            to_status=row.status,
            summary="Lead imported.",
        )
        created += 1
        items.append(lead_out(row))
    db.commit()
    return GrowthLeadImportOut(created=created, reused=reused, items=items)


def lead_detail(db: Session, lead_id: int) -> GrowthLeadDetailOut:
    row = _lead_or_404(db, lead_id)
    messages = (
        db.query(GrowthOutreachMessageRow)
        .filter(GrowthOutreachMessageRow.lead_id == row.id)
        .order_by(
            GrowthOutreachMessageRow.updated_at.desc(),
            GrowthOutreachMessageRow.id.desc(),
        )
        .all()
    )
    events = (
        db.query(GrowthOutreachEventRow)
        .filter(GrowthOutreachEventRow.lead_id == row.id)
        .order_by(
            GrowthOutreachEventRow.created_at.desc(), GrowthOutreachEventRow.id.desc()
        )
        .all()
    )
    return GrowthLeadDetailOut(
        lead=lead_out(row),
        messages=[message_out(item) for item in messages],
        events=[event_out(item) for item in events],
    )


def draft_message(
    db: Session,
    lead_id: int,
    *,
    campaign_id: int | None,
    channel: str,
    actor: str,
    notes: str,
) -> GrowthOutreachMessageOut:
    lead = _lead_or_404(db, lead_id)
    if lead.status == "do_not_contact":
        raise ValueError("do_not_contact lead cannot receive outreach drafts")
    draft = generate_outreach_draft(
        lead=lead_out(lead).model_dump(mode="json"),
        channel=channel,
        notes=notes,
    )
    row = GrowthOutreachMessageRow(
        lead_id=lead.id,
        campaign_id=campaign_id,
        channel=channel or "email",
        subject=draft.subject,
        body=draft.body,
        personalization_evidence_json=json_dumps(draft.personalization_evidence),
        status="needs_review",
        metadata_json=json_dumps(draft.metadata),
    )
    db.add(row)
    _set_lead_status(lead, "drafted")
    db.flush()
    _event(
        db,
        lead_id=lead.id,
        message_id=row.id,
        event_type="message_drafted",
        actor=actor,
        to_status="needs_review",
        summary="Agent drafted outreach message.",
        metadata=draft.metadata,
    )
    db.commit()
    return message_out(row)


def approve_message(
    db: Session, message_id: int, *, actor: str, metadata: dict[str, object]
) -> GrowthOutreachMessageOut:
    message = _message_or_404(db, message_id)
    if message.status not in {"draft", "needs_review"}:
        raise ValueError("only draft or needs_review messages can be approved")
    lead = _lead_or_404(db, message.lead_id)
    _transition_message(
        db,
        message,
        "approved",
        actor=actor,
        event_type="message_approved",
        metadata=metadata,
    )
    _set_lead_status(lead, "approved")
    message.approved_by = actor
    db.commit()
    return message_out(message)


def queue_message(
    db: Session, message_id: int, *, actor: str, metadata: dict[str, object]
) -> GrowthOutreachMessageOut:
    message = _message_or_404(db, message_id)
    if message.status != "approved":
        raise ValueError("only approved messages can be queued")
    lead = _lead_or_404(db, message.lead_id)
    _transition_message(
        db,
        message,
        "queued",
        actor=actor,
        event_type="message_queued",
        metadata=metadata,
    )
    _set_lead_status(lead, "queued")
    db.commit()
    return message_out(message)


def mark_message_sent(
    db: Session, message_id: int, *, actor: str, metadata: dict[str, object]
) -> GrowthOutreachMessageOut:
    message = _message_or_404(db, message_id)
    if message.status not in {"approved", "queued"}:
        raise ValueError("only approved or queued messages can be marked sent")
    lead = _lead_or_404(db, message.lead_id)
    message.sent_at = _utcnow()
    lead.last_contacted_at = message.sent_at
    _transition_message(
        db, message, "sent", actor=actor, event_type="message_sent", metadata=metadata
    )
    _set_lead_status(lead, "sent")
    db.commit()
    return message_out(message)


def record_reply(
    db: Session,
    message_id: int,
    *,
    actor: str,
    reply_summary: str,
    interested: bool,
    metadata: dict[str, object],
) -> GrowthOutreachMessageOut:
    message = _message_or_404(db, message_id)
    if message.status != "sent":
        raise ValueError("only sent messages can record replies")
    lead = _lead_or_404(db, message.lead_id)
    _set_lead_status(lead, "interested" if interested else "replied")
    _event(
        db,
        lead_id=lead.id,
        message_id=message.id,
        event_type="reply_received",
        actor=actor,
        from_status="sent",
        to_status=lead.status,
        summary=reply_summary,
        metadata=metadata,
    )
    db.commit()
    return message_out(message)


def do_not_contact(
    db: Session,
    lead_id: int,
    *,
    actor: str,
    summary: str,
    metadata: dict[str, object],
) -> GrowthLeadOut:
    lead = _lead_or_404(db, lead_id)
    previous = lead.status
    lead.status = "do_not_contact"
    for message in db.query(GrowthOutreachMessageRow).filter(
        GrowthOutreachMessageRow.lead_id == lead.id,
        GrowthOutreachMessageRow.status.in_(
            ("draft", "needs_review", "approved", "queued")
        ),
    ):
        message.status = "skipped"
    _event(
        db,
        lead_id=lead.id,
        event_type="do_not_contact_set",
        actor=actor,
        from_status=previous,
        to_status=lead.status,
        summary=summary or "Do-not-contact set.",
        metadata=metadata,
    )
    db.commit()
    return lead_out(lead)


def _count_by(db: Session, model, column) -> dict[str, int]:
    rows = db.query(column, func.count(model.id)).group_by(column).all()
    return {str(key or ""): int(count or 0) for key, count in rows if key}


def _event(
    db: Session,
    *,
    lead_id: int | None,
    event_type: str,
    actor: str = "operator",
    message_id: int | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    summary: str = "",
    metadata: dict[str, object] | None = None,
) -> None:
    db.add(
        GrowthOutreachEventRow(
            lead_id=lead_id,
            message_id=message_id,
            event_type=event_type,
            actor=actor,
            from_status=from_status,
            to_status=to_status,
            summary=summary,
            metadata_json=json_dumps(metadata or {}),
        )
    )


def _find_existing_lead(db: Session, body: GrowthLeadCreate) -> GrowthLeadRow | None:
    if body.source_url.strip():
        return (
            db.query(GrowthLeadRow)
            .filter(
                GrowthLeadRow.lead_type == body.lead_type,
                GrowthLeadRow.source_url == body.source_url.strip(),
            )
            .first()
        )
    return (
        db.query(GrowthLeadRow)
        .filter(
            GrowthLeadRow.lead_type == body.lead_type,
            GrowthLeadRow.name == body.name.strip(),
            GrowthLeadRow.organization == body.organization.strip(),
        )
        .first()
    )


def _lead_or_404(db: Session, lead_id: int) -> GrowthLeadRow:
    row = db.query(GrowthLeadRow).filter(GrowthLeadRow.id == int(lead_id)).first()
    if row is None:
        raise ValueError("growth lead not found")
    return row


def _message_or_404(db: Session, message_id: int) -> GrowthOutreachMessageRow:
    row = (
        db.query(GrowthOutreachMessageRow)
        .filter(GrowthOutreachMessageRow.id == int(message_id))
        .first()
    )
    if row is None:
        raise ValueError("outreach message not found")
    return row


def _lead_values(body: GrowthLeadCreate) -> dict[str, Any]:
    return {
        "lead_type": body.lead_type,
        "project_key": body.project_key.strip() or "growing",
        "name": body.name.strip(),
        "organization": body.organization.strip(),
        "role_title": body.role_title.strip(),
        "public_profile_urls_json": json_dumps(body.public_profile_urls),
        "contact_channels_json": json_dumps(body.contact_channels),
        "source_kind": body.source_kind.strip() or "manual",
        "source_url": body.source_url.strip(),
        "status": body.status,
        "fit_score": int(body.fit_score or 0),
        "confidence_score": int(body.confidence_score or 0),
        "risk_flags_json": json_dumps(body.risk_flags),
        "evidence_json": json_dumps(body.evidence),
        "metadata_json": json_dumps(body.metadata),
        "next_action": body.next_action.strip(),
    }


def _transition_message(
    db: Session,
    message: GrowthOutreachMessageRow,
    to_status: str,
    *,
    actor: str,
    event_type: str,
    metadata: dict[str, object],
) -> None:
    previous = message.status
    message.status = to_status
    _event(
        db,
        lead_id=message.lead_id,
        message_id=message.id,
        event_type=event_type,
        actor=actor,
        from_status=previous,
        to_status=to_status,
        summary=f"Message moved to {to_status}.",
        metadata=metadata,
    )


def _set_lead_status(lead: GrowthLeadRow, status: str) -> None:
    if lead.status != "do_not_contact":
        lead.status = status


def _validate_lead(body: GrowthLeadCreate) -> None:
    if body.lead_type not in LEAD_TYPES:
        raise ValueError("lead_type must be investor or provider")
    if body.status not in LEAD_STATUSES:
        raise ValueError("invalid growth lead status")
    if not body.name.strip():
        raise ValueError("lead name is required")


def _limit(value: int) -> int:
    return min(max(int(value or 50), 1), 100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
