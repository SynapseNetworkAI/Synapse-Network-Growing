from __future__ import annotations

"""Deterministic routing for planner candidates.

The router decides whether a freshly created candidate may be promoted into the
declarative workflow rail. Business intent stays in the Operating Manifest;
automation permission lives here and in project/workflow policy.
"""

from dataclasses import dataclass
from typing import Mapping

from sqlalchemy.orm import Session

from server.database import ProjectPolicyRow, RequirementCandidateRow
from server.services.result_objects import ServiceObjectResult
from server.services.workflows.declarative import built_in_workflow_specs


ROUTER_POLICY_VERSION = "candidate_risk_router_v1"
AUTO_START_WORKFLOWS = {"gateway_reliability_repair", "agent_self_repair"}
LOW_RISK_LEVELS = {"low", "normal"}
HIGH_RISK_LEVELS = {"high", "critical"}
FORBIDDEN_ATOM_TOKENS = {
    "production_deploy",
    "funds",
    "settlement",
    "contract",
    "auth",
    "credential",
    "secret",
    "external_paid",
    "public_post",
}


@dataclass(frozen=True)
class CandidateRoutingDecision:
    decision: str
    reason: str
    policy_version: str = ROUTER_POLICY_VERSION

    def to_dict(self) -> ServiceObjectResult:
        return ServiceObjectResult(
            {
                "decision": self.decision,
                "reason": self.reason,
                "policy_version": self.policy_version,
            }
        )


def route_candidate(db: Session, candidate: RequirementCandidateRow) -> CandidateRoutingDecision:
    """Return the safest deterministic action for a candidate."""

    risk_level = str(candidate.risk_level or "normal").strip().lower() or "normal"
    workflow_key = str(candidate.workflow_key or "").strip()
    if risk_level in HIGH_RISK_LEVELS:
        return CandidateRoutingDecision("pending_operator_review", f"risk_level_{risk_level}")
    if risk_level not in LOW_RISK_LEVELS:
        return CandidateRoutingDecision("pending_operator_review", f"unsupported_risk_level_{risk_level}")
    if workflow_key not in AUTO_START_WORKFLOWS:
        return CandidateRoutingDecision("pending_operator_review", "workflow_not_allowlisted")
    if _workflow_has_forbidden_atom(workflow_key):
        return CandidateRoutingDecision("blocked_requires_operator", "workflow_contains_forbidden_atom")
    if _project_policy_requires_review(db, candidate):
        return CandidateRoutingDecision("pending_operator_review", "project_policy_requires_manual_review")
    return CandidateRoutingDecision("auto_materialize_and_start", "low_risk_allowlisted_workflow")


def _workflow_has_forbidden_atom(workflow_key: str) -> bool:
    spec = built_in_workflow_specs().get(workflow_key)
    if not isinstance(spec, Mapping):
        return True
    states = spec.get("states") if isinstance(spec.get("states"), Mapping) else {}
    for state in states.values():
        if not isinstance(state, Mapping):
            continue
        atom_key = str(state.get("atom") or state.get("agent") or "").strip().lower()
        if any(token in atom_key for token in FORBIDDEN_ATOM_TOKENS):
            return True
    return False


def _project_policy_requires_review(db: Session, candidate: RequirementCandidateRow) -> bool:
    project_key = str(candidate.project_key or "").strip()
    if not project_key:
        return False
    policy = db.query(ProjectPolicyRow).filter(ProjectPolicyRow.project_key == project_key).first()
    if policy is None:
        return False
    if str(policy.status or "active") != "active":
        return True
    autonomy_mode = str(policy.autonomy_mode or "").strip().lower()
    if autonomy_mode in {"execute_autonomously", "autonomous", "auto"}:
        return False
    return bool(policy.requires_manual_approval)
