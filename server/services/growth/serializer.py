from __future__ import annotations

import json
from typing import Any

from server.database_growth import (
    GrowthAIVisibilityCheckRow,
    GrowthDiscoveryListingRow,
    GrowthLeadRow,
    GrowthOutreachEventRow,
    GrowthOutreachMessageRow,
    GrowthResearchRunRow,
    GrowthSourceConfigRow,
)
from server.schemas_growth import (
    GrowthAIVisibilityCheckOut,
    GrowthDiscoveryListingOut,
    GrowthLeadOut,
    GrowthOutreachEventOut,
    GrowthOutreachMessageOut,
    GrowthResearchRunOut,
    GrowthSourceConfigOut,
)


def json_loads(value: object, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return fallback


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def lead_out(row: GrowthLeadRow) -> GrowthLeadOut:
    return GrowthLeadOut(
        id=row.id,
        lead_type=row.lead_type,
        project_key=row.project_key,
        name=row.name,
        organization=row.organization or "",
        role_title=row.role_title or "",
        public_profile_urls=json_loads(row.public_profile_urls_json, []),
        contact_channels=json_loads(row.contact_channels_json, []),
        source_kind=row.source_kind or "manual",
        source_url=row.source_url or "",
        status=row.status or "new",
        fit_score=int(row.fit_score or 0),
        confidence_score=int(row.confidence_score or 0),
        risk_flags=json_loads(row.risk_flags_json, []),
        evidence=json_loads(row.evidence_json, []),
        metadata=json_loads(row.metadata_json, {}),
        next_action=row.next_action or "",
        last_contacted_at=row.last_contacted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def source_config_out(row: GrowthSourceConfigRow) -> GrowthSourceConfigOut:
    return GrowthSourceConfigOut(
        id=row.id,
        config_key=row.config_key,
        name=row.name,
        config_type=row.config_type,
        status=row.status or "enabled",
        description=row.description or "",
        query=json_loads(row.query_json, {}),
        cadence=json_loads(row.cadence_json, {}),
        thresholds=json_loads(row.thresholds_json, {}),
        last_run_at=row.last_run_at,
        last_result=json_loads(row.last_result_json, {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def research_run_out(row: GrowthResearchRunRow) -> GrowthResearchRunOut:
    return GrowthResearchRunOut(
        id=row.id,
        source_config_id=row.source_config_id,
        status=row.status or "running",
        dry_run=bool(row.dry_run),
        params=json_loads(row.params_json, {}),
        candidate_count=int(row.candidate_count or 0),
        created_count=int(row.created_count or 0),
        reused_count=int(row.reused_count or 0),
        drafted_count=int(row.drafted_count or 0),
        error_summary=row.error_summary or "",
        result=json_loads(row.result_json, {}),
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def message_out(row: GrowthOutreachMessageRow) -> GrowthOutreachMessageOut:
    return GrowthOutreachMessageOut(
        id=row.id,
        lead_id=row.lead_id,
        campaign_id=row.campaign_id,
        channel=row.channel,
        subject=row.subject or "",
        body=row.body or "",
        personalization_evidence=json_loads(row.personalization_evidence_json, []),
        status=row.status or "draft",
        approved_by=row.approved_by,
        sent_at=row.sent_at,
        failure_reason=row.failure_reason,
        metadata=json_loads(row.metadata_json, {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def event_out(row: GrowthOutreachEventRow) -> GrowthOutreachEventOut:
    return GrowthOutreachEventOut(
        id=row.id,
        lead_id=row.lead_id,
        message_id=row.message_id,
        event_type=row.event_type,
        actor=row.actor,
        from_status=row.from_status,
        to_status=row.to_status,
        summary=row.summary or "",
        metadata=json_loads(row.metadata_json, {}),
        created_at=row.created_at,
    )


def ai_check_out(row: GrowthAIVisibilityCheckRow) -> GrowthAIVisibilityCheckOut:
    return GrowthAIVisibilityCheckOut(
        id=row.id,
        query=row.query,
        platform=row.platform,
        answer_summary=row.answer_summary or "",
        synapse_mentioned=bool(row.synapse_mentioned),
        synapse_cited=bool(row.synapse_cited),
        cited_urls=json_loads(row.cited_urls_json, []),
        competitor_mentions=json_loads(row.competitor_mentions_json, []),
        missing_facts=json_loads(row.missing_facts_json, []),
        next_action=row.next_action or "",
        run_at=row.run_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def listing_out(row: GrowthDiscoveryListingRow) -> GrowthDiscoveryListingOut:
    return GrowthDiscoveryListingOut(
        id=row.id,
        surface=row.surface,
        target_repo=row.target_repo or "",
        package_name=row.package_name or "",
        listing_url=row.listing_url or "",
        status=row.status or "candidate",
        submission_evidence=json_loads(row.submission_evidence_json, {}),
        verification_evidence=json_loads(row.verification_evidence_json, {}),
        failure_reason=row.failure_reason or "",
        last_checked_at=row.last_checked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
