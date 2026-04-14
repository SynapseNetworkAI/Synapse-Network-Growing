"""Skills API router — lists available agent skills."""
from fastapi import APIRouter

from server.services.agents.skills import list_skills

router = APIRouter(prefix="/api/skills", tags=["skills"])


@router.get("")
def get_skills() -> list[str]:
    """Return all available skill names from .agents/skills/."""
    return list_skills()
