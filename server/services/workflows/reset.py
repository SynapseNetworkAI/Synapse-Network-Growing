"""Reset helpers for the declarative workflow control plane."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from server.database import (
    AtomInvocationRow,
    BlackboardSnapshotRow,
    DeploymentRecordRow,
    HumanGateRequestRow,
    ReleaseRecordRow,
    RequirementAcceptanceCheckRow,
    RequirementAttachmentRow,
    RequirementDependencyRow,
    RequirementRow,
    ValidationRecordRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
)


def _delete_all(db: Session, model: Any) -> int:
    count = int(db.query(model).count())
    db.query(model).delete(synchronize_session=False)
    return count


def reset_declarative_runtime_data(db: Session) -> dict[str, int]:
    """Clear derived workflow runtime data while preserving requirements."""

    summary: dict[str, int] = {}
    summary["requirements_detached"] = int(
        db.query(RequirementRow).filter(RequirementRow.active_workflow_run_id.isnot(None)).count()
    )
    db.query(RequirementRow).update(
        {
            "active_workflow_run_id": None,
            "workflow_state": "draft",
            "phase": "draft",
            "assets_status": "pending",
            "attention_reason": None,
            "failure_reason": None,
            "recovery_status": None,
        },
        synchronize_session=False,
    )
    db.flush()

    for key, model in (
        ("human_gate_requests_deleted", HumanGateRequestRow),
        ("atom_invocations_deleted", AtomInvocationRow),
        ("blackboard_snapshots_deleted", BlackboardSnapshotRow),
        ("workflow_artifacts_deleted", WorkflowArtifactRow),
        ("workflow_state_events_deleted", WorkflowStateEventRow),
        ("validation_records_deleted", ValidationRecordRow),
        ("release_records_deleted", ReleaseRecordRow),
        ("deployment_records_deleted", DeploymentRecordRow),
        ("workflow_runs_deleted", WorkflowRunRow),
    ):
        summary[key] = _delete_all(db, model)

    db.commit()
    return summary


def reset_company_ops_state_data(db: Session) -> dict[str, int]:
    """Clear requirement and workflow state for a local destructive reset."""

    summary = reset_declarative_runtime_data(db)
    db.query(RequirementRow).update(
        {
            "linked_requirement_id": None,
            "followup_requirement_id": None,
            "origin_validation_id": None,
            "requirement_candidate_id": None,
        },
        synchronize_session=False,
    )
    db.flush()
    for key, model in (
        ("requirement_dependencies_deleted", RequirementDependencyRow),
        ("acceptance_checks_deleted", RequirementAcceptanceCheckRow),
        ("requirement_attachments_deleted", RequirementAttachmentRow),
        ("requirements_deleted", RequirementRow),
    ):
        summary[key] = _delete_all(db, model)

    db.commit()
    return summary
