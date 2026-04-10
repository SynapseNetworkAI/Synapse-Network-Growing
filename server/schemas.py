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
    group: str = ""
    persona_path: Optional[str] = None
    skills: Optional[str] = "[]"
    created_at: Optional[datetime] = None
    task_count: int = 0
    completed_count: int = 0

    model_config = {"from_attributes": True}


# ── Task ──────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    description: str
    agent_id: Optional[str] = None
    requires_approval: bool = False
    priority: str = "normal"
    skill_name: Optional[str] = None
    context_files: Optional[list[str]] = None
    confirm_auto_selection: bool = False


class TaskOut(BaseModel):
    id: int
    description: str
    agent_id: str
    status: str
    requires_approval: bool
    priority: str
    project_id: Optional[str] = None
    project_label: Optional[str] = None
    agent_group: Optional[str] = None
    skill_name: Optional[str] = None
    context_files: Optional[str] = None
    retry_of_task_id: Optional[int] = None
    attempt_no: int = 1
    last_error_message: Optional[str] = None
    runtime_backend: Optional[str] = None
    runtime_session_id: Optional[str] = None
    runtime_selected_agent: Optional[str] = None
    output_path: Optional[str] = None
    output_content: Optional[str] = None
    execution_time_ms: Optional[int] = None
    requirement_id: Optional[int] = None
    requirement_title: Optional[str] = None
    output_files: Optional[list[str]] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskHistoryOut(BaseModel):
    task_id: int
    retry_of_task_id: Optional[int] = None
    attempt_no: int = 1
    status: str
    project_id: Optional[str] = None
    agent_group: Optional[str] = None
    agent_id: str
    skill_name: Optional[str] = None
    last_error_message: Optional[str] = None
    runtime_backend: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TaskBulkRetryRequest(BaseModel):
    task_ids: list[int]
    mode: str = "run_now"


class TaskExecutionSuggestionRequest(BaseModel):
    description: str
    agent_id: Optional[str] = None
    skill_name: Optional[str] = None
    limit: int = 3


class TaskExecutionCandidate(BaseModel):
    agent_id: str
    display_name: str
    agent_group: str = ""
    skill_name: str
    confidence: float = 0.0
    reason: str = ""


class TaskExecutionSuggestion(BaseModel):
    agent_id: Optional[str] = None
    skill_name: Optional[str] = None
    confidence: float = 0.0
    reason: str = ""
    requires_confirmation: bool = False
    candidates: list[TaskExecutionCandidate] = []


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


class ApprovalBulkDecide(BaseModel):
    approval_ids: list[int]
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


# ── Agent Match ───────────────────────────────────────────────

class AgentMatch(BaseModel):
    id: str
    display_name: str
    goal: str
    group: str = ""
    skills: list[str] = []
    matched_skills: list[str] = []
    confidence: float = 0.0

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


# ── Requirements / Workflow ─────────────────────────────────

class RequirementCreate(BaseModel):
    title: str
    description_markdown: str
    priority: str = "normal"
    source: str = "manual"
    source_ref: Optional[str] = None
    target_project_path: Optional[str] = None
    depends_on_requirement_ids: list[int] = []
    auto_start: bool = False


class RequirementDependencyUpdate(BaseModel):
    depends_on_requirement_ids: list[int] = []


class RequirementRevisionRequest(BaseModel):
    title: Optional[str] = None
    description_markdown: str
    source_ref: Optional[str] = None
    revision_note: Optional[str] = None
    depends_on_requirement_ids: Optional[list[int]] = None


class RequirementPatch(BaseModel):
    title: Optional[str] = None
    description_markdown: Optional[str] = None
    priority: Optional[str] = None
    source_ref: Optional[str] = None
    target_project_path: Optional[str] = None


class ArtifactOut(BaseModel):
    id: int
    requirement_id: int
    workflow_run_id: Optional[int] = None
    step_id: Optional[int] = None
    producer_step_id: Optional[int] = None
    artifact_type: str
    path: Optional[str] = None
    content_summary: Optional[str] = None
    human_readable_body: Optional[str] = None
    machine_readable_payload: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RequirementDependencyOut(BaseModel):
    id: int
    requirement_id: int
    depends_on_requirement_id: int
    depends_on_title: str
    depends_on_status: str
    dependency_type: str


class RequirementAcceptanceCheckOut(BaseModel):
    id: int
    requirement_id: int
    check_key: str
    description: str
    check_type: str
    owner_role: str
    status: str
    success_criteria_markdown: Optional[str] = None
    verified_by_step_id: Optional[int] = None
    evidence_artifact_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkflowStepOut(BaseModel):
    id: int
    workflow_run_id: int
    requirement_id: int
    step_key: str
    step_type: str
    title: str
    status: str
    sequence_no: int
    assigned_agent_id: Optional[str] = None
    assigned_workflow_role: Optional[str] = None
    branch_from_step_id: Optional[int] = None
    compatibility_task_id: Optional[int] = None
    retry_count: int = 0
    handoff_summary_markdown: Optional[str] = None
    done_when_markdown: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WorkflowRunOut(BaseModel):
    id: int
    requirement_id: int
    plan_version: int
    status: str
    triggered_by: str
    planner_artifact_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    steps: list[WorkflowStepOut] = []

    model_config = {"from_attributes": True}


class RequirementOut(BaseModel):
    id: int
    title: str
    description_markdown: str
    status: str
    priority: str
    source: str
    source_ref: Optional[str] = None
    target_project_path: Optional[str] = None
    current_plan_version: int
    blocked_by_count: int
    active_workflow_run_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RequirementDetailOut(BaseModel):
    requirement: RequirementOut
    workflow_run: Optional[WorkflowRunOut] = None
    dependencies: list[RequirementDependencyOut] = []
    acceptance_checks: list[RequirementAcceptanceCheckOut] = []
    artifacts: list[ArtifactOut] = []


# ── Copilot Auth ─────────────────────────────────────────────

class CopilotAuthStatus(BaseModel):
    authenticated: bool
    host: str = "https://github.com"
    login: Optional[str] = None
    source: Optional[str] = None
    message: str = ""


class CopilotDeviceCodeRequest(BaseModel):
    host: str = "https://github.com"


class CopilotDeviceCodeOut(BaseModel):
    host: str
    client_id: str
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class CopilotDeviceCodePollRequest(BaseModel):
    host: str = "https://github.com"
    device_code: str
    client_id: Optional[str] = None


class CopilotDeviceCodePollOut(BaseModel):
    status: str
    host: str
    login: Optional[str] = None
    source: Optional[str] = None
    interval: Optional[int] = None
    message: str = ""
