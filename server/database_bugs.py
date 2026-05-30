from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from server.database import Base, utcnow


class BugFixAttemptRow(Base):
    __tablename__ = "bug_fix_attempts"
    __table_args__ = (
        Index("bug_fix_attempts_bug_idx", "bug_id"),
        Index("bug_fix_attempts_status_idx", "status"),
        Index("bug_fix_attempts_agent_idx", "agent_id"),
        Index("bug_fix_attempts_requirement_idx", "requirement_id"),
        Index("bug_fix_attempts_workflow_idx", "workflow_run_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bug_id = Column(Integer, ForeignKey("bug_records.id"), nullable=False)
    status = Column(Text, nullable=False, default="claimed")
    agent_id = Column(Text, nullable=False, default="agent")
    branch_name = Column(Text)
    commit_sha = Column(Text)
    pr_url = Column(Text)
    workflow_run_id = Column(Integer, ForeignKey("workflow_runs.id"))
    requirement_id = Column(Integer, ForeignKey("requirements.id"))
    lease_token = Column(Text)
    lease_expires_at = Column(DateTime)
    verification_summary = Column(Text)
    verification_commands_json = Column(Text, nullable=False, default="[]")
    verification_screenshots_json = Column(Text, nullable=False, default="[]")
    failure_reason = Column(Text)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    verified_at = Column(DateTime)

    bug = relationship("BugRecordRow")
    requirement = relationship("RequirementRow")


class BugEventRow(Base):
    __tablename__ = "bug_events"
    __table_args__ = (
        Index("bug_events_bug_idx", "bug_id"),
        Index("bug_events_type_idx", "event_type"),
        Index("bug_events_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    bug_id = Column(Integer, ForeignKey("bug_records.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    actor = Column(Text, nullable=False, default="agent")
    from_status = Column(Text)
    to_status = Column(Text)
    message = Column(Text, nullable=False, default="")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    bug = relationship("BugRecordRow")
