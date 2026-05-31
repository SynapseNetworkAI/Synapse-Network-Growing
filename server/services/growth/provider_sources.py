from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from server.database_growth import (
    GrowthResearchRunRow,
    GrowthSourceConfigRow,
)
from server.schemas_growth import (
    GrowthResearchRunListOut,
    GrowthResearchRunOut,
    GrowthSourceConfigCreate,
    GrowthSourceConfigListOut,
    GrowthSourceConfigOut,
    GrowthSourceConfigPatch,
)
from server.services.growth.provider_apply import apply_candidates
from server.services.growth.provider_catalog import (
    DEFAULT_SOURCE_KEY,
    default_source_body,
    firecrawl_candidate,
    tavily_candidate,
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


class GrowthProviderSourceSweepResult(BaseModel):
    dry_run: bool
    source_count: int
    run_ids: list[int] = Field(default_factory=list)
    candidate_count: int = 0
    created_count: int = 0
    reused_count: int = 0
    drafted_count: int = 0


def list_source_configs(db: Session) -> GrowthSourceConfigListOut:
    rows = (
        db.query(GrowthSourceConfigRow)
        .filter(GrowthSourceConfigRow.status != "archived")
        .order_by(
            GrowthSourceConfigRow.updated_at.desc(), GrowthSourceConfigRow.id.desc()
        )
        .all()
    )
    return GrowthSourceConfigListOut(
        items=[source_config_out(row) for row in rows], total=len(rows)
    )


def create_source_config(
    db: Session, body: GrowthSourceConfigCreate
) -> GrowthSourceConfigOut:
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
        query.order_by(
            GrowthResearchRunRow.started_at.desc(), GrowthResearchRunRow.id.desc()
        )
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
    row = (
        db.query(GrowthResearchRunRow)
        .filter(GrowthResearchRunRow.id == int(run_id))
        .first()
    )
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
    thresholds = _thresholds(json_loads(source.thresholds_json, {}))
    result = apply_candidates(
        db,
        source=source,
        run=run,
        candidates=candidates,
        dry_run=dry_run,
        create_score=int(thresholds["create_lead_score"]),
        draft_score=int(thresholds["auto_draft_score"]),
        create_drafts=create_drafts,
        actor=actor or "operator",
    ).model_dump()
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


def run_enabled_provider_sources(
    db: Session, *, dry_run: bool = False
) -> GrowthProviderSourceSweepResult:
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
        rows = (
            db.query(GrowthSourceConfigRow)
            .filter(GrowthSourceConfigRow.config_key == DEFAULT_SOURCE_KEY)
            .all()
        )
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
    return GrowthProviderSourceSweepResult(
        dry_run=bool(dry_run),
        source_count=len(rows),
        run_ids=[run.id for run in runs],
        candidate_count=sum(run.candidate_count for run in runs),
        created_count=sum(run.created_count for run in runs),
        reused_count=sum(run.reused_count for run in runs),
        drafted_count=sum(run.drafted_count for run in runs),
    )


def _discover_candidates(
    source: GrowthSourceConfigRow, *, max_results: int | None
) -> list[dict[str, Any]]:
    query = json_loads(source.query_json, {})
    seed_urls = [str(url) for url in query.get("seed_urls") or []]
    text = " ".join(
        seed_urls + [str(item) for item in query.get("queries") or []]
    ).lower()
    candidates: list[dict[str, Any]] = []
    if "firecrawl" in text or not seed_urls:
        candidates.append(firecrawl_candidate().model_dump())
    if "tavily" in text:
        candidates.append(tavily_candidate().model_dump())
    return candidates[
        : max(1, min(int(max_results or query.get("max_results") or 25), 100))
    ]


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
    row = (
        db.query(GrowthSourceConfigRow)
        .filter(GrowthSourceConfigRow.id == int(config_id))
        .first()
    )
    if row is None:
        raise ValueError("growth source config not found")
    return row


def _limit(value: int) -> int:
    return min(max(int(value or 50), 1), 100)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
