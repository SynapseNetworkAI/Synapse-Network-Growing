"""Schemas for deployment event log APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ReleaseTaskResetRunningRequest(BaseModel):
    confirm_phrase: str
    operator: str = "operator"
    reason: str | None = None


class DeploymentEventOut(BaseModel):
    id: int
    deployment_record_id: int
    sequence: int
    event_type: str
    step_key: str | None = None
    message: str = ""
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class DeploymentEventsPageOut(BaseModel):
    items: list[DeploymentEventOut] = []
    next_sequence: int = 0
    has_more: bool = False
