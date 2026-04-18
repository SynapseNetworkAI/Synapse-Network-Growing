from __future__ import annotations

import json

import pytest

from server.database import ArtifactRow, ExecutionRunRow, RequirementRow
from server.services.workflows.declarative import (
    AtomRegistry,
    AtomResult,
    WorkflowSpecError,
    build_agent_self_repair_workflow_spec,
    run_workflow_state_machine,
    validate_workflow_spec,
    workflow_blackboard,
)


def _create_execution_run(db_session) -> ExecutionRunRow:
    requirement = RequirementRow(
        title="Agent Ops self repair",
        description_markdown="Detect Ops Dashboard traceback, repair it, verify, and open PR for human approval.",
        target_project_path="/Users/cliff/workspace/agent/Synapse-Network-Growing",
    )
    db_session.add(requirement)
    db_session.flush()
    run = ExecutionRunRow(
        requirement_id=int(requirement.id),
        execution_mode="state_machine",
        execution_kind="agent_self_repair",
        status="queued",
        phase="queued",
        attempt_state="queued",
        plan_snapshot_json=json.dumps({"blackboard": {"trigger": {"source": "ops-dashboard"}}}),
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_agent_self_repair_scenario_loops_once_then_routes_to_human(db_session):
    run = _create_execution_run(db_session)
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
        "open_self_repair_pr",
        lambda _ctx: AtomResult(
            summary="draft PR prepared for human approval",
            writes={"pr": {"created": True, "url": "https://github.com/example/synapse-network-growing/pull/1"}},
            risk_flags=("self_modification_requires_human",),
        ),
    )

    result = run_workflow_state_machine(
        db_session,
        execution_run=run,
        spec=spec,
        registry=registry,
    )

    assert result.workflow_key == "agent_self_repair"
    assert result.final_state == "awaiting_operator"
    assert result.resolution == "route_to_human"
    assert calls == {"patch": 2, "verify": 2}
    assert run.status == "blocked"
    assert run.attempt_state == "route_to_human"

    blackboard = workflow_blackboard(run)
    assert blackboard["current_state"] == "awaiting_operator"
    assert blackboard["counters"]["patch_attempts"] == 1
    assert blackboard["diagnosis"]["action"] == "patch"
    assert blackboard["verification"]["status"] == "passed"
    assert "self_modification_requires_human" in blackboard["risk_flags"]

    transition_pairs = [
        (item["from_state"], item["to_state"])
        for item in blackboard["transition_history"]
    ]
    assert ("verify", "patch") in transition_pairs
    assert transition_pairs[-1] == ("open_pr", "awaiting_operator")

    transition_artifacts = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == run.requirement_id,
        ArtifactRow.artifact_type == "workflow_transition_event",
    ).all()
    agent_raw_artifacts = db_session.query(ArtifactRow).filter(
        ArtifactRow.requirement_id == run.requirement_id,
        ArtifactRow.artifact_type == "workflow_agent_raw_output",
    ).all()
    transition_artifacts = [
        artifact
        for artifact in transition_artifacts
        if json.loads(str(artifact.machine_readable_payload or "{}")).get("execution_run_id") == run.id
    ]
    agent_raw_artifacts = [
        artifact
        for artifact in agent_raw_artifacts
        if json.loads(str(artifact.machine_readable_payload or "{}")).get("execution_run_id") == run.id
    ]
    assert len(transition_artifacts) == len(transition_pairs)
    assert len(agent_raw_artifacts) == 3


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
