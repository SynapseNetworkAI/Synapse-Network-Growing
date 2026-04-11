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

from server.config import DATABASE_URL

logger = logging.getLogger("ops-dashboard.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
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
    runtime_session_id = Column(Text)
    runtime_selected_agent = Column(Text)
    runtime_event_cursor = Column(Integer, default=0)
    output_path = Column(Text)
    output_content = Column(Text)
    execution_time_ms = Column(Integer)
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
    target_project_path = Column(Text)
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
    scheduler_weight = Column(Float, nullable=False, default=1.0)
    max_parallel_requirements = Column(Integer, nullable=False, default=1)
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

    if "requirements" in tables:
        existing = {c["name"] for c in insp.get_columns("requirements")}
        if "target_project_path" not in existing:
            logger.info("Migrating: adding 'target_project_path' column to requirements table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE requirements ADD COLUMN target_project_path TEXT"))
                conn.commit()

    if "project_policies" in tables:
        existing = {c["name"] for c in insp.get_columns("project_policies")}
        project_policy_cols = {
            "scheduler_weight": "FLOAT DEFAULT 1.0",
            "max_parallel_requirements": "INTEGER DEFAULT 1",
        }
        for col, col_type in project_policy_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to project_policies table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE project_policies ADD COLUMN {col} {col_type}"))
                    conn.commit()

    if "tasks" in tables:
        existing = {c["name"] for c in insp.get_columns("tasks")}
        new_cols = {
            "project_id": "TEXT DEFAULT ''",
            "agent_group": "TEXT DEFAULT ''",
            "skill_name": "TEXT",
            "context_files": "TEXT",
            "execution_time_ms": "INTEGER",
            "retry_of_task_id": "INTEGER",
            "attempt_no": "INTEGER DEFAULT 1",
            "last_error_message": "TEXT",
            "runtime_backend": "TEXT DEFAULT ''",
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
