import json

from server.database import PlanningGoalRow
from server.services.planning.planner_agent import PlannerAgentError, synthesize_candidate_for_goal
from server.services.workflows.planner_provider import PlannerResponse


def _goal():
    return PlanningGoalRow(
        id=1,
        manifest_id=1,
        goal_key="growing_2026_04_20_gate",
        title="静态分析和架构契约武器化",
        intent_markdown="Use linting and architecture contract checks to prevent regressions.",
        success_metric="lint_contract_guardrails_enforced == true",
        domain="ops",
        workflow_key="agent_self_repair",
        project_key="synapse-network-growing",
        priority="normal",
        risk_level="normal",
    )


def _valid_payload(**overrides):
    payload = {
        "title": "Advance lint and architecture contracts",
        "description_markdown": "## Goal\nAdd checks that prove contract guardrails remain active.",
        "workflow_key": "agent_self_repair",
        "expected_outcome": "code_delivery",
        "priority": "normal",
        "risk_level": "normal",
        "confidence": 0.83,
        "rationale": "This is Growing self-repair and contract hardening work.",
        "acceptance_contract": {
            "acceptance_kind": "business",
            "execution_acceptance_steps": [
                {
                    "step_key": "contract_checks_pass",
                    "title": "Contract checks pass",
                    "expected_result": "Contract checks reject known architecture regressions.",
                    "required_commands": ["python -m pytest -q"],
                }
            ],
        },
    }
    payload.update(overrides)
    return payload


def test_planner_agent_valid_json_creates_candidate(monkeypatch):
    monkeypatch.setattr(
        "server.services.planning.planner_agent.generate_planner_text",
        lambda request: PlannerResponse(text=json.dumps(_valid_payload()), backend="test", model="fake-planner"),
    )

    candidate = synthesize_candidate_for_goal(
        manifest_payload={"focus_weights": {"ops": 1}},
        goal=_goal(),
        project_key="synapse-network-growing",
        default_workflow_key="agent_self_repair",
    )

    assert candidate.workflow_key == "agent_self_repair"
    assert candidate.expected_outcome == "code_delivery"
    assert candidate.acceptance_contract["execution_acceptance_steps"]
    assert candidate.metadata["generated_by"] == "planner_agent_v1"
    assert candidate.metadata["planner_agent_backend"] == "test"


def test_planner_agent_repairs_invalid_json(monkeypatch):
    calls = {"count": 0}

    def fake_generate(request):
        calls["count"] += 1
        if calls["count"] == 1:
            return PlannerResponse(text='{"title": "broken"', backend="test", model="fake-planner")
        return PlannerResponse(text=json.dumps(_valid_payload()), backend="test", model="fake-planner")

    monkeypatch.setattr("server.services.planning.planner_agent.generate_planner_text", fake_generate)

    candidate = synthesize_candidate_for_goal(
        manifest_payload={},
        goal=_goal(),
        project_key="synapse-network-growing",
        default_workflow_key="agent_self_repair",
    )

    assert calls["count"] == 2
    assert candidate.metadata["planner_repair_attempts"] == 1


def test_planner_agent_unknown_workflow_fails_closed(monkeypatch):
    monkeypatch.setattr(
        "server.services.planning.planner_agent.generate_planner_text",
        lambda request: PlannerResponse(
            text=json.dumps(_valid_payload(workflow_key="database_optimization_workflow")),
            backend="test",
            model="fake-planner",
        ),
    )

    try:
        synthesize_candidate_for_goal(
            manifest_payload={},
            goal=_goal(),
            project_key="synapse-network-growing",
            default_workflow_key="agent_self_repair",
        )
    except PlannerAgentError as exc:
        assert "unknown workflow_key" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("unknown workflow was accepted")


def test_planner_agent_missing_expected_outcome_fails_closed_after_repair(monkeypatch):
    monkeypatch.setattr(
        "server.services.planning.planner_agent.generate_planner_text",
        lambda request: PlannerResponse(
            text=json.dumps({key: value for key, value in _valid_payload().items() if key != "expected_outcome"}),
            backend="test",
            model="fake-planner",
        ),
    )

    try:
        synthesize_candidate_for_goal(
            manifest_payload={},
            goal=_goal(),
            project_key="synapse-network-growing",
            default_workflow_key="agent_self_repair",
        )
    except PlannerAgentError as exc:
        assert "expected_outcome" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("missing expected_outcome was accepted")


def test_planner_agent_context_hint_is_in_prompt(monkeypatch):
    prompts: list[str] = []

    def fake_generate(request):
        prompts.append(request.prompt)
        return PlannerResponse(
            text=json.dumps(_valid_payload(expected_outcome="verification_only")),
            backend="test",
            model="fake-planner",
        )

    monkeypatch.setattr("server.services.planning.planner_agent.generate_planner_text", fake_generate)

    candidate = synthesize_candidate_for_goal(
        manifest_payload={},
        goal=_goal(),
        project_key="synapse-network-growing",
        default_workflow_key="agent_self_repair",
        context_hint="System Note: prefer verification_only if already satisfied.",
    )

    assert candidate.expected_outcome == "verification_only"
    assert "prefer verification_only" in prompts[0]
