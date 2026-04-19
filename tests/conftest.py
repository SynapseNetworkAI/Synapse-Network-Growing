"""Shared test fixtures for the Ops Dashboard API tests."""
import json
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.database import Base, get_db, SessionLocal as _ProdSession
from server.main import app
from server.config import PROJECT_ROOT
from server.services.agents.loader import ensure_agents_loaded
from server.services.runtime.copilot_sdk_state import task_output_dir

# In-memory SQLite for tests — StaticPool ensures all connections share one DB
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(TEST_ENGINE, "connect")
def _enable_fk(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def _fake_vcs_delivery(db, requirement, workflow_run, step):
    branch_name = f"ops/req-{getattr(requirement, 'id', 'x')}-test"
    payload = {
        "status": "delivered",
        "branch_name": branch_name,
        "base_branch": "main",
        "remote_name": "origin",
        "remote_url": "https://github.com/example/test-repo.git",
        "blockers": [],
        "repositories": [
            {
                "repo_path": str(getattr(requirement, "target_project_path", "") or "test-repo"),
                "status": "delivered",
                "branch_name": branch_name,
                "commit_sha": "deadbeef0001",
                "remote_sha": "deadbeef0001",
                "remote_url": "https://github.com/example/test-repo.git",
                "committed": True,
                "pushed": True,
                "blockers": [],
            }
        ],
        "delivered_repository_count": 1,
    }
    return payload, None


def _fake_review_pr_sync(db, requirement, workflow_run, step, delivery_contract=None, vcs_payload=None):
    branch_name = str((vcs_payload or {}).get("branch_name") or f"ops/req-{getattr(requirement, 'id', 'x')}-test")
    base_branch = str((vcs_payload or {}).get("base_branch") or "main")
    return {
        "status": "draft",
        "pr_status": "draft",
        "pr_number": 1,
        "pr_url": "https://github.com/example/test-repo/pull/1",
        "head_branch": branch_name,
        "base_branch": base_branch,
        "compare_url": f"https://github.com/example/test-repo/compare/{base_branch}...{branch_name}",
        "blockers": [],
    }, None


def _fake_capture_task_file_change_baseline(db, task, requirement=None, step=None):
    raw_output_path = str(getattr(task, "output_path", "") or "").strip()
    if raw_output_path:
        output_path = Path(raw_output_path).expanduser()
        output_dir = output_path.parent
    else:
        output_dir = task_output_dir(PROJECT_ROOT, str(getattr(task, "agent_id", "test")), int(task.id))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "file-changes-baseline.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-04-13T00:00:00+00:00",
                "task_id": int(task.id),
                "step_id": int(getattr(step, "id", 0) or 0) or None,
                "baseline_mode": "content_hash",
                "project_baselines": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _fake_snapshot_file_changes(db, task, requirement, step=None):
    raw_output_path = str(getattr(task, "output_path", "") or "").strip()
    if raw_output_path:
        output_path = Path(raw_output_path).expanduser()
        output_dir = output_path.parent
    else:
        output_dir = task_output_dir(PROJECT_ROOT, str(getattr(task, "agent_id", "test")), int(task.id))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "file-changes.json").write_text(
        json.dumps(
            {
                "changed_files": [],
                "target_project_path": str(getattr(requirement, "target_project_path", "") or "") or None,
                "changed_target_project_paths": [],
                "project_snapshots": [],
                "all_target_project_paths": [],
                "source": "snapshot",
                "captured_at": "2026-04-13T00:00:00+00:00",
                "task_id": int(task.id),
                "step_id": int(getattr(step, "id", 0) or 0) or None,
                "baseline_captured_at": "2026-04-13T00:00:00+00:00",
                "baseline_mode": "content_hash",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _fake_generate_plan_brief_markdown_with_agent(db, requirement, *, acceptance_contract):
    return (
        "\n\n".join(
            [
                str(getattr(requirement, "title", "") or "").strip(),
                str(getattr(requirement, "description_markdown", "") or "").strip(),
                "Target project:",
                str(getattr(requirement, "target_project_path", "") or "test-repo").strip(),
                "Test raw Codex plan output.",
            ]
        ).strip(),
        {
            "planning_mode": "codex_raw_exec_plan",
            "planning_session_id": "thread-test-plan",
            "planning_prompt_path": "runtime/plans/req-test-plan.prompt.md",
            "planning_output_path": "runtime/plans/req-test-plan.md",
            "planning_command": ["codex", "exec", "-", "--sandbox", "read-only"],
        },
    )


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=TEST_ENGINE)
    with patch(
        "server.services.requirements.service._generate_plan_brief_markdown_with_agent",
        _fake_generate_plan_brief_markdown_with_agent,
    ), patch("server.main.config.COPILOT_SDK_MONITOR_ENABLED", False), patch(
        "server.main.config.OPENAI_RESPONSES_MONITOR_ENABLED", False
    ), patch(
        "server.main.config.CODEX_CLI_MONITOR_ENABLED", False
    ), patch(
        "server.main.config.BUG_LOG_SWEEP_SCHEDULER_ENABLED", False
    ), patch(
        "server.config.LARK_DELIVERY_DRY_RUN", True
    ):
        yield
    with TEST_ENGINE.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        inspector = inspect(conn)
        for table_name in inspector.get_table_names():
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    app.dependency_overrides.clear()


@pytest.fixture
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def synced_client(client):
    """Client with agents already loaded."""
    db = TestSession()
    ensure_agents_loaded(db)
    db.commit()
    db.close()
    return client
