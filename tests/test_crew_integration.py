"""Tests for skill_loader, context_loader, crew_engine, task_runner, and skills API."""
import json
import time
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

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
    engine = CrewEngine(PROJECT_ROOT)
    persona = {"display_name": "Test", "goal": "Test", "body": ""}
    with patch("server.services.crew_engine.LLM_API_KEY", ""):
        result = engine.execute(persona, "seo-audit", "test task")
    assert result.error is not None
    assert "OPENAI_API_KEY" in result.error


def test_crew_engine_execute_success(tmp_path):
    from server.services.crew_engine import CrewEngine
    engine = CrewEngine(tmp_path)
    # Create a minimal skill
    skills_dir = tmp_path / ".agents" / "skills" / "test-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("# Test Skill\nDo the thing.")

    persona = {"display_name": "Tester", "goal": "Test", "body": "You test."}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "# Result\nDone!"}}],
        "usage": {"total_tokens": 42},
    }

    with patch("server.services.crew_engine.LLM_API_KEY", "sk-test"), \
         patch("server.services.crew_engine.load_skill") as mock_load, \
         patch("httpx.post", return_value=mock_resp):
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
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = "Rate limited"

    with patch("server.services.crew_engine.LLM_API_KEY", "sk-test"), \
         patch("httpx.post", return_value=mock_resp):
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


def test_run_task_requires_skill(synced_client):
    create = synced_client.post("/api/tasks", json={
        "description": "test task",
        "agent_id": "dev_rel",
    })
    task_id = create.json()["id"]
    # No skill → error
    resp = synced_client.post(f"/api/tasks/{task_id}/run")
    assert resp.status_code == 400
    assert "skill" in resp.json()["detail"].lower()


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

    mock_result = MagicMock()
    mock_result.text = "# Landing Page\nGreat copy here"
    mock_result.files = []
    mock_result.error = None
    mock_result.execution_time_ms = 1234

    persona = {"role": "content_writer", "display_name": "Writer", "goal": "Write", "body": ""}

    with patch("server.services.task_runner._engine") as mock_engine:
        mock_engine.execute.return_value = mock_result
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

    with patch("server.services.task_runner._engine") as mock_engine:
        mock_engine.execute.side_effect = RuntimeError("LLM exploded")
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

    mock_result = MagicMock()
    mock_result.text = "Tweet: Check out Synapse!"
    mock_result.files = []
    mock_result.error = None
    mock_result.execution_time_ms = 500

    persona = {"role": "growth_lead", "display_name": "GL", "goal": "", "body": ""}

    with patch("server.services.task_runner._engine") as mock_engine:
        mock_engine.execute.return_value = mock_result
        _run_task_sync(task_id, persona, "social-content")

    resp = synced_client.get(f"/api/tasks/{task_id}")
    assert resp.json()["status"] == "pending_approval"

    # Approval should exist
    approvals = synced_client.get("/api/approvals?status=pending").json()
    assert any(a["task_id"] == task_id for a in approvals)
