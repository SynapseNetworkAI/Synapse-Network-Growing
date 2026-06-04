from __future__ import annotations

from sqlalchemy import Column, DateTime, Index, Integer, Text, UniqueConstraint

from server.database import Base, utcnow


class GrowthCampaignRow(Base):
    __tablename__ = "growth_campaigns"
    __table_args__ = (
        Index("growth_campaigns_key_idx", "campaign_key", unique=True),
        Index("growth_campaigns_type_idx", "campaign_type"),
        Index("growth_campaigns_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_key = Column(Text, nullable=False)
    campaign_type = Column(Text, nullable=False)
    audience = Column(Text, nullable=False, default="")
    objective = Column(Text, nullable=False, default="")
    offer = Column(Text, nullable=False, default="")
    channel_policy_json = Column(Text, nullable=False, default="{}")
    cadence_json = Column(Text, nullable=False, default="{}")
    status = Column(Text, nullable=False, default="draft")
    owner_role = Column(Text, nullable=False, default="growth_lead")
    success_metric = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthLeadRow(Base):
    __tablename__ = "growth_leads"
    __table_args__ = (
        Index("growth_leads_type_idx", "lead_type"),
        Index("growth_leads_status_idx", "status"),
        Index("growth_leads_project_idx", "project_key"),
        Index("growth_leads_source_idx", "source_url"),
        Index("growth_leads_updated_idx", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_type = Column(Text, nullable=False)
    project_key = Column(Text, nullable=False, default="growing")
    name = Column(Text, nullable=False)
    organization = Column(Text, nullable=False, default="")
    role_title = Column(Text, nullable=False, default="")
    public_profile_urls_json = Column(Text, nullable=False, default="[]")
    contact_channels_json = Column(Text, nullable=False, default="[]")
    source_kind = Column(Text, nullable=False, default="manual")
    source_url = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="new")
    fit_score = Column(Integer, nullable=False, default=0)
    confidence_score = Column(Integer, nullable=False, default=0)
    risk_flags_json = Column(Text, nullable=False, default="[]")
    evidence_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")
    next_action = Column(Text, nullable=False, default="")
    last_contacted_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthSourceConfigRow(Base):
    __tablename__ = "growth_source_configs"
    __table_args__ = (
        Index("growth_source_configs_key_idx", "config_key", unique=True),
        Index("growth_source_configs_type_idx", "config_type"),
        Index("growth_source_configs_status_idx", "status"),
        Index("growth_source_configs_updated_idx", "updated_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    config_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="enabled")
    description = Column(Text, nullable=False, default="")
    query_json = Column(Text, nullable=False, default="{}")
    cadence_json = Column(Text, nullable=False, default="{}")
    thresholds_json = Column(Text, nullable=False, default="{}")
    last_run_at = Column(DateTime)
    last_result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthResearchRunRow(Base):
    __tablename__ = "growth_research_runs"
    __table_args__ = (
        Index("growth_research_runs_source_idx", "source_config_id"),
        Index("growth_research_runs_status_idx", "status"),
        Index("growth_research_runs_started_idx", "started_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_config_id = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default="running")
    dry_run = Column(Integer, nullable=False, default=0)
    params_json = Column(Text, nullable=False, default="{}")
    candidate_count = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    reused_count = Column(Integer, nullable=False, default=0)
    drafted_count = Column(Integer, nullable=False, default=0)
    error_summary = Column(Text, nullable=False, default="")
    result_json = Column(Text, nullable=False, default="{}")
    started_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthOutreachMessageRow(Base):
    __tablename__ = "growth_outreach_messages"
    __table_args__ = (
        Index("growth_messages_lead_idx", "lead_id"),
        Index("growth_messages_campaign_idx", "campaign_id"),
        Index("growth_messages_status_idx", "status"),
        Index("growth_messages_channel_idx", "channel"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, nullable=False)
    campaign_id = Column(Integer)
    channel = Column(Text, nullable=False, default="email")
    subject = Column(Text, nullable=False, default="")
    body = Column(Text, nullable=False)
    personalization_evidence_json = Column(Text, nullable=False, default="[]")
    status = Column(Text, nullable=False, default="draft")
    approved_by = Column(Text)
    sent_at = Column(DateTime)
    failure_reason = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthOutreachEventRow(Base):
    __tablename__ = "growth_outreach_events"
    __table_args__ = (
        Index("growth_events_lead_idx", "lead_id"),
        Index("growth_events_message_idx", "message_id"),
        Index("growth_events_type_idx", "event_type"),
        Index("growth_events_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer)
    message_id = Column(Integer)
    event_type = Column(Text, nullable=False)
    actor = Column(Text, nullable=False, default="operator")
    from_status = Column(Text)
    to_status = Column(Text)
    summary = Column(Text, nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)


class GrowthProviderProfileRow(Base):
    __tablename__ = "growth_provider_profiles"
    __table_args__ = (
        UniqueConstraint("lead_id", name="growth_provider_profiles_lead_unique"),
        Index("growth_provider_profiles_org_idx", "organization"),
        Index("growth_provider_profiles_website_idx", "website_url"),
        Index("growth_provider_profiles_contact_idx", "contact_email"),
        Index("growth_provider_profiles_contacted_idx", "last_contacted_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, nullable=False)
    organization = Column(Text, nullable=False)
    website_url = Column(Text, nullable=False, default="")
    company_description = Column(Text, nullable=False, default="")
    contact_email = Column(Text, nullable=False, default="")
    contact_source_url = Column(Text, nullable=False, default="")
    source_url = Column(Text, nullable=False, default="")
    latest_message_id = Column(Integer)
    latest_message_subject = Column(Text, nullable=False, default="")
    latest_message_status = Column(Text, nullable=False, default="")
    last_contacted_at = Column(DateTime)
    profile_status = Column(Text, nullable=False, default="historical_lead")
    evidence_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthProviderReplyRow(Base):
    __tablename__ = "growth_provider_replies"
    __table_args__ = (
        UniqueConstraint(
            "mailbox_message_id", name="growth_provider_replies_mailbox_message_unique"
        ),
        Index("growth_provider_replies_lead_idx", "lead_id"),
        Index("growth_provider_replies_message_idx", "message_id"),
        Index("growth_provider_replies_from_idx", "from_email"),
        Index("growth_provider_replies_received_idx", "received_at"),
        Index("growth_provider_replies_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)
    provider_profile_id = Column(Integer)
    mailbox_message_id = Column(Text, nullable=False)
    thread_id = Column(Text, nullable=False, default="")
    from_email = Column(Text, nullable=False)
    from_name = Column(Text, nullable=False, default="")
    subject = Column(Text, nullable=False, default="")
    snippet = Column(Text, nullable=False, default="")
    body_excerpt = Column(Text, nullable=False, default="")
    received_at = Column(DateTime)
    classification = Column(Text, nullable=False, default="unknown")
    confidence_score = Column(Integer, nullable=False, default=0)
    suggested_reply_message_id = Column(Integer)
    status = Column(Text, nullable=False, default="drafted")
    evidence_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthAIVisibilityCheckRow(Base):
    __tablename__ = "growth_ai_visibility_checks"
    __table_args__ = (
        Index("growth_ai_checks_platform_idx", "platform"),
        Index("growth_ai_checks_query_idx", "query"),
        Index("growth_ai_checks_run_idx", "run_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    platform = Column(Text, nullable=False)
    answer_summary = Column(Text, nullable=False, default="")
    synapse_mentioned = Column(Integer, nullable=False, default=0)
    synapse_cited = Column(Integer, nullable=False, default=0)
    cited_urls_json = Column(Text, nullable=False, default="[]")
    competitor_mentions_json = Column(Text, nullable=False, default="[]")
    missing_facts_json = Column(Text, nullable=False, default="[]")
    next_action = Column(Text, nullable=False, default="")
    feed_key = Column(Text, nullable=False, default="")
    run_group = Column(Text, nullable=False, default="")
    result_rank = Column(Integer, nullable=False, default=0)
    evidence_url = Column(Text, nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")
    run_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class GrowthDiscoveryListingRow(Base):
    __tablename__ = "growth_discovery_listings"
    __table_args__ = (
        Index("growth_listings_surface_idx", "surface"),
        Index("growth_listings_status_idx", "status"),
        Index("growth_listings_checked_idx", "last_checked_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    surface = Column(Text, nullable=False)
    target_repo = Column(Text, nullable=False, default="")
    package_name = Column(Text, nullable=False, default="")
    listing_url = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="candidate")
    submission_evidence_json = Column(Text, nullable=False, default="{}")
    verification_evidence_json = Column(Text, nullable=False, default="{}")
    failure_reason = Column(Text, nullable=False, default="")
    last_checked_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
