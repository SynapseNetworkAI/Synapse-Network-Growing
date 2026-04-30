from __future__ import annotations

from sqlalchemy.orm import Session

from server.database import HumanGateRequestRow, WorkflowRunRow, WorkflowStateEventRow


def previous_state_before_gate(
    db: Session, run: WorkflowRunRow, gate: HumanGateRequestRow, *, default_state: str
) -> str:
    gate_state = str(gate.state_key or "awaiting_operator")
    event = (
        db.query(WorkflowStateEventRow)
        .filter(
            WorkflowStateEventRow.workflow_run_id == int(run.id),
            WorkflowStateEventRow.to_state == gate_state,
            WorkflowStateEventRow.from_state.isnot(None),
            WorkflowStateEventRow.from_state != gate_state,
        )
        .order_by(WorkflowStateEventRow.id.desc())
        .first()
    )
    return (
        str(event.from_state)
        if event is not None and event.from_state
        else str(default_state)
    )
