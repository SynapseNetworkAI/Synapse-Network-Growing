"""Database rows for MCP server release records."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from server.database import Base, utcnow


class McpServerReleaseRow(Base):
    __tablename__ = "mcp_server_releases"
    __table_args__ = (
        UniqueConstraint(
            "server_key", "package_version", name="mcp_server_release_version_uq"
        ),
        Index("mcp_server_releases_status_idx", "status"),
        Index("mcp_server_releases_server_idx", "server_key"),
        Index("mcp_server_releases_package_idx", "package_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_key = Column(Text, nullable=False)
    server_name = Column(Text, nullable=False)
    package_name = Column(Text, nullable=False)
    package_registry = Column(Text, nullable=False, default="npm")
    package_version = Column(Text, nullable=False)
    registry_name = Column(Text, nullable=False)
    git_tag = Column(Text)
    install_command = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="planned")
    package_url = Column(Text)
    registry_url = Column(Text)
    workflow_run_url = Column(Text)
    failure_summary = Column(Text)
    release_notes = Column(Text)
    smoke_evidence_json = Column(Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")
    published_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    surfaces = relationship(
        "McpServerSurfaceRow",
        back_populates="release",
        order_by="McpServerSurfaceRow.id",
        cascade="all, delete-orphan",
    )


class McpServerReleaseEventRow(Base):
    __tablename__ = "mcp_server_release_events"
    __table_args__ = (
        Index("mcp_server_release_events_release_idx", "mcp_server_release_id"),
        Index("mcp_server_release_events_action_idx", "action"),
        Index("mcp_server_release_events_created_idx", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    mcp_server_release_id = Column(
        Integer, ForeignKey("mcp_server_releases.id"), nullable=False
    )
    action = Column(Text, nullable=False)
    from_status = Column(Text)
    to_status = Column(Text)
    actor = Column(Text)
    note = Column(Text)
    workflow_run_url = Column(Text)
    error_summary = Column(Text)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)

    release = relationship("McpServerReleaseRow")


class McpServerSurfaceRow(Base):
    __tablename__ = "mcp_server_surfaces"
    __table_args__ = (
        UniqueConstraint(
            "mcp_server_release_id", "surface_key", name="mcp_server_surface_uq"
        ),
        Index("mcp_server_surfaces_release_idx", "mcp_server_release_id"),
        Index("mcp_server_surfaces_status_idx", "status"),
        Index("mcp_server_surfaces_surface_idx", "surface_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    mcp_server_release_id = Column(
        Integer, ForeignKey("mcp_server_releases.id"), nullable=False
    )
    surface_key = Column(Text, nullable=False)
    surface_label = Column(Text, nullable=False)
    category = Column(Text, nullable=False, default="directory")
    status = Column(Text, nullable=False, default="candidate")
    listing_url = Column(Text)
    failure_reason = Column(Text)
    evidence_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    release = relationship("McpServerReleaseRow", back_populates="surfaces")
