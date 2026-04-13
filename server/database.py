from __future__ import annotations

"""Database connection and table setup for Agentic Ops Dashboard."""
import logging
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

from server.config import (
    DATABASE_URL,
    DB_MAX_OVERFLOW,
    DB_POOL_PRE_PING,
    DB_POOL_RECYCLE,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    DB_SQLITE_BUSY_TIMEOUT,
    DB_SQLITE_JOURNAL_MODE,
    DB_SQLITE_SYNCHRONOUS,
)

logger = logging.getLogger("ops-dashboard.db")
_IS_SQLITE = DATABASE_URL.startswith("sqlite")
_IS_IN_MEMORY = ":memory:" in DATABASE_URL

_engine_kwargs = {
    "pool_pre_ping": DB_POOL_PRE_PING,
}
if _IS_SQLITE:
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": float(max(5, DB_SQLITE_BUSY_TIMEOUT)),
    }

if not _IS_IN_MEMORY:
    _engine_kwargs.update({
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT,
        "pool_recycle": DB_POOL_RECYCLE,
    })

engine = create_engine(DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_conn, _):
    if not _IS_SQLITE:
        return
    cursor = dbapi_conn.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        if not _IS_IN_MEMORY:
            try:
                cursor.execute(f"PRAGMA journal_mode={DB_SQLITE_JOURNAL_MODE}")
                cursor.fetchone()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to enforce SQLite journal_mode=%s: %s", DB_SQLITE_JOURNAL_MODE, exc)
        if DB_SQLITE_SYNCHRONOUS:
            try:
                cursor.execute(f"PRAGMA synchronous={DB_SQLITE_SYNCHRONOUS}")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to enforce SQLite synchronous=%s: %s", DB_SQLITE_SYNCHRONOUS, exc)
        busy_timeout_ms = max(1000, int(DB_SQLITE_BUSY_TIMEOUT * 1000))
        cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    finally:
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


# ── ORM Models ────────────────────────────────────────────────

class AgentRow(Base):
    __tablename__ = "agents"

    id = Column(Text, primary_key=True)
    display_name = Column(Text, nullable=False)
    goal = Column(Text, nullable=False)
    group = Column(Text, default="")  # content | growth | optimization
    persona_path = Column(Text)
    skills = Column(Text, default="[]")  # JSON array
    role_contract_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)

    tasks = relationship("TaskRow", back_populates="agent")
    workflow_steps = relationship("WorkflowStepRow", back_populates="agent")


class TaskRow(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description = Column(Text, nullable=False)
    agent_id = Column(Text, ForeignKey("agents.id"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    requires_approval = Column(Boolean, default=False)
    priority = Column(Text, default="normal")
    project_id = Column(Text, default="")
    agent_group = Column(Text, default="")
    skill_name = Column(Text)
    context_files = Column(Text)  # JSON array of relative paths
    retry_of_task_id = Column(Integer)
    attempt_no = Column(Integer, default=1)
    last_error_message = Column(Text)
    runtime_backend = Column(Text, default="")
    runtime_provider = Column(Text, default="")
    runtime_model = Column(Text, default="")
    runtime_session_id = Column(Text)
    runtime_selected_agent = Column(Text)
    runtime_event_cursor = Column(Integer, default=0)
    output_path = Column(Text)
    output_content = Column(Text)
    execution_time_ms = Column(Integer)
    tokens_used = Column(Integer, default=0)
    budget_cost_points = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    agent = relationship("AgentRow", back_populates="tasks")
    approvals = relationship("ApprovalRow", back_populates="task")
    logs = relationship("TaskLogRow", back_populates="task", order_by="TaskLogRow.created_at")
    workflow_steps = relationship("WorkflowStepRow", back_populates="compatibility_task")


class ApprovalRow(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    reviewer = Column(Text)
    comment = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    decided_at = Column(DateTime)

    task = relationship("TaskRow", back_populates="approvals")


class TaskLogRow(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    task = relationship("TaskRow", back_populates="logs")


class RequirementRow(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        Index("requirements_status_idx", "status"),
        Index("requirements_priority_idx", "priority"),
        Index("requirements_created_at_idx", "created_at"),
        Index("requirements_active_run_idx", "active_workflow_run_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    description_markdown = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")
    priority = Column(Text, nullable=False, default="normal")
    source = Column(Text, nullable=False, default="manual")
    source_ref = Column(Text)
    intake_metadata_json = Column(Text, nullable=False, default="{}")
    target_project_path = Column(Text)
    acceptance_contract_json = Column(Text, nullable=False, default="{}")
    approval_status = Column(Text, nullable=False, default="pending_approval")
    approval_contract_json = Column(Text, nullable=False, default="{}")
    approval_requested_at = Column(DateTime)
    approved_at = Column(DateTime)
    current_plan_version = Column(Integer, nullable=False, default=0)
    planned_roles_json = Column(Text, nullable=False, default="[]")
    blocked_by_count = Column(Integer, nullable=False, default=0)
    active_workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    workflow_runs = relationship(
        "WorkflowRunRow",
        back_populates="requirement",
        foreign_keys="WorkflowRunRow.requirement_id",
        order_by="WorkflowRunRow.id",
    )
    active_workflow_run = relationship("WorkflowRunRow", foreign_keys=[active_workflow_run_id], post_update=True)
    acceptance_checks = relationship(
        "RequirementAcceptanceCheckRow",
        back_populates="requirement",
        order_by="RequirementAcceptanceCheckRow.id",
    )
    artifacts = relationship("ArtifactRow", back_populates="requirement", order_by="ArtifactRow.id")
    attachments = relationship(
        "RequirementAttachmentRow",
        back_populates="requirement",
        order_by="RequirementAttachmentRow.id",
    )


class ProjectPolicyRow(Base):
    __tablename__ = "project_policies"
    __table_args__ = (
        Index("project_policies_project_key_idx", "project_key", unique=True),
        Index("project_policies_root_path_idx", "root_path", unique=True),
        Index("project_policies_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_key = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    root_path = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    allowed_write_globs_json = Column(Text, nullable=False, default="[]")
    forbidden_globs_json = Column(Text, nullable=False, default="[]")
    required_checks_json = Column(Text, nullable=False, default="[]")
    release_mode = Column(Text, nullable=False, default="manual")
    requires_manual_approval = Column(Boolean, nullable=False, default=True)
    autonomy_mode = Column(Text, nullable=False, default="recommend")
    allow_rebalance = Column(Boolean, nullable=False, default=True)
    allow_preemption = Column(Boolean, nullable=False, default=False)
    capability_matrix_json = Column(Text, nullable=False, default="{}")
    interrupt_policy_json = Column(Text, nullable=False, default="{}")
    scheduler_weight = Column(Float, nullable=False, default=1.0)
    max_parallel_requirements = Column(Integer, nullable=False, default=1)
    portfolio_budget_points = Column(Integer, nullable=False, default=100)
    deploy_repo_full_name = Column(Text)
    deploy_strategy = Column(Text, nullable=False, default="github_actions_ssh")
    deploy_trigger_enabled = Column(Boolean, nullable=False, default=False)
    staging_host_label = Column(Text)
    production_host_label = Column(Text)
    staging_workflow_file = Column(Text, nullable=False, default="deploy-staging.yml")
    production_workflow_file = Column(Text, nullable=False, default="deploy-production.yml")
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ProjectOnboardingRow(Base):
    __tablename__ = "project_onboardings"
    __table_args__ = (
        Index("project_onboardings_project_key_idx", "project_key"),
        Index("project_onboardings_root_path_idx", "root_path"),
        Index("project_onboardings_status_idx", "readiness_status"),
        Index("project_onboardings_policy_idx", "policy_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_key = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    root_path = Column(Text, nullable=False)
    docs_entrypoints_json = Column(Text, nullable=False, default="[]")
    validation_commands_json = Column(Text, nullable=False, default="[]")
    agents_memory_namespace = Column(Text)
    policy_id = Column(Integer, ForeignKey("project_policies.id"))
    readiness_status = Column(Text, nullable=False, default="needs_setup")
    readiness_score = Column(Integer, nullable=False, default=0)
    readiness_items_json = Column(Text, nullable=False, default="[]")
    missing_items_json = Column(Text, nullable=False, default="[]")
    notes = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    policy = relationship("ProjectPolicyRow")


class OptimizationSignalRow(Base):
    __tablename__ = "optimization_signals"
    __table_args__ = (
        Index("optimization_signals_dedupe_idx", "dedupe_key", unique=True),
        Index("optimization_signals_status_idx", "status"),
        Index("optimization_signals_project_idx", "project_key"),
        Index("optimization_signals_type_idx", "signal_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    dedupe_key = Column(Text, nullable=False)
    signal_type = Column(Text, nullable=False)
    source_kind = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="open")
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False, default="")
    severity = Column(Text, nullable=False, default="medium")
    confidence = Column(Float, nullable=False, default=0.5)
    project_key = Column(Text)
    project_root_path = Column(Text)
    routing_target_path = Column(Text)
    evidence_json = Column(Text, nullable=False, default="[]")
    occurrence_count = Column(Integer, nullable=False, default=1)
    latest_evidence_at = Column(DateTime)
    converted_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    converted_requirement = relationship("RequirementRow")


class BugRecordRow(Base):
    __tablename__ = "bug_records"
    __table_args__ = (
        Index("bug_records_bug_key_idx", "bug_key", unique=True),
        Index("bug_records_status_idx", "status"),
        Index("bug_records_project_idx", "project_key"),
        Index("bug_records_severity_idx", "severity"),
        Index("bug_records_source_idx", "source_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bug_key = Column(Text, nullable=False)
    source_key = Column(Text, nullable=False)
    source_kind = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="open")
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False, default="")
    severity = Column(Text, nullable=False, default="normal")
    fingerprint = Column(Text, nullable=False)
    project_key = Column(Text)
    project_root_path = Column(Text)
    source_ref = Column(Text)
    environment = Column(Text)
    occurrence_count = Column(Integer, nullable=False, default=1)
    evidence_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")
    scorecard_json = Column(Text, nullable=False, default="{}")
    converted_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    first_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    converted_requirement = relationship("RequirementRow")


class CompanyOperatingReviewRow(Base):
    __tablename__ = "company_operating_reviews"
    __table_args__ = (
        Index("company_operating_reviews_cycle_idx", "cycle_label"),
        Index("company_operating_reviews_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_label = Column(Text, nullable=False)
    title = Column(Text, nullable=False, default="Company Operating Review")
    summary_markdown = Column(Text, nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class RecurringWorkflowRow(Base):
    __tablename__ = "recurring_workflows"
    __table_args__ = (
        Index("recurring_workflows_key_idx", "workflow_key", unique=True),
        Index("recurring_workflows_status_idx", "status"),
        Index("recurring_workflows_trigger_idx", "trigger_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_key = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    description = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="active")
    trigger_type = Column(Text, nullable=False, default="scheduled")
    owner_role = Column(Text, nullable=False, default="portfolio_operator")
    schedule_json = Column(Text, nullable=False, default="{}")
    input_query_json = Column(Text, nullable=False, default="{}")
    output_action_json = Column(Text, nullable=False, default="{}")
    escalation_rule_json = Column(Text, nullable=False, default="{}")
    validation_signal_json = Column(Text, nullable=False, default="{}")
    is_builtin = Column(Boolean, nullable=False, default=True)
    last_run_at = Column(DateTime)
    last_result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class CodexSessionRow(Base):
    __tablename__ = "codex_sessions"
    __table_args__ = (
        Index("codex_sessions_session_key_idx", "session_key", unique=True),
        Index("codex_sessions_thread_id_idx", "thread_id"),
        Index("codex_sessions_scope_idx", "role_key", "project_root", "requirement_id"),
        Index("codex_sessions_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_key = Column(Text, nullable=False)
    role_key = Column(Text, nullable=False)
    project_root = Column(Text, nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id"))
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    current_task_id = Column(Integer, ForeignKey("tasks.id"))
    thread_id = Column(Text)
    status = Column(Text, nullable=False, default="active")
    last_used_at = Column(DateTime, nullable=False, default=utcnow)
    last_heartbeat_at = Column(DateTime)
    resume_count = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class DeploymentRecordRow(Base):
    __tablename__ = "deployment_records"
    __table_args__ = (
        Index("deployment_records_requirement_idx", "requirement_id"),
        Index("deployment_records_project_env_idx", "project_key", "environment"),
        Index("deployment_records_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    project_policy_id = Column(Integer, ForeignKey("project_policies.id"))
    project_key = Column(Text, nullable=False)
    environment = Column(Text, nullable=False)
    action = Column(Text, nullable=False, default="deploy")
    status = Column(Text, nullable=False, default="requested")
    commit_sha = Column(Text)
    branch_name = Column(Text)
    workflow_file = Column(Text)
    external_run_id = Column(Text)
    external_url = Column(Text)
    actor = Column(Text)
    trigger_source = Column(Text, nullable=False, default="ops_console")
    rollback_target_sha = Column(Text)
    health_status = Column(Text)
    notes = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    started_at = Column(DateTime, nullable=False, default=utcnow)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requirement = relationship("RequirementRow")
    project_policy = relationship("ProjectPolicyRow")


class RequirementDependencyRow(Base):
    __tablename__ = "requirement_dependencies"
    __table_args__ = (
        Index("req_dep_requirement_idx", "requirement_id"),
        Index("req_dep_depends_on_idx", "depends_on_requirement_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    depends_on_requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    dependency_type = Column(Text, nullable=False, default="hard_block")
    created_at = Column(DateTime, nullable=False, default=utcnow)


class WorkflowRunRow(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("workflow_runs_requirement_idx", "requirement_id"),
        Index("workflow_runs_status_idx", "status"),
        Index("workflow_runs_plan_version_idx", "requirement_id", "plan_version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    plan_version = Column(Integer, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    triggered_by = Column(Text, nullable=False, default="system")
    planner_artifact_id = Column(Integer, ForeignKey("artifacts.id"))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requirement = relationship("RequirementRow", back_populates="workflow_runs", foreign_keys=[requirement_id])
    steps = relationship("WorkflowStepRow", back_populates="workflow_run", order_by="WorkflowStepRow.sequence_no")


class WorkflowStepRow(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (
        Index("workflow_steps_run_idx", "workflow_run_id"),
        Index("workflow_steps_requirement_idx", "requirement_id"),
        Index("workflow_steps_status_idx", "status"),
        Index("workflow_steps_assigned_agent_idx", "assigned_agent_id"),
        Index("workflow_steps_compat_task_idx", "compatibility_task_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    step_key = Column(Text, nullable=False)
    step_type = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    sequence_no = Column(Integer, nullable=False, default=0)
    assigned_agent_id = Column(Text, ForeignKey("agents.id"))
    assigned_workflow_role = Column(Text)
    branch_from_step_id = Column(Integer, ForeignKey("workflow_steps.id"))
    context_scope = Column(Text, nullable=False, default="step_private")
    handoff_summary_markdown = Column(Text)
    done_when_markdown = Column(Text, nullable=False, default="")
    context_policy_json = Column(Text, nullable=False, default="{}")
    execution_profile_json = Column(Text, nullable=False, default="{}")
    file_scope_json = Column(Text, nullable=False, default="{}")
    validation_targets_json = Column(Text, nullable=False, default="[]")
    failure_policy_json = Column(Text, nullable=False, default="{}")
    approval_policy_json = Column(Text, nullable=False, default="{}")
    runtime_backend = Column(Text, nullable=False, default="")
    runtime_session_id = Column(Text)
    compatibility_task_id = Column(Integer, ForeignKey("tasks.id"))
    retry_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    workflow_run = relationship("WorkflowRunRow", back_populates="steps")
    requirement = relationship("RequirementRow")
    agent = relationship("AgentRow", back_populates="workflow_steps")
    compatibility_task = relationship("TaskRow", back_populates="workflow_steps")
    branch_from_step = relationship("WorkflowStepRow", remote_side=[id])
    input_bindings = relationship("StepInputBindingRow", back_populates="step", order_by="StepInputBindingRow.id")
    produced_artifacts = relationship("ArtifactRow", back_populates="step", foreign_keys="ArtifactRow.step_id")


class WorkflowStepDependencyRow(Base):
    __tablename__ = "workflow_step_dependencies"
    __table_args__ = (
        Index("step_deps_step_idx", "step_id"),
        Index("step_deps_depends_on_idx", "depends_on_step_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=False)
    depends_on_step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=False)
    dependency_kind = Column(Text, nullable=False)
    required_artifact_types_json = Column(Text, nullable=False, default="[]")
    is_blocking = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("artifacts_requirement_idx", "requirement_id"),
        Index("artifacts_run_idx", "workflow_run_id"),
        Index("artifacts_step_idx", "step_id"),
        Index("artifacts_type_idx", "artifact_type"),
        Index("artifacts_producer_step_idx", "producer_step_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    step_id = Column(Integer, ForeignKey("workflow_steps.id"))
    producer_step_id = Column(Integer, ForeignKey("workflow_steps.id"))
    artifact_type = Column(Text, nullable=False)
    path = Column(Text)
    content_summary = Column(Text)
    human_readable_body = Column(Text)
    machine_readable_payload = Column(Text)
    checksum = Column(Text)
    snapshot_version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Text, nullable=False, default="1.0")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    requirement = relationship("RequirementRow", back_populates="artifacts")
    step = relationship("WorkflowStepRow", back_populates="produced_artifacts", foreign_keys=[step_id])


class StepInputBindingRow(Base):
    __tablename__ = "step_input_bindings"
    __table_args__ = (
        Index("step_input_bindings_step_idx", "step_id"),
        Index("step_input_bindings_artifact_idx", "artifact_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=False)
    artifact_id = Column(Integer, ForeignKey("artifacts.id"), nullable=False)
    purpose = Column(Text, nullable=False)
    is_required = Column(Boolean, nullable=False, default=True)
    consumed_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    step = relationship("WorkflowStepRow", back_populates="input_bindings")
    artifact = relationship("ArtifactRow")


class RequirementAcceptanceCheckRow(Base):
    __tablename__ = "requirement_acceptance_checks"
    __table_args__ = (
        Index("req_checks_requirement_idx", "requirement_id"),
        Index("req_checks_status_idx", "status"),
        Index("req_checks_owner_role_idx", "owner_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    check_key = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    check_type = Column(Text, nullable=False)
    owner_role = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    success_criteria_markdown = Column(Text)
    verified_by_step_id = Column(Integer, ForeignKey("workflow_steps.id"))
    evidence_artifact_id = Column(Integer, ForeignKey("artifacts.id"))
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requirement = relationship("RequirementRow", back_populates="acceptance_checks")


class RequirementAttachmentRow(Base):
    __tablename__ = "requirement_attachments"
    __table_args__ = (
        Index("requirement_attachments_requirement_idx", "requirement_id"),
        Index("requirement_attachments_kind_idx", "attachment_kind"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    file_name = Column(Text, nullable=False)
    stored_path = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False, default="application/octet-stream")
    attachment_kind = Column(Text, nullable=False, default="file")
    source = Column(Text, nullable=False, default="upload")
    size_bytes = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    requirement = relationship("RequirementRow", back_populates="attachments")


class ApprovalRequestRow(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("approval_requests_requirement_idx", "requirement_id"),
        Index("approval_requests_step_idx", "step_id"),
        Index("approval_requests_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"))
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    step_id = Column(Integer, ForeignKey("workflow_steps.id"))
    approval_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    reviewer = Column(Text)
    comment = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    decided_at = Column(DateTime)


class WorkflowStepEventRow(Base):
    __tablename__ = "workflow_step_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_id = Column(Integer, ForeignKey("workflow_steps.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)


# ── Init ──────────────────────────────────────────────────────

def _migrate(engine_):
    """Add missing columns to existing tables (lightweight migration)."""
    insp = inspect(engine_)
    tables = insp.get_table_names()

    if "agents" in tables:
        existing = {c["name"] for c in insp.get_columns("agents")}
        if "group" not in existing:
            logger.info("Migrating: adding 'group' column to agents table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE agents ADD COLUMN \"group\" TEXT DEFAULT ''"))
                conn.commit()
        if "role_contract_json" not in existing:
            logger.info("Migrating: adding 'role_contract_json' column to agents table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE agents ADD COLUMN role_contract_json TEXT DEFAULT '{}'"))
                conn.commit()

    if "requirements" in tables:
        existing = {c["name"] for c in insp.get_columns("requirements")}
        if "intake_metadata_json" not in existing:
            logger.info("Migrating: adding 'intake_metadata_json' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN intake_metadata_json TEXT DEFAULT '{}'"))
                conn.commit()
        if "target_project_path" not in existing:
            logger.info("Migrating: adding 'target_project_path' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN target_project_path TEXT"))
                conn.commit()
        if "acceptance_contract_json" not in existing:
            logger.info("Migrating: adding 'acceptance_contract_json' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN acceptance_contract_json TEXT DEFAULT '{}'"))
                conn.commit()
        if "approval_status" not in existing:
            logger.info("Migrating: adding 'approval_status' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN approval_status TEXT DEFAULT 'pending_approval'"))
                conn.commit()
        if "approval_contract_json" not in existing:
            logger.info("Migrating: adding 'approval_contract_json' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN approval_contract_json TEXT DEFAULT '{}'"))
                conn.commit()
        if "approval_requested_at" not in existing:
            logger.info("Migrating: adding 'approval_requested_at' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN approval_requested_at DATETIME"))
                conn.commit()
        if "approved_at" not in existing:
            logger.info("Migrating: adding 'approved_at' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN approved_at DATETIME"))
                conn.commit()

    if "recurring_workflows" not in tables:
        logger.info("Migrating: creating 'recurring_workflows' table")
        RecurringWorkflowRow.__table__.create(bind=engine_, checkfirst=True)

    if "project_policies" in tables:
        existing = {c["name"] for c in insp.get_columns("project_policies")}
        project_policy_cols = {
            "autonomy_mode": "TEXT DEFAULT 'recommend'",
            "allow_rebalance": "BOOLEAN DEFAULT 1",
            "allow_preemption": "BOOLEAN DEFAULT 0",
            "capability_matrix_json": "TEXT DEFAULT '{}'",
            "interrupt_policy_json": "TEXT DEFAULT '{}'",
            "scheduler_weight": "FLOAT DEFAULT 1.0",
            "max_parallel_requirements": "INTEGER DEFAULT 1",
            "portfolio_budget_points": "INTEGER DEFAULT 100",
            "deploy_repo_full_name": "TEXT",
            "deploy_strategy": "TEXT DEFAULT 'github_actions_ssh'",
            "deploy_trigger_enabled": "BOOLEAN DEFAULT 0",
            "staging_host_label": "TEXT",
            "production_host_label": "TEXT",
            "staging_workflow_file": "TEXT DEFAULT 'deploy-staging.yml'",
            "production_workflow_file": "TEXT DEFAULT 'deploy-production.yml'",
        }
        for col, col_type in project_policy_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to project_policies table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE project_policies ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "workflow_steps" in tables:
        existing = {c["name"] for c in insp.get_columns("workflow_steps")}
        workflow_step_cols = {
            "compatibility_task_id": "INTEGER",
            "context_policy_json": "TEXT DEFAULT '{}'",
            "execution_profile_json": "TEXT DEFAULT '{}'",
        }
        for col, col_type in workflow_step_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to workflow_steps table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE workflow_steps ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "company_operating_reviews" not in tables:
        logger.info("Migrating: company_operating_reviews table will be created via metadata")

    if "bug_records" not in tables:
        logger.info("Migrating: creating 'bug_records' table")
        BugRecordRow.__table__.create(bind=engine_, checkfirst=True)
    else:
        existing = {c["name"] for c in insp.get_columns("bug_records")}
        if "scorecard_json" not in existing:
            logger.info("Migrating: adding 'scorecard_json' column to bug_records table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE bug_records ADD COLUMN scorecard_json TEXT DEFAULT '{}'"))
                conn.commit()

    if "codex_sessions" not in tables:
        logger.info("Migrating: creating 'codex_sessions' table")
        CodexSessionRow.__table__.create(bind=engine_, checkfirst=True)

    if "deployment_records" not in tables:
        logger.info("Migrating: creating 'deployment_records' table")
        DeploymentRecordRow.__table__.create(bind=engine_, checkfirst=True)

    if "tasks" in tables:
        existing = {c["name"] for c in insp.get_columns("tasks")}
        new_cols = {
            "project_id": "TEXT DEFAULT ''",
            "agent_group": "TEXT DEFAULT ''",
            "skill_name": "TEXT",
            "context_files": "TEXT",
            "execution_time_ms": "INTEGER",
            "tokens_used": "INTEGER DEFAULT 0",
            "budget_cost_points": "INTEGER DEFAULT 0",
            "retry_of_task_id": "INTEGER",
            "attempt_no": "INTEGER DEFAULT 1",
            "last_error_message": "TEXT",
            "runtime_backend": "TEXT DEFAULT ''",
            "runtime_provider": "TEXT DEFAULT ''",
            "runtime_model": "TEXT DEFAULT ''",
            "runtime_session_id": "TEXT",
            "runtime_selected_agent": "TEXT",
            "runtime_event_cursor": "INTEGER DEFAULT 0",
        }
        for col, col_type in new_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to tasks table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}"))
                    conn.commit()

        if "project_id" in {c["name"] for c in insp.get_columns("tasks")} and "agent_group" in {c["name"] for c in insp.get_columns("tasks")}:
            from server.services.task_metadata import project_for_group

            with engine_.connect() as conn:
                rows = conn.execute(text(
                    "SELECT tasks.id, COALESCE(tasks.project_id, ''), COALESCE(tasks.agent_group, ''), COALESCE(agents.\"group\", '') "
                    "FROM tasks LEFT JOIN agents ON agents.id = tasks.agent_id"
                )).fetchall()
                for task_id, project_id, agent_group, current_group in rows:
                    next_group = agent_group or current_group or ""
                    next_project = project_id or project_for_group(next_group)
                    if next_group != agent_group or next_project != project_id:
                        conn.execute(
                            text("UPDATE tasks SET agent_group = :agent_group, project_id = :project_id WHERE id = :task_id"),
                            {"agent_group": next_group, "project_id": next_project, "task_id": task_id},
                        )
                conn.commit()

    if "requirement_attachments" not in tables:
        logger.info("Migrating: creating 'requirement_attachments' table")
        RequirementAttachmentRow.__table__.create(bind=engine_, checkfirst=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    from server.services.project_policy import ensure_default_project_policies

    db = SessionLocal()
    try:
        ensure_default_project_policies(db)
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
