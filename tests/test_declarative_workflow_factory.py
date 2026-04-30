from __future__ import annotations

import json
import sys

import pytest

import server.services.workflows.declarative as declarative_module
import server.services.workflows.acceptance_runtime as acceptance_runtime_module
from server.database import (
    AtomInvocationRow,
    BlackboardSnapshotRow,
    HumanGateRequestRow,
    NotificationDeliveryRow,
    NotificationEventRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
)
from server.services.workflows.declarative import (
    AtomRegistry,
    AtomResult,
    WorkflowSpecError,
    WorkflowContext,
    build_agent_self_repair_workflow_spec,
    build_gateway_reliability_repair_workflow_spec,
    decide_human_gate,
    default_atom_registry,
    run_workflow_state_machine,
    validate_workflow_spec,
    workflow_blackboard,
    _run_acceptance_command_result_artifact,
)
from server.services.workflows.acceptance_runtime import acceptance_execution_command
from server.services.workflows.gate_resume import previous_state_before_gate


@pytest.fixture(autouse=True)
def _disable_lark_webhooks(monkeypatch):
    for name in (
        "LARK_REQUIREMENT_WEBHOOK_URL",
        "LARK_ALERT_WEBHOOK_URL",
        "LARK_APPROVAL_WEBHOOK_URL",
        "LARK_RELEASE_WEBHOOK_URL",
    ):
        monkeypatch.setattr(f"server.config.{name}", "")


def _create_workflow_run(
    db_session, *, workflow_key: str = "agent_self_repair"
) -> WorkflowRunRow:
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
        blackboard_json=json.dumps(
            {"trigger": {"source": "ops-dashboard"}, "current_state": initial_state}
        ),
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
                "evidence": [
                    {"kind": "log", "path": "server/logs/ops-dashboard.jsonl"}
                ],
            },
        ),
    )
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: json.dumps(
            {
                "status": "completed",
                "summary": "TypeError from stale parser boundary",
                "writes": {
                    "diagnosis": {
                        "action": "patch",
                        "module": "server/services/workflows/declarative.py",
                    }
                },
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
                writes={
                    "verification": {
                        "status": "failed",
                        "failed_command": "pytest tests/test_declarative_workflow_factory.py",
                    }
                },
            )
        return AtomResult(
            summary="targeted tests passed",
            writes={
                "verification": {
                    "status": "passed",
                    "command": "pytest tests/test_declarative_workflow_factory.py",
                }
            },
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

    transition_artifacts = (
        db_session.query(WorkflowArtifactRow)
        .filter(
            WorkflowArtifactRow.workflow_run_id == run.id,
            WorkflowArtifactRow.artifact_type == "workflow_transition_event",
        )
        .all()
    )
    agent_raw_artifacts = (
        db_session.query(WorkflowArtifactRow)
        .filter(
            WorkflowArtifactRow.workflow_run_id == run.id,
            WorkflowArtifactRow.artifact_type == "workflow_agent_raw_output",
        )
        .all()
    )
    invocations = (
        db_session.query(AtomInvocationRow)
        .filter(AtomInvocationRow.workflow_run_id == run.id)
        .all()
    )
    snapshots = (
        db_session.query(BlackboardSnapshotRow)
        .filter(BlackboardSnapshotRow.workflow_run_id == run.id)
        .all()
    )
    gates = (
        db_session.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == run.id)
        .all()
    )
    deliveries = db_session.query(NotificationDeliveryRow).all()
    assert len(transition_artifacts) == 0
    assert len(transition_events) == len(transition_pairs)
    assert len(agent_raw_artifacts) == 3
    assert len(invocations) == 8
    assert len(snapshots) >= len(transition_pairs)
    assert len(gates) == 0
    assert "alert" not in {row.channel for row in deliveries}


def test_acceptance_command_runner_hard_times_out_and_records_kill_metadata(db_session):
    run = _create_workflow_run(db_session)
    ctx = WorkflowContext(
        db=db_session,
        workflow_run=run,
        requirement=run.requirement,
        spec=build_agent_self_repair_workflow_spec(),
        state_key="verify",
        state_spec={"atom": "run_ops_self_repair_verification"},
        blackboard=workflow_blackboard(run),
    )

    result = _run_acceptance_command_result_artifact(
        ctx,
        command=f'{sys.executable} -c "import time; time.sleep(5)"',
        purpose="Exercise hard timeout behavior.",
        step_key="timeout_step",
        timeout_seconds=1,
        kill_grace_seconds=1,
    )

    assert result["exit_code"] == 124
    assert result["timeout"] is True
    assert result["timeout_seconds"] == 1
    assert result["kill_grace_seconds"] == 1
    assert "command timed out after 1s" in result["stderr_excerpt"]
    assert result["step_key"] == "timeout_step"


def test_acceptance_execution_command_binds_portable_pytest_to_current_python(
    monkeypatch,
):
    monkeypatch.delenv("PYTHON_BIN", raising=False)
    monkeypatch.setattr(
        acceptance_runtime_module.os.path, "exists", lambda path: path == sys.executable
    )

    command = acceptance_execution_command(
        "PYTHONPATH=. python -m pytest tests/test_planning_mission_board.py -q -k traction"
    )

    assert command.startswith(f"PYTHONPATH=. {sys.executable} -m pytest ")
    assert "tests/test_planning_mission_board.py" in command
    assert " -k traction" in command


def test_acceptance_execution_command_handles_parse_and_non_pytest(monkeypatch):
    monkeypatch.setattr(acceptance_runtime_module.os.path, "exists", lambda path: False)

    assert (
        acceptance_execution_command("python -c 'print(1)'") == "python -c 'print(1)'"
    )
    assert acceptance_execution_command("PYTHONPATH=.") == "PYTHONPATH=."
    assert (
        acceptance_execution_command("python 'unterminated") == "python 'unterminated"
    )

    command = acceptance_execution_command("PYTHONPATH=. pytest -q")
    assert f"{acceptance_runtime_module.sys.executable} -m pytest -q" in command


def test_self_repair_verification_runs_acceptance_matrix_commands(
    db_session, monkeypatch
):
    run = _create_workflow_run(db_session)
    run.requirement.acceptance_contract_json = json.dumps(
        {
            "execution_acceptance_steps": [
                {
                    "step_key": "architecture_doc_search",
                    "title": "Architecture docs are searchable",
                    "expected_result": "The architecture doc contains the workflow constitution.",
                    "required_commands": [
                        'rg -n "Workflow Constraints" ARCHITECTURE.md'
                    ],
                    "required_evidence_types": ["workflow_command_result"],
                }
            ]
        }
    )
    db_session.flush()
    monkeypatch.setattr(
        "server.services.workflows.declarative._launch_final_regression_runner",
        lambda _runner_command, _env: None,
    )

    result = run_workflow_state_machine(
        db_session,
        workflow_run=run,
        spec=build_agent_self_repair_workflow_spec(),
        registry=default_atom_registry(),
    )

    assert result.final_state == "awaiting_ci"
    blackboard = workflow_blackboard(run)
    assert blackboard["verification"]["status"] == "passed"
    assert blackboard["verification"]["acceptance_matrix_status"] == "passed"
    assert blackboard["acceptance_matrix"]["status"] == "passed"
    assert blackboard["acceptance_matrix"]["current_command"] is None
    assert blackboard["acceptance_matrix"]["steps"][0]["status"] == "passed"
    commands = blackboard["verification"]["command_results"]
    assert any(
        command["command"] == 'rg -n "Workflow Constraints" ARCHITECTURE.md'
        and command["exit_code"] == 0
        for command in commands
    )


def test_self_repair_verification_skips_ops_compile_for_cross_project_requirements(
    db_session, monkeypatch
):
    run = _create_workflow_run(db_session)
    run.requirement.target_project_path = "/tmp"
    run.requirement.acceptance_contract_json = json.dumps(
        {
            "execution_acceptance_steps": [
                {
                    "step_key": "architecture_doc_search",
                    "title": "Architecture docs are searchable",
                    "expected_result": "The architecture doc contains the workflow constitution.",
                    "required_commands": [
                        'cd /Users/cliff/workspace/agent/Synapse-Network-Growing && rg -n "Workflow Constraints" ARCHITECTURE.md'
                    ],
                    "required_evidence_types": ["workflow_command_result"],
                }
            ]
        }
    )
    db_session.flush()
    monkeypatch.setattr(
        "server.services.workflows.declarative._launch_final_regression_runner",
        lambda _runner_command, _env: None,
    )

    result = run_workflow_state_machine(
        db_session,
        workflow_run=run,
        spec=build_agent_self_repair_workflow_spec(),
        registry=default_atom_registry(),
    )

    assert result.final_state == "awaiting_ci"
    commands = workflow_blackboard(run)["verification"]["command_results"]
    assert not any(
        "server/services/workflows/declarative.py" in item["command"]
        for item in commands
    )
    assert any(
        item["command"].startswith(
            "cd /Users/cliff/workspace/agent/Synapse-Network-Growing"
        )
        for item in commands
    )


def test_self_repair_verification_cannot_pass_when_acceptance_matrix_command_fails(
    db_session,
):
    run = _create_workflow_run(db_session)
    run.requirement.acceptance_contract_json = json.dumps(
        {
            "execution_acceptance_steps": [
                {
                    "step_key": "missing_marker",
                    "title": "Missing marker must fail",
                    "expected_result": "A nonexistent marker is present.",
                    "required_commands": [
                        'rg -n "definitely-not-present-acceptance-marker" ARCHITECTURE.md'
                    ],
                    "required_evidence_types": ["workflow_command_result"],
                }
            ]
        }
    )
    db_session.flush()

    result = run_workflow_state_machine(
        db_session,
        workflow_run=run,
        spec=build_agent_self_repair_workflow_spec(),
        registry=default_atom_registry(),
    )

    assert result.final_state == "awaiting_operator"
    blackboard = workflow_blackboard(run)
    assert blackboard["verification"]["status"] == "failed"
    assert blackboard["acceptance_matrix"]["status"] == "failed"
    assert "missing_marker" in blackboard["acceptance_matrix"]["failure_summary"]
    assert (
        "acceptance command failed"
        in blackboard["acceptance_matrix"]["failure_summary"]
    )


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

    registry.register(
        "detect_ops_failure",
        lambda _ctx: AtomResult(writes={"ops_failure_detected": True}),
    )
    registry.register(
        "collect_ops_logs", lambda _ctx: AtomResult(writes={"logs_collected": True})
    )
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: {
            "status": "completed",
            "writes": {"diagnosis": {"action": "patch"}},
        },
    )
    registry.register(
        "ops_self_repair_coder",
        lambda _ctx: {
            "status": "completed",
            "writes": {"patch_result": {"changed_files_count": 1}},
        },
    )
    registry.register(
        "run_ops_self_repair_verification",
        lambda _ctx: AtomResult(
            summary="tests failed", writes={"verification": {"status": "failed"}}
        ),
    )

    result = run_workflow_state_machine(
        db_session, workflow_run=run, spec=spec, registry=registry
    )

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
        lambda _ctx: AtomResult(
            summary="drift detected",
            writes={"gateway_drift_detected": True, "no_gateway_drift": False},
        ),
    )
    registry.register(
        "collect_gateway_logs",
        lambda _ctx: AtomResult(
            summary="logs collected",
            writes={"logs_collected": True, "logs_missing": False},
        ),
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
            "writes": {
                "patch_result": {
                    "changed_files_count": 1,
                    "changed_files": ["services/gateway/gateway_fastapi.py"],
                }
            },
        },
    )
    registry.register(
        "run_gateway_verification",
        lambda _ctx: AtomResult(
            summary="gateway tests passed",
            writes={"verification": {"status": "passed"}},
        ),
    )
    registry.register(
        "risk_evidence_gate",
        lambda _ctx: AtomResult(
            summary="low-risk gate", writes={"gate": {"decision": "auto_flow"}}
        ),
    )
    registry.register(
        "open_gateway_repair_pr",
        lambda _ctx: AtomResult(
            summary="draft PR prepared",
            writes={
                "pr": {"created": True, "url": "https://github.com/example/repo/pull/2"}
            },
        ),
    )
    registry.register(
        "observe_gateway_recovery",
        lambda _ctx: AtomResult(
            summary="gateway restored",
            writes={"observation": {"restored": True, "not_restored": False}},
        ),
    )

    result = run_workflow_state_machine(
        db_session, workflow_run=run, spec=spec, registry=registry
    )

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
    command_artifacts = (
        db_session.query(WorkflowArtifactRow)
        .filter(
            WorkflowArtifactRow.workflow_run_id == run.id,
            WorkflowArtifactRow.artifact_type == "workflow_command_result",
        )
        .all()
    )
    assert command_artifacts
    deliveries = db_session.query(NotificationDeliveryRow).all()
    assert "pr_opened" in {row.event_type for row in deliveries}
    succeeded_event = (
        db_session.query(NotificationEventRow)
        .filter(NotificationEventRow.event_type == "workflow_run_succeeded")
        .one()
    )
    assert succeeded_event.channel == "digest"
    assert succeeded_event.status == "digest"
    assert "approval" not in {row.channel for row in deliveries}


def test_human_gate_decision_writes_back_to_blackboard(db_session):
    run = _create_workflow_run(db_session)
    spec = build_agent_self_repair_workflow_spec()
    registry = AtomRegistry()
    registry.register(
        "detect_ops_failure",
        lambda _ctx: AtomResult(writes={"ops_failure_detected": True}),
    )
    registry.register(
        "collect_ops_logs", lambda _ctx: AtomResult(writes={"logs_collected": True})
    )
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: {
            "status": "completed",
            "writes": {"diagnosis": {"action": "needs_operator"}},
        },
    )
    run_workflow_state_machine(
        db_session, workflow_run=run, spec=spec, registry=registry
    )

    gate = (
        db_session.query(HumanGateRequestRow)
        .filter(HumanGateRequestRow.workflow_run_id == run.id)
        .one()
    )
    decide_human_gate(
        db_session,
        gate_id=int(gate.id),
        decision="reject",
        reviewer="tester",
        comment="unsafe",
    )

    assert gate.status == "decided"
    assert gate.decision == "reject"
    assert run.status == "failed"
    assert workflow_blackboard(run)["human_gate_decisions"][0]["comment"] == "unsafe"
    assert "human_gate_request.decided" in {
        row.event_type for row in db_session.query(NotificationDeliveryRow).all()
    }


def test_human_gate_continue_retry_preserves_resume_blackboard_updates(
    db_session, monkeypatch
):
    run = _create_workflow_run(db_session)
    run.current_state = "awaiting_operator"
    run.status = "awaiting_operator"
    run.blackboard_json = json.dumps(
        {
            "current_state": "awaiting_operator",
            "ci": {"ci_exit_code_path": "old-marker"},
        }
    )
    gate = HumanGateRequestRow(
        workflow_run_id=int(run.id),
        state_key="awaiting_operator",
        gate_type="ci_final_regression_failed",
        risk_level="normal",
        status="pending",
        reason="Final regression failed.",
    )
    db_session.add(gate)
    db_session.flush()

    def fake_resume(db, *, gate, decision, blackboard):
        latest = workflow_blackboard(gate.workflow_run)
        latest["ci"] = {"ci_exit_code_path": "new-marker"}
        latest["current_state"] = "awaiting_ci"
        gate.workflow_run.blackboard_json = json.dumps(latest)
        gate.workflow_run.current_state = "awaiting_ci"
        gate.workflow_run.status = "awaiting_ci"
        gate.workflow_run.resolution = "waiting_for_final_regression"
        db.flush()
        return {"resume_status": "resumed", "next_state": "awaiting_ci"}

    monkeypatch.setattr(
        declarative_module, "resume_workflow_after_gate_decision", fake_resume
    )

    decide_human_gate(
        db_session,
        gate_id=int(gate.id),
        decision="continue_retry",
        reviewer="tester",
        comment="retry",
    )

    blackboard = workflow_blackboard(run)
    assert blackboard["ci"]["ci_exit_code_path"] == "new-marker"
    assert blackboard["human_gate_decisions"][0]["comment"] == "retry"


def test_continue_retry_resumes_latest_non_gate_state_after_gate_self_loop(
    db_session, monkeypatch
):
    run = _create_workflow_run(db_session)
    run.current_state = "awaiting_operator"
    run.status = "awaiting_operator"
    db_session.add_all(
        [
            WorkflowStateEventRow(
                workflow_run_id=int(run.id),
                from_state="verify",
                to_state="awaiting_operator",
                condition='verification.status == "failed"',
            ),
            WorkflowStateEventRow(
                workflow_run_id=int(run.id),
                from_state="awaiting_operator",
                to_state="awaiting_operator",
                condition="operator.continue_retry",
            ),
        ]
    )
    gate = HumanGateRequestRow(
        workflow_run_id=int(run.id),
        state_key="awaiting_operator",
        gate_type="human_gate",
        risk_level="normal",
        status="pending",
        reason="Verification failed.",
    )
    db_session.add(gate)
    db_session.flush()

    assert (
        previous_state_before_gate(
            db_session, run, gate, default_state="awaiting_operator"
        )
        == "verify"
    )

    def fake_run_workflow_state_machine(
        db, *, workflow_run, spec, registry, initial_blackboard
    ):
        workflow_run.status = "pending"
        workflow_run.current_state = initial_blackboard["current_state"]
        db.flush()
        return workflow_run

    monkeypatch.setattr(
        declarative_module,
        "run_workflow_state_machine",
        fake_run_workflow_state_machine,
    )

    result = declarative_module.resume_workflow_after_gate_decision(
        db_session,
        gate=gate,
        decision="continue_retry",
        blackboard=workflow_blackboard(run),
    )

    assert result["resume_status"] == "resumed"
    assert result["next_state"] == "verify"
    assert run.current_state == "verify"
    assert run.status == "pending"
