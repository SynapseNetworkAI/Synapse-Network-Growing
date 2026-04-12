from __future__ import annotations

"""Load agent metadata from the roles/ directory into the database.

Auto-discovers roles by scanning roles/*/prompts/persona.md and reading
YAML frontmatter. No hardcoded role list — add a new role directory and
it appears automatically.
"""
import json
import yaml
from pathlib import Path

from server.config import ROLES_DIR


def _parse_frontmatter(filepath: Path) -> dict | None:
    """Extract YAML frontmatter from a Markdown file."""
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    return yaml.safe_load(text[3:end])


def _default_role_contract(frontmatter: dict) -> dict:
    group = str(frontmatter.get("group") or "").strip()
    role_id = str(frontmatter.get("role") or "").strip()
    default_acceptance_scope = "analysis_validation" if group == "optimization" else "peer_review"
    default_acceptance_steps = ["test"] if group == "optimization" else ["review"]
    return {
        "mission": str(frontmatter.get("mission") or frontmatter.get("goal") or ""),
        "input_channels": list(frontmatter.get("input_channels") or ["requirements", "optimization_signals", "company_review"]),
        "outputs": list(frontmatter.get("outputs") or ["artifact", "requirement_update"]),
        "decision_rights": list(frontmatter.get("decision_rights") or ["decide_step_execution_within_scope", "propose_followup_requirement"]),
        "handoff_targets": list(frontmatter.get("handoff_targets") or ["reviewer", "tester", "portfolio_operator"]),
        "success_metrics": list(frontmatter.get("success_metrics") or ["completion_rate", "reopen_rate", "acceptance_pass_rate"]),
        "acceptance_ownership": list(frontmatter.get("acceptance_ownership") or [{
            "owner_role": role_id,
            "acceptance_scope": default_acceptance_scope,
            "workflow_step_types": default_acceptance_steps,
            "triggers": ["acceptance_ready", "daily_acceptance_sweep"],
        }]),
    }


def discover_agents() -> list[dict]:
    """Scan roles/*/prompts/persona.md and return agent metadata dicts."""
    agents = []
    roles_path = Path(ROLES_DIR).resolve()

    for role_dir in sorted(roles_path.iterdir()):
        if not role_dir.is_dir():
            continue
        persona_path = role_dir / "prompts" / "persona.md"
        if not persona_path.exists():
            continue

        fm = _parse_frontmatter(persona_path)
        if not fm or "role" not in fm:
            continue

        role_id = fm["role"]
        skills = fm.get("skills", [])

        agents.append({
            "id": role_id,
            "display_name": fm.get("display_name", fm.get("title", role_id)),
            "goal": fm.get("goal", ""),
            "group": fm.get("group", ""),
            "persona_path": str(persona_path),
            "skills": json.dumps(skills) if isinstance(skills, list) else skills,
            "role_contract_json": json.dumps(_default_role_contract(fm), ensure_ascii=False),
        })

    return agents
