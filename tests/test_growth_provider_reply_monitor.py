from datetime import datetime

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
    GrowthProviderReplyRow,
)
from server.services.growth.provider_reply_monitor import (
    InboxEmail,
    scan_provider_replies,
)
from server.services.growth.serializer import json_dumps


def _sent_provider(db_session, *, email="partnerships@firecrawl.dev"):
    lead = GrowthLeadRow(
        lead_type="provider",
        project_key="growing",
        name="Firecrawl",
        organization="Firecrawl",
        contact_channels_json=json_dumps(
            [
                {
                    "kind": "email",
                    "value": email,
                    "source_url": "https://docs.firecrawl.dev/partner-integration",
                }
            ]
        ),
        source_kind="public_web",
        source_url="https://github.com/firecrawl/firecrawl-mcp-server",
        status="sent",
        fit_score=95,
        confidence_score=90,
        evidence_json=json_dumps(
            [
                {
                    "source": "github",
                    "reason": "Official MCP server for search, scrape, crawl, and extraction.",
                }
            ]
        ),
        metadata_json=json_dumps({"contact_email": email}),
        next_action="Watch for provider reply",
        last_contacted_at=datetime(2026, 6, 2, 12, 0, 0),
    )
    db_session.add(lead)
    db_session.flush()
    message = GrowthOutreachMessageRow(
        lead_id=lead.id,
        channel="email",
        subject="Synapse provider channel",
        body="Official site: https://www.synapse-network.ai/",
        personalization_evidence_json=json_dumps(
            [{"source": "github", "reason": "provider fit"}]
        ),
        status="sent",
        sent_at=datetime(2026, 6, 2, 12, 1, 0),
        metadata_json=json_dumps(
            {
                "recipient": email,
                "campaign_key": "provider-outreach-2026-06-02",
            }
        ),
    )
    db_session.add(message)
    db_session.commit()
    return lead, message


def test_provider_reply_monitor_creates_review_draft_and_updates_ledger(
    synced_client, db_session
):
    lead, message = _sent_provider(db_session)
    inbound = InboxEmail(
        mailbox_message_id="<reply-firecrawl-1@example.com>",
        thread_id="thread-firecrawl",
        from_header="Firecrawl Partnerships <partnerships@firecrawl.dev>",
        subject="Re: Synapse provider channel",
        snippet="Yes, please send details.",
        body_text="Yes, please send details about the provider registration and pricing.",
        received_at=datetime(2026, 6, 2, 13, 0, 0),
    )

    result = scan_provider_replies(db_session, [inbound])

    assert result.created == 1
    reply = db_session.query(GrowthProviderReplyRow).one()
    assert reply.lead_id == lead.id
    assert reply.message_id == message.id
    assert reply.classification == "interested"
    assert reply.from_email == "partnerships@firecrawl.dev"
    draft = db_session.get(GrowthOutreachMessageRow, reply.suggested_reply_message_id)
    assert draft is not None
    assert draft.status == "needs_review"
    assert draft.subject == "Re: Synapse provider channel"
    assert "provider registration details" in draft.body
    db_session.refresh(lead)
    assert lead.status == "interested"
    event_types = {
        event.event_type for event in db_session.query(GrowthOutreachEventRow)
    }
    assert {"reply_received", "provider_reply_draft_created"} <= event_types

    response = synced_client.get("/api/growth/provider-replies?q=firecrawl")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["classification"] == "interested"
    assert payload["items"][0]["suggested_reply_message_id"] == draft.id
    assert payload["items"][0]["suggested_reply_status"] == "needs_review"
    assert (
        "provider registration details" in payload["items"][0]["suggested_reply_body"]
    )


def test_provider_reply_monitor_is_idempotent_and_classifies_not_interested(db_session):
    lead, _message = _sent_provider(db_session, email="support@exa.ai")
    inbound = InboxEmail(
        mailbox_message_id="<reply-exa-1@example.com>",
        thread_id="thread-exa",
        from_header="Exa Support <support@exa.ai>",
        subject="Re: Synapse provider channel",
        snippet="Not interested, please remove me.",
        body_text="Not interested, please remove me from follow ups.",
        received_at=datetime(2026, 6, 2, 14, 0, 0),
    )

    first = scan_provider_replies(db_session, [inbound])
    second = scan_provider_replies(db_session, [inbound])

    assert first.created == 1
    assert second.created == 0
    assert second.skipped_existing == 1
    assert db_session.query(GrowthProviderReplyRow).count() == 1
    reply = db_session.query(GrowthProviderReplyRow).one()
    assert reply.classification == "not_interested"
    draft = db_session.get(GrowthOutreachMessageRow, reply.suggested_reply_message_id)
    assert draft is not None
    assert "will not follow up further" in draft.body
    assert draft.status == "skipped"
    db_session.refresh(lead)
    assert lead.status == "do_not_contact"


def test_provider_reply_monitor_ignores_unmatched_inbox_messages(db_session):
    _sent_provider(db_session)
    inbound = InboxEmail(
        mailbox_message_id="<unmatched@example.com>",
        thread_id="thread-other",
        from_header="Random Sender <hello@example.org>",
        subject="Unrelated",
        snippet="Nothing to do with providers.",
        body_text="Nothing to do with providers.",
        received_at=datetime(2026, 6, 2, 15, 0, 0),
    )

    result = scan_provider_replies(db_session, [inbound])

    assert result.created == 0
    assert result.skipped_unmatched == 1
    assert db_session.query(GrowthProviderReplyRow).count() == 0
