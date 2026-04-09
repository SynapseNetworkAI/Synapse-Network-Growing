"""Skill-based agent matching service.

Given a list of requested skills, score each agent by how many skills overlap
and return a ranked list with confidence.  This is the Phase-1 Agent Registry
interface that external orchestrators (e.g. Spec2Flow) can query via
GET /api/agents/match?skills=seo-audit,copywriting
"""
import json

from server.schemas import AgentMatch


def _parse_skills(raw: str | list | None) -> list[str]:
    """Normalise the skills field (JSON string or list) into a plain list."""
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def match_agents(agent_rows, requested_skills: list[str], limit: int = 5) -> list[AgentMatch]:
    """Score and rank agents against *requested_skills*.

    Confidence = |intersection| / |requested_skills|
    """
    if not requested_skills:
        return []

    requested_set = {s.lower() for s in requested_skills}
    scored: list[AgentMatch] = []

    for row in agent_rows:
        agent_skills = _parse_skills(getattr(row, "skills", None))
        agent_skills_lower = {s.lower() for s in agent_skills}

        matched = requested_set & agent_skills_lower
        if not matched:
            continue

        # Map back to original casing from agent_skills
        matched_original = [s for s in agent_skills if s.lower() in matched]

        confidence = round(len(matched) / len(requested_set), 2)

        scored.append(AgentMatch(
            id=row.id,
            display_name=row.display_name,
            goal=row.goal or "",
            group=getattr(row, "group", ""),
            skills=agent_skills,
            matched_skills=matched_original,
            confidence=confidence,
        ))

    # Sort by confidence desc, then alphabetically by id
    scored.sort(key=lambda m: (-m.confidence, m.id))
    return scored[:limit]
