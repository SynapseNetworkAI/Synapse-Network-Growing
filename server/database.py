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
    UniqueConstraint,
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

from server.database_social_budget import migrate_social_x_read_budget
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


def _rebuild_sqlite_deployment_records_with_nullable_requirement(engine_) -> None:  # pragma: no cover
    """SQLite cannot drop a NOT NULL constraint in place."""
    if not _IS_SQLITE:
        return
    columns = [column.name for column in DeploymentRecordRow.__table__.columns]
    column_sql = ", ".join(columns)
    with engine_.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.commit()
        conn.execute(text("ALTER TABLE deployment_records RENAME TO deployment_records_old"))
        conn.commit()
        DeploymentRecordRow.__table__.create(bind=conn, checkfirst=True)
        conn.execute(text(f"INSERT INTO deployment_records ({column_sql}) SELECT {column_sql} FROM deployment_records_old"))
        conn.execute(text("DROP TABLE deployment_records_old"))
        conn.commit()
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()


def _rebuild_sqlite_release_tasks_with_current_fks(engine_) -> None:  # pragma: no cover
    """Repair release_tasks FKs after SQLite table rebuilds rename referenced tables."""
    if not _IS_SQLITE:
        return
    columns = [column.name for column in ReleaseTaskRow.__table__.columns]
    column_sql = ", ".join(columns)
    with engine_.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        conn.commit()
        conn.execute(text("ALTER TABLE release_tasks RENAME TO release_tasks_old"))
        conn.commit()
        ReleaseTaskRow.__table__.create(bind=conn, checkfirst=True)
        conn.execute(text(f"INSERT INTO release_tasks ({column_sql}) SELECT {column_sql} FROM release_tasks_old"))
        conn.execute(text("DROP TABLE release_tasks_old"))
        conn.commit()
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()


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


class RequirementRow(Base):
    __tablename__ = "requirements"
    __table_args__ = (
        Index("requirements_status_idx", "status"),
        Index("requirements_priority_idx", "priority"),
        Index("requirements_created_at_idx", "created_at"),
        Index("requirements_active_run_idx", "active_workflow_run_id"),
        Index("requirements_planning_goal_idx", "operating_manifest_id", "goal_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    description_markdown = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")
    priority = Column(Text, nullable=False, default="normal")
    source = Column(Text, nullable=False, default="manual")
    source_ref = Column(Text)
    intake_metadata_json = Column(Text, nullable=False, default="{}")
    operating_manifest_id = Column(Integer, ForeignKey("operating_manifests.id"))
    goal_key = Column(Text)
    requirement_candidate_id = Column(Integer, ForeignKey("requirement_candidates.id"))
    project_id = Column(Integer, ForeignKey("projects.id"))
    project_key = Column(Text)
    project_display_name = Column(Text)
    target_project_path = Column(Text)
    target_project_path_override = Column(Text)
    acceptance_contract_json = Column(Text, nullable=False, default="{}")
    execution_plan_json = Column(Text, nullable=False, default="{}")
    assets_status = Column(Text, nullable=False, default="pending")
    assets_error_message = Column(Text)
    workflow_family = Column(Text, nullable=False, default="declarative_state_machine")
    phase = Column(Text, nullable=False, default="draft")
    workflow_state = Column(Text, nullable=False, default="draft")
    attention_reason = Column(Text)
    failure_reason = Column(Text)
    recovery_status = Column(Text)
    linked_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    followup_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    origin_validation_id = Column(Integer, ForeignKey("validation_records.id"))
    resolution_path = Column(Text)
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
    project = relationship("ProjectRow")
    acceptance_checks = relationship(
        "RequirementAcceptanceCheckRow",
        back_populates="requirement",
        order_by="RequirementAcceptanceCheckRow.id",
    )
    attachments = relationship(
        "RequirementAttachmentRow",
        back_populates="requirement",
        order_by="RequirementAttachmentRow.id",
    )
    operating_manifest = relationship("OperatingManifestRow", foreign_keys=[operating_manifest_id])
    requirement_candidate = relationship("RequirementCandidateRow", foreign_keys=[requirement_candidate_id])


class ProjectPolicyRow(Base):
    __tablename__ = "project_policies"
    __table_args__ = (
        Index("project_policies_project_key_idx", "project_key", unique=True),
        Index("project_policies_root_path_idx", "root_path", unique=True),
        Index("project_policies_project_idx", "project_id"),
        Index("project_policies_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
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

    project = relationship("ProjectRow")


class ProjectRow(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("projects_project_key_idx", "project_key", unique=True),
        Index("projects_root_path_idx", "root_path", unique=True),
        Index("projects_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_key = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    root_path = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    repo_full_name = Column(Text)
    default_branch = Column(Text, nullable=False, default="main")
    deploy_repo_full_name = Column(Text)
    deploy_strategy = Column(Text, nullable=False, default="disabled")
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
    discovery_status = Column(Text, nullable=False, default="pending")
    discovery_recommendation_json = Column(Text, nullable=False, default="{}")
    last_discovery_at = Column(DateTime)
    first_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    converted_requirement = relationship("RequirementRow")


class RequirementIntakeFingerprintRow(Base):
    __tablename__ = "requirement_intake_fingerprints"
    __table_args__ = (
        Index("requirement_intake_fingerprints_source_idx", "source_kind", "source_key"),
        Index("requirement_intake_fingerprints_status_idx", "status"),
        Index("requirement_intake_fingerprints_project_idx", "project_key"),
        Index("requirement_intake_fingerprints_last_seen_idx", "last_seen_at"),
    )

    fingerprint_key = Column(Text, primary_key=True)
    source_kind = Column(Text, nullable=False)
    source_key = Column(Text, nullable=False, default="")
    project_key = Column(Text)
    project_root_path = Column(Text)
    status = Column(Text, nullable=False, default="open")
    linked_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    linked_workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    linked_release_id = Column(Integer, ForeignKey("release_records.id"))
    first_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_materialized_at = Column(DateTime)
    resolved_at = Column(DateTime)
    cooldown_until = Column(DateTime)
    occurrence_count = Column(Integer, nullable=False, default=0)
    suppressed_count = Column(Integer, nullable=False, default=0)
    latest_evidence_json = Column(Text, nullable=False, default="{}")
    resolution_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    linked_requirement = relationship("RequirementRow")
    linked_workflow_run = relationship("WorkflowRunRow")
    linked_release = relationship("ReleaseRecordRow")


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
class RecurringWorkflowRunRow(Base):
    __tablename__ = "recurring_workflow_runs"
    __table_args__ = (
        Index("recurring_workflow_runs_workflow_idx", "workflow_key"),
        Index("recurring_workflow_runs_status_idx", "status"),
        Index("recurring_workflow_runs_started_idx", "started_at"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_key = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="running")
    triggered_by = Column(Text, nullable=False, default="operator")
    dry_run = Column(Boolean, nullable=False, default=False)
    params_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=False, default="{}")
    error_excerpt = Column(Text)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime)
    duration_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
class SchedulerLockRow(Base):
    __tablename__ = "scheduler_locks"
    __table_args__ = (
        Index("scheduler_locks_status_idx", "status"),
        Index("scheduler_locks_expires_idx", "expires_at"),
    )
    lock_key = Column(Text, primary_key=True)
    owner_id = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="held")
    acquired_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    heartbeat_at = Column(DateTime)
    metadata_json = Column(Text, nullable=False, default="{}")
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
    current_task_id = Column(Integer)
    thread_id = Column(Text)
    status = Column(Text, nullable=False, default="active")
    workspace_trust_state = Column(Text, nullable=False, default="clean")
    requires_workspace_recovery = Column(Boolean, nullable=False, default=False)
    killed_at = Column(DateTime)
    kill_signal = Column(Text)
    trusted_checkpoint_json = Column(Text, nullable=False, default="{}")
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
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=True)
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

class ReleaseTaskRow(Base):
    __tablename__ = "release_tasks"
    __table_args__ = (
        Index("release_tasks_requirement_idx", "requirement_id"),
        Index("release_tasks_deployment_record_idx", "deployment_record_id"),
        Index("release_tasks_project_env_idx", "project_key", "environment"),
        Index("release_tasks_status_idx", "status"),
        Index("release_tasks_source_idx", "source_type"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(Text, nullable=False, default="manual")
    requirement_id = Column(Integer, ForeignKey("requirements.id"))
    deployment_record_id = Column(Integer, ForeignKey("deployment_records.id"))
    project_key = Column(Text, nullable=False)
    project_display_name = Column(Text)
    service_key = Column(Text)
    branch_name = Column(Text, nullable=False)
    environment = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="requested")
    actor = Column(Text)
    operator = Column(Text)
    note = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    requirement = relationship("RequirementRow")
    deployment_record = relationship("DeploymentRecordRow")
class SocialAccountRow(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "handle", name="social_accounts_platform_handle_uq"),
        Index("social_accounts_platform_idx", "platform"),
        Index("social_accounts_status_idx", "status"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    handle = Column(Text, nullable=False)
    display_name = Column(Text)
    secret_ref = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
class SocialOAuthSessionRow(Base):
    __tablename__ = "social_oauth_sessions"
    __table_args__ = (
        Index("social_oauth_sessions_state_idx", "state", unique=True),
        Index("social_oauth_sessions_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    account_id = Column(Integer, ForeignKey("social_accounts.id"), nullable=True)
    state = Column(Text, nullable=False)
    code_verifier = Column(Text, nullable=False)
    redirect_uri = Column(Text, nullable=False)
    scope = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="pending")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    expires_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)

    account = relationship("SocialAccountRow")


class SocialPostDraftRow(Base):
    __tablename__ = "social_post_drafts"
    __table_args__ = (
        Index("social_post_drafts_status_idx", "status"),
        Index("social_post_drafts_platform_idx", "platform"),
        Index("social_post_drafts_account_idx", "account_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    account_id = Column(Integer, ForeignKey("social_accounts.id"), nullable=False)
    source_type = Column(Text, nullable=False, default="manual_prompt")
    title = Column(Text)
    body_text = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="needs_review")
    generated_by = Column(Text, nullable=False, default="operator")
    reviewed_by = Column(Text)
    review_note = Column(Text)
    target_audience = Column(Text)
    cta = Column(Text)
    agent_rationale = Column(Text)
    policy_check_json = Column(Text, nullable=False, default="{}")
    raw_agent_output_json = Column(Text, nullable=False, default="{}")
    published_at = Column(DateTime)
    external_post_id = Column(Text)
    failure_summary = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    account = relationship("SocialAccountRow")
    events = relationship("SocialPublishEventRow", order_by="SocialPublishEventRow.id", back_populates="post")
    media_assets = relationship("SocialPostMediaAssetRow", order_by="SocialPostMediaAssetRow.id", back_populates="post")


class SocialPostMediaAssetRow(Base):
    __tablename__ = "social_post_media_assets"
    __table_args__ = (
        Index("social_post_media_assets_post_idx", "post_id"),
        Index("social_post_media_assets_status_idx", "status"),
        Index("social_post_media_assets_type_idx", "media_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("social_post_drafts.id"), nullable=False)
    media_type = Column(Text, nullable=False, default="image")
    status = Column(Text, nullable=False, default="generating")
    prompt = Column(Text)
    alt_text = Column(Text)
    local_path = Column(Text)
    preview_url = Column(Text)
    x_media_id = Column(Text)
    failure_summary = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    post = relationship("SocialPostDraftRow", back_populates="media_assets")


class SocialPublishEventRow(Base):
    __tablename__ = "social_publish_events"
    __table_args__ = (
        Index("social_publish_events_post_idx", "post_id"),
        Index("social_publish_events_type_idx", "event_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("social_post_drafts.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    actor = Column(Text, nullable=False, default="operator")
    summary = Column(Text)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    post = relationship("SocialPostDraftRow", back_populates="events")


class SocialCampaignGoalRow(Base):
    __tablename__ = "social_campaign_goals"
    __table_args__ = (
        Index("social_campaign_goals_status_idx", "status"),
        Index("social_campaign_goals_platform_idx", "platform"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    title = Column(Text, nullable=False)
    objective = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="active")
    cadence = Column(Text, nullable=False, default="daily")
    content_pillars_json = Column(Text, nullable=False, default="[]")
    success_metrics_json = Column(Text, nullable=False, default="[]")
    created_by = Column(Text, nullable=False, default="operator")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SocialTrendItemRow(Base):
    __tablename__ = "social_trend_items"
    __table_args__ = (
        Index("social_trend_items_status_idx", "status"),
        Index("social_trend_items_topic_idx", "topic"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_platform = Column(Text, nullable=False, default="x")
    source_url = Column(Text)
    author_handle = Column(Text)
    topic = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    relevance_score = Column(Float, nullable=False, default=0.0)
    status = Column(Text, nullable=False, default="new")
    collected_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SocialWatchlistAccountRow(Base):
    __tablename__ = "social_watchlist_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "handle", name="social_watchlist_platform_handle_uq"),
        Index("social_watchlist_status_idx", "status"),
        Index("social_watchlist_category_idx", "category"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    handle = Column(Text, nullable=False)
    x_user_id = Column(Text)
    display_name = Column(Text)
    category = Column(Text, nullable=False, default="ai_agent_builder")
    rationale = Column(Text)
    status = Column(Text, nullable=False, default="active")
    last_checked_at = Column(DateTime)
    latest_summary = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SocialReplyItemRow(Base):
    __tablename__ = "social_reply_items"
    __table_args__ = (
        UniqueConstraint("platform", "external_reply_id", name="social_reply_platform_external_uq"),
        Index("social_reply_items_status_idx", "status"),
        Index("social_reply_items_intent_idx", "intent"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    external_reply_id = Column(Text, nullable=False)
    source_candidate_id = Column(Integer)
    source_post_id = Column(Text)
    source_author_handle = Column(Text)
    source_text = Column(Text)
    author_handle = Column(Text)
    incoming_text = Column(Text, nullable=False)
    intent = Column(Text, nullable=False, default="unknown")
    suggested_reply = Column(Text)
    generation_reason = Column(Text)
    risk_level = Column(Text, nullable=False, default="normal")
    status = Column(Text, nullable=False, default="needs_review")
    source_url = Column(Text)
    published_external_post_id = Column(Text)
    reviewed_by = Column(Text)
    failure_summary = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SocialRepostCandidateRow(Base):
    __tablename__ = "social_repost_candidates"
    __table_args__ = (
        Index("social_repost_candidates_status_idx", "status"),
        Index("social_repost_candidates_score_idx", "relevance_score"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(Text, nullable=False, default="x")
    source_url = Column(Text)
    author_handle = Column(Text)
    source_text = Column(Text, nullable=False)
    suggested_quote = Column(Text)
    relevance_score = Column(Float, nullable=False, default=0.0)
    status = Column(Text, nullable=False, default="candidate")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SocialPostMetricRow(Base):
    __tablename__ = "social_post_metrics"
    __table_args__ = (
        Index("social_post_metrics_post_idx", "post_id"),
        Index("social_post_metrics_external_post_idx", "external_post_id"),
        Index("social_post_metrics_observed_idx", "observed_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("social_post_drafts.id"))
    external_post_id = Column(Text)
    impressions = Column(Integer, nullable=False, default=0)
    likes = Column(Integer, nullable=False, default=0)
    replies = Column(Integer, nullable=False, default=0)
    reposts = Column(Integer, nullable=False, default=0)
    follows = Column(Integer, nullable=False, default=0)
    link_clicks = Column(Integer, nullable=False, default=0)
    summary = Column(Text)
    observed_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)

import server.database_deployments, server.database_scheduled_jobs, server.database_social_distribution  # noqa: E402,F401


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
        Index("workflow_runs_workflow_key_idx", "workflow_key"),
        Index("workflow_runs_current_state_idx", "current_state"),
        Index("workflow_runs_planning_goal_idx", "operating_manifest_id", "goal_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    operating_manifest_id = Column(Integer, ForeignKey("operating_manifests.id"))
    goal_key = Column(Text)
    plan_version = Column(Integer, nullable=False, default=1)
    workflow_key = Column(Text, nullable=False, default="declarative_workflow")
    current_state = Column(Text, nullable=False, default="queued")
    resolution = Column(Text)
    risk_level = Column(Text, nullable=False, default="normal")
    retry_counters_json = Column(Text, nullable=False, default="{}")
    blackboard_json = Column(Text, nullable=False, default="{}")
    status = Column(Text, nullable=False, default="pending")
    triggered_by = Column(Text, nullable=False, default="system")
    planner_artifact_id = Column(Integer)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    archived_at = Column(DateTime)
    archived_by = Column(Text)
    archive_reason = Column(Text)
    delivery_pr_url = Column(Text)
    delivery_compare_url = Column(Text)
    delivery_branch = Column(Text)
    delivery_base_branch = Column(Text)
    delivery_status = Column(Text)
    delivery_is_simulated = Column(Boolean, nullable=False, default=False)
    delivery_synced_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requirement = relationship("RequirementRow", back_populates="workflow_runs", foreign_keys=[requirement_id])
    operating_manifest = relationship("OperatingManifestRow", foreign_keys=[operating_manifest_id])
    state_events = relationship("WorkflowStateEventRow", back_populates="workflow_run", order_by="WorkflowStateEventRow.id")
    workflow_artifacts = relationship("WorkflowArtifactRow", back_populates="workflow_run", order_by="WorkflowArtifactRow.id")
    blackboard_snapshots = relationship("BlackboardSnapshotRow", back_populates="workflow_run", order_by="BlackboardSnapshotRow.id")
    atom_invocations = relationship("AtomInvocationRow", back_populates="workflow_run", order_by="AtomInvocationRow.id")
    human_gate_requests = relationship("HumanGateRequestRow", back_populates="workflow_run", order_by="HumanGateRequestRow.id")


class WorkflowDefinitionRow(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        Index("workflow_definitions_key_idx", "workflow_key", unique=True),
        Index("workflow_definitions_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_key = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    title = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="draft")
    spec_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class WorkflowStateEventRow(Base):
    __tablename__ = "workflow_state_events"
    __table_args__ = (
        Index("workflow_state_events_run_idx", "workflow_run_id"),
        Index("workflow_state_events_state_idx", "to_state"),
        Index("workflow_state_events_type_idx", "event_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    event_type = Column(Text, nullable=False, default="transition")
    from_state = Column(Text)
    to_state = Column(Text, nullable=False)
    condition = Column(Text)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    workflow_run = relationship("WorkflowRunRow", back_populates="state_events")


class WorkflowArtifactRow(Base):
    __tablename__ = "workflow_artifacts"
    __table_args__ = (
        Index("workflow_artifacts_run_idx", "workflow_run_id"),
        Index("workflow_artifacts_type_idx", "artifact_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    artifact_type = Column(Text, nullable=False)
    state_key = Column(Text)
    atom_key = Column(Text)
    path = Column(Text)
    content_summary = Column(Text, nullable=False, default="")
    human_readable_body = Column(Text, nullable=False, default="")
    machine_readable_payload = Column(Text, nullable=False, default="{}")
    checksum = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    workflow_run = relationship("WorkflowRunRow", back_populates="workflow_artifacts")


class BlackboardSnapshotRow(Base):
    __tablename__ = "blackboard_snapshots"
    __table_args__ = (
        Index("blackboard_snapshots_run_idx", "workflow_run_id"),
        Index("blackboard_snapshots_state_idx", "state_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    state_key = Column(Text, nullable=False)
    snapshot_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    workflow_run = relationship("WorkflowRunRow", back_populates="blackboard_snapshots")


class AtomInvocationRow(Base):
    __tablename__ = "atom_invocations"
    __table_args__ = (
        Index("atom_invocations_run_idx", "workflow_run_id"),
        Index("atom_invocations_atom_idx", "atom_key"),
        Index("atom_invocations_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    state_key = Column(Text, nullable=False)
    atom_key = Column(Text, nullable=False)
    atom_type = Column(Text, nullable=False, default="deterministic")
    output_schema = Column(Text)
    status = Column(Text, nullable=False, default="running")
    input_summary = Column(Text, nullable=False, default="")
    output_summary = Column(Text, nullable=False, default="")
    artifact_ids_json = Column(Text, nullable=False, default="[]")
    error_excerpt = Column(Text)
    duration_ms = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime)

    workflow_run = relationship("WorkflowRunRow", back_populates="atom_invocations")


class HumanGateRequestRow(Base):
    __tablename__ = "human_gate_requests"
    __table_args__ = (
        Index("human_gate_requests_run_idx", "workflow_run_id"),
        Index("human_gate_requests_status_idx", "status"),
        Index("human_gate_requests_risk_idx", "risk_level"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False)
    state_key = Column(Text, nullable=False)
    gate_type = Column(Text, nullable=False, default="human_gate")
    risk_level = Column(Text, nullable=False, default="high")
    status = Column(Text, nullable=False, default="pending")
    reason = Column(Text, nullable=False, default="")
    payload_json = Column(Text, nullable=False, default="{}")
    decided_by = Column(Text)
    decision = Column(Text)
    decision_comment = Column(Text)
    decided_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    workflow_run = relationship("WorkflowRunRow", back_populates="human_gate_requests")


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
    verified_by_step_id = Column(Integer)
    evidence_artifact_id = Column(Integer)
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


class ValidationRecordRow(Base):
    __tablename__ = "validation_records"
    __table_args__ = (
        Index("validation_records_requirement_idx", "requirement_id"),
        Index("validation_records_workflow_run_idx", "workflow_run_id"),
        Index("validation_records_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"), nullable=False, default=0)
    profile = Column(Text, nullable=False, default="minimal")
    status = Column(Text, nullable=False, default="pending")
    summary_markdown = Column(Text, nullable=False, default="")
    checks_json = Column(Text, nullable=False, default="[]")
    verification_plan_json = Column(Text, nullable=False, default="{}")
    verification_agent_id = Column(Text)
    verification_agent_label = Column(Text)
    evidence_json = Column(Text, nullable=False, default="[]")
    reasoning_markdown = Column(Text, nullable=False, default="")
    suggested_next_action = Column(Text)
    resolution_recommendation = Column(Text)
    resolution_confidence = Column(Float)
    resolution_reason = Column(Text)
    resolution_path = Column(Text)
    followup_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    followup_requirement_payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requirement = relationship("RequirementRow", foreign_keys=[requirement_id])
    followup_requirement = relationship("RequirementRow", foreign_keys=[followup_requirement_id])


class ReleaseRecordRow(Base):
    __tablename__ = "release_records"
    __table_args__ = (
        Index("release_records_requirement_idx", "requirement_id"),
        Index("release_records_workflow_run_idx", "workflow_run_id"),
        Index("release_records_status_idx", "status"),
        Index("release_records_planning_goal_idx", "operating_manifest_id", "goal_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    operating_manifest_id = Column(Integer, ForeignKey("operating_manifests.id"))
    goal_key = Column(Text)
    project_id = Column(Integer, ForeignKey("projects.id"))
    project_key = Column(Text)
    project_display_name = Column(Text)
    target_project_path = Column(Text)
    status = Column(Text, nullable=False, default="not_ready")
    delivery_state = Column(Text, nullable=False, default="pending")
    branch_name = Column(Text)
    planned_branch_name = Column(Text)
    actual_branch_name = Column(Text)
    branch_reuse_status = Column(Text)
    base_branch = Column(Text)
    commit_sha = Column(Text)
    compare_url = Column(Text)
    pr_url = Column(Text)
    pr_number = Column(Integer)
    notes = Column(Text)
    delivery_blocker_type = Column(Text)
    blocker_kind = Column(Text)
    delivery_failure_excerpt = Column(Text)
    delivery_failure_raw_output = Column(Text)
    failed_gate_name = Column(Text)
    repairable = Column(Boolean, nullable=False, default=False)
    repairability = Column(Text, nullable=False, default="manual_only")
    repair_attempt_count = Column(Integer, nullable=False, default=0)
    next_action = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    prepared_at = Column(DateTime)
    delivered_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    requirement = relationship("RequirementRow", foreign_keys=[requirement_id])
    workflow_run = relationship("WorkflowRunRow", foreign_keys=[workflow_run_id])
    operating_manifest = relationship("OperatingManifestRow", foreign_keys=[operating_manifest_id])
    project = relationship("ProjectRow")


class OperationRequestRow(Base):
    __tablename__ = "operation_requests"
    __table_args__ = (
        Index("operation_requests_target_idx", "target_type", "target_id"),
        Index("operation_requests_key_idx", "operation_key", unique=True),
        Index("operation_requests_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_key = Column(Text, nullable=False)
    target_type = Column(Text, nullable=False)
    target_id = Column(Integer, nullable=False)
    action = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="applied")
    result_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class OperatingManifestRow(Base):
    __tablename__ = "operating_manifests"
    __table_args__ = (
        Index("operating_manifests_key_idx", "manifest_key", unique=True),
        Index("operating_manifests_status_idx", "status"),
        Index("operating_manifests_active_slot_idx", "active_slot", unique=True),
        Index("operating_manifests_cycle_idx", "cycle_label"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_key = Column(Text, nullable=False)
    version_name = Column(Text, nullable=False, default="")
    cycle_label = Column(Text, nullable=False, default="")
    status = Column(Text, nullable=False, default="draft")
    active_slot = Column(Text)
    revision = Column(Integer, nullable=False, default=1)
    payload_json = Column(Text, nullable=False, default="{}")
    review_summary_json = Column(Text, nullable=False, default="{}")
    change_log_json = Column(Text, nullable=False, default="[]")
    created_by = Column(Text, nullable=False, default="operator")
    archived_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class PlanningGoalRow(Base):
    __tablename__ = "planning_goals"
    __table_args__ = (
        UniqueConstraint("manifest_id", "goal_key", name="planning_goals_manifest_goal_key_uniq"),
        Index("planning_goals_manifest_idx", "manifest_id"),
        Index("planning_goals_status_idx", "manifest_id", "status"),
        Index("planning_goals_goal_key_idx", "goal_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id = Column(Integer, ForeignKey("operating_manifests.id"), nullable=False)
    goal_key = Column(Text, nullable=False)
    title = Column(Text, nullable=False, default="")
    intent_markdown = Column(Text, nullable=False, default="")
    success_metric = Column(Text, nullable=False, default="")
    domain = Column(Text, nullable=False, default="ops")
    status = Column(Text, nullable=False, default="active")
    workflow_key = Column(Text, nullable=False, default="gateway_reliability_repair")
    project_key = Column(Text)
    priority = Column(Text, nullable=False, default="normal")
    risk_level = Column(Text, nullable=False, default="normal")
    weight = Column(Float, nullable=False, default=0.0)
    acceptance_kind = Column(Text, nullable=False, default="business")
    execution_acceptance_steps_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")
    closed_at = Column(DateTime)
    review_note = Column(Text)
    drop_decision_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    manifest = relationship("OperatingManifestRow")


class RequirementCandidateRow(Base):
    __tablename__ = "requirement_candidates"
    __table_args__ = (
        Index("requirement_candidates_manifest_idx", "manifest_id"),
        Index("requirement_candidates_goal_idx", "manifest_id", "goal_key"),
        Index("requirement_candidates_status_idx", "status"),
        Index("requirement_candidates_fingerprint_idx", "candidate_fingerprint"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id = Column(Integer, ForeignKey("operating_manifests.id"), nullable=False)
    goal_key = Column(Text, nullable=False)
    candidate_fingerprint = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description_markdown = Column(Text, nullable=False, default="")
    project_id = Column(Integer, ForeignKey("projects.id"))
    project_key = Column(Text)
    workflow_key = Column(Text, nullable=False, default="gateway_reliability_repair")
    priority = Column(Text, nullable=False, default="normal")
    risk_level = Column(Text, nullable=False, default="normal")
    confidence = Column(Float, nullable=False, default=0.0)
    rationale = Column(Text, nullable=False, default="")
    expected_evidence_json = Column(Text, nullable=False, default="[]")
    status = Column(Text, nullable=False, default="pending")
    suppression_reason = Column(Text)
    rejected_at = Column(DateTime)
    rejected_by = Column(Text)
    reject_reason = Column(Text)
    reject_comment = Column(Text)
    approved_at = Column(DateTime)
    approved_by = Column(Text)
    materialized_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    cooldown_until = Column(DateTime)
    stale_at = Column(DateTime)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    manifest = relationship("OperatingManifestRow")
    project = relationship("ProjectRow", foreign_keys=[project_id])
    materialized_requirement = relationship("RequirementRow", foreign_keys=[materialized_requirement_id])


class PlannerSweepRow(Base):
    __tablename__ = "planner_sweeps"
    __table_args__ = (
        Index("planner_sweeps_manifest_idx", "manifest_id"),
        Index("planner_sweeps_status_idx", "status"),
        Index("planner_sweeps_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manifest_id = Column(Integer, ForeignKey("operating_manifests.id"), nullable=False)
    status = Column(Text, nullable=False, default="running")
    triggered_by = Column(Text, nullable=False, default="operator")
    dry_run = Column(Boolean, nullable=False, default=False)
    input_snapshot_json = Column(Text, nullable=False, default="{}")
    parsed_output_json = Column(Text, nullable=False, default="{}")
    created_candidate_ids_json = Column(Text, nullable=False, default="[]")
    suppressed_items_json = Column(Text, nullable=False, default="[]")
    error_excerpt = Column(Text)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime)
    duration_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    manifest = relationship("OperatingManifestRow")


class ErrorFingerprintRow(Base):
    __tablename__ = "error_fingerprints"
    __table_args__ = (
        Index("error_fingerprints_key_idx", "fingerprint_key", unique=True),
        Index("error_fingerprints_status_idx", "status"),
        Index("error_fingerprints_latest_seen_idx", "latest_seen_at"),
        Index("error_fingerprints_project_idx", "project_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint_key = Column(Text, nullable=False)
    source_kind = Column(Text, nullable=False)
    service_name = Column(Text)
    project_key = Column(Text)
    project_root_path = Column(Text)
    incident_code = Column(Text)
    status = Column(Text, nullable=False, default="open")
    severity = Column(Text, nullable=False, default="normal")
    summary = Column(Text, nullable=False, default="")
    normalized_message = Column(Text, nullable=False, default="")
    stack_signature = Column(Text, nullable=False, default="")
    evidence_excerpt = Column(Text, nullable=False, default="")
    occurrence_count = Column(Integer, nullable=False, default=1)
    latest_error_event_id = Column(Integer)
    linked_requirement_id = Column(Integer, ForeignKey("requirements.id"))
    discovery_status = Column(Text, nullable=False, default="pending")
    discovery_recommendation_json = Column(Text, nullable=False, default="{}")
    last_discovery_at = Column(DateTime)
    metadata_json = Column(Text, nullable=False, default="{}")
    first_seen_at = Column(DateTime, nullable=False, default=utcnow)
    latest_seen_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    linked_requirement = relationship("RequirementRow")


class ErrorEventRow(Base):
    __tablename__ = "error_events"
    __table_args__ = (
        Index("error_events_fingerprint_idx", "fingerprint_key"),
        Index("error_events_source_kind_idx", "source_kind"),
        Index("error_events_occurred_at_idx", "occurred_at"),
        Index("error_events_project_idx", "project_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint_key = Column(Text, nullable=False)
    source_kind = Column(Text, nullable=False)
    service_name = Column(Text)
    project_key = Column(Text)
    project_root_path = Column(Text)
    incident_code = Column(Text)
    severity = Column(Text, nullable=False, default="normal")
    summary = Column(Text, nullable=False, default="")
    message = Column(Text, nullable=False, default="")
    stack_trace = Column(Text)
    source_ref = Column(Text)
    environment = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    occurred_at = Column(DateTime, nullable=False, default=utcnow)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class NotificationDeliveryRow(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("notification_deliveries_event_key_idx", "event_key", unique=True),
        Index("notification_deliveries_channel_idx", "channel"),
        Index("notification_deliveries_object_idx", "object_type", "object_key"),
        Index("notification_deliveries_status_idx", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    event_key = Column(Text, nullable=False)
    object_type = Column(Text, nullable=False)
    object_key = Column(Text, nullable=False)
    service_name = Column(Text)
    status = Column(Text, nullable=False, default="pending")
    payload_json = Column(Text, nullable=False, default="{}")
    response_excerpt = Column(Text)
    delivered_at = Column(DateTime)
    event_id = Column(Integer)
    fingerprint_key = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class NotificationEventRow(Base):
    __tablename__ = "notification_events"
    __table_args__ = (
        Index("notification_events_status_idx", "status"),
        Index("notification_events_fingerprint_idx", "fingerprint_key"),
        Index("notification_events_channel_priority_idx", "channel", "priority"),
        Index("notification_events_object_idx", "object_type", "object_key"),
        Index("notification_events_created_at_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    priority = Column(Text, nullable=False, default="p2")
    severity = Column(Text, nullable=False, default="normal")
    risk_level = Column(Text, nullable=False, default="normal")
    object_type = Column(Text, nullable=False)
    object_key = Column(Text, nullable=False)
    fingerprint_key = Column(Text, nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    status = Column(Text, nullable=False, default="queued")
    delivery_id = Column(Integer)
    suppressed_reason = Column(Text)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class NotificationFingerprintRow(Base):
    __tablename__ = "notification_fingerprints"
    __table_args__ = (
        Index("notification_fingerprints_channel_idx", "channel"),
        Index("notification_fingerprints_status_idx", "status"),
        Index("notification_fingerprints_last_seen_idx", "last_seen_at"),
    )

    fingerprint_key = Column(Text, primary_key=True)
    channel = Column(Text, nullable=False)
    event_type = Column(Text, nullable=False)
    priority = Column(Text, nullable=False, default="p2")
    severity = Column(Text, nullable=False, default="normal")
    risk_level = Column(Text, nullable=False, default="normal")
    status = Column(Text, nullable=False, default="open")
    first_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_seen_at = Column(DateTime, nullable=False, default=utcnow)
    last_sent_at = Column(DateTime)
    occurrence_count = Column(Integer, nullable=False, default=0)
    suppressed_count = Column(Integer, nullable=False, default=0)
    latest_payload_json = Column(Text, nullable=False, default="{}")
    cooldown_until = Column(DateTime)
    escalation_level = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ── Init ──────────────────────────────────────────────────────

def _migrate(engine_):
    """Add missing columns to existing tables (lightweight migration)."""
    insp = inspect(engine_)
    tables = insp.get_table_names()

    if "projects" not in tables:
        logger.info("Migrating: creating 'projects' table")
        ProjectRow.__table__.create(bind=engine_, checkfirst=True)
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
        requirement_cols = {
            "project_id": "INTEGER",
            "project_key": "TEXT",
            "project_display_name": "TEXT",
            "target_project_path_override": "TEXT",
            "operating_manifest_id": "INTEGER",
            "goal_key": "TEXT",
            "requirement_candidate_id": "INTEGER",
            "workflow_family": "TEXT DEFAULT 'declarative_state_machine'",
            "phase": "TEXT DEFAULT 'draft'",
            "workflow_state": "TEXT DEFAULT 'draft'",
            "attention_reason": "TEXT",
            "failure_reason": "TEXT",
            "recovery_status": "TEXT",
        }
        for col, col_type in requirement_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to requirements table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE requirements ADD COLUMN {col} {col_type}"))
                    conn.commit()
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
        if "execution_plan_json" not in existing:
            logger.info("Migrating: adding 'execution_plan_json' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN execution_plan_json TEXT DEFAULT '{}'"))
                conn.commit()
        if "assets_status" not in existing:
            logger.info("Migrating: adding 'assets_status' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN assets_status TEXT DEFAULT 'pending'"))
                conn.commit()
        if "assets_error_message" not in existing:
            logger.info("Migrating: adding 'assets_error_message' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN assets_error_message TEXT"))
                conn.commit()
        with engine_.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE requirements
                    SET assets_status = 'ready'
                    WHERE COALESCE(assets_status, 'pending') = 'pending'
                      AND TRIM(COALESCE(acceptance_contract_json, '{}')) NOT IN ('', '{}')
                      AND TRIM(COALESCE(execution_plan_json, '{}')) NOT IN ('', '{}')
                    """
                )
            )
            conn.commit()
        requirement_cols = {
            "linked_requirement_id": "INTEGER",
            "followup_requirement_id": "INTEGER",
            "origin_validation_id": "INTEGER",
            "resolution_path": "TEXT",
        }
        for col, col_type in requirement_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to requirements table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE requirements ADD COLUMN {col} {col_type}"))
                    conn.commit()
        with engine_.connect() as conn:
            conn.execute(
                text(
                    """
                    UPDATE requirements
                    SET workflow_family = 'declarative_state_machine'
                    WHERE COALESCE(NULLIF(TRIM(workflow_family), ''), 'declarative_state_machine') != workflow_family
                       OR workflow_family IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE requirements
                    SET phase = CASE
                        WHEN status IN ('draft', 'planning') THEN 'draft'
                        WHEN status IN ('ready', 'waiting_execution', 'queued') THEN 'ready'
                        WHEN status IN ('running', 'validating') THEN 'executing'
                        WHEN status IN ('blocked', 'paused', 'cancelled') THEN 'blocked'
                        WHEN status = 'needs_revision' THEN 'needs_revision'
                        WHEN status IN ('delivery_ready', 'pr_opened') THEN 'delivery_ready'
                        WHEN status = 'done' THEN 'done'
                        ELSE COALESCE(NULLIF(phase, ''), 'draft')
                    END
                    WHERE COALESCE(NULLIF(TRIM(phase), ''), '') = ''
                       OR phase IS NULL
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE requirements
                    SET workflow_state = CASE
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') = 'deleted' THEN 'cancelled'
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') = 'cancelled' THEN 'cancelled'
                        WHEN COALESCE(NULLIF(TRIM(phase), ''), '') IN ('draft', 'planning') THEN 'draft'
                        WHEN COALESCE(NULLIF(TRIM(phase), ''), '') = 'awaiting_execution_approval' THEN 'ready'
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') = 'ready' THEN 'ready'
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') = 'running' THEN 'executing'
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') IN ('blocked', 'needs_revision') THEN 'awaiting_operator'
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') = 'delivery_ready' THEN 'delivering'
                        WHEN COALESCE(NULLIF(TRIM(status), ''), '') = 'done' THEN 'ready_for_merge'
                        ELSE COALESCE(NULLIF(TRIM(workflow_state), ''), 'draft')
                    END
                    WHERE COALESCE(NULLIF(TRIM(workflow_state), ''), '') = ''
                       OR workflow_state IS NULL
                    """
                )
            )
            conn.commit()

    if "recurring_workflows" not in tables:
        logger.info("Migrating: creating 'recurring_workflows' table")
        RecurringWorkflowRow.__table__.create(bind=engine_, checkfirst=True)

    if "project_policies" in tables:
        existing = {c["name"] for c in insp.get_columns("project_policies")}
        project_policy_cols = {
            "project_id": "INTEGER",
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

    if "company_operating_reviews" not in tables:
        logger.info("Migrating: company_operating_reviews table will be created via metadata")

    if "bug_records" not in tables:
        logger.info("Migrating: creating 'bug_records' table")
        BugRecordRow.__table__.create(bind=engine_, checkfirst=True)
    else:
        existing = {c["name"] for c in insp.get_columns("bug_records")}
        bug_cols = {
            "scorecard_json": "TEXT DEFAULT '{}'",
            "discovery_status": "TEXT DEFAULT 'pending'",
            "discovery_recommendation_json": "TEXT DEFAULT '{}'",
            "last_discovery_at": "DATETIME",
        }
        for col, col_type in bug_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to bug_records table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE bug_records ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "requirement_intake_fingerprints" not in tables:
        logger.info("Migrating: creating 'requirement_intake_fingerprints' table")
        RequirementIntakeFingerprintRow.__table__.create(bind=engine_, checkfirst=True)

    if "codex_sessions" not in tables:
        logger.info("Migrating: creating 'codex_sessions' table")
        CodexSessionRow.__table__.create(bind=engine_, checkfirst=True)
    else:  # pragma: no cover - startup migration for already-created local DBs
        existing = {c["name"] for c in insp.get_columns("codex_sessions")}
        session_cols = (("workspace_trust_state", "TEXT DEFAULT 'clean'"), ("requires_workspace_recovery", "BOOLEAN DEFAULT 0"), ("killed_at", "DATETIME"), ("kill_signal", "TEXT"), ("trusted_checkpoint_json", "TEXT DEFAULT '{}'"))
        for col, col_type in session_cols:
            if col not in existing:
                logger.info("Migrating: adding '%s' column to codex_sessions table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE codex_sessions ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "deployment_records" not in tables:
        logger.info("Migrating: creating 'deployment_records' table")
        DeploymentRecordRow.__table__.create(bind=engine_, checkfirst=True)
    else:  # pragma: no cover - startup migration for already-created local DBs
        deployment_columns = {c["name"]: c for c in insp.get_columns("deployment_records")}
        requirement_col = deployment_columns.get("requirement_id")
        if requirement_col is not None and requirement_col.get("nullable") is False:
            logger.info("Migrating: making deployment_records.requirement_id nullable")
            if _IS_SQLITE:
                _rebuild_sqlite_deployment_records_with_nullable_requirement(engine_)
                insp = inspect(engine_)
            else:
                with engine_.connect() as conn:
                    conn.execute(text("ALTER TABLE deployment_records ALTER COLUMN requirement_id DROP NOT NULL"))
                    conn.commit()

    if "deployment_events" not in tables:
        logger.info("Migrating: creating 'deployment_events' table")
        server.database_deployments.DeploymentEventRow.__table__.create(bind=engine_, checkfirst=True)

    if "release_tasks" not in tables:
        logger.info("Migrating: creating 'release_tasks' table")
        ReleaseTaskRow.__table__.create(bind=engine_, checkfirst=True)
    else:  # pragma: no cover - startup migration for already-created local DBs
        existing = {c["name"] for c in insp.get_columns("release_tasks")}
        release_task_cols = {
            "service_key": "TEXT",
        }
        for col, col_type in release_task_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to release_tasks table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE release_tasks ADD COLUMN {col} {col_type}"))
                    conn.commit()
        release_task_fks = insp.get_foreign_keys("release_tasks")
        if any(fk.get("referred_table") == "deployment_records_old" for fk in release_task_fks):
            logger.info("Migrating: repairing release_tasks deployment_record foreign key")
            _rebuild_sqlite_release_tasks_with_current_fks(engine_)
            insp = inspect(engine_)

    social_tables = {"social_campaign_goals": SocialCampaignGoalRow, "social_oauth_sessions": SocialOAuthSessionRow, "social_trend_items": SocialTrendItemRow, "social_watchlist_accounts": SocialWatchlistAccountRow, "social_reply_items": SocialReplyItemRow, "social_repost_candidates": SocialRepostCandidateRow, "social_post_metrics": SocialPostMetricRow}
    for table_name, row_class in social_tables.items():
        if table_name not in tables:
            logger.info("Migrating: creating '%s' table", table_name)
            row_class.__table__.create(bind=engine_, checkfirst=True)
    migrate_social_x_read_budget(engine_, tables)

    if "social_reply_items" in tables:
        existing = {c["name"] for c in insp.get_columns("social_reply_items")}
        social_reply_cols = {
            "source_candidate_id": "INTEGER",
            "source_post_id": "TEXT",
            "source_author_handle": "TEXT",
            "source_text": "TEXT",
            "generation_reason": "TEXT",
            "published_external_post_id": "TEXT",
            "reviewed_by": "TEXT",
            "failure_summary": "TEXT",
            "metadata_json": "TEXT DEFAULT '{}'",
        }
        for col, col_type in social_reply_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to social_reply_items table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE social_reply_items ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "social_post_drafts" in tables:
        existing = {c["name"] for c in insp.get_columns("social_post_drafts")}
        if "source_type" not in existing:
            logger.info("Migrating: adding 'source_type' column to social_post_drafts table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE social_post_drafts ADD COLUMN source_type TEXT DEFAULT 'manual_prompt'"))
                conn.commit()

    if "social_watchlist_accounts" in tables:
        existing = {c["name"] for c in insp.get_columns("social_watchlist_accounts")}
        if "x_user_id" not in existing:
            logger.info("Migrating: adding 'x_user_id' column to social_watchlist_accounts table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE social_watchlist_accounts ADD COLUMN x_user_id TEXT")); conn.commit()

    server.database_social_distribution.migrate_social_distribution_schema(engine_, insp, tables)

    if "workflow_runs" in tables:
        existing = {c["name"] for c in insp.get_columns("workflow_runs")}
        workflow_run_cols = {
            "operating_manifest_id": "INTEGER",
            "goal_key": "TEXT",
            "workflow_key": "TEXT DEFAULT 'declarative_workflow'",
            "current_state": "TEXT DEFAULT 'queued'",
            "resolution": "TEXT",
            "risk_level": "TEXT DEFAULT 'normal'",
            "retry_counters_json": "TEXT DEFAULT '{}'",
            "blackboard_json": "TEXT DEFAULT '{}'",
            "archived_at": "DATETIME",
            "archived_by": "TEXT",
            "archive_reason": "TEXT",
            "delivery_pr_url": "TEXT",
            "delivery_compare_url": "TEXT",
            "delivery_branch": "TEXT",
            "delivery_base_branch": "TEXT",
            "delivery_status": "TEXT",
            "delivery_is_simulated": "BOOLEAN DEFAULT 0",
            "delivery_synced_at": "DATETIME",
        }
        for col, col_type in workflow_run_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to workflow_runs table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE workflow_runs ADD COLUMN {col} {col_type}"))
                    conn.commit()

    declarative_tables = {
        "workflow_definitions": WorkflowDefinitionRow,
        "workflow_state_events": WorkflowStateEventRow,
        "workflow_artifacts": WorkflowArtifactRow,
        "blackboard_snapshots": BlackboardSnapshotRow,
        "atom_invocations": AtomInvocationRow,
        "human_gate_requests": HumanGateRequestRow,
    }
    for table_name, row_class in declarative_tables.items():
        if table_name not in tables:
            logger.info("Migrating: creating '%s' table", table_name)
            row_class.__table__.create(bind=engine_, checkfirst=True)

    if "recurring_workflow_runs" not in tables:
        logger.info("Migrating: creating 'recurring_workflow_runs' table")
        RecurringWorkflowRunRow.__table__.create(bind=engine_, checkfirst=True)

    if "scheduler_locks" not in tables:
        logger.info("Migrating: creating 'scheduler_locks' table")
        SchedulerLockRow.__table__.create(bind=engine_, checkfirst=True)

    if "validation_records" not in tables:
        logger.info("Migrating: creating 'validation_records' table")
        ValidationRecordRow.__table__.create(bind=engine_, checkfirst=True)
    else:
        existing = {c["name"] for c in insp.get_columns("validation_records")}
        validation_cols = {
            "verification_plan_json": "TEXT DEFAULT '{}'",
            "verification_agent_id": "TEXT",
            "verification_agent_label": "TEXT",
            "evidence_json": "TEXT DEFAULT '[]'",
            "reasoning_markdown": "TEXT DEFAULT ''",
            "suggested_next_action": "TEXT",
            "resolution_recommendation": "TEXT",
            "resolution_confidence": "FLOAT",
            "resolution_reason": "TEXT",
            "resolution_path": "TEXT",
            "followup_requirement_id": "INTEGER",
            "followup_requirement_payload_json": "TEXT DEFAULT '{}'",
        }
        for col, col_type in validation_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to validation_records table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE validation_records ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "release_records" not in tables:
        logger.info("Migrating: creating 'release_records' table")
        ReleaseRecordRow.__table__.create(bind=engine_, checkfirst=True)
    else:
        existing = {c["name"] for c in insp.get_columns("release_records")}
        release_cols = {
            "workflow_run_id": "INTEGER",
            "operating_manifest_id": "INTEGER",
            "goal_key": "TEXT",
            "project_id": "INTEGER",
            "project_display_name": "TEXT",
            "delivery_state": "TEXT DEFAULT 'pending'",
            "planned_branch_name": "TEXT",
            "actual_branch_name": "TEXT",
            "branch_reuse_status": "TEXT",
            "delivery_blocker_type": "TEXT",
            "blocker_kind": "TEXT",
            "delivery_failure_excerpt": "TEXT",
            "delivery_failure_raw_output": "TEXT",
            "failed_gate_name": "TEXT",
            "repairable": "BOOLEAN DEFAULT 0",
            "repairability": "TEXT DEFAULT 'manual_only'",
            "repair_attempt_count": "INTEGER DEFAULT 0",
            "next_action": "TEXT",
        }
        for col, col_type in release_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to release_records table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE release_records ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "error_fingerprints" not in tables:
        logger.info("Migrating: creating 'error_fingerprints' table")
        ErrorFingerprintRow.__table__.create(bind=engine_, checkfirst=True)
    else:
        existing = {c["name"] for c in insp.get_columns("error_fingerprints")}
        fingerprint_cols = {
            "discovery_status": "TEXT DEFAULT 'pending'",
            "discovery_recommendation_json": "TEXT DEFAULT '{}'",
            "last_discovery_at": "DATETIME",
        }
        for col, col_type in fingerprint_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to error_fingerprints table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE error_fingerprints ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "error_events" not in tables:
        logger.info("Migrating: creating 'error_events' table")
        ErrorEventRow.__table__.create(bind=engine_, checkfirst=True)

    if "notification_events" not in tables:
        logger.info("Migrating: creating 'notification_events' table")
        NotificationEventRow.__table__.create(bind=engine_, checkfirst=True)

    if "notification_fingerprints" not in tables:
        logger.info("Migrating: creating 'notification_fingerprints' table")
        NotificationFingerprintRow.__table__.create(bind=engine_, checkfirst=True)

    if "notification_deliveries" not in tables:
        logger.info("Migrating: creating 'notification_deliveries' table")
        NotificationDeliveryRow.__table__.create(bind=engine_, checkfirst=True)
    else:
        existing = {c["name"] for c in insp.get_columns("notification_deliveries")}
        delivery_cols = {
            "event_id": "INTEGER",
            "fingerprint_key": "TEXT",
        }
        for col, col_type in delivery_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to notification_deliveries table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE notification_deliveries ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "requirement_attachments" not in tables:
        logger.info("Migrating: creating 'requirement_attachments' table")
        RequirementAttachmentRow.__table__.create(bind=engine_, checkfirst=True)

    if "operation_requests" not in tables:
        logger.info("Migrating: creating 'operation_requests' table")
        OperationRequestRow.__table__.create(bind=engine_, checkfirst=True)


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate(engine)
    from server.services.projects.policy import ensure_default_project_policies
    from server.services.projects.project_center import ensure_projects_materialized
    db = SessionLocal()
    try:
        ensure_default_project_policies(db)
        ensure_projects_materialized(db)
    finally:
        db.close()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
