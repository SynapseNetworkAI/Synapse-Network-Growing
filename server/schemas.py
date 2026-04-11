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


class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    status_counts: dict[str, int]


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


class ProjectPolicyCreate(BaseModel):
    project_key: str
    display_name: str
    root_path: str
    status: str = "active"
    allowed_write_globs: list[str] = ["**"]
    forbidden_globs: list[str] = []
    required_checks: list[str] = []
    release_mode: str = "manual"
    requires_manual_approval: bool = True
    notes: Optional[str] = None


class ProjectPolicyPatch(BaseModel):
    display_name: Optional[str] = None
    root_path: Optional[str] = None
    status: Optional[str] = None
    allowed_write_globs: Optional[list[str]] = None
    forbidden_globs: Optional[list[str]] = None
    required_checks: Optional[list[str]] = None
    release_mode: Optional[str] = None
    requires_manual_approval: Optional[bool] = None
    notes: Optional[str] = None


class ProjectPolicyOut(BaseModel):
    id: int
    project_key: str
    display_name: str
    root_path: str
    status: str
    allowed_write_globs: list[str]
    forbidden_globs: list[str]
    required_checks: list[str]
    release_mode: str
    requires_manual_approval: bool
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectReadinessItemOut(BaseModel):
    key: str
    label: str
    status: str
    message: str
    details: list[str] = []


class ProjectOnboardingCreate(BaseModel):
    project_key: str
    display_name: str
    root_path: str
    docs_entrypoints: list[str] = []
    validation_commands: list[str] = []
    agents_memory_namespace: Optional[str] = None
    auto_create_policy: bool = True
    allowed_write_globs: list[str] = ["**"]
    forbidden_globs: list[str] = []
    release_mode: str = "manual"
    requires_manual_approval: bool = True
    notes: Optional[str] = None


class ProjectOnboardingOut(BaseModel):
    id: int
    project_key: str
    display_name: str
    root_path: str
    docs_entrypoints: list[str]
    validation_commands: list[str]
    agents_memory_namespace: Optional[str] = None
    policy_id: Optional[int] = None
    readiness_status: str
    readiness_score: int
    readiness_items: list[ProjectReadinessItemOut] = []
    missing_items: list[str] = []
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OptimizationSignalEvidenceOut(BaseModel):
    data: dict[str, object] = {}


class OptimizationSignalOut(BaseModel):
    id: int
    dedupe_key: str
    signal_type: str
    source_kind: str
    status: str
    title: str
    summary: str
    severity: str
    confidence: float
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    routing_target_path: Optional[str] = None
    evidence: list[dict[str, object]] = []
    occurrence_count: int = 0
    latest_evidence_at: Optional[datetime] = None
    converted_requirement_id: Optional[int] = None
    score_breakdown: dict[str, float | bool | str | None] = {}
    recommended_priority: str = "normal"
    auto_intake_eligible: bool = False
    intake_recommendation: str = "observe"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OptimizationSignalCreateRequirementRequest(BaseModel):
    title: Optional[str] = None
    auto_start: bool = False


class OptimizationSignalAutoIntakeRequest(BaseModel):
    min_score: float = 60.0
    max_created: int = 1
    auto_start: bool = False


class OptimizationSignalAutoIntakeItemOut(BaseModel):
    signal_id: int
    requirement_id: int
    title: str
    score: float


class OptimizationSignalAutoIntakeResultOut(BaseModel):
    created: list[OptimizationSignalAutoIntakeItemOut] = []
    skipped: list[str] = []


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


class RequirementPublishRequest(BaseModel):
    completed_checks: list[str] = []
    note: Optional[str] = None


class TaskPatch(BaseModel):
    description: Optional[str] = None
    priority: Optional[str] = None


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


class DeliveryStateOut(BaseModel):
    branch_name: Optional[str] = None
    branch_strategy: Optional[str] = None
    base_branch: Optional[str] = None
    review_status: str = "unplanned"
    publish_status: str = "unplanned"
    release_mode: Optional[str] = None
    requires_manual_approval: bool = False
    required_checks: list[str] = []
    confirmed_checks: list[str] = []
    pending_checks: list[str] = []
    publish_blockers: list[str] = []
    review_surface_summary: Optional[str] = None
    rollback_hint_markdown: Optional[str] = None
    review_ready_at: Optional[str] = None
    published_at: Optional[str] = None
    publish_note: Optional[str] = None


class ProjectScorecardOut(BaseModel):
    project_key: str
    display_name: str
    root_path: str
    policy_status: str
    release_mode: str
    requires_manual_approval: bool = False
    readiness_status: str = "unknown"
    readiness_score: int = 0
    automation_ready: bool = False
    onboarding_present: bool = False
    active_requirement_count: int = 0
    completed_requirement_count: int = 0
    total_requirement_count: int = 0
    bug_report_count: int = 0
    blocked_publish_count: int = 0
    manual_override_count: int = 0
    validation_pass_rate: float = 0.0
    automation_coverage: float = 0.0
    notes: Optional[str] = None
    agents_memory_namespace: Optional[str] = None


class RequirementRoutingContextOut(BaseModel):
    routing_mode: str = "unrouted"
    target_project_path: Optional[str] = None
    summary: Optional[str] = None
    automation_ready: bool = False
    readiness_status: str = "unknown"
    routed_project_keys: list[str] = []
    routed_display_names: list[str] = []
    skipped_project_keys: list[str] = []
    project_scorecards: list[ProjectScorecardOut] = []


class RequirementScoreBreakdownOut(BaseModel):
    total: float = 0.0
    priority: float = 0.0
    aging: float = 0.0
    status_adjustment: float = 0.0
    blocker_penalty: float = 0.0
    readiness_adjustment: float = 0.0
    bug_pressure: float = 0.0
    delivery_pressure: float = 0.0
    manual_escalation_pressure: float = 0.0
    signal_impact: float = 0.0
    signal_risk: float = 0.0
    signal_confidence: float = 0.0
    signal_urgency: float = 0.0
    implementation_cost_adjustment: float = 0.0
    automation_gap: float = 0.0


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
    routing_context: RequirementRoutingContextOut = RequirementRoutingContextOut()
    score_breakdown: RequirementScoreBreakdownOut = RequirementScoreBreakdownOut()


class RequirementDetailOut(BaseModel):
    requirement: RequirementOut
    workflow_run: Optional[WorkflowRunOut] = None
    dependencies: list[RequirementDependencyOut] = []
    acceptance_checks: list[RequirementAcceptanceCheckOut] = []
    artifacts: list[ArtifactOut] = []
    delivery_state: Optional[DeliveryStateOut] = None


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
