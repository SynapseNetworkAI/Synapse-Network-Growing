"""Growth acquisition and AI discovery API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas_growth import (
    GrowthAIVisibilityCheckCreate,
    GrowthAIVisibilityCheckListOut,
    GrowthAIVisibilityCheckOut,
    GrowthDiscoveryListingCreate,
    GrowthDiscoveryListingListOut,
    GrowthDiscoveryListingOut,
    GrowthDiscoveryListingPatch,
    GrowthDraftMessageRequest,
    GrowthLeadCreate,
    GrowthLeadDetailOut,
    GrowthLeadImportOut,
    GrowthLeadImportRequest,
    GrowthLeadListOut,
    GrowthLeadOut,
    GrowthMessageActionRequest,
    GrowthOutreachMessageOut,
    GrowthOverviewOut,
    GrowthProviderProfileListOut,
    GrowthProviderReplyListOut,
    GrowthResearchRunListOut,
    GrowthResearchRunOut,
    GrowthReplyRequest,
    GrowthSourceConfigCreate,
    GrowthSourceConfigListOut,
    GrowthSourceConfigOut,
    GrowthSourceConfigPatch,
    GrowthSourceRunRequest,
)
from server.services.growth import (
    discovery,
    gmail_drafts,
    provider_profiles,
    provider_sources,
    provider_reply_monitor,
    workbench,
)

router = APIRouter(prefix="/api/growth", tags=["growth"])


@router.get("/overview", response_model=GrowthOverviewOut)
def growth_overview(db: Session = Depends(get_db)):
    return discovery.overview(db)


@router.get("/leads", response_model=GrowthLeadListOut)
def list_growth_leads(
    lead_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return workbench.list_leads(
        db,
        lead_type=lead_type,
        status=status,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/provider-profiles", response_model=GrowthProviderProfileListOut)
def list_growth_provider_profiles(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return provider_profiles.list_provider_profiles(
        db,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get("/provider-replies", response_model=GrowthProviderReplyListOut)
def list_growth_provider_replies(
    q: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return provider_reply_monitor.list_provider_replies(
        db,
        q=q,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/leads", response_model=GrowthLeadOut, status_code=201)
def create_growth_lead(body: GrowthLeadCreate, db: Session = Depends(get_db)):
    try:
        return workbench.create_lead(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/source-configs", response_model=GrowthSourceConfigListOut)
def list_growth_source_configs(db: Session = Depends(get_db)):
    return provider_sources.list_source_configs(db)


@router.post(
    "/source-configs",
    response_model=GrowthSourceConfigOut,
    status_code=201,
)
def create_growth_source_config(
    body: GrowthSourceConfigCreate, db: Session = Depends(get_db)
):
    try:
        return provider_sources.create_source_config(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/source-configs/{config_id}", response_model=GrowthSourceConfigOut)
def patch_growth_source_config(
    config_id: int, body: GrowthSourceConfigPatch, db: Session = Depends(get_db)
):
    try:
        return provider_sources.patch_source_config(db, config_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/source-configs/default-provider", response_model=GrowthSourceConfigOut)
def ensure_default_growth_provider_source(db: Session = Depends(get_db)):
    return provider_sources.ensure_default_provider_source_config(db)


@router.post("/source-configs/{config_id}/run", response_model=GrowthResearchRunOut)
def run_growth_source_config(
    config_id: int, body: GrowthSourceRunRequest, db: Session = Depends(get_db)
):
    try:
        return provider_sources.run_source_config(
            db,
            config_id,
            dry_run=body.dry_run,
            max_results=body.max_results,
            create_drafts=body.create_drafts,
            actor=body.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/source-configs/{config_id}/runs", response_model=GrowthResearchRunListOut)
def list_growth_source_runs(
    config_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    try:
        return provider_sources.list_research_runs(
            db, config_id, limit=limit, offset=offset
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/research-runs/{run_id}", response_model=GrowthResearchRunOut)
def get_growth_research_run(run_id: int, db: Session = Depends(get_db)):
    try:
        return provider_sources.get_research_run(db, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/leads/import", response_model=GrowthLeadImportOut, status_code=201)
def import_growth_leads(body: GrowthLeadImportRequest, db: Session = Depends(get_db)):
    try:
        return workbench.import_leads(db, body.leads)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/leads/{lead_id}", response_model=GrowthLeadDetailOut)
def growth_lead_detail(lead_id: int, db: Session = Depends(get_db)):
    try:
        return workbench.lead_detail(db, lead_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/leads/{lead_id}/draft-message",
    response_model=GrowthOutreachMessageOut,
    status_code=201,
)
def draft_growth_message(
    lead_id: int,
    body: GrowthDraftMessageRequest,
    db: Session = Depends(get_db),
):
    try:
        return workbench.draft_message(
            db,
            lead_id,
            campaign_id=body.campaign_id,
            channel=body.channel,
            actor=body.actor,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/messages/{message_id}/approve", response_model=GrowthOutreachMessageOut)
def approve_growth_message(
    message_id: int,
    body: GrowthMessageActionRequest,
    db: Session = Depends(get_db),
):
    return _message_action(
        workbench.approve_message,
        db,
        message_id,
        actor=body.actor,
        metadata=body.metadata,
    )


@router.post("/messages/{message_id}/queue", response_model=GrowthOutreachMessageOut)
def queue_growth_message(
    message_id: int,
    body: GrowthMessageActionRequest,
    db: Session = Depends(get_db),
):
    return _message_action(
        workbench.queue_message,
        db,
        message_id,
        actor=body.actor,
        metadata=body.metadata,
    )


@router.post(
    "/messages/{message_id}/create-gmail-draft",
    response_model=GrowthOutreachMessageOut,
)
def create_growth_gmail_draft(
    message_id: int,
    body: GrowthMessageActionRequest,
    db: Session = Depends(get_db),
):
    try:
        return gmail_drafts.create_gmail_draft(
            db,
            message_id,
            actor=body.actor,
            metadata=body.metadata,
        )
    except gmail_drafts.GmailDraftError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/messages/{message_id}/mark-sent", response_model=GrowthOutreachMessageOut
)
def mark_growth_message_sent(
    message_id: int,
    body: GrowthMessageActionRequest,
    db: Session = Depends(get_db),
):
    return _message_action(
        workbench.mark_message_sent,
        db,
        message_id,
        actor=body.actor,
        metadata=body.metadata,
    )


@router.post("/messages/{message_id}/reply", response_model=GrowthOutreachMessageOut)
def record_growth_reply(
    message_id: int,
    body: GrowthReplyRequest,
    db: Session = Depends(get_db),
):
    try:
        return workbench.record_reply(
            db,
            message_id,
            actor=body.actor,
            reply_summary=body.reply_summary,
            interested=body.interested,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/leads/{lead_id}/do-not-contact", response_model=GrowthLeadOut)
def growth_do_not_contact(
    lead_id: int,
    body: GrowthMessageActionRequest,
    db: Session = Depends(get_db),
):
    try:
        return workbench.do_not_contact(
            db,
            lead_id,
            actor=body.actor,
            summary=body.summary,
            metadata=body.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/ai-visibility/checks", response_model=GrowthAIVisibilityCheckListOut)
def list_ai_visibility_checks(
    q: str | None = None,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return discovery.list_ai_checks(
        db, q=q, platform=platform, limit=limit, offset=offset
    )


@router.post(
    "/ai-visibility/checks",
    response_model=GrowthAIVisibilityCheckOut,
    status_code=201,
)
def create_ai_visibility_check(
    body: GrowthAIVisibilityCheckCreate, db: Session = Depends(get_db)
):
    try:
        return discovery.create_ai_check(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/discovery-listings", response_model=GrowthDiscoveryListingListOut)
def list_discovery_listings(
    surface: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return discovery.list_listings(
        db, surface=surface, status=status, limit=limit, offset=offset
    )


@router.post(
    "/discovery-listings",
    response_model=GrowthDiscoveryListingOut,
    status_code=201,
)
def create_discovery_listing(
    body: GrowthDiscoveryListingCreate, db: Session = Depends(get_db)
):
    try:
        return discovery.create_listing(db, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/discovery-listings/{listing_id}",
    response_model=GrowthDiscoveryListingOut,
)
def patch_discovery_listing(
    listing_id: int,
    body: GrowthDiscoveryListingPatch,
    db: Session = Depends(get_db),
):
    try:
        return discovery.patch_listing(db, listing_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _message_action(action, db: Session, message_id: int, **kwargs):
    try:
        return action(db, message_id, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
