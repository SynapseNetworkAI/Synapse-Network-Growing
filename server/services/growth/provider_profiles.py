from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachMessageRow,
    GrowthProviderProfileRow,
)
from server.schemas_growth import GrowthProviderProfileListOut
from server.services.growth.serializer import (
    json_dumps,
    json_loads,
    provider_profile_out,
)


@dataclass(frozen=True)
class ProviderProfileSeed:
    website_url: str
    company_description: str
    evidence_source_url: str


class ProviderContact(BaseModel):
    value: str = ""
    source_url: str = ""


class ProviderProfileValues(BaseModel):
    lead_id: int
    organization: str
    website_url: str = ""
    company_description: str = ""
    contact_email: str = ""
    contact_source_url: str = ""
    source_url: str = ""
    latest_message_id: int
    latest_message_subject: str = ""
    latest_message_status: str = ""
    last_contacted_at: object = None
    profile_status: str = "historical_lead"
    evidence_json: str = "[]"
    metadata_json: str = "{}"


PROFILE_SEEDS: dict[str, ProviderProfileSeed] = {
    "firecrawl": ProviderProfileSeed(
        website_url="https://www.firecrawl.dev/",
        company_description=(
            "Firecrawl provides an API for AI systems to search, scrape, crawl, "
            "and interact with the web, returning clean LLM-ready data."
        ),
        evidence_source_url="https://www.firecrawl.dev/",
    ),
    "exa": ProviderProfileSeed(
        website_url="https://exa.ai/",
        company_description=(
            "Exa offers web search, research, answer, crawling, and content APIs "
            "built for AI applications."
        ),
        evidence_source_url="https://exa.ai/",
    ),
    "tavily": ProviderProfileSeed(
        website_url="https://www.tavily.com/",
        company_description=(
            "Tavily provides search APIs for AI agents and RAG workflows that need "
            "fresh web results and structured research context."
        ),
        evidence_source_url="https://www.tavily.com/",
    ),
    "browserbase": ProviderProfileSeed(
        website_url="https://www.browserbase.com/",
        company_description=(
            "Browserbase provides programmable browser infrastructure and APIs for "
            "web automation, agent browsing, search, and fetch workflows."
        ),
        evidence_source_url="https://www.browserbase.com/",
    ),
    "serpapi": ProviderProfileSeed(
        website_url="https://serpapi.com/",
        company_description=(
            "SerpApi exposes search engine results and related public web data as "
            "structured APIs across Google, Bing, Maps, Shopping, YouTube, and more."
        ),
        evidence_source_url="https://serpapi.com/",
    ),
    "apify": ProviderProfileSeed(
        website_url="https://apify.com/",
        company_description=(
            "Apify is a web scraping and automation platform with API-accessible "
            "Actors for extracting data from websites and workflows."
        ),
        evidence_source_url="https://apify.com/",
    ),
    "bright data": ProviderProfileSeed(
        website_url="https://brightdata.com/",
        company_description=(
            "Bright Data provides web data infrastructure, proxy networks, datasets, "
            "and scraping tools for large-scale public web data collection."
        ),
        evidence_source_url="https://brightdata.com/",
    ),
    "oxylabs": ProviderProfileSeed(
        website_url="https://oxylabs.io/",
        company_description=(
            "Oxylabs provides proxy, scraper, and web data gathering APIs for "
            "collecting public data at scale."
        ),
        evidence_source_url="https://oxylabs.io/",
    ),
    "dataforseo": ProviderProfileSeed(
        website_url="https://dataforseo.com/",
        company_description=(
            "DataForSEO provides SEO, SERP, keyword, backlinks, business, app, "
            "reviews, and AI visibility data through APIs and databases."
        ),
        evidence_source_url="https://dataforseo.com/",
    ),
    "parallel": ProviderProfileSeed(
        website_url="https://parallel.ai/",
        company_description=(
            "Parallel provides web intelligence infrastructure and APIs for search, "
            "extract, task, find-all, chat, and monitor workflows."
        ),
        evidence_source_url="https://parallel.ai/",
    ),
    "linkup": ProviderProfileSeed(
        website_url="https://www.linkup.so/",
        company_description=(
            "Linkup provides a production-grade web search API for AI systems, "
            "including search, fetch, and research workflows."
        ),
        evidence_source_url="https://www.linkup.so/",
    ),
}


def sync_provider_profiles(db: Session) -> list[GrowthProviderProfileRow]:
    profiles: list[GrowthProviderProfileRow] = []
    for lead, message in sent_provider_messages(db):
        profile = upsert_provider_profile(db, lead, message)
        profiles.append(profile)
    db.commit()
    return profiles


def list_provider_profiles(
    db: Session,
    *,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> GrowthProviderProfileListOut:
    query = db.query(GrowthProviderProfileRow)
    if q:
        pattern = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(GrowthProviderProfileRow.organization).like(pattern),
                func.lower(GrowthProviderProfileRow.website_url).like(pattern),
                func.lower(GrowthProviderProfileRow.contact_email).like(pattern),
                func.lower(GrowthProviderProfileRow.company_description).like(pattern),
            )
        )
    total = query.count()
    rows = (
        query.order_by(
            GrowthProviderProfileRow.last_contacted_at.desc().nullslast(),
            GrowthProviderProfileRow.id.desc(),
        )
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 200))
        .all()
    )
    return GrowthProviderProfileListOut(
        items=[provider_profile_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def sent_provider_messages(
    db: Session,
) -> Iterable[tuple[GrowthLeadRow, GrowthOutreachMessageRow]]:
    rows = (
        db.query(GrowthLeadRow, GrowthOutreachMessageRow)
        .join(
            GrowthOutreachMessageRow,
            GrowthOutreachMessageRow.lead_id == GrowthLeadRow.id,
        )
        .filter(GrowthLeadRow.lead_type == "provider")
        .filter(GrowthOutreachMessageRow.status == "sent")
        .order_by(GrowthLeadRow.id.asc(), GrowthOutreachMessageRow.sent_at.desc())
        .all()
    )
    seen_leads: set[int] = set()
    for lead, message in rows:
        lead_id = int(lead.id)
        if lead_id in seen_leads:
            continue
        seen_leads.add(lead_id)
        yield lead, message


def upsert_provider_profile(
    db: Session,
    lead: GrowthLeadRow,
    message: GrowthOutreachMessageRow,
) -> GrowthProviderProfileRow:
    profile = (
        db.query(GrowthProviderProfileRow)
        .filter(GrowthProviderProfileRow.lead_id == lead.id)
        .first()
    )
    values = provider_profile_values(lead, message).model_dump()
    if profile is None:
        profile = GrowthProviderProfileRow(**values)
        db.add(profile)
    else:
        for key, value in values.items():
            setattr(profile, key, value)
    db.flush()
    return profile


def provider_profile_values(
    lead: GrowthLeadRow,
    message: GrowthOutreachMessageRow,
) -> ProviderProfileValues:
    seed = profile_seed_for(lead)
    contact = primary_email_contact(lead)
    evidence = json_loads(lead.evidence_json, [])
    evidence.append(
        {
            "source": seed.evidence_source_url,
            "reason": "Company website and description source for customer profile.",
        }
    )
    return ProviderProfileValues(
        lead_id=int(lead.id),
        organization=lead.organization or lead.name,
        website_url=seed.website_url,
        company_description=seed.company_description,
        contact_email=contact.value,
        contact_source_url=contact.source_url,
        source_url=lead.source_url or "",
        latest_message_id=int(message.id),
        latest_message_subject=message.subject or "",
        latest_message_status=message.status or "",
        last_contacted_at=message.sent_at or lead.last_contacted_at,
        profile_status="historical_lead",
        evidence_json=json_dumps(evidence),
        metadata_json=json_dumps(
            {
                "synced_from": "growth_sent_provider_messages",
                "lead_status": lead.status,
                "message_metadata": json_loads(message.metadata_json, {}),
            }
        ),
    )


def profile_seed_for(lead: GrowthLeadRow) -> ProviderProfileSeed:
    known_seed = known_profile_seed_for(lead)
    if known_seed is not None:
        return known_seed
    website_url = first_public_website_url(lead)
    reason = first_evidence_reason(lead)
    return ProviderProfileSeed(
        website_url=website_url or lead.source_url or "",
        company_description=reason
        or f"{lead.organization or lead.name} provider lead.",
        evidence_source_url=website_url or lead.source_url or "",
    )


def known_profile_seed_for(lead: GrowthLeadRow) -> ProviderProfileSeed | None:
    key_candidates = {
        (lead.organization or "").strip().lower(),
        (lead.name or "").strip().lower(),
    }
    for key in key_candidates:
        if key in PROFILE_SEEDS:
            return PROFILE_SEEDS[key]
    return None


def first_public_website_url(lead: GrowthLeadRow) -> str:
    urls = json_loads(lead.public_profile_urls_json, [])
    return next((str(url) for url in urls if str(url).startswith("http")), "")


def first_evidence_reason(lead: GrowthLeadRow) -> str:
    for item in json_loads(lead.evidence_json, []):
        if isinstance(item, dict) and str(item.get("reason", "")).strip():
            return str(item.get("reason", ""))
    return ""


def primary_email_contact(lead: GrowthLeadRow) -> ProviderContact:
    for item in json_loads(lead.contact_channels_json, []):
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "email" and str(item.get("value", "")).strip():
            return ProviderContact(
                value=str(item.get("value", "")),
                source_url=str(item.get("source_url", "")),
            )
    return ProviderContact()
