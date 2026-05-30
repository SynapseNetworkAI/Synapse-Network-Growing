"""Guardrails for local agent-driven release API calls."""

from __future__ import annotations

import os

from fastapi import HTTPException

from server import config


_HUMAN_RELEASE_ACTORS = {
    "",
    "operator",
    "ops-lead",
    "admin",
    "super_admin",
    "human",
}


def actor_requires_agent_deploy_token(actor: str | None) -> bool:
    return str(actor or "").strip().lower() not in _HUMAN_RELEASE_ACTORS


def require_agent_deploy_token_for_actor(
    actor: str | None, provided_token: str | None
) -> None:
    if not actor_requires_agent_deploy_token(actor):
        return
    if config.ENV != "local":
        raise HTTPException(
            status_code=403,
            detail="Agent release API is only enabled for local Growing backends.",
        )
    expected = str(
        config.OPS_AGENT_DEPLOY_API_TOKEN
        or os.environ.get("OPS_AGENT_DEPLOY_API_TOKEN", "")
    ).strip()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail="OPS_AGENT_DEPLOY_API_TOKEN is required for agent release API calls.",
        )
    if str(provided_token or "").strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid agent release API token.")
