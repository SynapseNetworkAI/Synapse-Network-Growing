from __future__ import annotations

import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from scripts.db.migrate_sqlite_to_postgres import migrate
from scripts.db.validate_postgres_migration import validate


POSTGRES_URL = os.environ.get("OPS_TEST_POSTGRES_URL", "").strip()


pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="OPS_TEST_POSTGRES_URL is not configured for Postgres integration tests",
)


def test_sqlite_to_postgres_migration_copies_rows(tmp_path):
    sqlite_path = tmp_path / "ops.db"
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "CREATE TABLE example_rows (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO example_rows (id, name) VALUES (1, 'alpha')")
        conn.commit()

    migrate(
        sqlite_path,
        POSTGRES_URL,
        reset_postgres=True,
        backup_dir=tmp_path / "backups",
    )
    checks = validate(sqlite_path, POSTGRES_URL, check_hashes=True)

    assert [check for check in checks if check.table_name == "example_rows"][0].ok
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT name FROM example_rows WHERE id = 1")).one()
    assert row[0] == "alpha"
