from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from server.database_social_budget import ensure_social_x_read_budget_table


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run_config_import(database_url: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if database_url is None:
        env["OPS_DATABASE_URL"] = ""
    else:
        env["OPS_DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import server.config as c; print(c.DATABASE_URL)",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_ops_database_url_is_required() -> None:
    result = _run_config_import(None)

    assert result.returncode != 0
    assert "OPS_DATABASE_URL is required" in result.stderr


def test_sqlite_database_url_is_rejected() -> None:
    result = _run_config_import("sqlite:///server/ops.db")

    assert result.returncode != 0
    assert "must be a PostgreSQL URL" in result.stderr


def test_postgres_database_url_is_accepted() -> None:
    url = "postgresql+psycopg://user:pass@127.0.0.1:5432/synapse_growing_test"
    result = _run_config_import(url)

    assert result.returncode == 0, result.stderr
    assert url in result.stdout


def test_social_x_read_budget_schema_is_postgres_compatible(db_session) -> None:
    ensure_social_x_read_budget_table(db_session)
    db_session.execute(
        text(
            "INSERT INTO social_x_read_budget_events "
            "(local_date, workflow_key, request_count, source_post_count, detail) "
            "VALUES (:local_date, :workflow_key, :request_count, :source_post_count, :detail)"
        ),
        {
            "local_date": "2026-05-16",
            "workflow_key": "trend_radar",
            "request_count": 1,
            "source_post_count": 2,
            "detail": "postgres-compatible ddl smoke",
        },
    )
    db_session.commit()

    count = db_session.execute(
        text("SELECT COUNT(*) FROM social_x_read_budget_events")
    ).scalar_one()
    assert count == 1
