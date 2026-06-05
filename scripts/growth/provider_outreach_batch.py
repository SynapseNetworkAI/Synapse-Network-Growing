#!/usr/bin/env python3
"""Import and send the June 2026 provider outreach batch.

The script is intentionally local-runner oriented: it reads SMTP credentials from
the ignored `.env`, writes Growth ledger rows, and sends only after an explicit
confirmation phrase.
"""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server.database import SessionLocal
from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
)
from scripts.growth.local_env import load_dotenv
from server.services.growth import workbench
from server.services.growth.serializer import json_dumps, json_loads

OFFICIAL_SITE = "https://www.synapse-network.ai/"
OFFICIAL_SENDER = "cliff@synapse-network.ai"
CAMPAIGN_KEY = "provider-outreach-2026-06-02"
CONFIRM_PHRASE = "SEND_PROVIDER_OUTREACH_20260602"


@dataclass(frozen=True)
class ProviderLead:
    name: str
    organization: str
    email: str
    source_url: str
    product_url: str
    why_fit: str
    contact_source_url: str
    fit_score: int
    confidence_score: int


PROVIDERS: tuple[ProviderLead, ...] = (
    ProviderLead(
        name="Exa",
        organization="Exa",
        email="support@exa.ai",
        source_url="https://exa.ai/contact",
        product_url="https://docs.exa.ai/",
        why_fit="Exa provides web search, crawling, research, and answer APIs for AI applications.",
        contact_source_url="https://exa.ai/contact",
        fit_score=92,
        confidence_score=86,
    ),
    ProviderLead(
        name="Tavily",
        organization="Tavily",
        email="support@tavily.com",
        source_url="https://help.tavily.com/articles/1354977158-what-level-of-support-does-tavily-provide",
        product_url="https://docs.tavily.com/",
        why_fit="Tavily is a search API built for AI agents and RAG workflows.",
        contact_source_url="https://community.tavily.com/t/tavily-contact-for-sales/727",
        fit_score=90,
        confidence_score=84,
    ),
    ProviderLead(
        name="Browserbase",
        organization="Browserbase",
        email="support@browserbase.com",
        source_url="https://www.browserbase.com/",
        product_url="https://docs.browserbase.com/reference/api",
        why_fit="Browserbase exposes browser sessions, search, and fetch APIs that make the web programmable for agents.",
        contact_source_url="https://www.browserbase.com/privacy-policy",
        fit_score=90,
        confidence_score=82,
    ),
    ProviderLead(
        name="SerpApi",
        organization="SerpApi",
        email="contact@serpapi.com",
        source_url="https://serpapi.com/faq",
        product_url="https://serpapi.com/search-api",
        why_fit="SerpApi offers search engine result APIs with developer-friendly JSON responses.",
        contact_source_url="https://serpapi.com/faq",
        fit_score=88,
        confidence_score=88,
    ),
    ProviderLead(
        name="Apify",
        organization="Apify",
        email="hello@apify.com",
        source_url="https://apify.com/contact",
        product_url="https://docs.apify.com/api/v2/",
        why_fit="Apify runs a large ecosystem of web scraping, automation, and MCP-ready Actors exposed through APIs.",
        contact_source_url="https://apify.com/contact",
        fit_score=88,
        confidence_score=86,
    ),
    ProviderLead(
        name="Bright Data",
        organization="Bright Data",
        email="sales@brightdata.com",
        source_url="https://docs.brightdata.com/general/faqs",
        product_url="https://brightdata.com/products/web-scraper",
        why_fit="Bright Data provides web data, proxy, scraper, and dataset APIs for data-heavy applications.",
        contact_source_url="https://docs.brightdata.com/general/faqs",
        fit_score=84,
        confidence_score=82,
    ),
    ProviderLead(
        name="Oxylabs",
        organization="Oxylabs",
        email="sales@oxylabs.io",
        source_url="https://oxylabs.io/",
        product_url="https://developers.oxylabs.io/",
        why_fit="Oxylabs offers scraping, proxy, and headless browser APIs that can be metered per agent task.",
        contact_source_url="https://oxylabs.cn/contact-us",
        fit_score=84,
        confidence_score=84,
    ),
    ProviderLead(
        name="DataForSEO",
        organization="DataForSEO",
        email="info@dataforseo.com",
        source_url="https://dataforseo.com/",
        product_url="https://docs.dataforseo.com/",
        why_fit="DataForSEO exposes SERP, keyword, backlinks, business data, app data, and content analysis APIs.",
        contact_source_url="https://dataforseo.com/contact",
        fit_score=86,
        confidence_score=84,
    ),
    ProviderLead(
        name="Parallel",
        organization="Parallel",
        email="hello@parallel.ai",
        source_url="https://parallel.ai/",
        product_url="https://docs.parallel.ai/",
        why_fit="Parallel provides Search, Extract, Task, FindAll, Chat, and Monitor APIs for web intelligence agents.",
        contact_source_url="https://parallel.ai/",
        fit_score=91,
        confidence_score=86,
    ),
    ProviderLead(
        name="Linkup",
        organization="Linkup",
        email="contact@linkup.so",
        source_url="https://www.linkup.so/contact",
        product_url="https://docs.linkup.so/",
        why_fit="Linkup provides production-grade web search, fetch, and research APIs for AI systems.",
        contact_source_url="https://www.linkup.so/contact",
        fit_score=90,
        confidence_score=88,
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Send email via SMTP.")
    parser.add_argument(
        "--confirm", default="", help=f"Required phrase: {CONFIRM_PHRASE}"
    )
    parser.add_argument(
        "--only", action="append", default=[], help="Provider name filter."
    )
    args = parser.parse_args()

    load_dotenv(Path(".env"), override_existing=True)
    validate_sender()
    selected = select_providers(args.only)
    should_send = bool(args.send)
    if should_send and args.confirm != CONFIRM_PHRASE:
        raise SystemExit(f"--confirm {CONFIRM_PHRASE} is required to send")

    with SessionLocal() as db:
        smtp = None
        if should_send:
            smtp = connect_smtp()
        try:
            for provider in selected:
                lead = upsert_lead(db, provider)
                message = upsert_message(db, provider, lead)
                if should_send and message.status != "sent":
                    send_message(smtp, provider, message)
                    workbench.mark_message_sent(
                        db,
                        int(message.id),
                        actor="codex/operator_request",
                        metadata={
                            "campaign_key": CAMPAIGN_KEY,
                            "recipient": provider.email,
                            "official_site": OFFICIAL_SITE,
                            "smtp_sent": True,
                            "transport": "gmail_smtp",
                        },
                    )
                    db.refresh(message)
                print(
                    f"{provider.name}: lead_id={lead.id} message_id={message.id} "
                    f"status={message.status} email={provider.email}"
                )
        finally:
            if smtp is not None:
                smtp.quit()
    return 0


def validate_sender() -> None:
    email_from = os.environ.get("EMAIL_FROM", "").strip()
    smtp_user = os.environ.get("GMAIL_SMTP_USERNAME", "").strip()
    if email_from != OFFICIAL_SENDER or smtp_user != OFFICIAL_SENDER:
        raise SystemExit(
            "Refusing to send: EMAIL_FROM and GMAIL_SMTP_USERNAME must both be "
            f"{OFFICIAL_SENDER}"
        )
    required = [
        "GMAIL_SMTP_HOST",
        "GMAIL_SMTP_PORT",
        "GMAIL_SMTP_APP_PASSWORD",
    ]
    missing = [key for key in required if not os.environ.get(key, "").strip()]
    if missing:
        raise SystemExit(f"Missing SMTP env keys: {', '.join(missing)}")


def select_providers(names: Iterable[str]) -> list[ProviderLead]:
    filters = {name.lower() for name in names}
    if not filters:
        return list(PROVIDERS)
    selected = [
        provider
        for provider in PROVIDERS
        if provider.name.lower() in filters or provider.organization.lower() in filters
    ]
    if len(selected) != len(filters):
        found = {provider.name.lower() for provider in selected}
        missing = sorted(filters - found)
        raise SystemExit(f"Unknown provider filter(s): {', '.join(missing)}")
    return selected


def upsert_lead(db, provider: ProviderLead) -> GrowthLeadRow:
    lead = (
        db.query(GrowthLeadRow)
        .filter(
            GrowthLeadRow.lead_type == "provider",
            GrowthLeadRow.source_url == provider.source_url,
        )
        .first()
    )
    values = {
        "lead_type": "provider",
        "project_key": "growing",
        "name": provider.name,
        "organization": provider.organization,
        "role_title": "API provider team",
        "public_profile_urls_json": json_dumps([provider.product_url]),
        "contact_channels_json": json_dumps(
            [
                {
                    "kind": "email",
                    "value": provider.email,
                    "confidence": "high",
                    "provenance": "official_public_contact",
                    "source_url": provider.contact_source_url,
                }
            ]
        ),
        "source_kind": "public_web",
        "source_url": provider.source_url,
        "status": "approved",
        "fit_score": provider.fit_score,
        "confidence_score": provider.confidence_score,
        "risk_flags_json": json_dumps([]),
        "evidence_json": json_dumps(
            [
                {"source": provider.product_url, "reason": provider.why_fit},
                {
                    "source": provider.contact_source_url,
                    "reason": f"Official public contact email: {provider.email}",
                },
            ]
        ),
        "metadata_json": json_dumps(
            {
                "campaign_key": CAMPAIGN_KEY,
                "contact_email": provider.email,
                "why_this_provider": provider.why_fit,
                "send_policy": "operator_requested_batch",
            }
        ),
        "next_action": "Send provider outreach email",
    }
    if lead is None:
        lead = GrowthLeadRow(**values)
        db.add(lead)
        db.flush()
        add_event(
            db,
            lead_id=int(lead.id),
            message_id=None,
            event_type="lead_imported",
            actor="codex/operator_request",
            from_status=None,
            to_status=lead.status,
            summary="Provider lead imported for operator-requested outreach batch.",
            metadata={"campaign_key": CAMPAIGN_KEY},
        )
    else:
        for key, value in values.items():
            if key != "status" or lead.status != "do_not_contact":
                setattr(lead, key, value)
        db.flush()
    return lead


def upsert_message(
    db, provider: ProviderLead, lead: GrowthLeadRow
) -> GrowthOutreachMessageRow:
    for message in (
        db.query(GrowthOutreachMessageRow)
        .filter(GrowthOutreachMessageRow.lead_id == lead.id)
        .order_by(GrowthOutreachMessageRow.id.desc())
        .all()
    ):
        metadata = json_loads(message.metadata_json, {})
        if metadata.get("campaign_key") == CAMPAIGN_KEY:
            return message

    subject, body = render_email(provider)
    message = GrowthOutreachMessageRow(
        lead_id=lead.id,
        campaign_id=None,
        channel="email",
        subject=subject,
        body=body,
        personalization_evidence_json=json_dumps(
            [{"source": provider.product_url, "reason": provider.why_fit}]
        ),
        status="approved",
        approved_by="operator_goal",
        metadata_json=json_dumps(
            {
                "campaign_key": CAMPAIGN_KEY,
                "recipient": provider.email,
                "official_site": OFFICIAL_SITE,
                "source": "provider_outreach_batch_script",
            }
        ),
    )
    db.add(message)
    db.flush()
    add_event(
        db,
        lead_id=int(lead.id),
        message_id=int(message.id),
        event_type="message_drafted",
        actor="codex/operator_request",
        from_status=None,
        to_status="approved",
        summary="Standard provider outreach email drafted and operator-approved by explicit goal.",
        metadata={"campaign_key": CAMPAIGN_KEY, "auto_send": False},
    )
    add_event(
        db,
        lead_id=int(lead.id),
        message_id=int(message.id),
        event_type="message_approved",
        actor="operator_goal",
        from_status="draft",
        to_status="approved",
        summary="Operator goal approved this provider outreach batch for sending.",
        metadata={"campaign_key": CAMPAIGN_KEY},
    )
    db.commit()
    return message


def render_email(provider: ProviderLead) -> tuple[str, str]:
    subject = "Synapse provider channel"
    body = f"""Hi {provider.organization} team,

I am reaching out because {provider.why_fit}

Synapse Network is the settlement layer for AI agents. Agent builders can discover provider services, invoke metered APIs with budget caps, and keep receipt evidence for every call.

Official site: {OFFICIAL_SITE}

For an API provider, the flow is straightforward:
- register an API or service interface on Synapse
- set usage pricing for successful calls
- let agent developers call it through Synapse with budget isolation
- earn USDC settlement from agent-driven API usage

{provider.organization} looks like a strong fit because your API is already useful to agent, automation, or data workflows. Would it be worth sending the provider registration details and a sample service contract?

Best,
Cliff
Synapse Network
{OFFICIAL_SITE}

If this is not relevant, reply "not interested" and I will not follow up.
"""
    return subject, body


def connect_smtp():
    smtp = smtplib.SMTP(
        os.environ["GMAIL_SMTP_HOST"].strip(),
        int(os.environ["GMAIL_SMTP_PORT"].strip()),
        timeout=30,
    )
    smtp.ehlo()
    smtp.starttls(context=ssl.create_default_context())
    smtp.ehlo()
    smtp.login(OFFICIAL_SENDER, os.environ["GMAIL_SMTP_APP_PASSWORD"])
    return smtp


def send_message(
    smtp, provider: ProviderLead, message: GrowthOutreachMessageRow
) -> None:
    email = EmailMessage()
    email["From"] = f"Synapse Network <{OFFICIAL_SENDER}>"
    email["To"] = provider.email
    email["Reply-To"] = OFFICIAL_SENDER
    email["Subject"] = message.subject
    email.set_content(message.body)
    smtp.send_message(email)


def add_event(
    db,
    *,
    lead_id: int,
    message_id: int | None,
    event_type: str,
    actor: str,
    from_status: str | None,
    to_status: str | None,
    summary: str,
    metadata: dict[str, object],
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
            metadata_json=json_dumps(metadata),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
