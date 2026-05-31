"""Schemas for MCP server release cockpit APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class McpServerSurfaceOut(BaseModel):
    id: int
    mcp_server_release_id: int
    surface_key: str
    surface_label: str
    category: str = "directory"
    status: str = "candidate"
    listing_url: Optional[str] = None
    submission_url: Optional[str] = None
    failure_reason: Optional[str] = None
    operator_note: Optional[str] = None
    evidence: dict[str, object] = Field(default_factory=dict)
    last_checked_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class McpDiscoverySurfaceOut(BaseModel):
    id: int
    surface_key: str
    surface_label: str
    category: str
    requires_npm: bool = False
    requires_remote_http: bool = False
    supports_auto_submit: bool = False
    submission_url: Optional[str] = None
    docs_url: Optional[str] = None
    priority: int = 100
    status: str = "active"
    updated_at: Optional[datetime] = None


class McpSurfaceConfigOut(BaseModel):
    id: int
    surface_key: str
    submission_mode: str
    auth_mode: str
    credential_ref: Optional[str] = None
    required_env_vars: list[str] = Field(default_factory=list)
    docs_url: Optional[str] = None
    submission_url: Optional[str] = None
    is_enabled: bool = True
    verification_status: str = "not_configured"
    verification_summary: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class McpSurfaceConfigPatchRequest(BaseModel):
    submission_mode: Optional[str] = None
    auth_mode: Optional[str] = None
    credential_ref: Optional[str] = None
    required_env_vars: Optional[list[str]] = None
    docs_url: Optional[str] = None
    submission_url: Optional[str] = None
    is_enabled: Optional[bool] = None
    metadata: Optional[dict[str, object]] = None


class McpSurfaceConfigVerifyOut(BaseModel):
    surface_key: str
    verification_status: str
    verification_summary: str
    missing_env_vars: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    checked_at: datetime


class McpSubmissionReadinessItemOut(BaseModel):
    surface_key: str
    surface_label: str
    category: str
    surface_status: str
    config_status: str
    readiness_status: str
    reason: Optional[str] = None
    required_env_vars: list[str] = Field(default_factory=list)
    missing_env_vars: list[str] = Field(default_factory=list)
    submission_mode: str = "manual"
    credential_ref: Optional[str] = None


class McpSubmissionReadinessOut(BaseModel):
    server_id: int
    release_id: Optional[int] = None
    items: list[McpSubmissionReadinessItemOut] = Field(default_factory=list)


class McpSurfaceLiveCheckOut(BaseModel):
    release_id: int
    surface_key: str
    status: str
    summary: str
    evidence: dict[str, object] = Field(default_factory=dict)
    checked_at: datetime


class McpServerOut(BaseModel):
    id: int
    server_key: str
    server_name: str
    repo_full_name: str
    repo_url: str
    local_repo_path: Optional[str] = None
    package_name: str
    package_registry: str = "npm"
    registry_name: str
    transport_kind: str = "stdio"
    remote_endpoint_url: Optional[str] = None
    install_command: str
    tools: list[str] = Field(default_factory=list)
    security_boundary: Optional[str] = None
    status: str = "active"
    metadata: dict[str, object] = Field(default_factory=dict)
    latest_release: Optional[dict[str, object]] = None
    surface_summary: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class McpServerPageOut(BaseModel):
    items: list[McpServerOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    total_pages: int = 0


class McpServerReleaseOut(BaseModel):
    id: int
    mcp_server_id: Optional[int] = None
    server_key: str
    server_name: str
    package_name: str
    package_registry: str
    package_version: str
    registry_name: str
    git_tag: Optional[str] = None
    install_command: str
    status: str = "planned"
    package_url: Optional[str] = None
    registry_url: Optional[str] = None
    workflow_run_url: Optional[str] = None
    failure_summary: Optional[str] = None
    release_notes: Optional[str] = None
    smoke_evidence: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    surfaces: list[McpServerSurfaceOut] = Field(default_factory=list)
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class McpServerReleasePageOut(BaseModel):
    items: list[McpServerReleaseOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    total_pages: int = 0


class McpServerReleaseEventOut(BaseModel):
    id: int
    mcp_server_release_id: int
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    actor: Optional[str] = None
    note: Optional[str] = None
    workflow_run_url: Optional[str] = None
    error_summary: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class McpServerReleaseCreateRequest(BaseModel):
    package_version: str
    release_notes: Optional[str] = None
    server_key: str = "synapse-network-mcp-server"
    mcp_server_id: Optional[int] = None


class McpServerCreateRequest(BaseModel):
    server_key: str
    server_name: str
    repo_full_name: str
    repo_url: str
    local_repo_path: Optional[str] = None
    package_name: str
    package_registry: str = "npm"
    registry_name: str
    transport_kind: str = "stdio"
    remote_endpoint_url: Optional[str] = None
    install_command: str
    tools: list[str] = Field(default_factory=list)
    security_boundary: Optional[str] = None
    status: str = "active"
    metadata: dict[str, object] = Field(default_factory=dict)


class McpServerReleaseActionRequest(BaseModel):
    actor: str = "operator"
    note: Optional[str] = None
    confirm_phrase: Optional[str] = None


class McpServerSurfacePatchRequest(BaseModel):
    status: Optional[str] = None
    listing_url: Optional[str] = None
    submission_url: Optional[str] = None
    failure_reason: Optional[str] = None
    operator_note: Optional[str] = None
    evidence: Optional[dict[str, object]] = None


class McpServerSurfaceSubmitRequest(BaseModel):
    surface_key: str
    actor: str = "operator"
    note: Optional[str] = None


class McpServerReleaseSyncResult(BaseModel):
    processed_count: int = 0
    ready_ids: list[int] = Field(default_factory=list)
    package_published_ids: list[int] = Field(default_factory=list)
    registry_listed_ids: list[int] = Field(default_factory=list)
    smoke_passed_ids: list[int] = Field(default_factory=list)
    error_ids: list[int] = Field(default_factory=list)
