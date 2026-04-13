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
from server.services.agent_loader import ensure_agents_loaded
from server.services.copilot_sdk_state import task_output_dir

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
        "blockers": [],
        "repositories": [
            {
                "repo_path": str(getattr(requirement, "target_project_path", "") or "test-repo"),
                "status": "delivered",
                "branch_name": branch_name,
                "commit_sha": "deadbeef0001",
                "remote_sha": "deadbeef0001",
                "committed": True,
                "pushed": True,
                "blockers": [],
            }
        ],
        "delivered_repository_count": 1,
    }
    return payload, None


def _fake_capture_task_file_change_baseline(db, task, requirement=None, step=None):
    output_dir = task_output_dir(Path("/tmp"), str(getattr(task, "agent_id", "test")), int(task.id))
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
    output_dir = task_output_dir(Path("/tmp"), str(getattr(task, "agent_id", "test")), int(task.id))
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
    # Also patch SessionLocal used by task_runner to use test DB
    with patch("server.services.task_runner.SessionLocal", TestSession), patch(
        "server.services.copilot_sdk_monitor.SessionLocal", TestSession
    ), patch(
        "server.services.workflow_orchestrator.SessionLocal", TestSession
    ), patch(
        "server.services.workflow_orchestrator._execute_requirement_vcs_delivery", _fake_vcs_delivery
    ), patch(
        "server.services.workflow_orchestrator.capture_task_file_change_baseline",
        _fake_capture_task_file_change_baseline,
    ), patch(
        "server.services.workflow_orchestrator._snapshot_file_changes",
        _fake_snapshot_file_changes,
    ), patch(
        "server.services.workflow_orchestrator._schedule_advance_queue", lambda: None
    ), patch("server.main.config.COPILOT_SDK_MONITOR_ENABLED", False), patch(
        "server.main.config.OPENAI_RESPONSES_MONITOR_ENABLED", False
    ), patch(
        "server.main.config.CODEX_CLI_MONITOR_ENABLED", False
    ), patch(
        "server.main.config.BUG_LOG_SWEEP_SCHEDULER_ENABLED", False
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
