from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from server.services.workflows.verification_agent import verify_with_agent


def test_verify_with_agent_serializes_datetime_payload_before_provider_call():
    observed_prompt: dict[str, str] = {}

    def _fake_call_full_plan_provider(**kwargs):
        observed_prompt["prompt"] = kwargs["prompt"]
        return (
            '{"status":"passed","summary":"ok","checks_run":[],"evidence_used":[],"reasoning":"ok","suggested_next_action":"release_ready"}',
            0,
        )

    payload = {
        "activity_stream": [
            {
                "event": "run_created",
                "ts": datetime(2026, 4, 14, 10, 58, 24, tzinfo=timezone.utc),
            }
        ]
    }

    with patch("server.services.workflows.verification_agent.get_provider", return_value=object()), patch(
        "server.services.workflows.verification_agent.planner_provider_name",
        return_value="codex",
    ), patch(
        "server.services.workflows.verification_agent.planner_model_name",
        return_value="gpt-5-codex",
    ), patch(
        "server.services.workflows.verification_agent.call_full_plan_provider",
        side_effect=_fake_call_full_plan_provider,
    ):
        result = verify_with_agent(payload, skip_provider=False)

    assert result["status"] == "passed"
    assert '"ts": "2026-04-14T10:58:24+00:00"' in observed_prompt["prompt"]


def test_verify_with_agent_promotes_inconclusive_to_fallback_pass_when_execution_evidence_is_strong():
    def _fake_call_full_plan_provider(**kwargs):
        return (
            '{"status":"inconclusive","summary":"not sure","checks_run":[],"evidence_used":[],"reasoning":"missing artifact","suggested_next_action":"revise_requirement"}',
            0,
        )

    payload = {
        "raw_task_output": "Implemented the logging changes and targeted pytest passed.",
        "changed_files": [{"path": "services/gateway/src/core/log_config.py"}],
        "check_results": [],
    }

    with patch("server.services.workflows.verification_agent.get_provider", return_value=object()), patch(
        "server.services.workflows.verification_agent.planner_provider_name",
        return_value="codex",
    ), patch(
        "server.services.workflows.verification_agent.planner_model_name",
        return_value="gpt-5-codex",
    ), patch(
        "server.services.workflows.verification_agent.call_full_plan_provider",
        side_effect=_fake_call_full_plan_provider,
    ):
        result = verify_with_agent(payload, skip_provider=False)

    assert result["status"] == "passed"
    assert result["suggested_next_action"] == "release_ready"
    assert "raw_output" in " ".join(result["evidence_used"])
