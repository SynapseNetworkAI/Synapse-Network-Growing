"""Database rows for scheduled Cloud Run Job release tasks."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from server.database import Base, utcnow


class ScheduledJobReleaseTaskRow(Base):
    __tablename__ = "scheduled_job_release_tasks"
    __table_args__ = (
        Index("scheduled_job_release_tasks_status_idx", "status"),
        Index("scheduled_job_release_tasks_job_idx", "job_name"),
        Index("scheduled_job_release_tasks_family_idx", "job_family"),
        Index("scheduled_job_release_tasks_environment_idx", "environment"),
        Index("scheduled_job_release_tasks_deployment_idx", "deployment_record_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_key = Column(Text, nullable=False, default="synapse-network")
    job_name = Column(Text, nullable=False)
    job_family = Column(Text, nullable=False)
    job_type = Column(Text, nullable=False, default="periodic")
    environment = Column(Text, nullable=False, default="staging")
    source_ref_type = Column(Text, nullable=False, default="branch")
    source_ref = Column(Text, nullable=False, default="main")
    status = Column(Text, nullable=False, default="requested")
    health_status = Column(Text, nullable=False, default="pending")
    deployment_record_id = Column(Integer, ForeignKey("deployment_records.id"))
    run_smoke_jobs = Column(Boolean, nullable=False, default=False)
    run_migrations = Column(Boolean, nullable=False, default=False)
    created_by = Column(Text, nullable=False, default="operator")
    executed_by = Column(Text)
    note = Column(Text)
    failure_summary = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)

    deployment_record = relationship("DeploymentRecordRow")
