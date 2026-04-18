"""Declarative workflow state machine runner with Blackboard persistence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from sqlalchemy.orm import Session

from server.database import ArtifactRow, ExecutionRunRow, RequirementRow, utcnow


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
    execution_run: ExecutionRunRow
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
    execution_run: ExecutionRunRow,
    spec: Mapping[str, Any],
    registry: AtomRegistry,
    initial_blackboard: Mapping[str, Any] | None = None,
) -> WorkflowRunResult:
    """Run a declarative workflow until it reaches a terminal state."""

    validate_workflow_spec(spec)
    requirement = _requirement_for_run(execution_run)
    workflow_key = str(spec["workflow_key"])
    limits = dict(spec.get("limits") or {})
    max_transitions = int(limits.get("max_transitions") or 100)
    states = spec["states"]
    blackboard = _load_blackboard(execution_run)
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
    execution_run.status = "running"
    execution_run.phase = current_state
    execution_run.attempt_state = current_state
    execution_run.started_at = execution_run.started_at or utcnow()
    _persist_blackboard(execution_run, blackboard)
    db.flush()

    while transition_count <= max_transitions:
        state = states[current_state]
        blackboard["current_state"] = current_state
        execution_run.phase = current_state
        execution_run.attempt_state = current_state
        _persist_blackboard(execution_run, blackboard)

        if state.get("terminal") is True:
            resolution = str(state.get("resolution") or "completed")
            execution_run.status = "blocked" if resolution == "route_to_human" else "succeeded"
            execution_run.phase = current_state
            execution_run.attempt_state = resolution
            execution_run.completed_at = utcnow()
            _persist_blackboard(execution_run, blackboard)
            db.flush()
            return WorkflowRunResult(
                workflow_key=workflow_key,
                final_state=current_state,
                resolution=resolution,
                transition_count=transition_count,
                blackboard=dict(blackboard),
            )

        _execute_state_atom(db, requirement, execution_run, spec, current_state, state, registry, blackboard)
        next_state = _select_next_state(db, requirement, execution_run, current_state, state, blackboard, spec)
        current_state = next_state
        transition_count += 1

    raise WorkflowRuntimeError(f"workflow exceeded max_transitions={max_transitions}: {workflow_key}")


def workflow_blackboard(execution_run: ExecutionRunRow) -> dict[str, Any]:
    """Return the stored blackboard from an execution run plan snapshot."""

    return _load_blackboard(execution_run)


def _requirement_for_run(execution_run: ExecutionRunRow) -> RequirementRow:
    requirement = getattr(execution_run, "requirement", None)
    if requirement is None:
        raise WorkflowRuntimeError("execution_run.requirement must be loaded for declarative workflow execution")
    return requirement


def _execute_state_atom(
    db: Session,
    requirement: RequirementRow,
    execution_run: ExecutionRunRow,
    spec: Mapping[str, Any],
    state_key: str,
    state: Mapping[str, Any],
    registry: AtomRegistry,
    blackboard: dict[str, Any],
) -> None:
    atom_key = str(state.get("agent") or state.get("atom") or "").strip()
    handler = registry.get(atom_key)
    context = WorkflowContext(
        db=db,
        execution_run=execution_run,
        requirement=requirement,
        spec=spec,
        state_key=state_key,
        state_spec=state,
        blackboard=blackboard,
    )
    raw_result = handler(context)
    result = _coerce_atom_result(raw_result)
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
            requirement_id=int(requirement.id),
            execution_run_id=int(execution_run.id),
            artifact_type="workflow_agent_raw_output",
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
        blackboard.setdefault("artifacts", {})[f"{state_key}_raw_output_artifact_id"] = int(artifact.id)
    _persist_blackboard(execution_run, blackboard)
    db.flush()


def _select_next_state(
    db: Session,
    requirement: RequirementRow,
    execution_run: ExecutionRunRow,
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
            requirement_id=int(requirement.id),
            execution_run_id=int(execution_run.id),
            artifact_type="workflow_transition_event",
            content_summary=f"{state_key} -> {target}",
            human_readable_body=json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True),
            machine_readable_payload=event,
        )
        event["artifact_id"] = int(artifact.id)
        blackboard.setdefault("transition_history", []).append(event)
        blackboard["current_state"] = target
        _persist_blackboard(execution_run, blackboard)
        db.flush()
        return target
    raise WorkflowRuntimeError(f"no transition matched for state: {state_key}")


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


def _load_blackboard(execution_run: ExecutionRunRow) -> dict[str, Any]:
    snapshot = _json_load(getattr(execution_run, "plan_snapshot_json", None), {})
    blackboard = snapshot.get("blackboard") if isinstance(snapshot, dict) else {}
    return dict(blackboard) if isinstance(blackboard, dict) else {}


def _persist_blackboard(execution_run: ExecutionRunRow, blackboard: Mapping[str, Any]) -> None:
    snapshot = _json_load(getattr(execution_run, "plan_snapshot_json", None), {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    persist_keys = _persist_keys_from_blackboard(blackboard)
    persisted = {key: blackboard.get(key) for key in persist_keys if key in blackboard}
    snapshot["blackboard"] = persisted
    execution_run.plan_snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    execution_run.updated_at = utcnow()


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
        "diagnosis",
        "patch_result",
        "verification",
        "pr",
        "risk_flags",
        "evidence",
        "state_outputs",
        "transition_history",
        "artifacts",
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
    requirement_id: int,
    execution_run_id: int,
    artifact_type: str,
    content_summary: str,
    human_readable_body: str,
    machine_readable_payload: Mapping[str, Any] | list[Any] | str | None = None,
) -> ArtifactRow:
    payload_for_storage: Mapping[str, Any] | list[Any] | str | None
    if isinstance(machine_readable_payload, Mapping):
        payload_for_storage = dict(machine_readable_payload)
        payload_for_storage.setdefault("execution_run_id", execution_run_id)
    else:
        payload_for_storage = machine_readable_payload
    payload_text = (
        json.dumps(payload_for_storage, ensure_ascii=False, sort_keys=True)
        if payload_for_storage is not None and not isinstance(payload_for_storage, str)
        else payload_for_storage
    )
    checksum_source = str(payload_text or human_readable_body or content_summary)
    artifact = ArtifactRow(
        requirement_id=requirement_id,
        artifact_type=artifact_type,
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
