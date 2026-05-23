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


class SdkPackageReleasePageOut(BaseModel):
    items: list[SdkPackageReleaseOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 10
    total_pages: int = 0


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


class SdkPackageReleaseHistoryItemOut(BaseModel):
    id: int
    release_train_version: str
    sdk_language: str
    package_name: str
    registry: str
    channel: str = "preview"
    package_version: str
    status: str = "planned"
    package_url: Optional[str] = None
    repo_url: str
    git_tag: Optional[str] = None
    git_tag_url: Optional[str] = None
    workflow_run_url: Optional[str] = None
    failure_summary: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SdkPackageReleaseHistoryPageOut(BaseModel):
    items: list[SdkPackageReleaseHistoryItemOut]
    total: int
    limit: int = 10
    offset: int = 0


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
    confirm_phrase: Optional[str] = None


class SdkPackageReleaseSyncResult(BaseModel):
    processed_count: int = 0
    publishing_ids: list[int] = Field(default_factory=list)
    ready_ids: list[int] = Field(default_factory=list)
    published_ids: list[int] = Field(default_factory=list)
    failed_ids: list[int] = Field(default_factory=list)
    error_ids: list[int] = Field(default_factory=list)


class SdkPackagePlatformOut(BaseModel):
    platform_key: str
    sdk_language: str
    registry: str
    package_name: str
    registry_url: str
    package_url_template: str
    credential_env_var: str
    enabled: bool = False
    configured: bool = False
    credential_present: bool = False
    dry_run_template: str
    publish_template: str
    verify_template: str
    install_command: str
    notes: Optional[str] = None
    metadata: dict[str, object] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class SdkPackagePlatformPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    registry_url: Optional[str] = None
    package_name: Optional[str] = None
    package_url_template: Optional[str] = None
    credential_env_var: Optional[str] = None
    notes: Optional[str] = None
