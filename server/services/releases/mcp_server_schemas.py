"""Schemas for MCP server release cockpit APIs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class McpServerSurfaceOut(BaseModel):
    id: int
    mcp_server_release_id: int
    surface_key: str
    surface_label: str
    status: str = "candidate"
    listing_url: Optional[str] = None
    failure_reason: Optional[str] = None
    evidence: dict[str, object] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class McpServerReleaseOut(BaseModel):
    id: int
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


class McpServerReleaseActionRequest(BaseModel):
    actor: str = "operator"
    note: Optional[str] = None
    confirm_phrase: Optional[str] = None


class McpServerSurfacePatchRequest(BaseModel):
    status: Optional[str] = None
    listing_url: Optional[str] = None
    failure_reason: Optional[str] = None
    evidence: Optional[dict[str, object]] = None


class McpServerReleaseSyncResult(BaseModel):
    processed_count: int = 0
    ready_ids: list[int] = Field(default_factory=list)
    package_published_ids: list[int] = Field(default_factory=list)
    registry_listed_ids: list[int] = Field(default_factory=list)
    smoke_passed_ids: list[int] = Field(default_factory=list)
    error_ids: list[int] = Field(default_factory=list)
