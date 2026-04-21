from __future__ import annotations

import json

import pytest

from server.database import (
    AtomInvocationRow,
    BlackboardSnapshotRow,
    HumanGateRequestRow,
    NotificationDeliveryRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
)
from server.services.workflows.declarative import (
    AtomRegistry,
    AtomResult,
    WorkflowSpecError,
    build_agent_self_repair_workflow_spec,
    build_gateway_reliability_repair_workflow_spec,
    decide_human_gate,
    run_workflow_state_machine,
    validate_workflow_spec,
    workflow_blackboard,
)


@pytest.fixture(autouse=True)
def _disable_lark_webhooks(monkeypatch):
    for name in (
        "LARK_REQUIREMENT_WEBHOOK_URL",
        "LARK_ALERT_WEBHOOK_URL",
        "LARK_APPROVAL_WEBHOOK_URL",
        "LARK_RELEASE_WEBHOOK_URL",
    ):
        monkeypatch.setattr(f"server.config.{name}", "")


def _create_workflow_run(db_session, *, workflow_key: str = "agent_self_repair") -> WorkflowRunRow:
    requirement = RequirementRow(
        title="Agent Ops self repair",
        description_markdown="Detect Ops Dashboard traceback, repair it, verify, and open PR for human approval.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()
    initial_state = "detect_ops_failure"
    if workflow_key == "gateway_reliability_repair":
        initial_state = "detect_ops_failure"
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        workflow_key=workflow_key,
        current_state=initial_state,
        status="queued",
        triggered_by="test",
        blackboard_json=json.dumps({"trigger": {"source": "ops-dashboard"}, "current_state": initial_state}),
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_agent_self_repair_scenario_loops_once_then_awaits_final_regression(db_session):
    run = _create_workflow_run(db_session)
    spec = build_agent_self_repair_workflow_spec()
    registry = AtomRegistry()
    calls = {"patch": 0, "verify": 0}

    registry.register(
        "detect_ops_failure",
        lambda _ctx: AtomResult(
            summary="ops traceback detected",
            writes={"ops_failure_detected": True, "no_ops_failure": False},
        ),
    )
    registry.register(
        "collect_ops_logs",
        lambda _ctx: AtomResult(
            summary="ops logs collected",
            writes={
                "logs_collected": True,
                "logs_missing": False,
                "evidence": [{"kind": "log", "path": "server/logs/ops-dashboard.jsonl"}],
            },
        ),
    )
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: json.dumps(
            {
                "status": "completed",
                "summary": "TypeError from stale parser boundary",
                "writes": {"diagnosis": {"action": "patch", "module": "server/services/workflows/declarative.py"}},
            }
        ),
    )

    def patch_agent(_ctx):
        calls["patch"] += 1
        return {
            "status": "completed",
            "summary": f"patch attempt {calls['patch']}",
            "writes": {
                "patch_result": {
                    "changed_files_count": 1,
                    "changed_files": ["server/services/workflows/declarative.py"],
                    "attempt": calls["patch"],
                }
            },
        }

    def verify_atom(_ctx):
        calls["verify"] += 1
        if calls["verify"] == 1:
            return AtomResult(
                summary="targeted tests failed",
                writes={"verification": {"status": "failed", "failed_command": "pytest tests/test_declarative_workflow_factory.py"}},
            )
        return AtomResult(
            summary="targeted tests passed",
            writes={"verification": {"status": "passed", "command": "pytest tests/test_declarative_workflow_factory.py"}},
        )

    registry.register("ops_self_repair_coder", patch_agent)
    registry.register("run_ops_self_repair_verification", verify_atom)
    registry.register(
        "start_self_repair_final_regression",
        lambda _ctx: AtomResult(
            summary="final regression launched",
            writes={"ci": {"status": "in_progress", "ci_backend": "local_marker"}},
        ),
    )

    result = run_workflow_state_machine(
        db_session,
        workflow_run=run,
        spec=spec,
        registry=registry,
    )

    assert result.workflow_key == "agent_self_repair"
    assert result.final_state == "awaiting_ci"
    assert result.resolution == "waiting_for_final_regression"
    assert calls == {"patch": 2, "verify": 2}
    assert run.status == "awaiting_ci"
    assert run.current_state == "awaiting_ci"
    assert run.resolution == "waiting_for_final_regression"

    blackboard = workflow_blackboard(run)
    assert blackboard["current_state"] == "awaiting_ci"
    assert blackboard["counters"]["patch_attempts"] == 1
    assert blackboard["diagnosis"]["action"] == "patch"
    assert blackboard["verification"]["status"] == "passed"
    assert blackboard["ci"]["status"] == "in_progress"

    transition_events = (
        db_session.query(WorkflowStateEventRow)
        .filter(WorkflowStateEventRow.workflow_run_id == run.id)
        .order_by(WorkflowStateEventRow.id)
        .all()
    )
    transition_pairs = [(item.from_state, item.to_state) for item in transition_events]
    assert ("verify", "patch") in transition_pairs
    assert transition_pairs[-1] == ("start_final_regression", "awaiting_ci")

    transition_artifacts = db_session.query(WorkflowArtifactRow).filter(
        WorkflowArtifactRow.workflow_run_id == run.id,
        WorkflowArtifactRow.artifact_type == "workflow_transition_event",
    ).all()
    agent_raw_artifacts = db_session.query(WorkflowArtifactRow).filter(
        WorkflowArtifactRow.workflow_run_id == run.id,
        WorkflowArtifactRow.artifact_type == "workflow_agent_raw_output",
    ).all()
    invocations = db_session.query(AtomInvocationRow).filter(AtomInvocationRow.workflow_run_id == run.id).all()
    snapshots = db_session.query(BlackboardSnapshotRow).filter(BlackboardSnapshotRow.workflow_run_id == run.id).all()
    gates = db_session.query(HumanGateRequestRow).filter(HumanGateRequestRow.workflow_run_id == run.id).all()
    deliveries = db_session.query(NotificationDeliveryRow).all()
    assert len(transition_artifacts) == 0
    assert len(transition_events) == len(transition_pairs)
    assert len(agent_raw_artifacts) == 3
    assert len(invocations) == 8
    assert len(snapshots) >= len(transition_pairs)
    assert len(gates) == 0
    assert "alert" not in {row.channel for row in deliveries}


def test_workflow_spec_validation_rejects_unbounded_loop():
    spec = build_agent_self_repair_workflow_spec()
    spec["states"]["verify"]["transitions"] = [
        {"if": 'verification.status == "failed"', "goto": "patch"},
    ]

    with pytest.raises(WorkflowSpecError, match="counter guard"):
        validate_workflow_spec(spec)


def test_workflow_spec_validation_requires_agent_output_schema():
    spec = build_agent_self_repair_workflow_spec()
    del spec["states"]["diagnose"]["output_schema"]

    with pytest.raises(WorkflowSpecError, match="output_schema"):
        validate_workflow_spec(spec)


def test_verification_failure_exhausts_retry_budget_and_alerts(db_session):
    run = _create_workflow_run(db_session)
    spec = build_agent_self_repair_workflow_spec()
    registry = AtomRegistry()

    registry.register("detect_ops_failure", lambda _ctx: AtomResult(writes={"ops_failure_detected": True}))
    registry.register("collect_ops_logs", lambda _ctx: AtomResult(writes={"logs_collected": True}))
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: {"status": "completed", "writes": {"diagnosis": {"action": "patch"}}},
    )
    registry.register(
        "ops_self_repair_coder",
        lambda _ctx: {"status": "completed", "writes": {"patch_result": {"changed_files_count": 1}}},
    )
    registry.register(
        "run_ops_self_repair_verification",
        lambda _ctx: AtomResult(summary="tests failed", writes={"verification": {"status": "failed"}}),
    )

    result = run_workflow_state_machine(db_session, workflow_run=run, spec=spec, registry=registry)

    assert result.final_state == "awaiting_operator"
    assert run.status == "awaiting_operator"
    deliveries = db_session.query(NotificationDeliveryRow).all()
    assert "workflow_retry_budget_exhausted" in {row.event_type for row in deliveries}
    assert "alert" in {row.channel for row in deliveries}


def test_gateway_reliability_repair_observes_recovery_and_completes(db_session):
    run = _create_workflow_run(db_session, workflow_key="gateway_reliability_repair")
    spec = build_gateway_reliability_repair_workflow_spec()
    registry = AtomRegistry()

    registry.register(
        "detect_gateway_drift",
        lambda _ctx: AtomResult(summary="drift detected", writes={"gateway_drift_detected": True, "no_gateway_drift": False}),
    )
    registry.register(
        "collect_gateway_logs",
        lambda _ctx: AtomResult(summary="logs collected", writes={"logs_collected": True, "logs_missing": False}),
    )
    registry.register(
        "gateway_reliability_diagnoser",
        lambda _ctx: {
            "status": "completed",
            "summary": "gateway timeout pattern",
            "writes": {"diagnosis": {"action": "patch", "module": "gateway"}},
        },
    )
    registry.register(
        "gateway_reliability_coder",
        lambda _ctx: {
            "status": "completed",
            "summary": "gateway patch prepared",
            "writes": {"patch_result": {"changed_files_count": 1, "changed_files": ["services/gateway/gateway_fastapi.py"]}},
        },
    )
    registry.register(
        "run_gateway_verification",
        lambda _ctx: AtomResult(summary="gateway tests passed", writes={"verification": {"status": "passed"}}),
    )
    registry.register(
        "risk_evidence_gate",
        lambda _ctx: AtomResult(summary="low-risk gate", writes={"gate": {"decision": "auto_flow"}}),
    )
    registry.register(
        "open_gateway_repair_pr",
        lambda _ctx: AtomResult(summary="draft PR prepared", writes={"pr": {"created": True, "url": "https://github.com/example/repo/pull/2"}}),
    )
    registry.register(
        "observe_gateway_recovery",
        lambda _ctx: AtomResult(summary="gateway restored", writes={"observation": {"restored": True, "not_restored": False}}),
    )

    result = run_workflow_state_machine(db_session, workflow_run=run, spec=spec, registry=registry)

    assert result.workflow_key == "gateway_reliability_repair"
    assert result.final_state == "done"
    assert result.resolution == "completed"
    assert run.status == "succeeded"
    blackboard = workflow_blackboard(run)
    assert blackboard["gate"]["decision"] == "auto_flow"
    assert blackboard["observation"]["restored"] is True
    assert blackboard["verification"]["status"] == "passed"
    assert blackboard["verification"]["command_results"][0]["exit_code"] == 0
    assert blackboard["verification"]["command_results"][0]["simulated"] is True
    command_artifacts = db_session.query(WorkflowArtifactRow).filter(
        WorkflowArtifactRow.workflow_run_id == run.id,
        WorkflowArtifactRow.artifact_type == "workflow_command_result",
    ).all()
    assert command_artifacts
    deliveries = db_session.query(NotificationDeliveryRow).all()
    assert {"pr_opened", "workflow_run_succeeded"} <= {row.event_type for row in deliveries}
    assert "approval" not in {row.channel for row in deliveries}


def test_human_gate_decision_writes_back_to_blackboard(db_session):
    run = _create_workflow_run(db_session)
    spec = build_agent_self_repair_workflow_spec()
    registry = AtomRegistry()
    registry.register("detect_ops_failure", lambda _ctx: AtomResult(writes={"ops_failure_detected": True}))
    registry.register("collect_ops_logs", lambda _ctx: AtomResult(writes={"logs_collected": True}))
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: {"status": "completed", "writes": {"diagnosis": {"action": "needs_operator"}}},
    )
    run_workflow_state_machine(db_session, workflow_run=run, spec=spec, registry=registry)

    gate = db_session.query(HumanGateRequestRow).filter(HumanGateRequestRow.workflow_run_id == run.id).one()
    decide_human_gate(db_session, gate_id=int(gate.id), decision="reject", reviewer="tester", comment="unsafe")

    assert gate.status == "decided"
    assert gate.decision == "reject"
    assert run.status == "failed"
    assert workflow_blackboard(run)["human_gate_decisions"][0]["comment"] == "unsafe"
    assert "human_gate_request.decided" in {row.event_type for row in db_session.query(NotificationDeliveryRow).all()}
