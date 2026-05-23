"""Deployment events for requirement-scoped deploy governance."""

from __future__ import annotations

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow
from server.services.delivery.deployment_events import record_deployment_event


def record_requested(db: Session, record: DeploymentRecordRow) -> None:
    record_deployment_event(
        db,
        record,
        event_type="deployment_requested",
        actor=record.actor,
        status_to="requested",
        summary="Requirement deployment request created a DeploymentRecord.",
        payload={
            "requirement_id": record.requirement_id,
            "environment": record.environment,
            "action": record.action,
        },
    )


def record_dispatched(db: Session, record: DeploymentRecordRow) -> None:
    record_deployment_event(
        db,
        record,
        event_type="deployment_dispatched",
        actor=record.actor,
        status_from="requested",
        status_to=str(record.status or "requested"),
        summary="Deployment workflow dispatched.",
        payload={
            "external_url": record.external_url,
            "workflow_file": record.workflow_file,
        },
    )


def record_blocked(db: Session, record: DeploymentRecordRow, exc: Exception) -> None:
    record_deployment_event(
        db,
        record,
        event_type="deployment_dispatch_blocked",
        actor=record.actor,
        status_from="requested",
        status_to="blocked",
        summary=str(exc)[:1000],
        payload={"workflow_file": record.workflow_file},
    )


def record_production_agent_review_started(
    db: Session, record: DeploymentRecordRow
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="production_agent_review_started",
        actor="agent_release_reviewer",
        status_from=str(record.status or "requested"),
        status_to=str(record.status or "requested"),
        summary="Production Approval Gate agent review started.",
        payload={
            "commit_sha": record.commit_sha,
            "workflow_file": record.workflow_file,
        },
    )


def record_production_agent_review_passed(
    db: Session, record: DeploymentRecordRow, approval: dict[str, object]
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="production_agent_review_passed",
        actor="agent_release_reviewer",
        status_from="requested",
        status_to="approved",
        summary="Production Approval Gate passed by agent release reviewer.",
        payload=approval,
    )


def record_production_agent_review_blocked(
    db: Session, record: DeploymentRecordRow, approval: dict[str, object]
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="production_agent_review_blocked",
        actor="agent_release_reviewer",
        status_from="requested",
        status_to="agent_blocked",
        summary="Production Approval Gate blocked promotion.",
        payload=approval,
    )


def record_production_dispatch_started(
    db: Session, record: DeploymentRecordRow
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="production_dispatch_started",
        actor=record.actor,
        status_from=str(record.status or "requested"),
        status_to="dispatching",
        summary="Production workflow dispatch started after approval.",
        payload={
            "workflow_file": record.workflow_file,
            "commit_sha": record.commit_sha,
        },
    )


def record_production_dispatch_failed(
    db: Session, record: DeploymentRecordRow, exc: Exception
) -> None:
    record_deployment_event(
        db,
        record,
        event_type="production_dispatch_failed",
        actor=record.actor,
        status_from="dispatching",
        status_to="failed",
        summary=str(exc)[:1000],
        payload={"workflow_file": record.workflow_file},
    )
