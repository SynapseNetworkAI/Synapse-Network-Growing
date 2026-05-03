"""Release task PR gate projection helpers."""

from __future__ import annotations

from server.database import ReleaseTaskRow
from server.schemas import ReleaseTaskPrGateOut


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _copy_pr_gate(gate: ReleaseTaskPrGateOut) -> ReleaseTaskPrGateOut:
    payload = gate.model_dump() if hasattr(gate, "model_dump") else gate.dict()
    return ReleaseTaskPrGateOut(**payload)


def _can_create_pr(
    row: ReleaseTaskRow,
    gate: ReleaseTaskPrGateOut,
    *,
    status: str,
    environment: str,
    has_deployment: bool,
    direct_staging_branches: set[str],
) -> bool:
    return bool(
        status == "requested"
        and environment == "staging"
        and not has_deployment
        and gate.branch_exists
        and _clean(row.branch_name) not in direct_staging_branches
        and not gate.pr_exists
    )


def _can_deploy_staging(
    row: ReleaseTaskRow,
    gate: ReleaseTaskPrGateOut,
    *,
    status: str,
    environment: str,
    has_deployment: bool,
    direct_staging_branches: set[str],
) -> bool:
    is_open_pr_state = (gate.pr_state or "").lower() in {"open", "merged"}
    return bool(
        status == "requested"
        and environment == "staging"
        and not has_deployment
        and gate.branch_exists
        and (
            _clean(row.branch_name) in direct_staging_branches
            or (gate.pr_exists and is_open_pr_state and gate.checks_status == "success")
        )
    )


def release_task_pr_gate_with_row_actions(
    row: ReleaseTaskRow,
    gate: ReleaseTaskPrGateOut,
    *,
    direct_staging_branches: set[str],
) -> ReleaseTaskPrGateOut:
    """Attach row-specific actions to a GitHub PR gate snapshot.

    GitHub branch/PR/check state is shared by branch, but create/deploy actions
    depend on the local task row. Keeping this split lets list endpoints cache
    expensive GitHub reads without reusing stale action booleans.
    """

    gate = _copy_pr_gate(gate)
    status = _clean(row.status).lower() or "requested"
    environment = _clean(row.environment).lower()
    has_deployment = row.deployment_record_id is not None
    gate.can_create_pr = _can_create_pr(
        row,
        gate,
        status=status,
        environment=environment,
        has_deployment=has_deployment,
        direct_staging_branches=direct_staging_branches,
    )
    gate.can_deploy_staging = _can_deploy_staging(
        row,
        gate,
        status=status,
        environment=environment,
        has_deployment=has_deployment,
        direct_staging_branches=direct_staging_branches,
    )
    return gate
