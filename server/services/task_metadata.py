"""Helpers for task classification metadata and retry history."""
from __future__ import annotations

from functools import lru_cache

import yaml

from server.config import PROJECT_ROOT


@lru_cache(maxsize=1)
def group_project_map() -> dict[str, str]:
    """Map agent group -> project repo name using org-structure.yaml."""
    org_path = PROJECT_ROOT / "server" / "org-structure.yaml"
    if not org_path.exists():
        return {}

    cfg = yaml.safe_load(org_path.read_text(encoding="utf-8")) or {}
    mapping: dict[str, str] = {}
    for domain in cfg.get("domains", []):
        project = domain.get("project", "")
        for team in domain.get("teams", []):
            team_id = team.get("id", "")
            if team_id:
                mapping[team_id] = project
    return mapping


def project_for_group(group: str | None) -> str:
    if not group:
        return ""
    return group_project_map().get(group, "")


def task_metadata_for_agent(agent_group: str | None) -> tuple[str, str]:
    """Return (project_id, agent_group) for a task snapshot."""
    normalized_group = agent_group or ""
    return project_for_group(normalized_group), normalized_group