from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from server.services.workflows.planner_provider import PlannerResponse
from server.services.workflows.verification_agent import generate_verification_plan, verify_with_agent


def test_verify_with_agent_serializes_datetime_payload_before_provider_call():
    observed_prompt: dict[str, str] = {}

    def _fake_generate_planner_text(request):
        observed_prompt["prompt"] = request.prompt
        return PlannerResponse(
            text='{"verification_plan":{"mode":"evidence_review","summary":"Review changed files and raw output.","checks":[],"evidence_expectations":["implementation summary"]},"status":"passed","summary":"ok","checks_run":[],"evidence_used":[],"reasoning":"ok","suggested_next_action":"release_ready"}',
            tokens=0,
        )

    payload = {
        "activity_stream": [
            {
                "event": "run_created",
                "ts": datetime(2026, 4, 14, 10, 58, 24, tzinfo=timezone.utc),
            }
        ]
    }

    with patch(
        "server.services.workflows.verification_agent.generate_planner_text",
        side_effect=_fake_generate_planner_text,
    ):
        result = verify_with_agent(payload, skip_provider=False)

    assert result["status"] == "passed"
    assert result["verification_plan"]["mode"] == "evidence_review"
    assert '"ts": "2026-04-14T10:58:24+00:00"' in observed_prompt["prompt"]


def test_verify_with_agent_promotes_inconclusive_to_fallback_pass_when_execution_evidence_is_strong():
    def _fake_generate_planner_text(request):
        return PlannerResponse(
            text='{"status":"inconclusive","summary":"not sure","checks_run":[],"evidence_used":[],"reasoning":"missing artifact","suggested_next_action":"revise_requirement"}',
            tokens=0,
        )

    payload = {
        "raw_task_output": "Implemented the logging changes and targeted pytest passed.",
        "changed_files": [{"path": "services/gateway/src/core/log_config.py"}],
        "check_results": [],
    }

    with patch(
        "server.services.workflows.verification_agent.generate_planner_text",
        side_effect=_fake_generate_planner_text,
    ):
        result = verify_with_agent(payload, skip_provider=False)

    assert result["status"] == "passed"
    assert result["suggested_next_action"] == "release_ready"
    assert result["verification_plan"]["mode"] == "evidence_review"
    assert "raw_output" in " ".join(result["evidence_used"])


def test_verify_with_agent_returns_none_required_plan_when_no_evidence_exists():
    result = verify_with_agent({"raw_task_output": "", "changed_files": [], "check_results": []}, skip_provider=True)

    assert result["verification_plan"]["mode"] == "none_required"
    assert result["verification_plan"]["why_no_verification"]
    assert result["resolution_recommendation"] == "revise_requirement"
    assert result["resolution_reason"]


def test_generate_verification_plan_replays_execution_commands_as_required_harness_checks():
    payload = {
        "requirement": {"target_project_path": "/tmp/project"},
        "commands_run": ["pytest tests/test_login.py -q"],
        "raw_task_output": "Commands run:\n- `pytest tests/test_login.py -q`",
        "changed_files": [{"path": "services/admin-front/src/app/login/page.tsx"}],
    }

    result = generate_verification_plan(payload, skip_provider=True)

    assert result["mode"] == "command_checks"
    assert result["required_commands"] == [
        {
            "required": True,
            "cwd": "/tmp/project",
            "command": "pytest tests/test_login.py -q",
            "timeout_sec": 300,
            "purpose": "Replay execution-agent reported command through the harness as authoritative evidence.",
        }
    ]
    assert "Verification Plan" in result["markdown"]


def test_verify_with_agent_preserves_supplied_verification_plan_required_commands():
    plan = {
        "mode": "command_checks",
        "summary": "Run login tests.",
        "required_commands": [
            {
                "required": True,
                "cwd": "/tmp/project",
                "command": "npm test -- login",
                "timeout_sec": 120,
                "purpose": "Verify login copy.",
            }
        ],
    }

    result = verify_with_agent(
        {
            "requirement": {"target_project_path": "/tmp/project"},
            "verification_plan": plan,
            "check_results": [
                {
                    "label": "login tests",
                    "command": "npm test -- login",
                    "project_path": "/tmp/project",
                    "status": "passed",
                }
            ],
            "raw_task_output": "Implemented and tested.",
            "changed_files": [{"path": "login/page.tsx"}],
        },
        skip_provider=True,
    )

    assert result["status"] == "passed"
    assert result["verification_plan"]["required_commands"][0]["command"] == "npm test -- login"
