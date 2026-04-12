"""Agents API router."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db, AgentRow, TaskRow
from server.schemas import AgentOut, AgentMatch
from server.services.agent_loader import discover_agents
from server.services.agent_matcher import match_agents

logger = logging.getLogger("ops-dashboard.agents")
router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)):
    rows = db.query(AgentRow).order_by(AgentRow.id).all()
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
    rows = db.query(AgentRow).all()
    return match_agents(rows, requested, limit)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
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


@router.post("/sync", response_model=list[AgentOut])
def sync_agents(db: Session = Depends(get_db)):
    """Scan roles/ directory and upsert agents into DB."""
    agents_data = discover_agents()
    logger.info("Syncing %d agents from roles/ directory", len(agents_data))
    results = []
    for data in agents_data:
        existing = db.query(AgentRow).filter(AgentRow.id == data["id"]).first()
        if existing:
            for k, v in data.items():
                setattr(existing, k, v)
            db.flush()
            out = AgentOut.model_validate(existing)
            out.role_contract = json.loads(getattr(existing, "role_contract_json", None) or "{}")
            results.append(out)
        else:
            row = AgentRow(**data)
            db.add(row)
            db.flush()
            out = AgentOut.model_validate(row)
            out.role_contract = json.loads(getattr(row, "role_contract_json", None) or "{}")
            results.append(out)
    db.commit()
    return results
