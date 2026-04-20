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
    role_contract: dict[str, object] = {}
    created_at: Optional[datetime] = None
    task_count: int = 0
    completed_count: int = 0

    model_config = {"from_attributes": True}


class RoleKPIOut(BaseModel):
    role_id: str
    display_name: str
    group: str = ""
    mission: str = ""
    task_count: int = 0
    completed_count: int = 0
    active_task_count: int = 0
    pending_task_count: int = 0
    failed_task_count: int = 0
    backlog_count: int = 0
    reopened_task_count: int = 0
    human_gate_dependency_count: int = 0
    completion_rate: float = 0.0
    reopen_rate: float = 0.0
    human_gate_dependency_rate: float = 0.0
    average_token_cost: float = 0.0
    average_budget_cost_points: float = 0.0
    tokens_used_total: int = 0
    budget_cost_points_total: int = 0
    open_requirement_count: int = 0
    status_mix: dict[str, int] = {}


class HumanGateRoleKPIOut(BaseModel):
    role_id: str
    assigned_count: int = 0
    pending_count: int = 0
    decided_count: int = 0
    average_turnaround_hours: float = 0.0
    disagreement_rate: float = 0.0
    route_to_human_rate: float = 0.0
    approve_recommendation_count: int = 0
    revise_recommendation_count: int = 0
    route_to_human_count: int = 0


class RoleWorkAllocationSummaryOut(BaseModel):
    role_count: int = 0
    total_backlog_count: int = 0
    overloaded_role_count: int = 0
    human_gate_pending_count: int = 0
    human_gate_stale_count: int = 0


class RoleKpiSnapshotOut(BaseModel):
    roles: list[RoleKPIOut] = []
    human_gate_roles: list[HumanGateRoleKPIOut] = []
    summary: RoleWorkAllocationSummaryOut = RoleWorkAllocationSummaryOut()


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


class DeclarativeWorkflowRunSummaryOut(BaseModel):
    id: int
    requirement_id: int
    workflow_key: str
    current_state: str
    status: str
    resolution: Optional[str] = None
    risk_level: str = "normal"
    pending_human_gate_count: int = 0
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WorkflowReadinessOut(BaseModel):
    requirement_id: int
    assets_status: str = "pending"
    active_workflow_run_id: Optional[int] = None
    active_workflow_run_summary: Optional[DeclarativeWorkflowRunSummaryOut] = None
    blocking_reason: Optional[str] = None
    next_action: str = "generate_workflow_assets"
    can_start_workflow: bool = False
    recommended_workflow_key: Optional[str] = None


class PlanningManifestOut(BaseModel):
    id: int
    manifest_key: str
    version_name: str = ""
    cycle_label: str = ""
    status: str = "draft"
    revision: int = 1
    payload: dict[str, object] = {}
    goal_count: int = 0
    active_goal_count: int = 0
    dropped_goal_count: int = 0
    achieved_goal_count: int = 0
    review_summary: dict[str, object] = {}
    change_log: list[dict[str, object]] = []
    created_by: str = "operator"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None


class PlanningManifestSaveRequest(BaseModel):
    version_name: Optional[str] = None
    cycle_label: Optional[str] = None
    payload: dict[str, object]
    operator: str = "operator"


class PlanningManifestHistoryOut(BaseModel):
    items: list[PlanningManifestOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class PlanningArchiveCycleRequest(BaseModel):
    version_name: str
    cycle_label: str
    operator: str = "operator"
    payload_patch: dict[str, object] = {}


class PlanningDropGoalRequest(BaseModel):
    reason: str
    operator: str = "operator"
    halt_mode: str = "safe_halt"


class PlanningGoalStatusRequest(BaseModel):
    status: str
    reason: str = ""
    operator: str = "operator"


class PlanningDropGoalResultOut(BaseModel):
    manifest: PlanningManifestOut
    goal_key: str
    halt_summary: dict[str, object] = {}
    decision: dict[str, object] = {}


class PlanningGoalRollupOut(BaseModel):
    manifest_id: int
    goal_key: str
    goal: dict[str, object] = {}
    candidate_status_counts: dict[str, int] = {}
    requirement_status_counts: dict[str, int] = {}
    workflow_status_counts: dict[str, int] = {}
    release_status_counts: dict[str, int] = {}


class PlanningGlobalSteeringOut(BaseModel):
    focus_weights: dict[str, object] = {}
    global_budget: dict[str, object] = {}
    global_constraints: list[object] = []


class RequirementCandidateOut(BaseModel):
    id: int
    manifest_id: int
    goal_key: str
    candidate_fingerprint: str
    title: str
    description_markdown: str = ""
    project_id: Optional[int] = None
    project_key: Optional[str] = None
    workflow_key: str = ""
    priority: str = "normal"
    risk_level: str = "normal"
    confidence: float = 0.0
    rationale: str = ""
    expected_evidence: list[object] = []
    status: str = "pending"
    suppression_reason: Optional[str] = None
    reject_reason: Optional[str] = None
    reject_comment: Optional[str] = None
    approved_by: Optional[str] = None
    materialized_requirement_id: Optional[int] = None
    metadata: dict[str, object] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None


class RequirementCandidatePageOut(BaseModel):
    items: list[RequirementCandidateOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 30
    total_pages: int = 1


class CandidateDecisionRequest(BaseModel):
    operator: str = "operator"
    reason: str = ""
    comment: Optional[str] = None


class CandidateMaterializeResultOut(BaseModel):
    candidate: RequirementCandidateOut
    requirement_id: int


class CandidateApproveRunResultOut(BaseModel):
    candidate: RequirementCandidateOut
    requirement_id: int
    workflow_run_id: Optional[int] = None
    workflow_status: str = ""
    workflow_current_state: str = ""
    auto_run_status: str = ""
    next_action: str = ""


class PlannerSweepRunRequest(BaseModel):
    dry_run: bool = False
    triggered_by: str = "operator"


class PlannerSweepOut(BaseModel):
    id: int
    manifest_id: int
    status: str = "running"
    triggered_by: str = "operator"
    dry_run: bool = False
    input_snapshot: dict[str, object] = {}
    parsed_output: dict[str, object] = {}
    created_candidate_ids: list[int] = []
    suppressed_items: list[dict[str, object]] = []
    error_excerpt: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0


class PlanningGoalMissionLaneOut(BaseModel):
    goal_key: str
    goal: dict[str, object] = {}
    rollup: PlanningGoalRollupOut
    candidates: list[RequirementCandidateOut] = []


class PlanningMissionControlOut(BaseModel):
    manifest: PlanningManifestOut
    global_steering: PlanningGlobalSteeringOut
    goal_lanes: list[PlanningGoalMissionLaneOut] = []
    candidate_totals: dict[str, int] = {}
    history_preview: PlanningManifestHistoryOut
    last_sweep: Optional[PlannerSweepOut] = None


# ── Dashboard ─────────────────────────────────────────────────

class DashboardStats(BaseModel):
    agent_count: int
    requirement_total: int
    requirement_active: int
    workflow_total: int
    workflow_running: int
    workflow_succeeded: int
    workflow_failed: int
    human_gate_pending: int


class OperatingReviewPortfolioSummaryOut(BaseModel):
    active_requirements: int = 0
    completed_requirements: int = 0
    completion_rate: float = 0.0
    open_signals: int = 0
    human_gate_required_decisions: int = 0
    rebalance_opportunities: int = 0
    projects_over_budget: int = 0
    blocked_publish_projects: int = 0
    budget_spent_points: int = 0
    tokens_used: int = 0
    prompt_cache_saved_chars: int = 0
    deduped_bindings: int = 0
    escalations: int = 0
    downgrades: int = 0
    tier_mix: dict[str, int] = {}
    human_gate_hotspots: int = 0
    open_bug_pressure: int = 0
    unresolved_critical_bugs: int = 0
    bug_requirements_created: int = 0
    recurring_bug_fingerprint_count: int = 0
    cross_project_bug_recoveries: int = 0


class OperatingReviewProjectHighlightOut(BaseModel):
    project_key: str
    display_name: str
    readiness_status: str
    readiness_score: int
    active_count: int = 0
    queued_count: int = 0
    bug_report_count: int = 0
    blocked_publish_count: int = 0
    scheduler_weight: float = 1.0
    autonomy_mode: str = "recommend"
    budget_used: int = 0
    budget_remaining: int = 0
    completed_requirements: int = 0
    budget_spent_points: int = 0
    prompt_cache_saved_chars: int = 0
    escalations: int = 0
    downgrades: int = 0
    tier_mix: dict[str, int] = {}
    open_bug_count: int = 0
    critical_bug_count: int = 0
    converted_bug_count: int = 0
    recurring_bug_count: int = 0


class OperatingReviewBugFingerprintOut(BaseModel):
    bug_id: int
    bug_key: str
    title: str
    severity: str = "medium"
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    fingerprint: str
    occurrence_count: int = 0
    score_total: float = 0.0
    source_key: str
    converted_requirement_id: Optional[int] = None
    last_seen_at: Optional[str] = None


class OperatingReviewCrossProjectBugRecoveryOut(BaseModel):
    item_key: str
    title: str
    severity: str = "medium"
    summary: str
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    recommendation: Optional[str] = None
    incident_family: Optional[str] = None
    incident_code: Optional[str] = None
    recovery_status: Optional[str] = None
    requirement_id: Optional[int] = None
    source_ref: Optional[str] = None
    affected_project_keys: list[str] = []
    affected_project_display_names: list[str] = []
    score_total: float = 0.0


class OperatingReviewItemOut(BaseModel):
    item_key: str
    title: str
    severity: str = "medium"
    summary: str
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    recommendation: Optional[str] = None
    incident_family: Optional[str] = None
    incident_code: Optional[str] = None
    recovery_status: Optional[str] = None
    requirement_id: Optional[int] = None
    source_ref: Optional[str] = None


class OperatingReviewGateHotspotOut(BaseModel):
    gate_key: str
    title: str
    approval_type: str
    approval_scope: Optional[str] = None
    step_type: Optional[str] = None
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    occurrence_count: int = 0
    pending_count: int = 0
    latest_status: str = "pending"
    summary: str
    recommendation: Optional[str] = None


class OperatingReviewAutomationCandidateOut(BaseModel):
    candidate_key: str
    title: str
    gate_key: str
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    automation_type: str
    priority: str = "normal"
    rationale: str
    occurrence_count: int = 0


class OperatingReviewRecommendationOut(BaseModel):
    candidate_type: str
    title: str
    project_key: str
    project_display_name: str
    action: str
    score: float = 0.0
    budget_cost: int = 0
    source_ref: Optional[str] = None
    rationale: str
    human_gate_required: bool = False
    requirement_id: Optional[int] = None
    signal_id: Optional[int] = None
    incident_family: Optional[str] = None
    incident_code: Optional[str] = None
    recovery_status: Optional[str] = None


class OperatingReviewBundleItemOut(BaseModel):
    bundle_item_key: str
    title: str
    candidate_type: str
    project_key: str
    project_display_name: str
    action: str
    materialization_mode: str
    priority: str = "normal"
    score: float = 0.0
    budget_cost: int = 0
    source_ref: Optional[str] = None
    target_project_path: Optional[str] = None
    requirement_id: Optional[int] = None
    template_key: Optional[str] = None
    rationale: str
    description_markdown: str
    acceptance_checks: list[dict[str, object]] = []
    human_gate_required: bool = False


class OperatingReviewOperatorDecisionOut(BaseModel):
    decision_key: str
    title: str
    decision_type: str
    severity: str = "medium"
    summary: str
    owner_hint: Optional[str] = None
    related_bundle_item_key: Optional[str] = None


class OperatingReviewOperatorPackageOut(BaseModel):
    title: str
    summary_markdown: str
    checklist: list[str] = []
    decisions: list[OperatingReviewOperatorDecisionOut] = []
    autonomous_decision_count: int = 0
    recommended_bundle_item_keys: list[str] = []


class OperatingReviewAutonomousCooPostureOut(BaseModel):
    mode: str = "autonomous_coo"
    operator_only_high_risk: bool = True
    autonomous_workflow_keys: list[str] = []
    high_risk_decision_count: int = 0
    autonomous_decision_count: int = 0
    operator_queue_count: int = 0
    pending_human_gate_count: int = 0
    auto_approved_requirement_count: int = 0
    stale_approval_count: int = 0
    stuck_requirement_count: int = 0
    critical_incident_count: int = 0
    requires_operator_attention: bool = False
    autonomous_execution_rate: float = 0.0
    summary_markdown: str = ""


class CompanyOperatingReviewOut(BaseModel):
    id: int
    cycle_label: str
    title: str
    summary_markdown: str
    portfolio_summary: OperatingReviewPortfolioSummaryOut
    project_highlights: list[OperatingReviewProjectHighlightOut] = []
    bottlenecks: list[OperatingReviewItemOut] = []
    incidents: list[OperatingReviewItemOut] = []
    recurring_bug_fingerprints: list[OperatingReviewBugFingerprintOut] = []
    cross_project_bug_recoveries: list[OperatingReviewCrossProjectBugRecoveryOut] = []
    human_gate_hotspots: list[OperatingReviewGateHotspotOut] = []
    automation_candidates: list[OperatingReviewAutomationCandidateOut] = []
    next_cycle_recommendations: list[OperatingReviewRecommendationOut] = []
    next_cycle_requirement_bundle: list[OperatingReviewBundleItemOut] = []
    operator_review_package: OperatingReviewOperatorPackageOut
    autonomous_coo_posture: OperatingReviewAutonomousCooPostureOut
    source_snapshot: dict[str, object] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CompanyReviewBundleMaterializeRequest(BaseModel):
    bundle_item_keys: list[str] = []
    auto_start: bool = False


class CompanyReviewBundleMaterializeItemOut(BaseModel):
    bundle_item_key: str
    status: str
    title: str
    action: str
    requirement_id: Optional[int] = None
    source_ref: Optional[str] = None


class CompanyReviewBundleMaterializeResultOut(BaseModel):
    review_id: int
    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped_bundle_item_keys: list[str] = []
    items: list[CompanyReviewBundleMaterializeItemOut] = []


class ProjectCapabilityMatrix(BaseModel):
    shell_access: bool = True
    git_read: bool = True
    git_write: bool = True
    git_push: bool = False
    network_access: bool = False
    publish: bool = False


class ProjectInterruptPolicy(BaseModel):
    operator_confirmation_actions: list[str] = []
    auto_pause_on_events: list[str] = []
    auto_abort_on_events: list[str] = []


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
    autonomy_mode: str = "recommend"
    allow_rebalance: bool = True
    allow_preemption: bool = False
    capability_matrix: ProjectCapabilityMatrix = ProjectCapabilityMatrix()
    interrupt_policy: ProjectInterruptPolicy = ProjectInterruptPolicy()
    scheduler_weight: float = 1.0
    max_parallel_requirements: int = 1
    portfolio_budget_points: int = 100
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: str = "github_actions_ssh"
    deploy_trigger_enabled: bool = False
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    staging_workflow_file: str = "deploy-staging.yml"
    production_workflow_file: str = "deploy-production.yml"
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
    autonomy_mode: Optional[str] = None
    allow_rebalance: Optional[bool] = None
    allow_preemption: Optional[bool] = None
    capability_matrix: Optional[ProjectCapabilityMatrix] = None
    interrupt_policy: Optional[ProjectInterruptPolicy] = None
    scheduler_weight: Optional[float] = None
    max_parallel_requirements: Optional[int] = None
    portfolio_budget_points: Optional[int] = None
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: Optional[str] = None
    deploy_trigger_enabled: Optional[bool] = None
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    staging_workflow_file: Optional[str] = None
    production_workflow_file: Optional[str] = None
    notes: Optional[str] = None


class ProjectPolicyOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    project_key: str
    display_name: str
    root_path: str
    status: str
    allowed_write_globs: list[str]
    forbidden_globs: list[str]
    required_checks: list[str]
    release_mode: str
    requires_manual_approval: bool
    autonomy_mode: str = "recommend"
    allow_rebalance: bool = True
    allow_preemption: bool = False
    capability_matrix: ProjectCapabilityMatrix = ProjectCapabilityMatrix()
    interrupt_policy: ProjectInterruptPolicy = ProjectInterruptPolicy()
    scheduler_weight: float = 1.0
    max_parallel_requirements: int = 1
    portfolio_budget_points: int = 100
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: str = "github_actions_ssh"
    deploy_trigger_enabled: bool = False
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    staging_workflow_file: str = "deploy-staging.yml"
    production_workflow_file: str = "deploy-production.yml"
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectCreate(BaseModel):
    project_key: str
    display_name: str
    root_path: str
    status: str = "active"
    repo_full_name: Optional[str] = None
    default_branch: str = "main"
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: str = "disabled"
    deploy_trigger_enabled: bool = False
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    staging_workflow_file: str = "deploy-staging.yml"
    production_workflow_file: str = "deploy-production.yml"
    notes: Optional[str] = None


class ProjectPatch(BaseModel):
    project_key: Optional[str] = None
    display_name: Optional[str] = None
    root_path: Optional[str] = None
    status: Optional[str] = None
    repo_full_name: Optional[str] = None
    default_branch: Optional[str] = None
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: Optional[str] = None
    deploy_trigger_enabled: Optional[bool] = None
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    staging_workflow_file: Optional[str] = None
    production_workflow_file: Optional[str] = None
    notes: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    project_key: str
    display_name: str
    root_path: str
    status: str
    repo_full_name: Optional[str] = None
    default_branch: str = "main"
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: str = "disabled"
    deploy_trigger_enabled: bool = False
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    staging_workflow_file: str = "deploy-staging.yml"
    production_workflow_file: str = "deploy-production.yml"
    notes: Optional[str] = None
    policy_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ProjectWithPolicyOut(ProjectOut):
    policy: Optional[ProjectPolicyOut] = None


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
    incident_family: Optional[str] = None
    incident_code: Optional[str] = None
    recovery_status: Optional[str] = None
    recovery_narrative: Optional[str] = None
    score_breakdown: dict[str, float | bool | str | None] = {}
    recommended_priority: str = "normal"
    auto_intake_eligible: bool = False
    intake_recommendation: str = "observe"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OptimizationSignalCreateRequirementRequest(BaseModel):
    title: Optional[str] = None
    auto_start: bool = False


class OptimizationRequirementTemplateOut(BaseModel):
    template_key: str
    category: str
    display_name: str
    description: str
    supported_signal_types: list[str] = []
    default_acceptance_checks: list[dict[str, object]] = []


class OptimizationTemplateCreateRequirementRequest(BaseModel):
    title: str
    context_summary: str
    target_project_path: Optional[str] = None
    priority: str = "normal"
    evidence: list[dict[str, object]] = []
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


class SchedulerProjectStateOut(BaseModel):
    project_key: str
    display_name: str
    root_path: str
    active_count: int = 0
    queued_count: int = 0
    max_parallel_requirements: int = 1
    autonomy_mode: str = "recommend"
    allow_rebalance: bool = True
    allow_preemption: bool = False
    scheduler_weight: float = 1.0
    portfolio_budget_points: int = 100
    budget_used: int = 0
    budget_remaining: int = 0
    readiness_status: str = "unknown"
    readiness_score: int = 0


class SchedulerDecisionOut(BaseModel):
    candidate_type: str
    action: str
    requirement_id: Optional[int] = None
    signal_id: Optional[int] = None
    title: str
    project_key: str = "org-ops"
    project_display_name: str = "Org Ops"
    score: float = 0.0
    base_score: float = 0.0
    scheduler_weight: float = 1.0
    autonomy_mode: str = "recommend"
    budget_cost: int = 0
    project_slot_available: bool = False
    reason: str = ""
    reasons: list[str] = []
    template_key: Optional[str] = None
    source: Optional[str] = None
    preempt_requirement_id: Optional[int] = None
    human_gate_required: bool = False


class SchedulerPlanOut(BaseModel):
    global_capacity: int
    active_count: int
    available_slots: int
    generated_at: Optional[datetime] = None
    project_states: list[SchedulerProjectStateOut] = []
    decisions: list[SchedulerDecisionOut] = []
    started_ids: list[int] = []
    created_requirement_ids: list[int] = []
    preempted_ids: list[int] = []
    rebalanced_ids: list[int] = []
    skipped: list[str] = []


# ── Requirements / Workflow ─────────────────────────────────

class RequirementCreate(BaseModel):
    title: str
    description_markdown: str
    acceptance_criteria_markdown: str = ""
    priority: str = "normal"
    source: str = "manual"
    source_ref: Optional[str] = None
    intake_metadata: Optional[dict[str, object]] = None
    project_id: Optional[int] = None
    target_project_path_override: Optional[str] = None
    target_project_path: Optional[str] = None
    depends_on_requirement_ids: list[int] = []
    auto_start: bool = False
    template_key: Optional[str] = None
    template_payload: Optional[dict[str, object]] = None
    template_acceptance_checks: list[dict[str, object]] = []
    acceptance_contract: Optional[dict[str, object]] = None
    attachments: list[dict[str, object]] = []


class RequirementDependencyUpdate(BaseModel):
    depends_on_requirement_ids: list[int] = []


class RequirementRevisionRequest(BaseModel):
    title: Optional[str] = None
    description_markdown: str
    acceptance_criteria_markdown: Optional[str] = None
    source_ref: Optional[str] = None
    revision_note: Optional[str] = None
    depends_on_requirement_ids: Optional[list[int]] = None


class RequirementPatch(BaseModel):
    title: Optional[str] = None
    description_markdown: Optional[str] = None
    acceptance_criteria_markdown: Optional[str] = None
    priority: Optional[str] = None
    source_ref: Optional[str] = None
    intake_metadata: Optional[dict[str, object]] = None
    project_id: Optional[int] = None
    target_project_path_override: Optional[str] = None
    target_project_path: Optional[str] = None
    acceptance_contract: Optional[dict[str, object]] = None
    execution_plan: Optional[dict[str, object]] = None


class RequirementPlanPatch(BaseModel):
    human_readable_body: str


class RequirementPublishRequest(BaseModel):
    completed_checks: list[str] = []
    note: Optional[str] = None


class AgentFirstRequirementOut(BaseModel):
    id: int
    title: str
    description_markdown: str
    acceptance_criteria_markdown: str = ""
    state: str = "draft"
    attention_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    requirement_plan_summary: Optional[str] = None
    project: Optional[RequirementProjectRefOut] = None
    current_attempt_id: Optional[int] = None
    current_delivery_id: Optional[int] = None
    status: str
    priority: str
    source: str
    source_ref: Optional[str] = None
    linked_requirement_id: Optional[int] = None
    followup_requirement_id: Optional[int] = None
    resolution_path: Optional[str] = None
    operating_manifest_id: Optional[int] = None
    goal_key: Optional[str] = None
    requirement_candidate_id: Optional[int] = None
    project_id: Optional[int] = None
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    target_project_path: Optional[str] = None
    target_project_path_override: Optional[str] = None
    target_projects: list[str] = []
    phase: str = "draft"
    allowed_actions: list[str] = []
    pending_operations: list[str] = []
    recovery_status: Optional[str] = None
    recovery_scope: Optional[str] = None
    recovery_deadline_at: Optional[datetime] = None
    recovery_timeout_status: Optional[str] = None
    time_remaining_seconds: Optional[int] = None
    assets_status: str = "pending"
    assets_error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    active_workflow_run_id: Optional[int] = None
    active_workflow_run_summary: Optional[DeclarativeWorkflowRunSummaryOut] = None
    latest_release_status: Optional[str] = None


class AgentFirstRequirementDetailOut(BaseModel):
    requirement: AgentFirstRequirementOut
    state: str = "draft"
    attention_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    policy_summary_markdown: str = ""
    project: Optional[ProjectOut] = None
    active_workflow_run_id: Optional[int] = None
    active_workflow_run_summary: Optional[DeclarativeWorkflowRunSummaryOut] = None
    latest_release_id: Optional[int] = None
    latest_release: Optional["ReleaseRecordSlimOut"] = None
    phase: str = "draft"
    allowed_actions: list[str] = []
    pending_operations: list[str] = []
    recovery_status: Optional[str] = None
    recovery_scope: Optional[str] = None
    recovery_deadline_at: Optional[datetime] = None
    recovery_timeout_status: Optional[str] = None
    time_remaining_seconds: Optional[int] = None
    assets_status: str = "pending"
    assets_error_message: Optional[str] = None
    acceptance_contract: dict[str, object] = {}
    execution_plan: dict[str, object] = {}
    workflow_readiness: Optional[WorkflowReadinessOut] = None
    attachments: list["RequirementAttachmentOut"] = []
    followup_requirement_id: Optional[int] = None
    resolution_path: Optional[str] = None


class ValidationCheckResultOut(BaseModel):
    label: str
    command: Optional[str] = None
    project_path: Optional[str] = None
    status: str
    output_excerpt: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    log_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timed_out: bool = False
    purpose: Optional[str] = None


class VerificationPlanOut(BaseModel):
    mode: str = "evidence_review"
    summary: str = ""
    checks: list[str] = []
    evidence_expectations: list[str] = []
    why_no_verification: Optional[str] = None
    markdown: str = ""
    required_commands: list[dict[str, object]] = []
    expected_artifacts: list[str] = []
    evidence_to_inspect: list[str] = []
    non_mutating_rules: list[str] = []
    verdict_rubric: list[str] = []


class WorkspaceBlockerOut(BaseModel):
    repo_path: str
    base_branch: Optional[str] = None
    target_branch: Optional[str] = None
    current_branch: Optional[str] = None
    dirty_file_count: int = 0
    dirty_files_preview: list[str] = []
    has_untracked: bool = False
    recommended_operator_action: Optional[str] = None
    workspace_mode: str = "shared_checkout"


class RequirementProjectRefOut(BaseModel):
    project_id: Optional[int] = None
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    target_project_path: Optional[str] = None
    target_project_path_override: Optional[str] = None


class ValidationRecordSlimOut(BaseModel):
    id: int
    requirement_id: int
    workflow_run_id: int
    profile: str
    status: str
    summary_markdown: str = ""
    checks: list[ValidationCheckResultOut] = []
    verification_plan: Optional[VerificationPlanOut] = None
    verification_agent_id: Optional[str] = None
    verification_agent_label: Optional[str] = None
    evidence_used: list[str] = []
    reasoning_markdown: str = ""
    suggested_next_action: Optional[str] = None
    resolution_recommendation: Optional[str] = None
    resolution_confidence: Optional[float] = None
    resolution_reason: Optional[str] = None
    resolution_path: Optional[str] = None
    followup_requirement_id: Optional[int] = None
    followup_requirement_payload: dict[str, object] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReleaseRecordSlimOut(BaseModel):
    id: int
    requirement_id: int
    workflow_run_id: Optional[int] = None
    state: str = "pending"
    project_id: Optional[int] = None
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    target_project_path: Optional[str] = None
    status: str
    branch_name: Optional[str] = None
    planned_branch_name: Optional[str] = None
    actual_branch_name: Optional[str] = None
    branch_reuse_status: Optional[str] = None
    base_branch: Optional[str] = None
    commit_sha: Optional[str] = None
    compare_url: Optional[str] = None
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    notes: Optional[str] = None
    blocker_kind: Optional[str] = None
    delivery_blocker_type: Optional[str] = None
    failed_gate_name: Optional[str] = None
    delivery_failure_excerpt: Optional[str] = None
    delivery_failure_raw_output: Optional[str] = None
    repairable: bool = False
    repairability: Optional[str] = None
    repair_attempt_count: int = 0
    next_action: Optional[str] = None
    workspace_blocker: Optional[WorkspaceBlockerOut] = None
    workspace_mode: str = "shared_checkout"
    prepared_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ReleaseCandidateOut(BaseModel):
    requirement: AgentFirstRequirementOut
    validation: ValidationRecordSlimOut
    release: Optional[ReleaseRecordSlimOut] = None


class ReleaseDetailOut(BaseModel):
    requirement: AgentFirstRequirementOut
    validation: Optional[ValidationRecordSlimOut] = None
    release: Optional[ReleaseRecordSlimOut] = None
    deployments: list[DeploymentRecordOut] = []


class ReleaseActionRequest(BaseModel):
    actor: str = "operator"
    note: Optional[str] = None


class ReleaseRollbackRequest(BaseModel):
    actor: str = "operator"
    note: Optional[str] = None
    rollback_target_sha: str


class ErrorIntakeRequest(BaseModel):
    source_kind: str
    service_name: str
    summary: str
    message: str
    severity: str = "normal"
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    incident_code: Optional[str] = None
    stack_trace: Optional[str] = None
    source_ref: Optional[str] = None
    environment: Optional[str] = None
    occurred_at: Optional[datetime] = None
    metadata: dict[str, object] = {}


class NotificationDeliveryOut(BaseModel):
    id: int
    channel: str
    event_type: str
    event_key: str
    object_type: str
    object_key: str
    service_name: Optional[str] = None
    status: str
    payload: dict[str, object] = {}
    event_id: Optional[int] = None
    fingerprint_key: Optional[str] = None
    fingerprint: dict[str, object] = {}
    response_excerpt: Optional[str] = None
    delivered_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DiscoveryRecommendationOut(BaseModel):
    discovery_action: str
    confidence: float = 0.0
    reason: str = ""
    target_project_key: Optional[str] = None
    suggested_title: Optional[str] = None
    suggested_priority: Optional[str] = None
    auto_start_allowed: bool = False


class ErrorEventOut(BaseModel):
    id: int
    fingerprint_key: str
    source_kind: str
    service_name: str
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    incident_code: Optional[str] = None
    severity: str
    summary: str
    message: str
    stack_trace: Optional[str] = None
    source_ref: Optional[str] = None
    environment: Optional[str] = None
    metadata: dict[str, object] = {}
    occurred_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ErrorFingerprintOut(BaseModel):
    fingerprint_key: str
    source_kind: str
    service_name: str
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    incident_code: Optional[str] = None
    severity: str
    summary: str
    evidence_excerpt: Optional[str] = None
    status: str
    occurrence_count: int
    first_seen_at: Optional[datetime] = None
    latest_seen_at: Optional[datetime] = None
    latest_error_event_id: Optional[int] = None
    linked_requirement_id: Optional[int] = None
    materialized_requirement_id: Optional[int] = None
    active_workflow_run_id: Optional[int] = None
    active_workflow_run_summary: Optional[DeclarativeWorkflowRunSummaryOut] = None
    discovery_status: str = "pending"
    discovery_recommendation: Optional[DiscoveryRecommendationOut] = None
    last_discovery_at: Optional[datetime] = None


class ErrorFingerprintDetailOut(BaseModel):
    fingerprint: ErrorFingerprintOut
    requirement: Optional[AgentFirstRequirementOut] = None
    release: Optional[ReleaseRecordSlimOut] = None
    events: list[ErrorEventOut] = []
    notifications: list[NotificationDeliveryOut] = []


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


class IncidentRecordOut(BaseModel):
    incident_key: str
    requirement_id: int
    workflow_run_id: Optional[int] = None
    step_id: Optional[int] = None
    source_artifact_id: int
    source_artifact_type: str
    incident_family: str
    incident_code: str
    severity: str
    recovery_status: str
    title: str
    summary: str
    recommended_action: str
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    project_display_name: Optional[str] = None
    evidence: list[dict[str, object]] = []
    occurred_at: Optional[str] = None


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
    vcs_status: Optional[str] = None
    vcs_remote_name: Optional[str] = None
    vcs_repositories: list[dict[str, object]] = []
    compare_url: Optional[str] = None
    pr_status: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    head_branch: Optional[str] = None
    latest_commit_sha: Optional[str] = None
    latest_remote_sha: Optional[str] = None
    review_bundle_generated_at: Optional[str] = None
    last_pushed_at: Optional[str] = None
    pr_metadata: dict[str, object] | None = None
    promotion_checklist: list[dict[str, object]] = []
    staging_status: dict[str, object] | None = None
    production_status: dict[str, object] | None = None
    last_deployed_sha: Optional[str] = None
    last_deployed_at: Optional[str] = None
    deploy_readiness: dict[str, object] | None = None


class DeploymentRecordOut(BaseModel):
    id: int
    requirement_id: int
    project_policy_id: Optional[int] = None
    project_key: str
    environment: str
    action: str
    status: str
    commit_sha: Optional[str] = None
    branch_name: Optional[str] = None
    workflow_file: Optional[str] = None
    external_run_id: Optional[str] = None
    external_url: Optional[str] = None
    actor: Optional[str] = None
    trigger_source: str = "ops_console"
    rollback_target_sha: Optional[str] = None
    health_status: Optional[str] = None
    notes: Optional[str] = None
    metadata: dict[str, object] = {}
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EnvironmentStatusOut(BaseModel):
    environment: str
    project_key: str
    deploy_repo_full_name: Optional[str] = None
    host_label: Optional[str] = None
    deploy_strategy: str = "github_actions_ssh"
    trigger_enabled: bool = False
    current_commit_sha: Optional[str] = None
    current_branch: Optional[str] = None
    last_success_at: Optional[str] = None
    health_status: Optional[str] = None
    last_trigger_source: Optional[str] = None
    last_external_url: Optional[str] = None
    last_record_id: Optional[int] = None


class DeploymentProjectOverviewOut(BaseModel):
    project_policy_id: int
    project_key: str
    display_name: str
    deploy_repo_full_name: Optional[str] = None
    deploy_strategy: str = "github_actions_ssh"
    deploy_trigger_enabled: bool = False
    staging_host_label: Optional[str] = None
    production_host_label: Optional[str] = None
    environment_statuses: list[EnvironmentStatusOut] = []
    recent_records: list[DeploymentRecordOut] = []


class DeploymentRequirementCandidateOut(BaseModel):
    requirement_id: int
    title: str
    status: str
    priority: str
    source: str
    source_ref: Optional[str] = None
    project_key: Optional[str] = None
    project_display_name: Optional[str] = None
    target_project_path: Optional[str] = None
    updated_at: Optional[datetime] = None
    delivery_state: Optional[DeliveryStateOut] = None
    deployment_records: list[DeploymentRecordOut] = []


class DeploymentOverviewOut(BaseModel):
    project_overviews: list[DeploymentProjectOverviewOut] = []
    release_candidates: list[DeploymentRequirementCandidateOut] = []


class DeploymentTriggerRequest(BaseModel):
    actor: str = "operator"
    note: Optional[str] = None
    commit_sha: Optional[str] = None
    rollback_target_sha: Optional[str] = None


class DeploymentReportRequest(BaseModel):
    status: str
    external_run_id: Optional[str] = None
    external_url: Optional[str] = None
    health_status: Optional[str] = None
    branch_name: Optional[str] = None
    commit_sha: Optional[str] = None
    notes: Optional[str] = None


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


class RequirementAttachmentOut(BaseModel):
    id: int
    requirement_id: int
    file_name: str
    stored_path: str
    content_type: str
    attachment_kind: str
    source: str
    size_bytes: int
    created_at: Optional[datetime] = None


class RequirementOut(BaseModel):
    id: int
    title: str
    description_markdown: str
    status: str
    priority: str
    source: str
    source_ref: Optional[str] = None
    intake_metadata: dict[str, object] = {}
    target_project_path: Optional[str] = None
    acceptance_contract: dict[str, object] = {}
    blocked_by_count: int
    active_workflow_run_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    routing_context: RequirementRoutingContextOut = RequirementRoutingContextOut()
    score_breakdown: RequirementScoreBreakdownOut = RequirementScoreBreakdownOut()

class RequirementSourceRegistryItemOut(BaseModel):
    source_key: str
    display_name: str
    description: str
    source_types: list[str] = []
    intake_supported: bool = False
    requirement_count: int = 0
    recent_requirement_count: int = 0
    open_candidate_count: int = 0
    last_requirement_at: Optional[datetime] = None
    sample_source_refs: list[str] = []
    latest_review_id: Optional[int] = None


class RequirementSourceRegistryOut(BaseModel):
    generated_at: Optional[datetime] = None
    total_requirements: int = 0
    sources: list[RequirementSourceRegistryItemOut] = []


class RequirementSourceIntakeRequest(BaseModel):
    source_key: str = "all"
    refresh: bool = True
    auto_start: bool = False
    min_score: float = 60.0
    max_created: int = 1
    bundle_item_keys: list[str] = []


class RequirementSourceIntakeItemOut(BaseModel):
    source_key: str
    action: str
    status: str
    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped: list[str] = []
    details: dict[str, object] = {}


class RequirementSourceIntakeResultOut(BaseModel):
    executed_sources: list[str] = []
    created_requirement_ids: list[int] = []
    reused_requirement_ids: list[int] = []
    skipped: list[str] = []
    items: list[RequirementSourceIntakeItemOut] = []


class BugSourceRegistryItemOut(BaseModel):
    source_key: str
    display_name: str
    source_kind: str
    ingest_mode: str
    project_resolution_rule: str
    severity_mapping: dict[str, object] = {}
    dedupe_scope: str
    auto_requirement_policy: dict[str, object] = {}
    sample_evidence_types: list[str] = []
    notes: Optional[str] = None
    observed_open_count: int = 0


class BugSourceRegistryOut(BaseModel):
    generated_at: Optional[datetime] = None
    total_sources: int = 0
    total_open_candidates: int = 0
    sources: list[BugSourceRegistryItemOut] = []


class BugIntakeRequest(BaseModel):
    source_key: str
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    title: str
    summary: str = ""
    severity: str = "normal"
    fingerprint: Optional[str] = None
    source_ref: Optional[str] = None
    environment: Optional[str] = None
    log_excerpt: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: dict[str, object] = {}


class BugRecordOut(BaseModel):
    id: int
    bug_key: str
    source_key: str
    source_kind: str
    status: str
    title: str
    summary: str
    severity: str
    fingerprint: str
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    source_ref: Optional[str] = None
    environment: Optional[str] = None
    occurrence_count: int = 1
    evidence: list[dict[str, object]] = []
    metadata: dict[str, object] = {}
    scorecard: dict[str, object] = {}
    converted_requirement_id: Optional[int] = None
    materialized_requirement_id: Optional[int] = None
    discovery_status: str = "pending"
    discovery_recommendation: Optional[DiscoveryRecommendationOut] = None
    last_discovery_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BugIntakeResultOut(BaseModel):
    result: str
    bug: BugRecordOut


class ExternalLogCenterEventRequest(BaseModel):
    project_key: Optional[str] = None
    project_root_path: Optional[str] = None
    service_name: Optional[str] = None
    title: Optional[str] = None
    message: str
    severity: str = "high"
    fingerprint: Optional[str] = None
    source_ref: Optional[str] = None
    environment: Optional[str] = None
    log_excerpt: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: dict[str, object] = {}


class ExternalLogCenterBatchRequest(BaseModel):
    source_system: str = "log_center"
    events: list[ExternalLogCenterEventRequest] = []


class ExternalLogCenterBatchResultOut(BaseModel):
    source_system: str
    accepted_count: int = 0
    created_bug_ids: list[int] = []
    updated_bug_ids: list[int] = []
    deduped_bug_ids: list[int] = []
    results: list[BugIntakeResultOut] = []


class RecurringWorkflowOut(BaseModel):
    id: int
    workflow_key: str
    display_name: str
    description: str
    status: str
    trigger_type: str
    owner_role: str
    schedule: dict[str, object] = {}
    input_query: dict[str, object] = {}
    output_action: dict[str, object] = {}
    escalation_rule: dict[str, object] = {}
    validation_signal: dict[str, object] = {}
    is_builtin: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    is_due: bool = False
    health_status: str = "unknown"
    last_result: dict[str, object] = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RecurringWorkflowRunOut(BaseModel):
    id: int
    workflow_key: str
    status: str
    triggered_by: str
    dry_run: bool = False
    params: dict[str, object] = {}
    result: dict[str, object] = {}
    error_excerpt: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: int = 0


class RecurringWorkflowRunRequest(BaseModel):
    dry_run: bool = False
    auto_start: bool = False
    intake_min_score: float = 60.0
    intake_max_created: int = 2
    acceptance_limit: int = 20
    auto_dispatch_acceptance: bool = False


class RecurringWorkflowRunResultOut(BaseModel):
    workflow_key: str
    status: str
    run_started_at: Optional[datetime] = None
    run_id: Optional[int] = None
    result: dict[str, object] = {}


class RecurringWorkflowHealthOut(BaseModel):
    bug_log_scheduler: dict[str, object] = {}
    notification_dispatcher: dict[str, object] = {}
    recurring_registry: dict[str, object] = {}


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
