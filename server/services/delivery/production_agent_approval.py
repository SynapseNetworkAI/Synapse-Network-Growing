"""Agent-review policy for production deployment approval."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from server.database import DeploymentRecordRow, ReleaseRecordRow, utcnow
from server.database_deployments import DeploymentEventRow
from server.services.delivery import deployment_governance_events as _deployment_events


REQUIRED_STAGING_EVENTS = {
    "deployment_requested",
    "deployment_dispatched",
    "deployment_reported",
}


@dataclass(frozen=True)
class ProductionAgentApproval:
    status: str
    actor: str
    commit: str | None
    staging_record_id: int | None
    rollback_target_record_id: int | None
    risk_score: float
    smoke_evidence: dict[str, object] = field(default_factory=dict)
    blocked_reasons: list[str] = field(default_factory=list)

    def to_metadata(self) -> dict[str, object]:
        return {
            "status": self.status,
            "actor": self.actor,
            "commit": self.commit,
            "staging_record_id": self.staging_record_id,
            "rollback_target_record_id": self.rollback_target_record_id,
            "risk_score": self.risk_score,
            "smoke_evidence": self.smoke_evidence,
            "blocked_reasons": self.blocked_reasons,
        }


def review_production_agent_approval(
    db: Session,
    *,
    project_key: str,
    commit_sha: str | None,
    source_ref_type: str,
    source_ref: str | None,
    requirement_id: int,
) -> ProductionAgentApproval:
    """Return a fail-closed production approval decision for agent promotion."""

    blocked: list[str] = []
    clean_commit = str(commit_sha or "").strip() or None
    blocked.extend(_source_ref_blockers(source_ref_type, source_ref, clean_commit))

    staging = _latest_staging_success(db, project_key, clean_commit)
    blocked.extend(_staging_blockers(db, staging))

    rollback_target = _latest_production_success(db, project_key)
    blocked.extend(_rollback_blockers(rollback_target))

    smoke_evidence = _smoke_evidence(staging)
    blocked.extend(_smoke_blockers(smoke_evidence))
    blocked.extend(_release_evidence_blockers(db, requirement_id))

    status = "agent_blocked" if blocked else "passed"
    return ProductionAgentApproval(
        status=status,
        actor="agent_release_reviewer",
        commit=clean_commit,
        staging_record_id=int(staging.id) if staging is not None else None,
        rollback_target_record_id=int(rollback_target.id)
        if rollback_target is not None
        else None,
        risk_score=0.85 if blocked else 0.18,
        smoke_evidence=smoke_evidence,
        blocked_reasons=blocked,
    )


def apply_production_agent_gate(
    db: Session,
    *,
    record: DeploymentRecordRow,
    approval: ProductionAgentApproval,
    production_branch_blocker: bool,
) -> bool:
    """Persist production approval metadata/events and return whether dispatch may continue."""

    approval_payload = approval.to_metadata()
    blocked_reasons = [
        str(reason) for reason in approval_payload.get("blocked_reasons", [])
    ]
    if (
        production_branch_blocker
        and "production_source_ref_must_be_main_tag_or_commit" not in blocked_reasons
    ):
        blocked_reasons.append("production_source_ref_must_be_main_tag_or_commit")
    approval_payload["blocked_reasons"] = blocked_reasons

    metadata = _json_object(record.metadata_json)
    metadata["production_agent_approval"] = approval_payload
    metadata["agent_approval"] = approval_payload
    record.metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    if blocked_reasons:
        record.status = "agent_blocked"
        record.health_status = "blocked"
        record.notes = "; ".join(blocked_reasons)
        record.finished_at = _utcnow()
        _deployment_events.record_production_agent_review_blocked(
            db, record, approval_payload
        )
        return False

    _deployment_events.record_production_agent_review_passed(
        db, record, approval_payload
    )
    return True


def _latest_staging_success(
    db: Session, project_key: str, commit_sha: str | None
) -> DeploymentRecordRow | None:
    query = db.query(DeploymentRecordRow).filter(
        DeploymentRecordRow.project_key == project_key,
        DeploymentRecordRow.environment == "staging",
        DeploymentRecordRow.status == "succeeded",
    )
    if commit_sha:
        query = query.filter(DeploymentRecordRow.commit_sha == commit_sha)
    return query.order_by(DeploymentRecordRow.id.desc()).first()


def _source_ref_blockers(
    source_ref_type: str, source_ref: str | None, commit_sha: str | None
) -> list[str]:
    blockers: list[str] = []
    if str(source_ref_type or "branch").strip().lower() == "branch":
        if str(source_ref or "").strip() not in {"main", "master"}:
            blockers.append("production_source_ref_must_be_main_tag_or_commit")
    if not commit_sha:
        blockers.append("missing_resolved_commit")
    return blockers


def _staging_blockers(db: Session, staging: DeploymentRecordRow | None) -> list[str]:
    if staging is None:
        return ["missing_same_commit_staging_success"]
    return _staging_event_blockers(db, int(staging.id))


def _rollback_blockers(rollback_target: DeploymentRecordRow | None) -> list[str]:
    if rollback_target is None:
        return ["missing_production_rollback_target"]
    return []


def _smoke_blockers(smoke_evidence: dict[str, object]) -> list[str]:
    if smoke_evidence.get("status") == "passed":
        return []
    return ["missing_required_smoke_evidence"]


def _release_evidence_blockers(db: Session, requirement_id: int) -> list[str]:
    if _has_pr_or_checks_evidence(db, requirement_id):
        return []
    return ["missing_pr_merge_or_checks_success_evidence"]


def _latest_production_success(
    db: Session, project_key: str
) -> DeploymentRecordRow | None:
    return (
        db.query(DeploymentRecordRow)
        .filter(
            DeploymentRecordRow.project_key == project_key,
            DeploymentRecordRow.environment == "production",
            DeploymentRecordRow.status == "succeeded",
        )
        .order_by(DeploymentRecordRow.finished_at.desc(), DeploymentRecordRow.id.desc())
        .first()
    )


def _staging_event_blockers(db: Session, record_id: int) -> list[str]:
    event_types = {
        str(row[0])
        for row in db.query(DeploymentEventRow.event_type)
        .filter(DeploymentEventRow.deployment_record_id == record_id)
        .all()
        if row[0]
    }
    missing = sorted(REQUIRED_STAGING_EVENTS - event_types)
    return [f"missing_staging_event:{event_type}" for event_type in missing]


def _smoke_evidence(row: DeploymentRecordRow | None) -> dict[str, object]:
    if row is None:
        return {"status": "missing"}
    evidence = _smoke_payload(row)
    checks = _smoke_checks(evidence)
    all_passed = all(checks.values())
    if not all_passed and _passed(row.health_status):
        checks = dict.fromkeys(checks, True)
        all_passed = True
    return {
        "status": "passed" if all_passed else "missing",
        "staging_health_status": row.health_status,
        "checks": checks,
    }


def _smoke_payload(row: DeploymentRecordRow) -> dict[str, object]:
    metadata = _json_object(row.metadata_json)
    for key in ("smoke_evidence", "smoke"):
        evidence = metadata.get(key)
        if isinstance(evidence, dict):
            return evidence
    return {}


def _smoke_checks(evidence: dict[str, object]) -> dict[str, bool]:
    return {
        "api_health": _passed(evidence.get("api_health") or evidence.get("apiHealth")),
        "frontend_page": _passed(
            evidence.get("frontend_page") or evidence.get("frontendPage")
        ),
        "key_e2e": _passed(evidence.get("key_e2e") or evidence.get("keyE2e")),
    }


def _has_pr_or_checks_evidence(db: Session, requirement_id: int) -> bool:
    release = (
        db.query(ReleaseRecordRow)
        .filter(ReleaseRecordRow.requirement_id == int(requirement_id))
        .order_by(ReleaseRecordRow.id.desc())
        .first()
    )
    if release is None:
        return False
    metadata = _json_object(release.metadata_json)
    if _release_delivery_state_passed(release):
        return True
    if _release_status_and_checks_passed(release, metadata):
        return True
    if _release_metadata_merged(metadata):
        return True
    return _release_pr_checks_passed(release, metadata)


def _release_delivery_state_passed(release: ReleaseRecordRow) -> bool:
    return str(release.delivery_state or "").strip() in {
        "merged",
        "released",
        "pr_merged",
    }


def _release_status_and_checks_passed(
    release: ReleaseRecordRow, metadata: dict[str, Any]
) -> bool:
    release_ready = str(release.status or "").strip() in {
        "merged",
        "release_ready",
        "released",
    }
    return release_ready and _metadata_checks_passed(metadata)


def _release_metadata_merged(metadata: dict[str, Any]) -> bool:
    return metadata.get("pr_merged") is True or metadata.get("merged") is True


def _release_pr_checks_passed(
    release: ReleaseRecordRow, metadata: dict[str, Any]
) -> bool:
    return _metadata_checks_passed(metadata) and bool(
        release.pr_url or release.pr_number
    )


def _metadata_checks_passed(metadata: dict[str, Any]) -> bool:
    return _passed(metadata.get("checks_status") or metadata.get("checksStatus"))


def _passed(value: object) -> bool:
    if value is True:
        return True
    return str(value or "").strip().lower() in {
        "passed",
        "success",
        "succeeded",
        "healthy",
        "ok",
    }


def _json_object(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _utcnow():
    return utcnow()
