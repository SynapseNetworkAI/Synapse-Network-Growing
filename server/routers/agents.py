"""Agents API router."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db, AgentRow, TaskRow
from server.schemas import AgentOut, AgentMatch, RoleKpiSnapshotOut
from server.services.agent_loader import ensure_agents_loaded
from server.services.agent_matcher import match_agents
from server.services.role_kpis import build_role_kpi_snapshot

logger = logging.getLogger("ops-dashboard.agents")
router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    rows = ensure_agents_loaded(db)
    result = []
    for r in rows:
        total = db.query(TaskRow).filter(TaskRow.agent_id == r.id).count()
        completed = db.query(TaskRow).filter(
            TaskRow.agent_id == r.id, TaskRow.status == "completed"
        ).count()
        out = AgentOut.model_validate(r)
        out.role_contract = json.loads(getattr(r, "role_contract_json", None) or "{}")
        out.task_count = total
        out.completed_count = completed
        result.append(out)
    return result


@router.get("/role-kpis", response_model=RoleKpiSnapshotOut)
def get_role_kpis(db: Session = Depends(get_db)):
    ensure_agents_loaded(db)
    return build_role_kpi_snapshot(db)


@router.get("/match", response_model=list[AgentMatch])
def match_agents_endpoint(
    skills: str,
    limit: int = 5,
    db: Session = Depends(get_db),
):
    """Find agents matching the requested skills, ranked by confidence.

    Query params:
        skills: comma-separated skill names  (e.g. "seo-audit,copywriting")
        limit:  max results (default 5)
    """
    requested = [s.strip() for s in skills.split(",") if s.strip()]
    if not requested:
        return []
    rows = ensure_agents_loaded(db)
    return match_agents(rows, requested, limit)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    ensure_agents_loaded(db)
    row = db.query(AgentRow).filter(AgentRow.id == agent_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    total = db.query(TaskRow).filter(TaskRow.agent_id == agent_id).count()
    completed = db.query(TaskRow).filter(
        TaskRow.agent_id == agent_id, TaskRow.status == "completed"
    ).count()
    out = AgentOut.model_validate(row)
    out.role_contract = json.loads(getattr(row, "role_contract_json", None) or "{}")
    out.task_count = total
    out.completed_count = completed
    return out
