"""Deployment governance database rows."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from server.database import Base, utcnow


class DeploymentEventRow(Base):
    __tablename__ = "deployment_events"
    __table_args__ = (
        Index("deployment_events_record_idx", "deployment_record_id"),
        Index("deployment_events_type_idx", "event_type"),
        Index("deployment_events_created_idx", "created_at"),
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    deployment_record_id = Column(
        Integer, ForeignKey("deployment_records.id", ondelete="CASCADE"), nullable=False
    )
    event_type = Column(Text, nullable=False)
    actor = Column(Text)
    status_from = Column(Text)
    status_to = Column(Text)
    summary = Column(Text)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    deployment_record = relationship("DeploymentRecordRow")
