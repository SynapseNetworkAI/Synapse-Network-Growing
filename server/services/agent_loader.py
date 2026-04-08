"""Load agent metadata from the roles/ directory into the database."""
import json
from pathlib import Path

from server.config import ROLES_DIR

# role_id → (display_name, goal, skills)
ROLE_META = {
    "dev_rel": ("DevRel Engineer", "负责 DX 和技术布道", ["content-strategy", "community-marketing"]),
    "growth_lead": ("Growth Lead", "负责 GTM 和增长策略", ["marketing-ideas", "marketing-psychology", "launch-strategy", "social-content"]),
    "content_writer": ("Content Writer", "负责极简主义文案写作", ["copywriting", "copy-editing", "cold-email", "email-sequence"]),
    "seo_strategist": ("SEO Strategist", "负责关键词与转化率优化", ["seo-audit", "ai-seo", "site-architecture", "schema-markup"]),
    "cro_optimizer": ("CRO Optimizer", "负责全链路转化率优化", ["page-cro", "signup-flow-cro", "ab-test-setup", "analytics-tracking"]),
    "launch_strategist": ("Launch Strategist", "负责发布节奏与飞轮编排", ["launch-strategy", "pricing-strategy", "referral-program"]),
}


def discover_agents() -> list[dict]:
    """Scan roles/ directory and return agent metadata dicts."""
    agents = []
    roles_path = Path(ROLES_DIR).resolve()

    for role_id, (display_name, goal, skills) in ROLE_META.items():
        persona_path = roles_path / role_id / "prompts" / "persona.md"
        agents.append({
            "id": role_id,
            "display_name": display_name,
            "goal": goal,
            "persona_path": str(persona_path) if persona_path.exists() else None,
            "skills": json.dumps(skills),
        })

    return agents
