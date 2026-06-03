from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr
from typing import Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
    GrowthProviderProfileRow,
    GrowthProviderReplyRow,
)
from server.schemas_growth import GrowthProviderReplyListOut
from server.services.growth import workbench
from server.services.growth.provider_reply_drafts import draft_provider_reply
from server.services.growth.serializer import (
    json_dumps,
    json_loads,
    provider_reply_out,
)

MONITOR_ACTOR = "gmail_provider_reply_monitor"


@dataclass(frozen=True)
class InboxEmail:
    mailbox_message_id: str
    thread_id: str
    from_header: str
    subject: str
    snippet: str
    body_text: str
    received_at: datetime | None = None


@dataclass(frozen=True)
class ReplyScanResult:
    scanned: int
    matched: int
    created: int
    skipped_existing: int
    skipped_unmatched: int
    reply_ids: list[int]


@dataclass(frozen=True)
class ReplyClassification:
    value: str
    confidence_score: int
    rationale: str


def list_provider_replies(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GrowthProviderReplyListOut:
    limit = min(max(limit, 1), 200)
    query = db.query(GrowthProviderReplyRow)
    if status:
        query = query.filter(GrowthProviderReplyRow.status == status)
    if q:
        pattern = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(GrowthProviderReplyRow.from_email).like(pattern),
                func.lower(GrowthProviderReplyRow.from_name).like(pattern),
                func.lower(GrowthProviderReplyRow.subject).like(pattern),
                func.lower(GrowthProviderReplyRow.snippet).like(pattern),
            )
        )
    total = query.count()
    rows = (
        query.order_by(
            GrowthProviderReplyRow.received_at.desc().nullslast(),
            GrowthProviderReplyRow.id.desc(),
        )
        .offset(max(offset, 0))
        .limit(limit)
        .all()
    )
    suggested_reply_ids = [
        int(row.suggested_reply_message_id)
        for row in rows
        if row.suggested_reply_message_id
    ]
    suggested_replies = (
        {
            int(row.id): row
            for row in db.query(GrowthOutreachMessageRow)
            .filter(GrowthOutreachMessageRow.id.in_(suggested_reply_ids))
            .all()
        }
        if suggested_reply_ids
        else {}
    )
    return GrowthProviderReplyListOut(
        items=[
            provider_reply_out(
                row, suggested_replies.get(int(row.suggested_reply_message_id or 0))
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=max(offset, 0),
    )


def scan_provider_replies(
    db: Session,
    emails: Iterable[InboxEmail],
    *,
    dry_run: bool = False,
) -> ReplyScanResult:
    scanned = matched = created = skipped_existing = skipped_unmatched = 0
    reply_ids: list[int] = []
    for email in emails:
        scanned += 1
        existing = (
            db.query(GrowthProviderReplyRow)
            .filter(
                GrowthProviderReplyRow.mailbox_message_id == email.mailbox_message_id
            )
            .first()
        )
        if existing is not None:
            skipped_existing += 1
            matched += 1
            reply_ids.append(int(existing.id))
            continue
        match = match_provider_sent_message(db, email)
        if match is None:
            skipped_unmatched += 1
            continue
        matched += 1
        if dry_run:
            continue
        row = create_provider_reply_record(db, email, match)
        created += 1
        reply_ids.append(int(row.id))
    if not dry_run:
        db.commit()
    return ReplyScanResult(
        scanned=scanned,
        matched=matched,
        created=created,
        skipped_existing=skipped_existing,
        skipped_unmatched=skipped_unmatched,
        reply_ids=reply_ids,
    )


def match_provider_sent_message(
    db: Session,
    email: InboxEmail,
) -> (
    tuple[GrowthLeadRow, GrowthOutreachMessageRow, GrowthProviderProfileRow | None]
    | None
):
    _, from_email = parseaddr(email.from_header)
    normalized_from = normalize_email(from_email)
    if not normalized_from:
        return None
    rows = (
        db.query(GrowthLeadRow, GrowthOutreachMessageRow)
        .join(
            GrowthOutreachMessageRow,
            GrowthOutreachMessageRow.lead_id == GrowthLeadRow.id,
        )
        .filter(GrowthLeadRow.lead_type == "provider")
        .filter(GrowthOutreachMessageRow.status == "sent")
        .order_by(
            GrowthOutreachMessageRow.sent_at.desc().nullslast(),
            GrowthOutreachMessageRow.id.desc(),
        )
        .all()
    )
    for lead, message in rows:
        contact_emails = provider_contact_emails(lead, message)
        if normalized_from in contact_emails:
            return lead, message, profile_for_lead(db, int(lead.id))
        if email_domain(normalized_from) and email_domain(normalized_from) in {
            email_domain(item) for item in contact_emails
        }:
            return lead, message, profile_for_lead(db, int(lead.id))
        if subject_matches(email.subject, message.subject):
            return lead, message, profile_for_lead(db, int(lead.id))
    return None


def create_provider_reply_record(
    db: Session,
    email: InboxEmail,
    match: tuple[
        GrowthLeadRow, GrowthOutreachMessageRow, GrowthProviderProfileRow | None
    ],
) -> GrowthProviderReplyRow:
    lead, sent_message, profile = match
    from_name, from_email = parseaddr(email.from_header)
    classification = classify_provider_reply(email.body_text or email.snippet)
    draft_message = create_suggested_reply_message(
        db,
        lead=lead,
        sent_message=sent_message,
        profile=profile,
        email=email,
        classification=classification,
    )
    row = create_inbound_reply_row(
        db,
        email=email,
        lead=lead,
        sent_message=sent_message,
        profile=profile,
        draft_message=draft_message,
        classification=classification,
        from_name=from_name,
        from_email=from_email,
    )
    if sent_message.status == "sent":
        record_reply_transition(
            db, email, lead, sent_message, draft_message, classification
        )
    add_reply_draft_event(db, lead, sent_message, draft_message, row, classification)
    return row


def create_suggested_reply_message(
    db: Session,
    *,
    lead: GrowthLeadRow,
    sent_message: GrowthOutreachMessageRow,
    profile: GrowthProviderProfileRow | None,
    email: InboxEmail,
    classification: ReplyClassification,
) -> GrowthOutreachMessageRow:
    reply_subject, reply_body = draft_provider_reply(
        organization=lead.organization or lead.name,
        company_description=profile.company_description if profile is not None else "",
        inbound_subject=email.subject,
        classification=classification.value,
    )
    row = GrowthOutreachMessageRow(
        lead_id=int(lead.id),
        campaign_id=sent_message.campaign_id,
        channel="email",
        subject=reply_subject,
        body=reply_body,
        personalization_evidence_json=json_dumps(
            [
                {
                    "source": "gmail_inbox",
                    "reason": f"Provider replied with classification={classification.value}.",
                }
            ]
        ),
        status="needs_review",
        metadata_json=json_dumps(
            {
                "draft_kind": "provider_reply",
                "parent_message_id": int(sent_message.id),
                "mailbox_message_id": email.mailbox_message_id,
                "thread_id": email.thread_id,
                "auto_send": False,
                "human_gate_required": True,
            }
        ),
    )
    db.add(row)
    db.flush()
    return row


def create_inbound_reply_row(
    db: Session,
    *,
    email: InboxEmail,
    lead: GrowthLeadRow,
    sent_message: GrowthOutreachMessageRow,
    profile: GrowthProviderProfileRow | None,
    draft_message: GrowthOutreachMessageRow,
    classification: ReplyClassification,
    from_name: str,
    from_email: str,
) -> GrowthProviderReplyRow:
    row = GrowthProviderReplyRow(
        lead_id=int(lead.id),
        message_id=int(sent_message.id),
        provider_profile_id=int(profile.id) if profile is not None else None,
        mailbox_message_id=email.mailbox_message_id,
        thread_id=email.thread_id,
        from_email=normalize_email(from_email),
        from_name=from_name or "",
        subject=email.subject or "",
        snippet=bounded(email.snippet, 500),
        body_excerpt=bounded(email.body_text, 2000),
        received_at=email.received_at,
        classification=classification.value,
        confidence_score=classification.confidence_score,
        suggested_reply_message_id=int(draft_message.id),
        status="drafted",
        evidence_json=json_dumps(
            [
                {"source": "gmail_inbox", "reason": classification.rationale},
                {
                    "source": "growth_outreach_messages",
                    "reason": f"Matched sent provider message {sent_message.id}.",
                },
            ]
        ),
        metadata_json=json_dumps(
            {
                "monitor": "provider_reply_monitor_v1",
                "auto_send": False,
                "recommended_lead_status": recommended_lead_status(
                    classification.value
                ),
            }
        ),
    )
    db.add(row)
    db.flush()
    return row


def record_reply_transition(
    db: Session,
    email: InboxEmail,
    lead: GrowthLeadRow,
    sent_message: GrowthOutreachMessageRow,
    draft_message: GrowthOutreachMessageRow,
    classification: ReplyClassification,
) -> None:
    metadata = {
        "mailbox_message_id": email.mailbox_message_id,
        "suggested_reply_message_id": int(draft_message.id),
        "classification": classification.value,
        "auto_send": False,
    }
    workbench.record_reply(
        db,
        int(sent_message.id),
        actor=MONITOR_ACTOR,
        reply_summary=reply_summary(email, classification),
        interested=classification.value in {"interested", "question"},
        metadata=metadata,
    )
    if classification.value == "not_interested":
        workbench.do_not_contact(
            db,
            int(lead.id),
            actor=MONITOR_ACTOR,
            summary="Provider asked not to continue outreach.",
            metadata=metadata,
        )


def add_reply_draft_event(
    db: Session,
    lead: GrowthLeadRow,
    sent_message: GrowthOutreachMessageRow,
    draft_message: GrowthOutreachMessageRow,
    reply: GrowthProviderReplyRow,
    classification: ReplyClassification,
) -> None:
    db.add(
        GrowthOutreachEventRow(
            lead_id=int(lead.id),
            message_id=int(draft_message.id),
            event_type="provider_reply_draft_created",
            actor=MONITOR_ACTOR,
            from_status=None,
            to_status=draft_message.status,
            summary="Agent drafted a human-reviewed provider reply email.",
            metadata_json=json_dumps(
                {
                    "provider_reply_id": int(reply.id),
                    "parent_message_id": int(sent_message.id),
                    "classification": classification.value,
                    "auto_send": False,
                }
            ),
        )
    )


def classify_provider_reply(text: str) -> ReplyClassification:
    value = normalize_text(text)
    if any(
        phrase in value
        for phrase in ["not interested", "unsubscribe", "remove me", "stop emailing"]
    ):
        return ReplyClassification(
            "not_interested", 95, "Provider asked not to continue outreach."
        )
    if any(
        phrase in value
        for phrase in [
            "send",
            "details",
            "interested",
            "tell me more",
            "sounds good",
            "yes",
        ]
    ):
        return ReplyClassification(
            "interested", 85, "Provider appears open to more details."
        )
    if "?" in text or any(
        phrase in value for phrase in ["how", "pricing", "what", "integration", "docs"]
    ):
        return ReplyClassification(
            "question", 75, "Provider asked a question or requested clarification."
        )
    return ReplyClassification(
        "unknown", 45, "Provider reply did not match a high-confidence intent pattern."
    )


def provider_contact_emails(
    lead: GrowthLeadRow, message: GrowthOutreachMessageRow
) -> set[str]:
    emails: set[str] = set()
    metadata = json_loads(message.metadata_json, {})
    for key in ("recipient", "contact_email"):
        value = normalize_email(metadata.get(key, ""))
        if value:
            emails.add(value)
    lead_metadata = json_loads(lead.metadata_json, {})
    value = normalize_email(lead_metadata.get("contact_email", ""))
    if value:
        emails.add(value)
    for item in json_loads(lead.contact_channels_json, []):
        if isinstance(item, dict) and item.get("kind") == "email":
            value = normalize_email(item.get("value", ""))
            if value:
                emails.add(value)
    return emails


def profile_for_lead(db: Session, lead_id: int) -> GrowthProviderProfileRow | None:
    return (
        db.query(GrowthProviderProfileRow)
        .filter(GrowthProviderProfileRow.lead_id == lead_id)
        .first()
    )


def recommended_lead_status(classification: str) -> str:
    if classification == "not_interested":
        return "do_not_contact"
    if classification in {"interested", "question"}:
        return "interested"
    return "replied"


def reply_summary(email: InboxEmail, classification: ReplyClassification) -> str:
    snippet = bounded(email.snippet or email.body_text, 180)
    return f"Provider reply classified as {classification.value}: {snippet}"


def normalize_email(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def email_domain(value: str) -> str:
    return value.rsplit("@", 1)[-1] if "@" in value else ""


def subject_matches(inbound_subject: str, sent_subject: str) -> bool:
    inbound = normalize_subject(inbound_subject)
    sent = normalize_subject(sent_subject)
    return bool(sent and (sent in inbound or inbound in sent))


def normalize_subject(value: str) -> str:
    subject = normalize_text(value)
    while subject.startswith("re:") or subject.startswith("fwd:"):
        subject = subject.split(":", 1)[1].strip()
    return subject


def bounded(value: str, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}..."
