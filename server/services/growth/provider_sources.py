from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthLeadRow,
    GrowthOutreachMessageRow,
    GrowthResearchRunRow,
    GrowthSourceConfigRow,
)
from server.schemas_growth import (
    GrowthLeadCreate,
    GrowthResearchRunListOut,
    GrowthResearchRunOut,
    GrowthSourceConfigCreate,
    GrowthSourceConfigListOut,
    GrowthSourceConfigOut,
    GrowthSourceConfigPatch,
)
from server.services.growth import workbench
from server.services.growth.provider_catalog import (
    DEFAULT_SOURCE_KEY,
    default_source_body,
    firecrawl_candidate,
    tavily_candidate,
)
from server.services.growth.provider_outreach import (
    create_provider_onboarding_draft,
    trusted_contact_email,
)
from server.services.growth.serializer import (
    json_dumps,
    json_loads,
    research_run_out,
    source_config_out,
)

SOURCE_TYPES = {
    "github_provider_search",
    "github_mcp_repos",
    "mcp_directory_watch",
    "api_provider_sites",
    "package_ecosystem",
    "manual_seed_list",
}
SOURCE_STATUSES = {"enabled", "paused", "archived"}
def list_source_configs(db: Session) -> GrowthSourceConfigListOut:
    rows = (
        db.query(GrowthSourceConfigRow)
        .filter(GrowthSourceConfigRow.status != "archived")
        .order_by(GrowthSourceConfigRow.updated_at.desc(), GrowthSourceConfigRow.id.desc())
        .all()
    )
    return GrowthSourceConfigListOut(items=[source_config_out(row) for row in rows], total=len(rows))


def create_source_config(db: Session, body: GrowthSourceConfigCreate) -> GrowthSourceConfigOut:
    _validate_source_config(body.config_type, body.status)
    config_key = _config_key(body)
    existing = (
        db.query(GrowthSourceConfigRow)
        .filter(GrowthSourceConfigRow.config_key == config_key)
        .first()
    )
    if existing is not None:
        return source_config_out(existing)
    row = GrowthSourceConfigRow(
        config_key=config_key,
        name=body.name.strip(),
        config_type=body.config_type,
        status=body.status,
        description=body.description.strip(),
        query_json=json_dumps(body.query),
        cadence_json=json_dumps(body.cadence),
        thresholds_json=json_dumps(_thresholds(body.thresholds)),
    )
    if not row.name:
        raise ValueError("source config name is required")
    db.add(row)
    db.commit()
    return source_config_out(row)


def patch_source_config(
    db: Session, config_id: int, body: GrowthSourceConfigPatch
) -> GrowthSourceConfigOut:
    row = _source_or_404(db, config_id)
    if body.status is not None:
        if body.status not in SOURCE_STATUSES:
            raise ValueError("invalid source config status")
        row.status = body.status
    if body.name is not None:
        row.name = body.name.strip()
    if body.description is not None:
        row.description = body.description.strip()
    if body.query is not None:
        row.query_json = json_dumps(body.query)
    if body.cadence is not None:
        row.cadence_json = json_dumps(body.cadence)
    if body.thresholds is not None:
        row.thresholds_json = json_dumps(_thresholds(body.thresholds))
    db.commit()
    return source_config_out(row)


def list_research_runs(
    db: Session, source_config_id: int, *, limit: int = 50, offset: int = 0
) -> GrowthResearchRunListOut:
    _source_or_404(db, source_config_id)
    query = db.query(GrowthResearchRunRow).filter(
        GrowthResearchRunRow.source_config_id == int(source_config_id)
    )
    total = int(query.count())
    rows = (
        query.order_by(GrowthResearchRunRow.started_at.desc(), GrowthResearchRunRow.id.desc())
        .offset(max(int(offset or 0), 0))
        .limit(_limit(limit))
        .all()
    )
    return GrowthResearchRunListOut(
        items=[research_run_out(row) for row in rows],
        total=total,
        limit=_limit(limit),
        offset=max(int(offset or 0), 0),
    )


def get_research_run(db: Session, run_id: int) -> GrowthResearchRunOut:
    row = db.query(GrowthResearchRunRow).filter(GrowthResearchRunRow.id == int(run_id)).first()
    if row is None:
        raise ValueError("growth research run not found")
    return research_run_out(row)


def run_source_config(
    db: Session,
    config_id: int,
    *,
    dry_run: bool,
    max_results: int | None,
    create_drafts: bool,
    actor: str,
) -> GrowthResearchRunOut:
    source = _source_or_404(db, config_id)
    if source.status != "enabled":
        raise ValueError("source config is not enabled")
    started_at = _utcnow()
    params = {
        "dry_run": bool(dry_run),
        "max_results": max_results,
        "create_drafts": bool(create_drafts),
        "actor": actor or "operator",
    }
    run = GrowthResearchRunRow(
        source_config_id=source.id,
        status="running",
        dry_run=1 if dry_run else 0,
        params_json=json_dumps(params),
        started_at=started_at,
    )
    db.add(run)
    db.flush()

    candidates = _discover_candidates(source, max_results=max_results)
    result = _apply_candidates(
        db,
        source=source,
        run=run,
        candidates=candidates,
        dry_run=dry_run,
        create_drafts=create_drafts,
        actor=actor or "operator",
    )
    completed_at = _utcnow()
    run.status = "succeeded"
    run.candidate_count = int(result["candidate_count"])
    run.created_count = int(result["created_count"])
    run.reused_count = int(result["reused_count"])
    run.drafted_count = int(result["drafted_count"])
    run.error_summary = str(result.get("error_summary") or "")
    run.result_json = json_dumps(result)
    run.completed_at = completed_at
    source.last_run_at = completed_at
    source.last_result_json = json_dumps(result)
    db.commit()
    return research_run_out(run)


def ensure_default_provider_source_config(db: Session) -> GrowthSourceConfigOut:
    body = default_source_body()
    existing = (
        db.query(GrowthSourceConfigRow)
        .filter(GrowthSourceConfigRow.config_key == DEFAULT_SOURCE_KEY)
        .first()
    )
    if existing is None:
        return create_source_config(db, body)
    existing.name = body.name
    existing.config_type = body.config_type
    existing.status = body.status
    existing.description = body.description
    existing.query_json = json_dumps(body.query)
    existing.cadence_json = json_dumps(body.cadence)
    existing.thresholds_json = json_dumps(_thresholds(body.thresholds))
    db.commit()
    return source_config_out(existing)


def run_enabled_provider_sources(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    rows = (
        db.query(GrowthSourceConfigRow)
        .filter(
            GrowthSourceConfigRow.status == "enabled",
            GrowthSourceConfigRow.config_type.in_(SOURCE_TYPES),
        )
        .order_by(GrowthSourceConfigRow.id.asc())
        .all()
    )
    if not rows:
        ensure_default_provider_source_config(db)
        rows = db.query(GrowthSourceConfigRow).filter(
            GrowthSourceConfigRow.config_key == DEFAULT_SOURCE_KEY
        ).all()
    runs = [
        run_source_config(
            db,
            row.id,
            dry_run=dry_run,
            max_results=None,
            create_drafts=True,
            actor="growth_provider_source_sweep",
        )
        for row in rows
    ]
    return {
        "dry_run": bool(dry_run),
        "source_count": len(rows),
        "run_ids": [run.id for run in runs],
        "candidate_count": sum(run.candidate_count for run in runs),
        "created_count": sum(run.created_count for run in runs),
        "reused_count": sum(run.reused_count for run in runs),
        "drafted_count": sum(run.drafted_count for run in runs),
    }


def _apply_candidates(
    db: Session,
    *,
    source: GrowthSourceConfigRow,
    run: GrowthResearchRunRow,
    candidates: list[dict[str, Any]],
    dry_run: bool,
    create_drafts: bool,
    actor: str,
) -> dict[str, Any]:
    thresholds = _thresholds(json_loads(source.thresholds_json, {}))
    create_score = int(thresholds["create_lead_score"])
    draft_score = int(thresholds["auto_draft_score"])
    created = reused = drafted = 0
    draft_errors: list[str] = []
    lead_ids: list[int] = []
    for candidate in candidates:
        score = int(candidate["fit_score"])
        if score < create_score or dry_run:
            continue
        lead_body = _candidate_to_lead(candidate, source_config_id=source.id, run_id=run.id)
        existing = _existing_lead(db, lead_body)
        existed = existing is not None
        if existing is not None:
            _sync_existing_lead(existing, lead_body)
        lead = workbench.create_lead(db, lead_body)
        lead_ids.append(lead.id)
        created += 0 if existed else 1
        reused += 1 if existed else 0
        active_message = _active_message(db, lead.id)
        if active_message is not None:
            _sync_existing_message(active_message, candidate)
        if create_drafts and score >= draft_score and active_message is None:
            if not trusted_contact_email(candidate):
                draft_errors.append(f"{candidate['name']}: blocked_missing_trusted_contact_email")
                continue
            try:
                create_provider_onboarding_draft(
                    db,
                    lead_id=lead.id,
                    candidate=candidate,
                    actor=actor,
                )
                drafted += 1
            except Exception as exc:  # fail closed for draft only
                draft_errors.append(f"{candidate['name']}: {str(exc)[:160]}")
    return {
        "candidate_count": len(candidates),
        "created_count": created,
        "reused_count": reused,
        "drafted_count": drafted,
        "lead_ids": lead_ids,
        "candidates": candidates,
        "error_summary": "; ".join(draft_errors)[:1000],
        "send_policy": "manual_gmail_draft_only",
    }


def _discover_candidates(source: GrowthSourceConfigRow, *, max_results: int | None) -> list[dict[str, Any]]:
    query = json_loads(source.query_json, {})
    seed_urls = [str(url) for url in query.get("seed_urls") or []]
    text = " ".join(seed_urls + [str(item) for item in query.get("queries") or []]).lower()
    candidates: list[dict[str, Any]] = []
    if "firecrawl" in text or not seed_urls:
        candidates.append(firecrawl_candidate())
    if "tavily" in text:
        candidates.append(tavily_candidate())
    return candidates[: max(1, min(int(max_results or query.get("max_results") or 25), 100))]


def _candidate_to_lead(
    candidate: dict[str, Any], *, source_config_id: int, run_id: int
) -> GrowthLeadCreate:
    metadata = {
        "source_config_id": source_config_id,
        "research_run_id": run_id,
        "provider_scorecard": candidate.get("provider_scorecard") or {},
        "dedupe_key": f"provider:{candidate['source_url']}",
        "why_this_provider": candidate.get("why_this_provider") or "",
        "send_policy": "manual_gmail_draft_only",
        "contact_email": trusted_contact_email(candidate),
        "contact_provenance": list(candidate.get("contact_provenance") or []),
        "provider_email_confidence": "high" if trusted_contact_email(candidate) else "missing",
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
        .filter(GrowthLeadRow.lead_type == body.lead_type, GrowthLeadRow.source_url == body.source_url)
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


def _has_active_message(db: Session, lead_id: int) -> bool:
    return _active_message(db, lead_id) is not None


def _active_message(db: Session, lead_id: int) -> GrowthOutreachMessageRow | None:
    return (
        db.query(GrowthOutreachMessageRow)
        .filter(
            GrowthOutreachMessageRow.lead_id == int(lead_id),
            GrowthOutreachMessageRow.status.in_(("draft", "needs_review", "approved", "queued")),
        )
        .first()
    )


def _sync_existing_message(row: GrowthOutreachMessageRow, candidate: dict[str, Any]) -> None:
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


def _validate_source_config(config_type: str, status: str) -> None:
    if config_type not in SOURCE_TYPES:
        raise ValueError("invalid growth source config type")
    if status not in SOURCE_STATUSES:
        raise ValueError("invalid source config status")


def _config_key(body: GrowthSourceConfigCreate) -> str:
    if body.config_key.strip():
        return body.config_key.strip()
    return body.name.strip().lower().replace(" ", "_").replace("+", "plus")


def _thresholds(value: dict[str, object]) -> dict[str, int]:
    return {
        "create_lead_score": int(value.get("create_lead_score") or 70),
        "auto_draft_score": int(value.get("auto_draft_score") or 80),
    }


def _source_or_404(db: Session, config_id: int) -> GrowthSourceConfigRow:
    row = db.query(GrowthSourceConfigRow).filter(GrowthSourceConfigRow.id == int(config_id)).first()
    if row is None:
        raise ValueError("growth source config not found")
    return row


def _limit(value: int) -> int:
    return min(max(int(value or 50), 1), 100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
