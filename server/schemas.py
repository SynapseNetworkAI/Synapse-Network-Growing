"""Pydantic schemas for request/response validation."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ── Agent ─────────────────────────────────────────────────────

class AgentOut(BaseModel):
    id: str
    display_name: str
    goal: str
    persona_path: Optional[str] = None
    skills: Optional[str] = "[]"
    created_at: Optional[datetime] = None
    task_count: int = 0
    completed_count: int = 0

    model_config = {"from_attributes": True}


# ── Task ──────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    description: str
    agent_id: str
    requires_approval: bool = False
    priority: str = "normal"


class TaskOut(BaseModel):
    id: int
    description: str
    agent_id: str
    status: str
    requires_approval: bool
    priority: str
    output_path: Optional[str] = None
    output_content: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Approval ──────────────────────────────────────────────────

class ApprovalOut(BaseModel):
    id: int
    task_id: int
    status: str
    reviewer: Optional[str] = None
    comment: Optional[str] = None
    created_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    task: Optional[TaskOut] = None

    model_config = {"from_attributes": True}


class ApprovalDecide(BaseModel):
    action: str  # "approve" | "reject"
    comment: str = ""
    reviewer: str = "cto"


# ── TaskLog ───────────────────────────────────────────────────

class TaskLogOut(BaseModel):
    id: int
    task_id: int
    event_type: str
    detail: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────

class DashboardStats(BaseModel):
    agent_count: int
    task_total: int
    task_pending: int
    task_running: int
    task_completed: int
    task_failed: int
    approval_pending: int
