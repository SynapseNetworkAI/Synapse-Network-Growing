"""Safety checks for public agent-generated distribution copy."""

from __future__ import annotations

import re

from server.services.social.agent_content_pack_models import AgentContentGenerationError


def validate_public_safe_text(value: str) -> None:
    if re.search(r"/(?:Users|home|workspace|tmp)/[A-Za-z0-9._/\-]*", value):
        raise AgentContentGenerationError(
            "agent_content_generation_failed: local_path_leak"
        )
    if re.search(
        r"\b(api[_-]?key|token|secret|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{10,}",
        value,
        flags=re.IGNORECASE,
    ):
        raise AgentContentGenerationError(
            "agent_content_generation_failed: secret_like_text"
        )
    if re.search(
        r"\b(workflow json|acceptance matrix|required_commands)\b",
        value,
        flags=re.IGNORECASE,
    ):
        raise AgentContentGenerationError(
            "agent_content_generation_failed: internal_workflow_leak"
        )
