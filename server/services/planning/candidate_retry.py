from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from server.database import RequirementCandidateRow, utcnow
from server.services.planning.lifecycle import (
    _candidate_acceptance_contract,
    _json_dumps,
    _json_loads,
)
from server.services.requirements.acceptance import (
    AcceptanceValidationError,
    validate_acceptance_contract_for_execution,
)


def get_candidate(db: Session, candidate_id: int) -> RequirementCandidateRow | None:
    return db.get(RequirementCandidateRow, int(candidate_id))


def _validation_failed_candidate(
    db: Session, candidate_id: int
) -> RequirementCandidateRow:
    row = db.get(RequirementCandidateRow, candidate_id)
    if row is None:
        raise ValueError("candidate not found")
    if str(row.status or "") != "validation_failed":
        raise ValueError(
            f"candidate validation can only be retried from validation_failed, got {row.status}"
        )
    return row


def _record_retry_validation_error(
    db: Session, row: RequirementCandidateRow, exc: AcceptanceValidationError
) -> None:
    metadata = _json_loads(row.metadata_json, {})
    metadata["last_retry_validation_error"] = str(exc)
    metadata["last_retry_validation_at"] = utcnow().isoformat()
    row.metadata_json = _json_dumps(metadata)
    row.updated_at = utcnow()
    db.commit()


def _retry_metadata(
    row: RequirementCandidateRow, *, operator: str
) -> tuple[dict, datetime]:
    now = utcnow()
    metadata = _json_loads(row.metadata_json, {})
    metadata.pop("acceptance_validation_error", None)
    metadata["retry_of_candidate_id"] = int(row.id)
    metadata["retry_created_by"] = operator
    metadata["retry_created_at"] = now.isoformat()
    return metadata, now


def _text(value: object, fallback: str = "") -> str:
    return str(value if value else fallback)


def _new_retry_candidate(
    row: RequirementCandidateRow, *, metadata: dict, now: datetime
) -> RequirementCandidateRow:
    return RequirementCandidateRow(
        manifest_id=int(row.manifest_id),
        goal_key=_text(row.goal_key),
        candidate_fingerprint=f"{row.candidate_fingerprint}:retry:{int(now.timestamp())}:{int(row.id)}",
        title=_text(row.title),
        description_markdown=_text(row.description_markdown),
        project_id=int(row.project_id) if row.project_id else None,
        project_key=_text(row.project_key) or None,
        workflow_key=_text(row.workflow_key),
        priority=_text(row.priority, "normal"),
        risk_level=_text(row.risk_level, "normal"),
        confidence=float(row.confidence if row.confidence else 0.0),
        rationale=_text(row.rationale),
        expected_evidence_json=_text(row.expected_evidence_json, "[]"),
        status="pending",
        metadata_json=_json_dumps(metadata),
    )


def retry_candidate_validation(
    db: Session, candidate_id: int, *, operator: str = "operator"
) -> RequirementCandidateRow:
    row = _validation_failed_candidate(db, candidate_id)
    try:
        validate_acceptance_contract_for_execution(
            _candidate_acceptance_contract(row),
            source="planner_candidate_retry",
            goal_key=str(row.goal_key or ""),
        )
    except AcceptanceValidationError as exc:
        _record_retry_validation_error(db, row, exc)
        raise ValueError(str(exc)) from exc

    metadata, now = _retry_metadata(row, operator=operator)
    retry = _new_retry_candidate(row, metadata=metadata, now=now)
    db.add(retry)
    db.commit()
    db.refresh(retry)
    return retry
