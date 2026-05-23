from __future__ import annotations

import sqlite3

from scripts.db.migrate_sqlite_to_postgres import migrate
from scripts.db.validate_postgres_migration import validate
from tests.conftest import TEST_DATABASE_URL


def test_sqlite_archive_can_be_imported_once_into_postgres(tmp_path) -> None:
    sqlite_path = tmp_path / "ops-archive.db"
    conn = sqlite3.connect(sqlite_path)
    try:
        conn.execute(
            "CREATE TABLE archived_demo (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO archived_demo (id, name) VALUES (1, 'imported')")
        conn.commit()
    finally:
        conn.close()

    migrate(
        sqlite_path,
        TEST_DATABASE_URL,
        reset_postgres=True,
        backup_dir=tmp_path / "backups",
    )
    checks = validate(sqlite_path, TEST_DATABASE_URL, check_hashes=True)

    assert checks
    assert all(check.ok for check in checks)
    assert any(
        check.table_name == "archived_demo"
        and check.sqlite_count == 1
        and check.postgres_count == 1
        for check in checks
    )
