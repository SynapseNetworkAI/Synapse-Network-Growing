from __future__ import annotations

"""Tests for role-based session reuse and serial requirement execution."""
from unittest.mock import MagicMock, patch, call
from pathlib import Path

import pytest

from server.database import RequirementRow, TaskRow
from server.services.runtime.task_runner import _run_task_sync
from server.services.runtime.task_runtime import (
    CopilotSDKTaskRuntime,
    RoleSessionInfo,
    TaskExecutionResult,
    get_copilot_sdk_runtime,
)


def _runtime_result(*, text: str = "", error: str | None = None):
    return TaskExecutionResult(
        text=text, files=[], error=error, execution_time_ms=5,
        runtime_backend="legacy", events=[], deferred=False,
    )


def _sync_dispatch(task_id: int, agent_persona: dict, skill_name: str):
    _run_task_sync(task_id, agent_persona, skill_name)
    return MagicMock(name=f"task-{task_id}")


# ── Role session reuse unit tests ────────────────────────────


class TestRoleSessionReuse:
    """Verify that CopilotSDKTaskRuntime reuses sessions per agent_id."""

    def test_first_call_creates_new_session(self, tmp_path):
        bridge = MagicMock()
        runtime = CopilotSDKTaskRuntime(project_root=tmp_path, bridge=bridge)

        result = runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Audit the site",
        )

        assert result.deferred is True
        assert result.runtime_session_id is not None
        assert result.runtime_session_id.startswith("role-seo_strategist-")
        bridge.start_session.assert_called_once()
        payload = bridge.start_session.call_args[0][0]
        assert payload["action"] == "start"
        assert "prompt" in payload

    def test_second_call_same_role_resumes_session(self, tmp_path):
        bridge = MagicMock()
        runtime = CopilotSDKTaskRuntime(project_root=tmp_path, bridge=bridge)

        result1 = runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="First task",
        )
        session_id = result1.runtime_session_id

        result2 = runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Second task",
        )

        assert result2.runtime_session_id == session_id
        bridge.resume_session.assert_called_once()
        resume_payload = bridge.resume_session.call_args[0][0]
        assert resume_payload["action"] == "resume"
        assert resume_payload["sessionId"] == session_id
        assert "prompt" in resume_payload  # New prompt sent on resume

    def test_different_roles_get_different_sessions(self, tmp_path):
        bridge = MagicMock()
        runtime = CopilotSDKTaskRuntime(project_root=tmp_path, bridge=bridge)

        result1 = runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="SEO task",
        )
        result2 = runtime.execute(
            persona={"role": "content_writer", "goal": "Write"},
            skill_name="copywriting",
            task_description="Write task",
        )

        assert result1.runtime_session_id != result2.runtime_session_id
        assert result1.runtime_session_id.startswith("role-seo_strategist-")
        assert result2.runtime_session_id.startswith("role-content_writer-")
        assert bridge.start_session.call_count == 2

    def test_resume_failure_falls_back_to_new_session(self, tmp_path):
        bridge = MagicMock()
        bridge.resume_session.side_effect = RuntimeError("session expired")
        runtime = CopilotSDKTaskRuntime(project_root=tmp_path, bridge=bridge)

        # First call: create
        runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="First task",
        )
        old_session = runtime._role_sessions["seo_strategist"].session_id

        # Second call: resume fails → fallback to new
        result2 = runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Second task",
        )

        assert result2.runtime_session_id != old_session
        assert result2.runtime_session_id.startswith("role-seo_strategist-")
        # start_session called twice: original + fallback
        assert bridge.start_session.call_count == 2

    def test_clear_role_sessions(self, tmp_path):
        bridge = MagicMock()
        runtime = CopilotSDKTaskRuntime(project_root=tmp_path, bridge=bridge)

        runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Task 1",
        )
        assert "seo_strategist" in runtime._role_sessions

        runtime.clear_role_sessions()
        assert len(runtime._role_sessions) == 0

        # Next call should create new session
        result = runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Task 2",
        )
        assert bridge.start_session.call_count == 2  # Two new sessions

    def test_each_task_gets_own_output_dir(self, tmp_path):
        bridge = MagicMock()
        runtime = CopilotSDKTaskRuntime(project_root=tmp_path, bridge=bridge)

        out1 = tmp_path / "out1"
        out2 = tmp_path / "out2"

        runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Task 1",
            output_dir=out1,
        )
        runtime.execute(
            persona={"role": "seo_strategist", "goal": "Optimize"},
            skill_name="seo-audit",
            task_description="Task 2",
            output_dir=out2,
        )

        # Resume payload should use the second output dir
        resume_payload = bridge.resume_session.call_args[0][0]
        assert resume_payload["outputDir"] == str(out2)


# ── Serial requirement execution tests ───────────────────────


class TestSerialRequirementExecution:
    """Verify that only one requirement can be in_progress at a time."""

    def test_start_blocked_when_another_is_in_progress(self, synced_client, db_session):
        # Create first requirement
        resp1 = synced_client.post(
            "/api/requirements",
            json={"title": "Req A", "description_markdown": "First requirement", "priority": "normal"},
        )
        req_a_id = resp1.json()["requirement"]["id"]
        synced_client.post(f"/api/requirements/{req_a_id}/plan")

        # Create second requirement
        resp2 = synced_client.post(
            "/api/requirements",
            json={"title": "Req B", "description_markdown": "Second requirement", "priority": "normal"},
        )
        req_b_id = resp2.json()["requirement"]["id"]
        synced_client.post(f"/api/requirements/{req_b_id}/plan")

        # Start first requirement — set it to in_progress manually via a non-completing runtime
        class HangingRuntime:
            def execute(self, **_kwargs):
                return TaskExecutionResult(
                    text="", files=[], error=None, execution_time_ms=0,
                    runtime_backend="copilot_sdk", runtime_session_id="test-session",
                    events=[], deferred=True,
                )

        with patch("server.services.runtime.task_runner.get_task_runtime", return_value=HangingRuntime()), patch(
            "server.services.runtime.task_runner.dispatch", side_effect=_sync_dispatch
        ):
            start_a = synced_client.post(f"/api/requirements/{req_a_id}/start")
        assert start_a.status_code == 200
        assert start_a.json()["requirement"]["status"] == "in_progress"

        # Try to start second requirement — should fail
        start_b = synced_client.post(f"/api/requirements/{req_b_id}/start")
        assert start_b.status_code == 400
        assert "调度槽位已满" in start_b.json()["detail"]

    def test_can_start_after_previous_completes(self, synced_client, db_session):
        class FakeRuntime:
            def execute(self, *, task_description, **_kwargs):
                if "[workflow_step:implementation]" in task_description:
                    return _runtime_result(text="Done implement.")
                if "[workflow_step:review]" in task_description:
                    return _runtime_result(text="Review passed.")
                if "[workflow_step:test]" in task_description:
                    return _runtime_result(text="Test passed.")
                return _runtime_result(text="noop")

        # Create & complete first requirement
        resp1 = synced_client.post(
            "/api/requirements",
            json={"title": "Req A", "description_markdown": "First", "priority": "normal"},
        )
        req_a_id = resp1.json()["requirement"]["id"]
        synced_client.post(f"/api/requirements/{req_a_id}/plan")

        with patch("server.services.runtime.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
            "server.services.runtime.task_runner.dispatch", side_effect=_sync_dispatch
        ), patch(
            "server.services.workflows.orchestrator._schedule_advance_queue", return_value=None
        ):
            start_a = synced_client.post(f"/api/requirements/{req_a_id}/start")
        assert start_a.json()["requirement"]["status"] == "done"

        # Create & start second requirement — should work since first is done
        resp2 = synced_client.post(
            "/api/requirements",
            json={"title": "Req B", "description_markdown": "Second", "priority": "normal"},
        )
        req_b_id = resp2.json()["requirement"]["id"]
        synced_client.post(f"/api/requirements/{req_b_id}/plan")

        with patch("server.services.runtime.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
            "server.services.runtime.task_runner.dispatch", side_effect=_sync_dispatch
        ), patch(
            "server.services.workflows.orchestrator._schedule_advance_queue", return_value=None
        ):
            start_b = synced_client.post(f"/api/requirements/{req_b_id}/start")
        assert start_b.status_code == 200
        assert start_b.json()["requirement"]["status"] == "done"


# ── Session cleanup on requirement completion ─────────────────


class TestSessionCleanupOnCompletion:
    """Verify role sessions are cleared when a requirement finishes."""

    def test_sessions_cleared_on_requirement_done(self, synced_client, db_session):
        call_log = []

        class FakeRuntime:
            def execute(self, *, task_description, **_kwargs):
                if "[workflow_step:implementation]" in task_description:
                    return _runtime_result(text="Done.")
                if "[workflow_step:review]" in task_description:
                    return _runtime_result(text="Passed.")
                if "[workflow_step:test]" in task_description:
                    return _runtime_result(text="Passed.")
                return _runtime_result(text="noop")

        resp = synced_client.post(
            "/api/requirements",
            json={"title": "Test Req", "description_markdown": "Test cleanup", "priority": "normal"},
        )
        req_id = resp.json()["requirement"]["id"]
        synced_client.post(f"/api/requirements/{req_id}/plan")

        with patch("server.services.runtime.task_runner.get_task_runtime", return_value=FakeRuntime()), patch(
            "server.services.runtime.task_runner.dispatch", side_effect=_sync_dispatch
        ), patch(
            "server.services.workflows.orchestrator._schedule_advance_queue", return_value=None
        ), patch(
            "server.services.workflows.orchestrator._clear_role_sessions", wraps=lambda: call_log.append("cleared")
        ) as mock_clear:
            start_resp = synced_client.post(f"/api/requirements/{req_id}/start")

        assert start_resp.json()["requirement"]["status"] == "done"
        # _clear_role_sessions should have been called at least once
        assert len(call_log) >= 1
