"""Build the full org tree from org-structure.yaml + discovered agents."""
import json
import yaml
from pathlib import Path

from server.config import PROJECT_ROOT
from server.services.agent_loader import discover_agents

ORG_YAML = Path(__file__).resolve().parent.parent / "org-structure.yaml"


def _load_config() -> dict:
    return yaml.safe_load(ORG_YAML.read_text(encoding="utf-8"))


def build_org_tree() -> dict:
    """Return the full org tree merging static config with auto-discovered agents."""
    cfg = _load_config()
    agents = discover_agents()
    agents_by_group: dict[str, list] = {}
    for a in agents:
        g = a.get("group", "")
        agents_by_group.setdefault(g, []).append(a)

    cto = cfg["cto"]

    domains = []
    for d in cfg["domains"]:
        domain_node = {
            "id": d["id"],
            "display_name": d["display_name"],
            "type": d["type"],
            "goal": d["goal"],
            "icon": d.get("icon", ""),
            "color": d.get("color", "gray"),
            "project": d.get("project", ""),
            "children": [],
        }

        if "teams" in d:
            # Growth domain: auto-fill from discovered agents
            for team in d["teams"]:
                team_node = {
                    "id": team["id"],
                    "display_name": team["label"],
                    "type": "team",
                    "goal": "",
                    "icon": team.get("icon", ""),
                    "color": team.get("color", "gray"),
                    "children": [],
                }
                for agent in agents_by_group.get(team["id"], []):
                    skills = agent.get("skills", "[]")
                    if isinstance(skills, str):
                        try:
                            skills_list = json.loads(skills)
                        except (json.JSONDecodeError, TypeError):
                            skills_list = []
                    else:
                        skills_list = skills
                    team_node["children"].append({
                        "id": agent["id"],
                        "display_name": agent["display_name"],
                        "type": "agent",
                        "goal": agent.get("goal", ""),
                        "icon": "",
                        "color": team.get("color", "gray"),
                        "skills": skills_list,
                        "children": [],
                    })
                domain_node["children"].append(team_node)

        if "children" in d:
            for child in d["children"]:
                domain_node["children"].append({
                    "id": child["id"],
                    "display_name": child["display_name"],
                    "type": child.get("type", "service"),
                    "goal": child.get("goal", ""),
                    "icon": "",
                    "color": d.get("color", "gray"),
                    "project": child.get("project", ""),
                    "children": [],
                })

        domains.append(domain_node)

    return {
        "root": {
            **cto,
            "children": domains,
        }
    }
