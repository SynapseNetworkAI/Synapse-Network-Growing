"""Declarative workflow state machine runner with Blackboard persistence."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from server.database import (
    AtomInvocationRow,
    BlackboardSnapshotRow,
    HumanGateRequestRow,
    RequirementRow,
    WorkflowArtifactRow,
    WorkflowDefinitionRow,
    WorkflowRunRow,
    WorkflowStateEventRow,
    utcnow,
)


class WorkflowSpecError(ValueError):
    """Raised when a declarative workflow spec is invalid."""


class WorkflowRuntimeError(RuntimeError):
    """Raised when a declarative workflow run cannot safely continue."""


@dataclass(frozen=True)
class AtomResult:
    """Normalized output from an agent or deterministic atom."""

    status: str = "completed"
    summary: str = ""
    writes: Mapping[str, Any] = field(default_factory=dict)
    raw_output: Any = None
    artifacts: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()


@dataclass
class WorkflowContext:
    """Runtime context passed to workflow atoms."""

    db: Session
    workflow_run: WorkflowRunRow
    requirement: RequirementRow
    spec: Mapping[str, Any]
    state_key: str
    state_spec: Mapping[str, Any]
    blackboard: dict[str, Any]


@dataclass(frozen=True)
class WorkflowRunResult:
    """Summary returned after a declarative workflow reaches a terminal state."""

    workflow_key: str
    final_state: str
    resolution: str
    transition_count: int
    blackboard: Mapping[str, Any]


AtomCallable = Callable[[WorkflowContext], AtomResult | Mapping[str, Any] | str]


class AtomRegistry:
    """Registry of governed deterministic and agent atoms."""

    def __init__(self) -> None:
        self._atoms: dict[str, AtomCallable] = {}

    def register(self, key: str, handler: AtomCallable) -> None:
        """Register an atom handler by key."""

        normalized = str(key or "").strip()
        if not normalized:
            raise WorkflowSpecError("atom key must not be empty")
        self._atoms[normalized] = handler

    def get(self, key: str) -> AtomCallable:
        """Return the registered handler for a workflow atom."""

        normalized = str(key or "").strip()
        try:
            return self._atoms[normalized]
        except KeyError as exc:
            raise WorkflowRuntimeError(f"workflow atom is not registered: {normalized}") from exc


def build_agent_self_repair_workflow_spec() -> dict[str, Any]:
    """Return the built-in scenario-1 workflow for Agent Ops self-repair."""

    return {
        "workflow_key": "agent_self_repair",
        "version": 1,
        "description": "Repair Agent Ops failures with bounded same-session patch/verify loop.",
        "initial_state": "detect_ops_failure",
        "limits": {
            "max_patch_attempts": 2,
            "max_transitions": 20,
        },
        "blackboard": {
            "persist_keys": [
                "workflow_key",
                "current_state",
                "limits",
                "counters",
                "trigger",
                "logs_collected",
                "ops_failure_detected",
                "diagnosis",
                "patch_result",
                "verification",
                "pr",
                "risk_flags",
                "evidence",
                "artifacts",
                "state_outputs",
                "transition_history",
                "human_gate_decisions",
            ]
        },
        "states": {
            "detect_ops_failure": {
                "atom": "detect_ops_failure",
                "transitions": [
                    {"if": "ops_failure_detected", "goto": "collect_logs"},
                    {"if": "no_ops_failure", "goto": "done"},
                ],
            },
            "collect_logs": {
                "atom": "collect_ops_logs",
                "transitions": [
                    {"if": "logs_collected", "goto": "diagnose"},
                    {"if": "logs_missing", "goto": "awaiting_operator"},
                ],
            },
            "diagnose": {
                "agent": "ops_self_repair_diagnoser",
                "output_key": "diagnosis",
                "output_schema": "schemas/ops_self_repair_diagnosis.schema.json",
                "transitions": [
                    {"if": 'diagnosis.action == "patch"', "goto": "patch"},
                    {"if": 'diagnosis.action == "needs_operator"', "goto": "awaiting_operator"},
                    {"if": 'diagnosis.action == "no_issue_found"', "goto": "done"},
                ],
            },
            "patch": {
                "agent": "ops_self_repair_coder",
                "output_key": "patch_result",
                "output_schema": "schemas/ops_self_repair_patch.schema.json",
                "transitions": [
                    {"if": "patch_result.changed_files_count > 0", "goto": "verify"},
                    {"if": "counters.patch_attempts >= limits.max_patch_attempts", "goto": "awaiting_operator"},
                ],
            },
            "verify": {
                "atom": "run_ops_self_repair_verification",
                "output_key": "verification",
                "transitions": [
                    {"if": 'verification.status == "passed"', "goto": "open_pr"},
                    {
                        "if": 'verification.status == "failed" and counters.patch_attempts < limits.max_patch_attempts',
                        "increment": "patch_attempts",
                        "goto": "patch",
                    },
                    {"if": 'verification.status == "failed"', "goto": "awaiting_operator"},
                ],
            },
            "open_pr": {
                "atom": "open_self_repair_pr",
                "output_key": "pr",
                "transitions": [
                    {"if": "pr.created", "goto": "awaiting_operator"},
                    {"if": "pr.failed", "goto": "awaiting_operator"},
                ],
            },
            "awaiting_operator": {
                "terminal": True,
                "resolution": "route_to_human",
            },
            "done": {
                "terminal": True,
                "resolution": "completed",
            },
        },
    }


def build_gateway_reliability_repair_workflow_spec() -> dict[str, Any]:
    """Return the first product-facing reliability repair workflow spec."""

    spec = build_agent_self_repair_workflow_spec()
    spec["workflow_key"] = "gateway_reliability_repair"
    spec["description"] = "Repair Synapse Gateway reliability drift with verification and observation."
    spec["blackboard"]["persist_keys"] = sorted(
        set(spec["blackboard"]["persist_keys"])
        | {
            "gateway_drift_detected",
            "no_gateway_drift",
            "gate",
            "observation",
        }
    )
    spec["states"]["detect_ops_failure"] = {
        "atom": "detect_gateway_drift",
        "transitions": [
            {"if": "gateway_drift_detected", "goto": "collect_logs"},
            {"if": "no_gateway_drift", "goto": "done"},
        ],
    }
    spec["states"]["collect_logs"]["atom"] = "collect_gateway_logs"
    spec["states"]["diagnose"]["agent"] = "gateway_reliability_diagnoser"
    spec["states"]["patch"]["agent"] = "gateway_reliability_coder"
    spec["states"]["verify"]["atom"] = "run_gateway_verification"
    spec["states"]["verify"]["transitions"][0]["goto"] = "risk_gate"
    spec["states"]["risk_gate"] = {
        "atom": "risk_evidence_gate",
        "output_key": "gate",
        "transitions": [
            {"if": 'gate.decision == "auto_flow"', "goto": "open_pr"},
            {"if": 'gate.decision == "human_required"', "goto": "awaiting_operator"},
        ],
    }
    spec["states"]["open_pr"]["atom"] = "open_gateway_repair_pr"
    spec["states"]["open_pr"]["transitions"] = [
        {"if": "pr.created", "goto": "observing"},
        {"if": "pr.failed", "goto": "awaiting_operator"},
    ]
    spec["states"]["observing"] = {
        "atom": "observe_gateway_recovery",
        "output_key": "observation",
        "transitions": [
            {"if": "observation.restored", "goto": "done"},
            {
                "if": "observation.not_restored and counters.patch_attempts < limits.max_patch_attempts",
                "increment": "patch_attempts",
                "goto": "patch",
            },
            {"if": "observation.not_restored", "goto": "awaiting_operator"},
        ],
    }
    return spec


def built_in_workflow_specs() -> dict[str, dict[str, Any]]:
    """Return built-in declarative workflow specs keyed by workflow key."""

    specs = {
        "agent_self_repair": build_agent_self_repair_workflow_spec(),
        "gateway_reliability_repair": build_gateway_reliability_repair_workflow_spec(),
    }
    return specs


def ensure_builtin_workflow_definitions(db: Session) -> None:
    """Persist built-in workflow definitions for API discovery."""

    for workflow_key, spec in built_in_workflow_specs().items():
        row = db.query(WorkflowDefinitionRow).filter(WorkflowDefinitionRow.workflow_key == workflow_key).first()
        spec_json = _json_dump(spec)
        if row is None:
            row = WorkflowDefinitionRow(
                workflow_key=workflow_key,
                version=int(spec.get("version") or 1),
                title=str(spec.get("description") or workflow_key),
                status="active",
                spec_json=spec_json,
            )
            db.add(row)
        else:
            row.version = int(spec.get("version") or row.version or 1)
            row.title = str(spec.get("description") or row.title or workflow_key)
            row.status = "active"
            row.spec_json = spec_json
            row.updated_at = utcnow()
    db.flush()


def list_workflow_definitions(db: Session) -> list[dict[str, Any]]:
    """Return active built-in and persisted workflow definitions."""

    ensure_builtin_workflow_definitions(db)
    rows = db.query(WorkflowDefinitionRow).order_by(WorkflowDefinitionRow.workflow_key.asc()).all()
    return [
        {
            "id": int(row.id),
            "workflow_key": row.workflow_key,
            "version": int(row.version or 1),
            "title": row.title,
            "status": row.status,
            "spec": _json_load(row.spec_json, {}),
        }
        for row in rows
    ]


def create_declarative_workflow_run(
    db: Session,
    *,
    requirement: RequirementRow,
    workflow_key: str,
    triggered_by: str = "system",
    initial_blackboard: Mapping[str, Any] | None = None,
    run_immediately: bool = True,
    registry: AtomRegistry | None = None,
) -> WorkflowRunRow:
    """Create and optionally run a new declarative workflow run for a requirement."""

    specs = built_in_workflow_specs()
    if workflow_key not in specs:
        raise WorkflowSpecError(f"unknown workflow_key: {workflow_key}")
    spec = specs[workflow_key]
    validate_workflow_spec(spec)
    blackboard = dict(initial_blackboard or {})
    blackboard.setdefault("trigger", {})
    blackboard.setdefault("workflow_key", workflow_key)
    blackboard.setdefault("current_state", str(spec["initial_state"]))
    run = WorkflowRunRow(
        requirement_id=int(requirement.id),
        plan_version=1,
        workflow_key=workflow_key,
        current_state=str(spec["initial_state"]),
        status="pending",
        triggered_by=triggered_by,
        risk_level=str(blackboard.get("risk_level") or "normal"),
        retry_counters_json="{}",
        blackboard_json=_json_dump(blackboard),
    )
    db.add(run)
    db.flush()
    requirement.active_workflow_run_id = int(run.id)
    requirement.workflow_family = "declarative_state_machine"
    requirement.workflow_state = "executing" if run_immediately else "ready"
    requirement.status = "in_progress" if run_immediately else "ready"
    requirement.phase = "executing" if run_immediately else "ready"
    db.flush()
    if run_immediately:
        run_workflow_state_machine(
            db,
            workflow_run=run,
            spec=spec,
            registry=registry or default_atom_registry(),
            initial_blackboard=blackboard,
        )
        if run.status == "succeeded":
            requirement.workflow_state = "completed"
            requirement.status = "completed"
            requirement.phase = "completed"
            requirement.completed_at = requirement.completed_at or utcnow()
        elif run.status == "awaiting_operator":
            requirement.workflow_state = "awaiting_operator"
            requirement.status = "blocked"
            requirement.phase = "blocked"
        db.flush()
    return run


def default_atom_registry() -> AtomRegistry:
    """Build the default governed atom registry for first-phase workflows."""

    registry = AtomRegistry()

    def _trigger(ctx: WorkflowContext) -> dict[str, Any]:
        return dict(ctx.blackboard.get("trigger") or {})

    registry.register(
        "detect_ops_failure",
        lambda ctx: AtomResult(
            summary="Ops failure signal evaluated",
            writes={
                "ops_failure_detected": bool(_trigger(ctx).get("ops_failure_detected", True)),
                "no_ops_failure": not bool(_trigger(ctx).get("ops_failure_detected", True)),
            },
        ),
    )
    registry.register(
        "collect_ops_logs",
        lambda _ctx: AtomResult(
            summary="Ops logs collected",
            writes={
                "logs_collected": True,
                "logs_missing": False,
                "evidence": [{"kind": "log", "path": "server/logs/ops-dashboard.jsonl"}],
            },
        ),
    )
    registry.register(
        "ops_self_repair_diagnoser",
        lambda _ctx: {
            "status": "completed",
            "summary": "Ops failure requires scoped patch",
            "writes": {"diagnosis": {"action": "patch", "module": "ops-dashboard"}},
        },
    )
    registry.register(
        "ops_self_repair_coder",
        lambda _ctx: {
            "status": "completed",
            "summary": "Prepared self-repair patch guidance",
            "writes": {"patch_result": {"changed_files_count": 1, "changed_files": ["server/services/workflows/declarative.py"]}},
        },
    )

    def _verify_self_repair(ctx: WorkflowContext) -> AtomResult:
        trigger = _trigger(ctx)
        counters = dict(ctx.blackboard.get("counters") or {})
        should_fail_once = bool(trigger.get("force_first_verification_failure"))
        if should_fail_once and int(counters.get("patch_attempts") or 0) == 0:
            return AtomResult(summary="Verification failed before retry", writes={"verification": {"status": "failed"}})
        return AtomResult(summary="Verification passed", writes={"verification": {"status": "passed"}})

    registry.register("run_ops_self_repair_verification", _verify_self_repair)
    registry.register(
        "open_self_repair_pr",
        lambda _ctx: AtomResult(
            summary="Self-repair PR prepared for human approval",
            writes={"pr": {"created": True, "url": "pending"}},
            risk_flags=("self_modification_requires_human",),
        ),
    )
    registry.register(
        "detect_gateway_drift",
        lambda ctx: AtomResult(
            summary="Gateway drift signal evaluated",
            writes={
                "gateway_drift_detected": bool(_trigger(ctx).get("gateway_drift_detected", True)),
                "no_gateway_drift": not bool(_trigger(ctx).get("gateway_drift_detected", True)),
            },
        ),
    )
    registry.register(
        "collect_gateway_logs",
        lambda _ctx: AtomResult(
            summary="Gateway logs collected",
            writes={"logs_collected": True, "logs_missing": False, "evidence": [{"kind": "log", "path": "gateway/logs"}]},
        ),
    )
    registry.register(
        "gateway_reliability_diagnoser",
        lambda _ctx: {"status": "completed", "summary": "Gateway reliability issue requires patch", "writes": {"diagnosis": {"action": "patch"}}},
    )
    registry.register(
        "gateway_reliability_coder",
        lambda _ctx: {"status": "completed", "summary": "Gateway patch prepared", "writes": {"patch_result": {"changed_files_count": 1}}},
    )
    registry.register(
        "run_gateway_verification",
        lambda _ctx: AtomResult(summary="Gateway verification passed", writes={"verification": {"status": "passed"}}),
    )
    registry.register(
        "risk_evidence_gate",
        lambda ctx: AtomResult(
            summary="Risk evidence gate evaluated",
            writes={
                "gate": {
                    "decision": "human_required"
                    if set(ctx.blackboard.get("risk_flags") or []).intersection({"funds", "settlement", "auth", "production", "contract"})
                    else "auto_flow"
                }
            },
        ),
    )
    registry.register(
        "open_gateway_repair_pr",
        lambda _ctx: AtomResult(summary="Gateway repair PR prepared", writes={"pr": {"created": True, "url": "pending"}}),
    )
    registry.register(
        "observe_gateway_recovery",
        lambda _ctx: AtomResult(summary="Gateway recovery observed", writes={"observation": {"restored": True, "not_restored": False}}),
    )
    return registry


def validate_workflow_spec(spec: Mapping[str, Any]) -> None:
    """Validate state machine shape, terminal states, loops, and atom contracts."""

    workflow_key = str(spec.get("workflow_key") or "").strip()
    if not workflow_key:
        raise WorkflowSpecError("workflow_key is required")
    initial_state = str(spec.get("initial_state") or "").strip()
    states = spec.get("states")
    if not initial_state:
        raise WorkflowSpecError("initial_state is required")
    if not isinstance(states, dict) or not states:
        raise WorkflowSpecError("states must be a non-empty mapping")
    if initial_state not in states:
        raise WorkflowSpecError(f"initial_state does not exist: {initial_state}")
    terminal_states = [key for key, state in states.items() if isinstance(state, dict) and state.get("terminal") is True]
    if not terminal_states:
        raise WorkflowSpecError("workflow must define at least one terminal state")

    graph: dict[str, list[dict[str, Any]]] = {}
    for state_key, raw_state in states.items():
        if not isinstance(raw_state, dict):
            raise WorkflowSpecError(f"state must be a mapping: {state_key}")
        is_terminal = raw_state.get("terminal") is True
        atom_key = str(raw_state.get("atom") or raw_state.get("agent") or "").strip()
        if not is_terminal and not atom_key:
            raise WorkflowSpecError(f"non-terminal state must define atom or agent: {state_key}")
        if raw_state.get("agent") and not str(raw_state.get("output_schema") or "").strip():
            raise WorkflowSpecError(f"agent state must define output_schema: {state_key}")
        transitions = raw_state.get("transitions") or []
        if not is_terminal and not transitions:
            raise WorkflowSpecError(f"non-terminal state must define transitions: {state_key}")
        if not isinstance(transitions, list):
            raise WorkflowSpecError(f"transitions must be a list: {state_key}")
        graph[state_key] = []
        for transition in transitions:
            if not isinstance(transition, dict):
                raise WorkflowSpecError(f"transition must be a mapping: {state_key}")
            target = str(transition.get("goto") or "").strip()
            if not target:
                raise WorkflowSpecError(f"transition missing goto: {state_key}")
            if target not in states:
                raise WorkflowSpecError(f"transition target does not exist: {state_key} -> {target}")
            graph[state_key].append(transition)

        risk = str(raw_state.get("risk") or raw_state.get("risk_level") or "").strip().lower()
        if risk in {"high", "critical"}:
            allowed_targets = {"risk_gate", "awaiting_operator"}
            for transition in transitions:
                target = str(transition.get("goto") or "").strip()
                if target not in allowed_targets and not bool(transition.get("human_gate")):
                    raise WorkflowSpecError(f"high-risk state must route through human/risk gate: {state_key}")

    _validate_loop_guards(graph)


def run_workflow_state_machine(
    db: Session,
    *,
    workflow_run: WorkflowRunRow,
    spec: Mapping[str, Any],
    registry: AtomRegistry,
    initial_blackboard: Mapping[str, Any] | None = None,
) -> WorkflowRunResult:
    """Run a declarative workflow until it reaches a terminal state."""

    validate_workflow_spec(spec)
    requirement = _requirement_for_run(workflow_run)
    workflow_key = str(spec["workflow_key"])
    limits = dict(spec.get("limits") or {})
    max_transitions = int(limits.get("max_transitions") or 100)
    states = spec["states"]
    blackboard = _load_blackboard(workflow_run)
    if initial_blackboard:
        blackboard.update(dict(initial_blackboard))
    spec_blackboard = spec.get("blackboard") if isinstance(spec.get("blackboard"), Mapping) else {}
    persist_keys = spec_blackboard.get("persist_keys") if isinstance(spec_blackboard, Mapping) else None
    if isinstance(persist_keys, list):
        blackboard.setdefault("persist_keys", [str(item) for item in persist_keys])
    blackboard.setdefault("workflow_key", workflow_key)
    blackboard.setdefault("counters", {})
    blackboard.setdefault("state_outputs", {})
    blackboard.setdefault("transition_history", [])
    blackboard.setdefault("risk_flags", [])
    blackboard.setdefault("evidence", [])
    blackboard["limits"] = limits

    current_state = str(blackboard.get("current_state") or spec["initial_state"])
    transition_count = 0
    workflow_run.workflow_key = workflow_key
    workflow_run.status = "running"
    workflow_run.current_state = current_state
    workflow_run.started_at = workflow_run.started_at or utcnow()
    _persist_blackboard(db, workflow_run, current_state, blackboard)
    db.flush()

    while transition_count <= max_transitions:
        state = states[current_state]
        blackboard["current_state"] = current_state
        workflow_run.current_state = current_state
        _persist_blackboard(db, workflow_run, current_state, blackboard)

        if state.get("terminal") is True:
            resolution = str(state.get("resolution") or "completed")
            workflow_run.status = "awaiting_operator" if resolution == "route_to_human" else "succeeded"
            workflow_run.current_state = current_state
            workflow_run.resolution = resolution
            workflow_run.retry_counters_json = _json_dump(dict(blackboard.get("counters") or {}))
            workflow_run.completed_at = utcnow()
            if resolution == "route_to_human":
                _ensure_human_gate_request(db, workflow_run, current_state, blackboard)
            _persist_blackboard(db, workflow_run, current_state, blackboard)
            db.flush()
            return WorkflowRunResult(
                workflow_key=workflow_key,
                final_state=current_state,
                resolution=resolution,
                transition_count=transition_count,
                blackboard=dict(blackboard),
            )

        _execute_state_atom(db, requirement, workflow_run, spec, current_state, state, registry, blackboard)
        next_state = _select_next_state(db, workflow_run, current_state, state, blackboard, spec)
        current_state = next_state
        transition_count += 1

    raise WorkflowRuntimeError(f"workflow exceeded max_transitions={max_transitions}: {workflow_key}")


def workflow_blackboard(workflow_run: WorkflowRunRow) -> dict[str, Any]:
    """Return the stored blackboard from the declarative workflow run."""

    return _load_blackboard(workflow_run)


def _requirement_for_run(workflow_run: WorkflowRunRow) -> RequirementRow:
    requirement = getattr(workflow_run, "requirement", None)
    if requirement is None:
        raise WorkflowRuntimeError("workflow_run.requirement must be loaded for declarative workflow execution")
    return requirement


def _execute_state_atom(
    db: Session,
    requirement: RequirementRow,
    workflow_run: WorkflowRunRow,
    spec: Mapping[str, Any],
    state_key: str,
    state: Mapping[str, Any],
    registry: AtomRegistry,
    blackboard: dict[str, Any],
) -> None:
    atom_key = str(state.get("agent") or state.get("atom") or "").strip()
    handler = registry.get(atom_key)
    started = time.perf_counter()
    invocation = AtomInvocationRow(
        workflow_run_id=int(workflow_run.id),
        state_key=state_key,
        atom_key=atom_key,
        atom_type="agent" if state.get("agent") else "deterministic",
        output_schema=str(state.get("output_schema") or "") or None,
        status="running",
        input_summary=f"state={state_key}",
        started_at=utcnow(),
    )
    db.add(invocation)
    db.flush()
    context = WorkflowContext(
        db=db,
        workflow_run=workflow_run,
        requirement=requirement,
        spec=spec,
        state_key=state_key,
        state_spec=state,
        blackboard=blackboard,
    )
    artifact_ids: list[int] = []
    try:
        raw_result = handler(context)
        result = _coerce_atom_result(raw_result)
    except Exception as exc:
        invocation.status = "failed"
        invocation.error_excerpt = str(exc)[:1000]
        invocation.duration_ms = int((time.perf_counter() - started) * 1000)
        invocation.completed_at = utcnow()
        db.flush()
        raise
    output_key = str(state.get("output_key") or state_key).strip()
    writes = dict(result.writes or {})
    if output_key:
        blackboard[output_key] = writes.get(output_key, writes)
    blackboard.update(writes)
    blackboard.setdefault("state_outputs", {})[state_key] = {
        "atom_key": atom_key,
        "status": result.status,
        "summary": result.summary,
        "output_key": output_key,
        "writes": writes,
        "artifacts": list(result.artifacts),
        "risk_flags": list(result.risk_flags),
    }
    if result.risk_flags:
        existing = list(blackboard.get("risk_flags") or [])
        existing.extend(flag for flag in result.risk_flags if flag not in existing)
        blackboard["risk_flags"] = existing
    if state.get("agent"):
        artifact = _create_workflow_artifact(
            db,
            workflow_run_id=int(workflow_run.id),
            artifact_type="workflow_agent_raw_output",
            state_key=state_key,
            atom_key=atom_key,
            content_summary=f"{state_key}: {result.summary or result.status}",
            human_readable_body=str(result.raw_output if result.raw_output is not None else raw_result),
            machine_readable_payload={
                "workflow_key": spec.get("workflow_key"),
                "state_key": state_key,
                "agent": atom_key,
                "status": result.status,
                "writes": writes,
            },
        )
        artifact_ids.append(int(artifact.id))
        blackboard.setdefault("artifacts", {})[f"{state_key}_raw_output_artifact_id"] = int(artifact.id)
    invocation.status = result.status
    invocation.output_summary = result.summary
    invocation.artifact_ids_json = _json_dump(artifact_ids)
    invocation.duration_ms = int((time.perf_counter() - started) * 1000)
    invocation.completed_at = utcnow()
    _persist_blackboard(db, workflow_run, state_key, blackboard)
    db.flush()


def _select_next_state(
    db: Session,
    workflow_run: WorkflowRunRow,
    state_key: str,
    state: Mapping[str, Any],
    blackboard: dict[str, Any],
    spec: Mapping[str, Any],
) -> str:
    for transition in state.get("transitions") or []:
        condition = str(transition.get("if") or "").strip()
        if condition and not _condition_matches(condition, blackboard):
            continue
        increment = transition.get("increment")
        if increment:
            counters = blackboard.setdefault("counters", {})
            if isinstance(increment, str):
                counters[increment] = int(counters.get(increment) or 0) + 1
            elif isinstance(increment, dict):
                for key, value in increment.items():
                    counters[str(key)] = int(counters.get(str(key)) or 0) + int(value or 1)
        target = str(transition["goto"]).strip()
        event = {
            "workflow_key": spec.get("workflow_key"),
            "from_state": state_key,
            "to_state": target,
            "condition": condition or "<default>",
            "increment": increment,
            "counters": dict(blackboard.get("counters") or {}),
            "ts": utcnow().isoformat(),
        }
        artifact = _create_workflow_artifact(
            db,
            workflow_run_id=int(workflow_run.id),
            artifact_type="workflow_transition_event",
            state_key=state_key,
            content_summary=f"{state_key} -> {target}",
            human_readable_body=json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True),
            machine_readable_payload=event,
        )
        event["artifact_id"] = int(artifact.id)
        state_event = WorkflowStateEventRow(
            workflow_run_id=int(workflow_run.id),
            event_type="transition",
            from_state=state_key,
            to_state=target,
            condition=condition or "<default>",
            payload_json=_json_dump(event),
        )
        db.add(state_event)
        blackboard.setdefault("transition_history", []).append(event)
        blackboard["current_state"] = target
        workflow_run.current_state = target
        workflow_run.retry_counters_json = _json_dump(dict(blackboard.get("counters") or {}))
        _persist_blackboard(db, workflow_run, target, blackboard)
        db.flush()
        return target
    raise WorkflowRuntimeError(f"no transition matched for state: {state_key}")


def decide_human_gate(
    db: Session,
    *,
    gate_id: int,
    decision: str,
    reviewer: str = "operator",
    comment: str = "",
) -> HumanGateRequestRow:
    """Record an operator decision for a pending human gate."""

    gate = db.query(HumanGateRequestRow).filter(HumanGateRequestRow.id == gate_id).first()
    if gate is None:
        raise WorkflowRuntimeError(f"human gate not found: {gate_id}")
    normalized = str(decision or "").strip().lower()
    if normalized not in {"approve", "reject", "continue_retry"}:
        raise WorkflowRuntimeError("decision must be approve, reject, or continue_retry")
    gate.status = "decided"
    gate.decision = normalized
    gate.decided_by = reviewer
    gate.decision_comment = comment
    gate.decided_at = utcnow()
    run = gate.workflow_run
    blackboard = workflow_blackboard(run)
    blackboard.setdefault("human_gate_decisions", []).append(
        {
            "gate_id": int(gate.id),
            "decision": normalized,
            "reviewer": reviewer,
            "comment": comment,
            "decided_at": gate.decided_at.isoformat(),
        }
    )
    if normalized == "continue_retry":
        run.status = "pending"
        run.resolution = "operator_continue_retry"
    elif normalized == "approve":
        run.resolution = "operator_approved"
    else:
        run.status = "failed"
        run.resolution = "operator_rejected"
    _persist_blackboard(db, run, str(run.current_state or gate.state_key), blackboard)
    db.flush()
    return gate


def workflow_run_detail(db: Session, workflow_run_id: int) -> dict[str, Any]:
    """Return the declarative workflow run detail used by API and UI."""

    run = db.query(WorkflowRunRow).filter(WorkflowRunRow.id == workflow_run_id).first()
    if run is None:
        raise WorkflowRuntimeError(f"workflow run not found: {workflow_run_id}")
    events = db.query(WorkflowStateEventRow).filter(WorkflowStateEventRow.workflow_run_id == run.id).order_by(WorkflowStateEventRow.id.asc()).all()
    artifacts = db.query(WorkflowArtifactRow).filter(WorkflowArtifactRow.workflow_run_id == run.id).order_by(WorkflowArtifactRow.id.asc()).all()
    invocations = db.query(AtomInvocationRow).filter(AtomInvocationRow.workflow_run_id == run.id).order_by(AtomInvocationRow.id.asc()).all()
    gates = db.query(HumanGateRequestRow).filter(HumanGateRequestRow.workflow_run_id == run.id).order_by(HumanGateRequestRow.id.asc()).all()
    return {
        "id": int(run.id),
        "requirement_id": int(run.requirement_id),
        "workflow_key": run.workflow_key,
        "current_state": run.current_state,
        "status": run.status,
        "resolution": run.resolution,
        "risk_level": run.risk_level,
        "retry_counters": _json_load(run.retry_counters_json, {}),
        "blackboard": workflow_blackboard(run),
        "events": [
            {
                "id": int(event.id),
                "event_type": event.event_type,
                "from_state": event.from_state,
                "to_state": event.to_state,
                "condition": event.condition,
                "payload": _json_load(event.payload_json, {}),
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
        "artifacts": [
            {
                "id": int(artifact.id),
                "artifact_type": artifact.artifact_type,
                "state_key": artifact.state_key,
                "atom_key": artifact.atom_key,
                "content_summary": artifact.content_summary,
                "payload": _json_load(artifact.machine_readable_payload, {}),
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            for artifact in artifacts
        ],
        "atom_invocations": [
            {
                "id": int(invocation.id),
                "state_key": invocation.state_key,
                "atom_key": invocation.atom_key,
                "atom_type": invocation.atom_type,
                "status": invocation.status,
                "output_summary": invocation.output_summary,
                "artifact_ids": _json_load(invocation.artifact_ids_json, []),
                "duration_ms": int(invocation.duration_ms or 0),
                "error_excerpt": invocation.error_excerpt,
            }
            for invocation in invocations
        ],
        "human_gates": [
            {
                "id": int(gate.id),
                "state_key": gate.state_key,
                "gate_type": gate.gate_type,
                "risk_level": gate.risk_level,
                "status": gate.status,
                "reason": gate.reason,
                "decision": gate.decision,
                "created_at": gate.created_at.isoformat() if gate.created_at else None,
            }
            for gate in gates
        ],
    }


def _ensure_human_gate_request(
    db: Session,
    workflow_run: WorkflowRunRow,
    state_key: str,
    blackboard: Mapping[str, Any],
) -> HumanGateRequestRow:
    existing = (
        db.query(HumanGateRequestRow)
        .filter(
            HumanGateRequestRow.workflow_run_id == int(workflow_run.id),
            HumanGateRequestRow.state_key == state_key,
            HumanGateRequestRow.status == "pending",
        )
        .first()
    )
    if existing is not None:
        return existing
    gate = HumanGateRequestRow(
        workflow_run_id=int(workflow_run.id),
        state_key=state_key,
        gate_type="human_gate",
        risk_level="high" if blackboard.get("risk_flags") else str(workflow_run.risk_level or "normal"),
        status="pending",
        reason="Workflow reached a human-gated terminal state.",
        payload_json=_json_dump(
            {
                "workflow_key": workflow_run.workflow_key,
                "current_state": state_key,
                "risk_flags": list(blackboard.get("risk_flags") or []),
                "summary": blackboard.get("pr") or blackboard.get("verification") or {},
            }
        ),
    )
    db.add(gate)
    db.flush()
    return gate


def _condition_matches(expression: str, blackboard: Mapping[str, Any]) -> bool:
    parts = [part.strip() for part in re.split(r"\s+and\s+", expression) if part.strip()]
    return all(_condition_part_matches(part, blackboard) for part in parts)


def _condition_part_matches(part: str, blackboard: Mapping[str, Any]) -> bool:
    if part.startswith("not "):
        return not _condition_part_matches(part[4:].strip(), blackboard)
    for operator in (">=", "<=", "==", "!=", ">", "<"):
        if operator not in part:
            continue
        left, right = [item.strip() for item in part.split(operator, 1)]
        left_value = _lookup_path(left, blackboard)
        right_value = _parse_literal(right, blackboard)
        return _compare_values(left_value, right_value, operator)
    return bool(_lookup_path(part, blackboard))


def _lookup_path(path: str, blackboard: Mapping[str, Any]) -> Any:
    current: Any = blackboard
    parts = [item for item in path.split(".") if item]
    for index, part in enumerate(parts):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        elif index > 0 and parts[0] == "counters":
            return 0
        else:
            return None
    return current


def _parse_literal(value: str, blackboard: Mapping[str, Any]) -> Any:
    stripped = value.strip()
    if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
        return stripped[1:-1]
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    if re.fullmatch(r"-?\d+\.\d+", stripped):
        return float(stripped)
    return _lookup_path(stripped, blackboard)


def _compare_values(left: Any, right: Any, operator: str) -> bool:
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    try:
        if operator == ">=":
            return left >= right
        if operator == "<=":
            return left <= right
        if operator == ">":
            return left > right
        if operator == "<":
            return left < right
    except TypeError:
        return False
    return False


def _coerce_atom_result(raw_result: AtomResult | Mapping[str, Any] | str) -> AtomResult:
    if isinstance(raw_result, AtomResult):
        return raw_result
    if isinstance(raw_result, str):
        parsed = _parse_json_output(raw_result)
        return _atom_result_from_mapping(parsed, raw_output=raw_result)
    if isinstance(raw_result, Mapping):
        return _atom_result_from_mapping(raw_result, raw_output=raw_result)
    raise WorkflowRuntimeError(f"unsupported atom result type: {type(raw_result).__name__}")


def _atom_result_from_mapping(payload: Mapping[str, Any], *, raw_output: Any) -> AtomResult:
    writes = payload.get("writes") if isinstance(payload.get("writes"), Mapping) else payload
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    risk_flags = payload.get("risk_flags") if isinstance(payload.get("risk_flags"), list) else []
    return AtomResult(
        status=str(payload.get("status") or "completed"),
        summary=str(payload.get("summary") or ""),
        writes=dict(writes or {}),
        raw_output=raw_output,
        artifacts=tuple(str(item) for item in artifacts),
        risk_flags=tuple(str(item) for item in risk_flags),
    )


def _parse_json_output(raw_output: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_output, flags=re.DOTALL)
        if not match:
            raise WorkflowRuntimeError("agent atom output is not valid JSON")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise WorkflowRuntimeError("agent atom output JSON must be an object")
    return parsed


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _load_blackboard(workflow_run: WorkflowRunRow) -> dict[str, Any]:
    blackboard = _json_load(getattr(workflow_run, "blackboard_json", None), {})
    return dict(blackboard) if isinstance(blackboard, dict) else {}


def _persist_blackboard(db: Session, workflow_run: WorkflowRunRow, state_key: str, blackboard: Mapping[str, Any]) -> None:
    persist_keys = _persist_keys_from_blackboard(blackboard)
    persisted = {key: blackboard.get(key) for key in persist_keys if key in blackboard}
    workflow_run.blackboard_json = _json_dump(persisted)
    workflow_run.retry_counters_json = _json_dump(dict(persisted.get("counters") or {}))
    workflow_run.updated_at = utcnow()
    db.add(
        BlackboardSnapshotRow(
            workflow_run_id=int(workflow_run.id),
            state_key=state_key,
            snapshot_json=workflow_run.blackboard_json,
        )
    )


def _persist_keys_from_blackboard(blackboard: Mapping[str, Any]) -> list[str]:
    keys = blackboard.get("persist_keys")
    if isinstance(keys, list):
        return [str(item) for item in keys]
    return [
        "workflow_key",
        "current_state",
        "counters",
        "trigger",
        "logs_collected",
        "ops_failure_detected",
        "gateway_drift_detected",
        "no_gateway_drift",
        "diagnosis",
        "patch_result",
        "verification",
        "gate",
        "observation",
        "pr",
        "risk_flags",
        "evidence",
        "state_outputs",
        "transition_history",
        "artifacts",
        "human_gate_decisions",
        "limits",
    ]


def _json_load(raw_value: Any, default: Any) -> Any:
    if raw_value is None:
        return default
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(str(raw_value or ""))
    except json.JSONDecodeError:
        return default


def _create_workflow_artifact(
    db: Session,
    *,
    workflow_run_id: int,
    artifact_type: str,
    content_summary: str,
    human_readable_body: str,
    machine_readable_payload: Mapping[str, Any] | list[Any] | str | None = None,
    state_key: str | None = None,
    atom_key: str | None = None,
) -> WorkflowArtifactRow:
    payload_for_storage: Mapping[str, Any] | list[Any] | str | None
    if isinstance(machine_readable_payload, Mapping):
        payload_for_storage = dict(machine_readable_payload)
        payload_for_storage.setdefault("workflow_run_id", workflow_run_id)
    else:
        payload_for_storage = machine_readable_payload
    payload_text = (
        json.dumps(payload_for_storage, ensure_ascii=False, sort_keys=True)
        if payload_for_storage is not None and not isinstance(payload_for_storage, str)
        else payload_for_storage
    )
    checksum_source = str(payload_text or human_readable_body or content_summary)
    artifact = WorkflowArtifactRow(
        workflow_run_id=workflow_run_id,
        artifact_type=artifact_type,
        state_key=state_key,
        atom_key=atom_key,
        content_summary=content_summary,
        human_readable_body=human_readable_body,
        machine_readable_payload=payload_text,
        checksum=hashlib.sha1(checksum_source.encode("utf-8")).hexdigest(),
    )
    db.add(artifact)
    db.flush()
    return artifact


def _validate_loop_guards(graph: Mapping[str, list[dict[str, Any]]]) -> None:
    cycles: list[list[tuple[str, dict[str, Any]]]] = []

    def visit(node: str, path: list[tuple[str, dict[str, Any]]], seen: set[str]) -> None:
        for transition in graph.get(node, []):
            target = str(transition.get("goto") or "")
            edge = (node, transition)
            if target in seen:
                cycle_start = next((index for index, item in enumerate(path) if item[0] == target), 0)
                cycles.append(path[cycle_start:] + [edge])
                continue
            visit(target, path + [edge], seen | {target})

    for state_key in graph:
        visit(state_key, [], {state_key})

    for cycle in cycles:
        guarded = False
        for _source, transition in cycle:
            condition = str(transition.get("if") or "")
            if transition.get("increment") or "counters." in condition:
                guarded = True
                break
        if not guarded:
            edge_list = " -> ".join(source for source, _transition in cycle)
            raise WorkflowSpecError(f"workflow loop must include counter guard: {edge_list}")
