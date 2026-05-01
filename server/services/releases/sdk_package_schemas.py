"""Schemas for SDK package release cockpit APIs."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SdkPackageReleaseOut(BaseModel):
    id: int
    release_train_version: str
    sdk_language: str
    package_name: str
    registry: str
    channel: str = "preview"
    package_version: str
    git_tag: Optional[str] = None
    status: str = "planned"
    package_url: Optional[str] = None
    workflow_run_url: Optional[str] = None
    failure_summary: Optional[str] = None
    release_notes: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SdkPackageReleaseEventOut(BaseModel):
    id: int
    sdk_package_release_id: int
    action: str
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    actor: Optional[str] = None
    note: Optional[str] = None
    workflow_run_url: Optional[str] = None
    error_summary: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class SdkReleaseTrainOut(BaseModel):
    release_train_version: str
    channel: str = "preview"
    package_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    packages: list[SdkPackageReleaseOut] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SdkPackageReleaseInitializeRequest(BaseModel):
    release_train_version: str
    channel: str = "preview"
    release_notes: Optional[str] = None
    packages: list[str] = Field(default_factory=list)


class SdkPackageReleaseActionRequest(BaseModel):
    actor: str = "operator"
    package_version: Optional[str] = None
    channel: Optional[str] = None
    note: Optional[str] = None


class SdkPackageReleaseSyncResult(BaseModel):
    processed_count: int = 0
    publishing_ids: list[int] = Field(default_factory=list)
    ready_ids: list[int] = Field(default_factory=list)
    published_ids: list[int] = Field(default_factory=list)
    failed_ids: list[int] = Field(default_factory=list)
    error_ids: list[int] = Field(default_factory=list)
