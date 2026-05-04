"""Typed API contracts for Synapse-Network Cloud Run Job releases."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ScheduledCloudRunJobOut(BaseModel):
    job_name: str
    family: str
    job_type: str
    cadence: str
    command: str
    purpose: str
    scheduler_job: Optional[str] = None
    freshness_required: bool = False
    migration_execution_required: bool = False


class ScheduledCloudRunJobStatusOut(ScheduledCloudRunJobOut):
    publish_status: str = "unknown"
    scheduler_status: str = "unknown"
    health_status: str = "unknown"
    image_digest: Optional[str] = None
    effective_image: Optional[str] = None
    latest_execution: Optional[str] = None
    last_published_at: Optional[datetime] = None
    last_deployment_record_id: Optional[int] = None
    external_url: Optional[str] = None
    failure_summary: Optional[str] = None
    diagnostic: Optional[str] = None
    metadata: dict[str, object] = {}


class ScheduledCloudRunJobsStatusOut(BaseModel):
    items: list[ScheduledCloudRunJobStatusOut] = []
    diagnostics: list[str] = []
    updated_at: Optional[datetime] = None


class ScheduledCloudRunJobRecordOut(BaseModel):
    id: int
    deployment_record_id: Optional[int] = None
    job_name: Optional[str] = None
    jobs: list[str] = []
    family: str
    job_type: Optional[str] = None
    environment: str = "staging"
    publish_mode: str = "single_job"
    source_ref_type: str = "branch"
    source_ref: Optional[str] = None
    status: str
    health_status: str = "unknown"
    actor: Optional[str] = None
    created_by: Optional[str] = None
    executed_by: Optional[str] = None
    workflow_file: Optional[str] = None
    external_run_id: Optional[str] = None
    external_url: Optional[str] = None
    failure_summary: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    metadata: dict[str, object] = {}


class ScheduledCloudRunJobRecordsOut(BaseModel):
    items: list[ScheduledCloudRunJobRecordOut] = []
    total: int = 0
    limit: int = 20
    offset: int = 0


class ScheduledCloudRunJobsPublishRequest(BaseModel):
    family: Optional[str] = None
    job_name: Optional[str] = None
    environment: str = "staging"
    source_ref_type: str = "branch"
    source_ref: str = "main"
    actor: str = "operator"
    note: Optional[str] = None
    run_smoke_jobs: bool = False
    run_migrations: bool = False


class ScheduledCloudRunJobTaskCreateRequest(BaseModel):
    job_name: str
    environment: str = "staging"
    source_ref_type: str = "branch"
    source_ref: str = "main"
    actor: str = "operator"
    note: Optional[str] = None
    run_smoke_jobs: bool = False
    run_migrations: bool = False


class ScheduledCloudRunJobTaskPublishRequest(BaseModel):
    actor: str = "operator"


class ScheduledCloudRunJobsPublishOut(BaseModel):
    deployment_record_id: Optional[int] = None
    task_id: Optional[int] = None
    family: str
    environment: str = "staging"
    publish_mode: str = "family"
    job_name: Optional[str] = None
    status: str
    external_url: Optional[str] = None
    jobs: list[str] = []
    message: str


class ScheduledCloudRunJobsSyncOut(BaseModel):
    processed_count: int = 0
    succeeded_ids: list[int] = []
    failed_ids: list[int] = []
    running_ids: list[int] = []
    pending_ids: list[int] = []
    error_ids: list[int] = []
