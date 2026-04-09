"""Tests for skill_loader, context_loader, crew_engine, task_runner, llm_adapter, and skills API."""
import json
import os
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from server.services.task_runtime import TaskExecutionResult


def _runtime_result(
    *,
    text: str = "",
    error: str | None = None,
    execution_time_ms: int = 1,
    runtime_backend: str = "legacy",
):
    return TaskExecutionResult(
        text=text,
        files=[],
        error=error,
        execution_time_ms=execution_time_ms,
        runtime_backend=runtime_backend,
    )

# ── skill_loader tests ───────────────────────────────────────


def test_list_skills():
    from server.services.skill_loader import list_skills
    skills = list_skills()
    assert isinstance(skills, list)
    assert len(skills) > 0
    assert "seo-audit" in skills
    assert "copywriting" in skills


def test_load_skill_exists():
    from server.services.skill_loader import load_skill
    text = load_skill("seo-audit")
    assert isinstance(text, str)
    assert len(text) > 100
    assert "SEO" in text.upper()


def test_load_skill_not_found():
    from server.services.skill_loader import load_skill
    with pytest.raises(FileNotFoundError, match="Skill not found"):
        load_skill("nonexistent-skill-xyz")


def test_load_skill_traversal_blocked():
    from server.services.skill_loader import load_skill
    with pytest.raises(FileNotFoundError):
        load_skill("../../etc/passwd")


# ── context_loader tests ─────────────────────────────────────


def test_load_context_default(tmp_path):
    from server.services.context_loader import load_context
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "product-marketing-context.md").write_text("# Product\nHello world")
    ctx = load_context(tmp_path)
    assert "Product Marketing Context" in ctx
    assert "Hello world" in ctx


def test_load_context_extra_files(tmp_path):
    from server.services.context_loader import load_context
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    (agents_dir / "product-marketing-context.md").write_text("# PMC")
    (tmp_path / "readme.md").write_text("This is readme")
    ctx = load_context(tmp_path, extra_files=["readme.md"])
    assert "PMC" in ctx
    assert "readme.md" in ctx
    assert "This is readme" in ctx


def test_load_context_traversal_blocked(tmp_path):
    from server.services.context_loader import load_context
    ctx = load_context(tmp_path, extra_files=["../../etc/passwd"])
    # Should not crash, just skip the bad path
    assert "passwd" not in ctx


def test_load_context_missing_context_file(tmp_path):
    from server.services.context_loader import load_context
    ctx = load_context(tmp_path)
    assert ctx == ""  # no product-marketing-context.md


def test_load_context_file_size_limit(tmp_path):
    from server.services.context_loader import load_context, MAX_FILE_SIZE
    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    big_content = "x" * (MAX_FILE_SIZE + 10000)
    (agents_dir / "product-marketing-context.md").write_text(big_content)
    ctx = load_context(tmp_path)
    # Content should be truncated
    assert len(ctx) <= MAX_FILE_SIZE + 200  # header + truncated content


# ── crew_engine tests ────────────────────────────────────────


def test_crew_engine_build_system_prompt():
    from server.services.crew_engine import CrewEngine
    engine = CrewEngine()
    persona = {"display_name": "SEO Expert", "goal": "Optimize rankings", "body": "You are detailed."}
    prompt = engine._build_system_prompt(persona)
    assert "SEO Expert" in prompt
    assert "Optimize rankings" in prompt
    assert "You are detailed." in prompt


def test_crew_engine_build_user_message():
    from server.services.crew_engine import CrewEngine
    from server.config import PROJECT_ROOT
    engine = CrewEngine(PROJECT_ROOT)
    msg = engine._build_user_message("seo-audit", "Audit synapse.network", None)
    assert "Task" in msg
    assert "Audit synapse.network" in msg
    assert "Skill Instructions" in msg


def test_crew_engine_build_user_message_missing_skill():
    from server.services.crew_engine import CrewEngine
    from server.config import PROJECT_ROOT
    engine = CrewEngine(PROJECT_ROOT)
    msg = engine._build_user_message("nonexistent-skill-xyz", "Test task", None)
    assert "Test task" in msg
    # Should proceed without skill instructions (just warns)


def test_crew_engine_execute_no_api_key():
    from server.services.crew_engine import CrewEngine
    from server.config import PROJECT_ROOT
    from server.services.llm_adapter import OpenAIProvider
    engine = CrewEngine(PROJECT_ROOT)
    persona = {"display_name": "Test", "goal": "Test", "body": ""}
    # Force openai provider with no key
    with patch("server.services.crew_engine.get_provider", return_value=OpenAIProvider(api_key="")):
        result = engine.execute(persona, "seo-audit", "test task")
    assert result.error is not None
    assert "API_KEY" in result.error


def test_crew_engine_execute_success(tmp_path):
    from server.services.crew_engine import CrewEngine
    engine = CrewEngine(tmp_path)
    # Create a minimal skill
    skills_dir = tmp_path / ".agents" / "skills" / "test-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("# Test Skill\nDo the thing.")

    persona = {"display_name": "Tester", "goal": "Test", "body": "You test."}
    mock_provider = MagicMock()
    mock_provider.name = "openai"
    mock_provider.call.return_value = ("# Result\nDone!", 42)

    with patch("server.services.crew_engine.get_provider", return_value=mock_provider), \
         patch("server.services.crew_engine.load_skill") as mock_load:
        mock_load.return_value = "# Test Skill\nDo the thing."
        output_dir = tmp_path / "output"
        result = engine.execute(persona, "test-skill", "do the test", output_dir=output_dir)

    assert result.error is None
    assert "Result" in result.text
    assert result.tokens_used == 42
    assert result.execution_time_ms >= 0
    assert len(result.files) == 1
    assert result.files[0].exists()
    # Check metadata file
    meta_path = output_dir / "metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["tokens_used"] == 42


def test_crew_engine_execute_api_error():
    from server.services.crew_engine import CrewEngine
    from server.config import PROJECT_ROOT
    engine = CrewEngine(PROJECT_ROOT)
    persona = {"display_name": "Test", "goal": "Test", "body": ""}
    mock_provider = MagicMock()
    mock_provider.name = "openai"
    mock_provider.call.side_effect = RuntimeError("LLM API error 429: Rate limited")

    with patch("server.services.crew_engine.get_provider", return_value=mock_provider):
        result = engine.execute(persona, "seo-audit", "test")
    assert result.error is not None
    assert "429" in result.error


# ── Skills API tests ─────────────────────────────────────────


def test_get_skills_api(client):
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    skills = resp.json()
    assert isinstance(skills, list)
    assert "seo-audit" in skills


# ── run_task with skill (integration) ────────────────────────


def test_run_task_uses_auto_selected_skill(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "test task",
        "agent_id": "dev_rel",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/run")

    assert resp.status_code == 200
    assert resp.json()["skill_name"]
    mock_dispatch.assert_called_once()


def test_run_task_with_skill_returns_running(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "audit my site SEO",
        "agent_id": "seo_strategist",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/run")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["skill_name"] == "seo-audit"
    mock_dispatch.assert_called_once()


def test_run_task_skill_from_query_param(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "write copy",
        "agent_id": "content_writer",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        resp = synced_client.post(f"/api/tasks/{task_id}/run?skill=copywriting")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["skill_name"] == "copywriting"


def test_create_task_with_skill_and_context(synced_client):
    resp = synced_client.post("/api/tasks", json={
        "description": "Analyze competitor",
        "agent_id": "seo_strategist",
        "skill_name": "competitor-alternatives",
        "context_files": ["README.md", "docs/phase2-plan.md"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["skill_name"] == "competitor-alternatives"
    assert "README.md" in data["context_files"]


def test_task_logs_include_skill(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "test",
        "agent_id": "dev_rel",
        "skill_name": "content-strategy",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")

    logs = synced_client.get(f"/api/tasks/{task_id}/logs").json()
    event_types = [l["event_type"] for l in logs]
    assert "started" in event_types
    started_log = next(l for l in logs if l["event_type"] == "started")
    assert "content-strategy" in started_log["detail"]


# ── task_runner unit tests ───────────────────────────────────


def test_task_runner_happy_path(synced_client):
    """Integration test: task_runner completes a task via mocked engine."""
    from server.services.task_runner import _run_task_sync

    # Create a task and move to running via API
    create = synced_client.post("/api/tasks", json={
        "description": "Write landing page",
        "agent_id": "content_writer",
        "skill_name": "copywriting",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "content_writer", "display_name": "Writer", "goal": "Write", "body": ""}

    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(text="# Landing Page\nGreat copy here", execution_time_ms=1234)
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "copywriting")

    # Verify task completed
    resp = synced_client.get(f"/api/tasks/{task_id}")
    data = resp.json()
    assert data["status"] == "completed"
    assert "Landing Page" in data["output_content"]
    assert data["execution_time_ms"] == 1234


def test_task_runner_failure(synced_client):
    """When engine raises, task should be marked failed."""
    from server.services.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "fail task",
        "agent_id": "dev_rel",
        "skill_name": "seo-audit",
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "dev_rel", "display_name": "DR", "goal": "", "body": ""}

    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.side_effect = RuntimeError("LLM exploded")
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "seo-audit")

    resp = synced_client.get(f"/api/tasks/{task_id}")
    data = resp.json()
    assert data["status"] == "failed"
    assert "LLM exploded" in data["output_content"]


def test_task_runner_with_approval(synced_client):
    """Task requiring approval goes to pending_approval after engine completes."""
    from server.services.task_runner import _run_task_sync

    create = synced_client.post("/api/tasks", json={
        "description": "publish tweet",
        "agent_id": "growth_lead",
        "skill_name": "social-content",
        "requires_approval": True,
    })
    task_id = create.json()["id"]

    with patch("server.services.task_runner.dispatch") as mock_dispatch:
        mock_dispatch.return_value = MagicMock()
        synced_client.post(f"/api/tasks/{task_id}/run")

    persona = {"role": "growth_lead", "display_name": "GL", "goal": "", "body": ""}

    with patch("server.services.task_runner.get_task_runtime") as mock_runtime_factory:
        mock_runtime = MagicMock()
        mock_runtime.execute.return_value = _runtime_result(text="Tweet: Check out Synapse!", execution_time_ms=500)
        mock_runtime_factory.return_value = mock_runtime
        _run_task_sync(task_id, persona, "social-content")

    resp = synced_client.get(f"/api/tasks/{task_id}")
    assert resp.json()["status"] == "pending_approval"

    # Approval should exist
    approvals = synced_client.get("/api/approvals?status=pending").json()
    assert any(a["task_id"] == task_id for a in approvals)


# ── LLM adapter tests ───────────────────────────────────────


def test_adapter_get_provider_default():
    from server.services.llm_adapter import get_provider, OpenAIProvider
    with patch("server.config.LLM_PROVIDER", "openai"):
        p = get_provider()
    assert isinstance(p, OpenAIProvider)


def test_adapter_get_provider_claude():
    from server.services.llm_adapter import get_provider, ClaudeProvider
    p = get_provider("claude")
    assert isinstance(p, ClaudeProvider)


def test_adapter_get_provider_copilot():
    from server.services.llm_adapter import get_provider, CopilotProvider
    p = get_provider("copilot")
    assert isinstance(p, CopilotProvider)


def test_adapter_get_provider_unknown():
    from server.services.llm_adapter import get_provider
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("gemini")


def test_adapter_openai_no_key():
    from server.services.llm_adapter import OpenAIProvider
    provider = OpenAIProvider(api_key="")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        provider.call("sys", "usr", "gpt-4o", 0.7, 30)


def test_adapter_claude_no_key():
    from server.services.llm_adapter import ClaudeProvider
    provider = ClaudeProvider(api_key="")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        provider.call("sys", "usr", "claude-3-5-sonnet-20241022", 0.7, 30)


def test_adapter_copilot_no_key():
    from server.services.llm_adapter import CopilotProvider
    auth_service = MagicMock()
    auth_service.resolve_stored_auth.return_value = None
    provider = CopilotProvider(api_key="", auth_service=auth_service)
    with pytest.raises(RuntimeError, match="copilot login"):
        provider.call("sys", "usr", "gpt-4o", 0.7, 30)


def test_adapter_openai_call_success():
    from server.services.llm_adapter import OpenAIProvider
    provider = OpenAIProvider(api_key="sk-test", base_url="http://localhost:9999")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Hello!"}}],
        "usage": {"total_tokens": 10},
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        text, tokens = provider.call("sys", "usr", "gpt-4o", 0.7, 30)
    assert text == "Hello!"
    assert tokens == 10
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "Bearer sk-test" in call_args.kwargs["headers"]["Authorization"]


def test_adapter_claude_call_success():
    from server.services.llm_adapter import ClaudeProvider
    provider = ClaudeProvider(api_key="sk-ant-test", base_url="http://localhost:9999")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [{"text": "Bonjour!"}],
        "usage": {"input_tokens": 5, "output_tokens": 8},
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        text, tokens = provider.call("sys", "usr", "claude-3-5-sonnet-20241022", 0.7, 30)
    assert text == "Bonjour!"
    assert tokens == 13
    call_args = mock_post.call_args
    assert call_args.kwargs["headers"]["x-api-key"] == "sk-ant-test"
    assert call_args.kwargs["headers"]["anthropic-version"] == "2023-06-01"


def test_adapter_copilot_call_success():
    from server.services.llm_adapter import CopilotProvider
    provider = CopilotProvider(api_key="gho_test", base_url="http://localhost:9999")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Copilot says hi"}}],
        "usage": {"total_tokens": 7},
    }
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        text, tokens = provider.call("sys", "usr", "gpt-4o", 0.5, 30)
    assert text == "Copilot says hi"
    assert tokens == 7
    call_args = mock_post.call_args
    assert "Bearer gho_test" in call_args.kwargs["headers"]["Authorization"]


def test_adapter_copilot_rejects_personal_access_token_before_request():
    from server.services.llm_adapter import CopilotProvider

    provider = CopilotProvider(api_key="github_pat_test", base_url="http://localhost:9999")

    with patch("httpx.post") as mock_post:
        with pytest.raises(RuntimeError, match="Personal Access Tokens are not supported"):
            provider.call("sys", "usr", "gpt-4o", 0.5, 30)

    mock_post.assert_not_called()


def test_adapter_copilot_uses_stored_oauth_token():
    from server.services.copilot_auth import StoredCopilotAuth
    from server.services.llm_adapter import CopilotProvider

    auth_service = MagicMock()
    auth_service.resolve_stored_auth.return_value = StoredCopilotAuth(
        token="gho_test",
        login="octocat",
        source="apps_json",
    )
    provider = CopilotProvider(base_url="http://localhost:9999", auth_service=auth_service)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Copilot says hi"}}],
        "usage": {"total_tokens": 7},
    }

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        text, tokens = provider.call("sys", "usr", "gpt-4o", 0.5, 30)

    assert text == "Copilot says hi"
    assert tokens == 7
    call_args = mock_post.call_args
    assert "Bearer gho_test" in call_args.kwargs["headers"]["Authorization"]


def test_adapter_api_error():
    from server.services.llm_adapter import OpenAIProvider
    provider = OpenAIProvider(api_key="sk-test")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    with patch("httpx.post", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="LLM API error 500"):
            provider.call("sys", "usr", "gpt-4o", 0.7, 30)


def test_adapter_provider_from_env():
    from server.services.llm_adapter import get_provider, ClaudeProvider
    with patch("server.config.LLM_PROVIDER", "claude"):
        p = get_provider()
    assert isinstance(p, ClaudeProvider)
