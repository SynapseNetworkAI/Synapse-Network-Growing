"""Agents API router."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db, AgentRow, TaskRow
from server.schemas import AgentOut
from server.services.agent_loader import discover_agents

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
        out.task_count = total
        out.completed_count = completed
        result.append(out)
    return result


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
            results.append(AgentOut.model_validate(existing))
        else:
            row = AgentRow(**data)
            db.add(row)
            db.flush()
            results.append(AgentOut.model_validate(row))
    db.commit()
    return results
