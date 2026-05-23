from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ScheduleTemplateOut(BaseModel):
    template_key: str
    display_name: str
    description: str
    category: str
    risk_level: str
    handler_key: str
    schedule: dict[str, object] = {}
    input_query: dict[str, object] = {}
    output_action: dict[str, object] = {}
    validation_signal: dict[str, object] = {}


class ScheduleCreateRequest(BaseModel):
    template_key: str
    workflow_key: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    owner_role: Optional[str] = None
    status: str = "active"
    schedule: dict[str, object] = {}
    input_query: dict[str, object] = {}


class ScheduleUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    owner_role: Optional[str] = None
    status: Optional[str] = None
    schedule: Optional[dict[str, object]] = None
    input_query: Optional[dict[str, object]] = None


class ScheduleDeleteResultOut(BaseModel):
    deleted: bool
    schedule: dict[str, object]
