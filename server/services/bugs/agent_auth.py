"""Guardrails for local agent-driven Bug List API calls."""

from __future__ import annotations

import os

from fastapi import HTTPException

from server import config


def require_agent_bug_token(provided_token: str | None) -> None:
    if config.ENV != "local":
        raise HTTPException(
            status_code=403,
            detail="Agent Bug List API is only enabled for local Growing backends.",
        )
    expected = str(
        config.OPS_AGENT_BUG_API_TOKEN or os.environ.get("OPS_AGENT_BUG_API_TOKEN", "")
    ).strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="OPS_AGENT_BUG_API_TOKEN is required for agent Bug List API calls.",
        )
    if str(provided_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid agent Bug List API token.")
