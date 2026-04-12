from __future__ import annotations

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import sessionmaker

from server import config
from server.database import TaskRow
from server.services.workflow_orchestrator import pause_task
from server.services.llm_adapter import OpenAIProvider
from server.services.openai_responses_monitor import OpenAIResponsesTaskMonitor
from server.services.task_runner import _run_task_sync
from server.services.task_runtime import OpenAIResponsesTaskRuntime, TaskExecutionResult


def _runtime_result(
    *,
    text: str = "",
    error: str | None = None,
    execution_time_ms: int = 1,
    runtime_backend: str = "openai_responses",
    runtime_session_id: str | None = None,
    deferred: bool = False,
    files: list[Path] | None = None,
):
    return TaskExecutionResult(
        text=text,
        files=files or [],
        error=error,
        execution_time_ms=execution_time_ms,
        runtime_backend=runtime_backend,
        runtime_session_id=runtime_session_id,
        deferred=deferred,
    )


def test_resolve_orchestration_backend_for_openai_session():
    assert config.resolve_orchestration_backend(provider="openai", execution_mode="session", override="") == "openai_responses"


def test_resolve_orchestration_backend_prefers_explicit_override():
    assert config.resolve_orchestration_backend(
        provider="openai",
        execution_mode="session",
        override="copilot_sdk",
    ) == "copilot_sdk"


def test_openai_responses_runtime_returns_deferred_result_and_writes_metadata(tmp_path):
    provider = MagicMock()
    provider.create_response.return_value = {
        "id": "resp_123",
        "status": "in_progress",
        "conversation": {"id": "conv_123"},
    }
    runtime = OpenAIResponsesTaskRuntime(project_root=tmp_path, provider=provider)
    output_dir = tmp_path / "roles" / "content_writer" / "outputs" / "task-1"

    result = runtime.execute(
        persona={"role": "content_writer", "display_name": "Writer", "goal": "Write", "body": ""},
        skill_name="copywriting",
        task_description="Draft the page copy",
        output_dir=output_dir,
    )

    assert result.deferred is True
    assert result.runtime_backend == "openai_responses"
    assert result.runtime_session_id == "resp_123"
    provider.create_response.assert_called_once()
    assert provider.create_response.call_args.kwargs["previous_response_id"] is None
    metadata = (output_dir / "metadata.json").read_text(encoding="utf-8")
    assert "resp_123" in metadata
    assert "conv_123" in metadata


def test_openai_responses_runtime_reuses_previous_response_id_for_same_role(tmp_path):
    provider = MagicMock()
    provider.create_response.side_effect = [
        {"id": "resp_1", "status": "in_progress"},
        {"id": "resp_2", "status": "in_progress"},
    ]
    runtime = OpenAIResponsesTaskRuntime(project_root=tmp_path, provider=provider)

    runtime.execute(
        persona={"role": "seo_strategist", "display_name": "SEO", "goal": "Audit", "body": ""},
        skill_name="seo-audit",
        task_description="First task",
        output_dir=tmp_path / "out1",
    )
    runtime.execute(
        persona={"role": "seo_strategist", "display_name": "SEO", "goal": "Audit", "body": ""},
        skill_name="seo-audit",
        task_description="Second task",
        output_dir=tmp_path / "out2",
    )

    assert provider.create_response.call_count == 2
    second_call = provider.create_response.call_args_list[1]
    assert second_call.kwargs["previous_response_id"] == "resp_1"


def test_openai_responses_runtime_handles_immediate_completion(tmp_path):
    provider = MagicMock()
    provider.create_response.return_value = {
        "id": "resp_done",
        "status": "completed",
        "output_text": "# Done\nAll set.",
        "created_at": 100,
        "completed_at": 102,
    }
    provider.extract_response_text.return_value = "# Done\nAll set."
    provider.extract_response_tokens.return_value = 123
    runtime = OpenAIResponsesTaskRuntime(project_root=tmp_path, provider=provider)
    output_dir = tmp_path / "task-output"

    result = runtime.execute(
        persona={"role": "content_writer", "display_name": "Writer", "goal": "Write", "body": ""},
        skill_name="copywriting",
        task_description="Complete immediately",
        output_dir=output_dir,
    )

    assert result.deferred is False
    assert result.tokens_used == 123
    assert result.runtime_session_id == "resp_done"
    assert (output_dir / "output.md").read_text(encoding="utf-8") == "# Done\nAll set."


def test_openai_monitor_completes_detached_task(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={
        "description": "Complete detached openai response",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    predicted_output = tmp_path / "roles" / "content_writer" / "outputs" / f"task-{task_id}" / "output.md"
    with patch("server.services.task_runner.PROJECT_ROOT", tmp_path), patch(
        "server.services.task_runner.get_task_runtime"
    ) as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            execution_time_ms=7,
            runtime_session_id="resp_async_123",
            deferred=True,
            files=[predicted_output],
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "content_writer", "display_name": "Writer", "goal": "", "body": ""}, "copywriting")

    provider = MagicMock()
    provider.retrieve_response.return_value = {
        "id": "resp_async_123",
        "status": "completed",
        "output_text": "# Async output\nFinished in background",
        "created_at": 100,
        "completed_at": 103,
    }
    provider.extract_response_text.return_value = "# Async output\nFinished in background"

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = OpenAIResponsesTaskMonitor(project_root=tmp_path, session_factory=session_factory, provider=provider)
    monitor.poll_once()

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "completed"
    assert task["runtime_backend"] == "openai_responses"
    assert task["runtime_session_id"] == "resp_async_123"
    assert "Async output" in task["output_content"]
    assert task["execution_time_ms"] == 3000


def test_openai_monitor_marks_incomplete_response_as_failed(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={
        "description": "Fail detached openai response",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    predicted_output = tmp_path / "roles" / "content_writer" / "outputs" / f"task-{task_id}" / "output.md"
    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).status = "running"
    cast(Any, row).runtime_backend = "openai_responses"
    cast(Any, row).runtime_session_id = "resp_async_fail"
    cast(Any, row).output_path = str(predicted_output)
    db_session.commit()

    provider = MagicMock()
    provider.retrieve_response.return_value = {
        "id": "resp_async_fail",
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
    }
    provider.extract_response_error.return_value = "Response incomplete: max_output_tokens"
    provider.extract_response_text.return_value = ""

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = OpenAIResponsesTaskMonitor(project_root=tmp_path, session_factory=session_factory, provider=provider)
    monitor.poll_once()

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "failed"
    assert "max_output_tokens" in (task["last_error_message"] or "")


def test_openai_monitor_alerts_and_pauses_on_quota_error(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={
        "description": "Quota guarded detached openai response",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch"):
        synced_client.post(f"/api/tasks/{task_id}/run")

    predicted_output = tmp_path / "roles" / "content_writer" / "outputs" / f"task-{task_id}" / "output.md"
    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).status = "running"
    cast(Any, row).runtime_backend = "openai_responses"
    cast(Any, row).runtime_session_id = "resp_quota_fail"
    cast(Any, row).output_path = str(predicted_output)
    db_session.commit()

    provider = MagicMock()
    provider.retrieve_response.return_value = {
        "id": "resp_quota_fail",
        "status": "failed",
        "error": {"message": "You exceeded your current quota."},
    }
    provider.extract_response_error.return_value = "You exceeded your current quota."
    provider.extract_response_text.return_value = ""

    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=db_session.bind)
    monitor = OpenAIResponsesTaskMonitor(project_root=tmp_path, session_factory=session_factory, provider=provider)
    with patch("server.services.openai_responses_monitor.send_lark_text_alert", return_value=(True, "ok")) as mock_alert, patch(
        "server.services.llm_adapter.OpenAIProvider.cancel_response",
        return_value={},
    ):
        monitor.poll_once()

    mock_alert.assert_called_once()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "cancelled"
    assert "current quota" in str(task["last_error_message"]).lower()

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_provider_alert" in event_types
    assert "paused" in event_types


def test_task_runner_pauses_immediate_openai_guard_errors(synced_client, db_session, tmp_path):
    create = synced_client.post("/api/tasks", json={
        "description": "Immediate openai guard failure",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.PROJECT_ROOT", tmp_path), patch(
        "server.services.task_runner.get_task_runtime"
    ) as mock_runtime_factory, patch(
        "server.services.openai_responses_monitor.send_lark_text_alert",
        return_value=(True, "ok"),
    ) as mock_alert:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(
            error="The requested model 'openai' does not exist.",
            runtime_backend="openai_responses",
            execution_time_ms=5,
        )
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, {"role": "content_writer", "display_name": "Writer", "goal": "", "body": ""}, "copywriting")

    mock_alert.assert_called_once()
    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "cancelled"
    assert "does not exist" in str(task["last_error_message"]).lower()

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [log["event_type"] for log in logs]
    assert "runtime_provider_alert" in event_types
    assert "paused" in event_types


def test_pause_task_tolerates_openai_response_already_failed(synced_client, db_session):
    create = synced_client.post("/api/tasks", json={
        "description": "Pause running openai response",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    row = db_session.query(TaskRow).filter_by(id=task_id).first()
    cast(Any, row).status = "running"
    cast(Any, row).runtime_backend = "openai_responses"
    cast(Any, row).runtime_session_id = "resp_terminal"
    db_session.commit()

    with patch(
        "server.services.llm_adapter.OpenAIProvider.cancel_response",
        side_effect=RuntimeError("LLM API error 400: Cannot cancel a failed response."),
    ):
        pause_task(db_session, task_id, reason="quota guard", event_detail="Paused after guard")

    task = synced_client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "cancelled"
    assert task["last_error_message"] == "quota guard"


def test_openai_provider_normalizes_provider_name_model_alias_for_chat_calls(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 7},
            }

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["model"] = json["model"]
        return FakeResponse()

    with patch("httpx.post", side_effect=fake_post):
        text, tokens = provider.call("sys", "user", "openai", 0.1, 30)

    assert text == "ok"
    assert tokens == 7
    assert captured["model"] == "gpt-4o"


def test_openai_provider_normalizes_provider_name_model_alias_for_responses(monkeypatch):
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    provider = OpenAIProvider()

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "resp_123", "status": "in_progress"}

    def fake_post(url, *, json=None, headers=None, timeout=None):
        captured["model"] = json["model"]
        return FakeResponse()

    with patch("httpx.post", side_effect=fake_post):
        payload = provider.create_response(
            instructions="plan",
            user_input="task",
            model="openai",
            temperature=0.1,
            timeout=30,
            background=False,
        )

    assert payload["id"] == "resp_123"
    assert captured["model"] == "gpt-4o"
