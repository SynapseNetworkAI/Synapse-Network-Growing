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
    mcp_server_id = Column(Integer, ForeignKey("mcp_servers.id"))
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

    server = relationship("McpServerRow", back_populates="releases")
    surfaces = relationship(
        "McpServerSurfaceRow",
        back_populates="release",
        order_by="McpServerSurfaceRow.id",
        cascade="all, delete-orphan",
    )


class McpServerRow(Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        UniqueConstraint("server_key", name="mcp_servers_key_uq"),
        Index("mcp_servers_status_idx", "status"),
        Index("mcp_servers_package_idx", "package_name"),
        Index("mcp_servers_transport_idx", "transport_kind"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    server_key = Column(Text, nullable=False)
    server_name = Column(Text, nullable=False)
    repo_full_name = Column(Text, nullable=False)
    repo_url = Column(Text, nullable=False)
    local_repo_path = Column(Text)
    package_name = Column(Text, nullable=False)
    package_registry = Column(Text, nullable=False, default="npm")
    registry_name = Column(Text, nullable=False)
    transport_kind = Column(Text, nullable=False, default="stdio")
    remote_endpoint_url = Column(Text)
    install_command = Column(Text, nullable=False)
    tools_json = Column(Text, nullable=False, default="[]")
    security_boundary = Column(Text)
    status = Column(Text, nullable=False, default="active")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    releases = relationship(
        "McpServerReleaseRow",
        back_populates="server",
        order_by="McpServerReleaseRow.updated_at.desc()",
    )


class McpDiscoverySurfaceRow(Base):
    __tablename__ = "mcp_discovery_surfaces"
    __table_args__ = (
        UniqueConstraint("surface_key", name="mcp_discovery_surfaces_key_uq"),
        Index("mcp_discovery_surfaces_category_idx", "category"),
        Index("mcp_discovery_surfaces_priority_idx", "priority"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    surface_key = Column(Text, nullable=False)
    surface_label = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    requires_npm = Column(Integer, nullable=False, default=0)
    requires_remote_http = Column(Integer, nullable=False, default=0)
    supports_auto_submit = Column(Integer, nullable=False, default=0)
    submission_url = Column(Text)
    docs_url = Column(Text)
    priority = Column(Integer, nullable=False, default=100)
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class McpSurfaceConfigRow(Base):
    __tablename__ = "mcp_surface_configs"
    __table_args__ = (
        UniqueConstraint("surface_key", name="mcp_surface_configs_key_uq"),
        Index("mcp_surface_configs_status_idx", "verification_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    surface_key = Column(Text, nullable=False)
    submission_mode = Column(Text, nullable=False, default="manual")
    auth_mode = Column(Text, nullable=False, default="manual")
    credential_ref = Column(Text)
    required_env_vars_json = Column(Text, nullable=False, default="[]")
    docs_url = Column(Text)
    submission_url = Column(Text)
    is_enabled = Column(Integer, nullable=False, default=1)
    verification_status = Column(Text, nullable=False, default="not_configured")
    verification_summary = Column(Text)
    last_verified_at = Column(DateTime)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


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
    submission_url = Column(Text)
    failure_reason = Column(Text)
    operator_note = Column(Text)
    evidence_json = Column(Text, nullable=False, default="{}")
    last_checked_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    release = relationship("McpServerReleaseRow", back_populates="surfaces")
