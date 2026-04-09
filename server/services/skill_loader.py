"""Load Skill SKILL.md files from .agents/skills/ directory."""
from pathlib import Path

from server.config import PROJECT_ROOT

SKILLS_DIR = PROJECT_ROOT / ".agents" / "skills"


def load_skill(skill_name: str) -> str:
    """Load .agents/skills/{skill_name}/SKILL.md full text."""
    safe_name = Path(skill_name).name  # prevent traversal
    path = SKILLS_DIR / safe_name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name}")
    return path.read_text(encoding="utf-8")


def list_skills() -> list[str]:
    """List all available skill names that have a SKILL.md."""
    if not SKILLS_DIR.exists():
        return []
    return sorted(
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )
