"""Shared test fixtures for the Ops Dashboard API tests."""

import json
import os
from pathlib import Path
import re
import threading
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker


DEFAULT_TEST_DATABASE_URL = (
    "postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/"
    "synapse_growing_test"
)
TEST_DATABASE_URL = (
    os.environ.get("OPS_TEST_POSTGRES_URL", "").strip()
    or os.environ.get("OPS_TEST_DATABASE_URL", "").strip()
    or DEFAULT_TEST_DATABASE_URL
)
# Tests own the database schema and reset it aggressively. Never inherit the
# runtime OPS_DATABASE_URL here, or a local test run can lock/drop the dev DB.
os.environ["OPS_DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("OPS_RELEASE_DEPLOY_BACKEND", "local")


def _ensure_postgres_database(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Tests require a PostgreSQL OPS_DATABASE_URL/OPS_TEST_POSTGRES_URL"
        )
    database_name = url.database or ""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database_name):
        raise RuntimeError(f"Unsafe PostgreSQL test database name: {database_name!r}")
    if not (database_name.endswith("_test") or database_name.startswith("test_")):
        raise RuntimeError(
            f"Refusing to run tests against non-test PostgreSQL database: {database_name!r}"
        )
    admin_url = url.set(database="postgres")
    admin_engine = create_engine(
        admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True
    )
    try:
        with admin_engine.connect() as conn:
            try:
                conn.execute(text(f"CREATE DATABASE {database_name}"))
            except ProgrammingError as exc:
                if "already exists" not in str(exc).lower():
                    raise
    finally:
        admin_engine.dispose()


_ensure_postgres_database(TEST_DATABASE_URL)

from server.database import Base, get_db, engine as APP_ENGINE
from server.main import app
from server.config import PROJECT_ROOT
from server.services.agents.loader import ensure_agents_loaded
from server.services.runtime.copilot_sdk_state import task_output_dir

TEST_ENGINE = create_engine(
    TEST_DATABASE_URL,
    pool_pre_ping=True,
)

TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)
_SCHEMA_RESET_LOCK = threading.Lock()


@pytest.fixture(autouse=True)
def clean_inherited_git_env(monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("GIT_"):
            monkeypatch.delenv(key, raising=False)


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
                "repo_path": str(
                    getattr(requirement, "target_project_path", "") or "test-repo"
                ),
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


def _fake_review_pr_sync(
    db, requirement, workflow_run, step, delivery_contract=None, vcs_payload=None
):
    branch_name = str(
        (vcs_payload or {}).get("branch_name")
        or f"ops/req-{getattr(requirement, 'id', 'x')}-test"
    )
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


class _FakePopen:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.returncode = None


def _fake_capture_task_file_change_baseline(db, task, requirement=None, step=None):
    raw_output_path = str(getattr(task, "output_path", "") or "").strip()
    if raw_output_path:
        output_path = Path(raw_output_path).expanduser()
        output_dir = output_path.parent
    else:
        output_dir = task_output_dir(
            PROJECT_ROOT, str(getattr(task, "agent_id", "test")), int(task.id)
        )
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
        output_dir = task_output_dir(
            PROJECT_ROOT, str(getattr(task, "agent_id", "test")), int(task.id)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "file-changes.json").write_text(
        json.dumps(
            {
                "changed_files": [],
                "target_project_path": str(
                    getattr(requirement, "target_project_path", "") or ""
                )
                or None,
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


def _fake_generate_plan_brief_markdown_with_agent(
    db, requirement, *, acceptance_contract
):
    return (
        "\n\n".join(
            [
                str(getattr(requirement, "title", "") or "").strip(),
                str(getattr(requirement, "description_markdown", "") or "").strip(),
                "Target project:",
                str(
                    getattr(requirement, "target_project_path", "") or "test-repo"
                ).strip(),
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
    _ensure_test_tables()
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _reset_postgres_schema() -> None:
    _ensure_test_tables()
    table_names = ", ".join(_quoted_table_name(table) for table in Base.metadata.tables.values())
    if not table_names:
        return
    with TEST_ENGINE.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


def _quoted_table_name(table) -> str:
    schema = str(table.schema or "public").replace('"', '""')
    name = str(table.name).replace('"', '""')
    return f'"{schema}"."{name}"'


def _rebuild_postgres_schema() -> None:
    with _SCHEMA_RESET_LOCK:
        _reset_postgres_schema()


def _drop_postgres_schema() -> None:
    TEST_ENGINE.dispose()
    APP_ENGINE.dispose()


def _ensure_test_tables() -> None:
    Base.metadata.create_all(bind=TEST_ENGINE)


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    app.dependency_overrides[get_db] = _override_get_db
    _rebuild_postgres_schema()
    with (
        patch(
            "server.services.requirements.service._generate_plan_brief_markdown_with_agent",
            _fake_generate_plan_brief_markdown_with_agent,
        ),
        patch("server.main.config.COPILOT_SDK_MONITOR_ENABLED", False),
        patch("server.main.config.OPENAI_RESPONSES_MONITOR_ENABLED", False),
        patch("server.main.config.CODEX_CLI_MONITOR_ENABLED", False),
        patch("server.main.config.BUG_LOG_SWEEP_SCHEDULER_ENABLED", False),
        patch("server.main.config.CI_STATUS_SWEEP_SCHEDULER_ENABLED", False),
        patch(
            "server.services.workflows.declarative._launch_final_regression_runner",
            lambda runner_command, env: _FakePopen(runner_command, env=env),
        ),
        patch("server.config.LARK_DELIVERY_DRY_RUN", True),
        patch("server.services.social.publishing.SessionLocal", TestSession),
    ):
        yield
    _drop_postgres_schema()
    app.dependency_overrides.clear()


@pytest.fixture
def db_session():
    _ensure_test_tables()
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
    _ensure_test_tables()
    db = TestSession()
    ensure_agents_loaded(db)
    db.commit()
    db.close()
    return client
