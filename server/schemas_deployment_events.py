"""Schemas for deployment event ledger APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DeploymentEventOut(BaseModel):
    id: int
    deployment_record_id: int
    event_type: str
    actor: Optional[str] = None
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    summary: Optional[str] = None
    payload: dict[str, object] = {}
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
