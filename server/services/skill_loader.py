"""Load Skill SKILL.md files from .agents/skills/ directory."""
from pathlib import Path

import yaml
from pydantic import BaseModel

from server.config import PROJECT_ROOT

SKILLS_DIR = PROJECT_ROOT / ".agents" / "skills"


class SkillMetadata(BaseModel):
    name: str
    description: str = ""
    body: str = ""


def _parse_frontmatter(frontmatter_text: str) -> dict:
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
        if isinstance(parsed, dict):
            return parsed
    except yaml.YAMLError:
        pass

    parsed: dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        if not line or line.startswith((" ", "\t")) or ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def load_skill(skill_name: str) -> str:
    """Load .agents/skills/{skill_name}/SKILL.md full text."""
    safe_name = Path(skill_name).name  # prevent traversal
    path = SKILLS_DIR / safe_name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name}")
    return path.read_text(encoding="utf-8")


def load_skill_metadata(skill_name: str) -> SkillMetadata:
    """Load parsed frontmatter + body for a skill."""
    text = load_skill(skill_name)
    frontmatter: dict = {}
    body = text

    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            _, remainder = parts
            frontmatter_text = text[len("---\n"):len(text) - len(remainder) - len("\n---\n")]
            frontmatter = _parse_frontmatter(frontmatter_text)
            body = remainder.strip()

    return SkillMetadata(
        name=frontmatter.get("name", skill_name),
        description=frontmatter.get("description", ""),
        body=body,
    )


def list_skills() -> list[str]:
    """List all available skill names that have a SKILL.md."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
