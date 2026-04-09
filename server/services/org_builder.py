"""Build a roles-only org tree from discovered agents."""
import json

from server.services.agent_loader import discover_agents


def build_org_tree() -> dict:
    """Return a dynamic tree that only contains agents discovered from roles/*."""
    agents = discover_agents()
    agents_by_group: dict[str, list] = {}
    for a in agents:
        g = str(a.get("group") or "ungrouped")
        agents_by_group.setdefault(g, []).append(a)

    groups = []
    for group_id in sorted(agents_by_group):
        group_agents = []
        for agent in sorted(agents_by_group[group_id], key=lambda item: item.get("display_name") or item.get("id") or ""):
            skills = agent.get("skills", "[]")
            if isinstance(skills, str):
                try:
                    skills_list = json.loads(skills)
                except (json.JSONDecodeError, TypeError):
                    skills_list = []
            else:
                skills_list = skills
            group_agents.append({
                "id": agent["id"],
                "display_name": agent["display_name"],
                "type": "agent",
                "goal": agent.get("goal", ""),
                "color": "blue",
                "skills": skills_list,
                "children": [],
            })

        groups.append({
            "id": f"group-{group_id}",
            "display_name": group_id,
            "type": "group",
            "goal": f"{len(group_agents)} discovered roles",
            "color": "gray",
            "children": group_agents,
        })

    return {
        "root": {
            "id": "roles",
            "display_name": "真实 Agent 角色",
            "type": "org",
            "goal": "Only roles discovered from roles/* are rendered here.",
            "children": groups,
        }
    }
