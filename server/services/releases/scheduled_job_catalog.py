"""Canonical Synapse-Network staging Cloud Run Job registry."""

from __future__ import annotations

from server.services.releases.scheduled_job_schemas import ScheduledCloudRunJobOut

SCHEDULED_JOBS_WORKFLOW_FILE = "local_scheduled_job_runner"
SCHEDULED_JOBS_REPO = "SynapseNetworkAI/Synapse-Network"
SCHEDULED_JOBS_TRIGGER_SOURCE = "local_deploy_runner"
SCHEDULED_JOB_ACTIVE_STATUSES = {"requested", "running", "pending"}
SCHEDULED_JOB_TERMINAL_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}
SCHEDULED_JOB_FAMILIES = {"gateway", "gateway-admin", "all"}


def scheduled_job_catalog() -> list[ScheduledCloudRunJobOut]:
    return [
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-deposit-indexer",
            family="gateway",
            job_type="periodic",
            cadence="every_minute",
            command="python -m src.worker deposit-indexer --once",
            purpose="确认充值入账",
            scheduler_job="synapse-staging-deposit-indexer-schedule",
            freshness_required=True,
        ),
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-provider-withdraw-reaper",
            family="gateway",
            job_type="periodic",
            cadence="every_minute",
            command="python -m src.worker provider-withdraw-reaper --once",
            purpose="过期 provider withdrawal ticket",
            scheduler_job="synapse-staging-provider-withdraw-reaper-schedule",
            freshness_required=True,
        ),
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-consumer-withdraw-processor",
            family="gateway",
            job_type="periodic",
            cadence="every_minute",
            command="python -m src.worker consumer-withdraw-processor --once",
            purpose="处理 consumer withdrawal 生命周期",
            scheduler_job="synapse-staging-consumer-withdraw-processor-schedule",
            freshness_required=True,
        ),
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-notification-outbox-drain",
            family="gateway",
            job_type="periodic",
            cadence="every_minute",
            command="python -m src.worker notification-outbox --once",
            purpose="发送异步通知 / Gmail",
            scheduler_job="synapse-staging-notification-outbox-drain-schedule",
            freshness_required=True,
        ),
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-in-app-notification-cleanup",
            family="gateway",
            job_type="periodic",
            cadence="daily",
            command="python -m src.worker in-app-cleanup --once",
            purpose="清理过期站内通知",
            scheduler_job="synapse-staging-in-app-notification-cleanup-schedule",
        ),
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-db-migrate",
            family="gateway",
            job_type="migration",
            cadence="release_time",
            command="gateway database migration job",
            purpose="Gateway DB migration",
            migration_execution_required=True,
        ),
        ScheduledCloudRunJobOut(
            job_name="synapse-staging-gateway-admin-db-migrate",
            family="gateway-admin",
            job_type="migration",
            cadence="release_time",
            command="gateway-admin database migration job",
            purpose="Gateway Admin DB migration",
            migration_execution_required=True,
        ),
    ]
