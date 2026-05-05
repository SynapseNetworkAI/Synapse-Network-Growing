#!/usr/bin/env python3
"""Run idempotent SQL migrations against the configured Ops database."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from sqlalchemy import create_engine, text


def _checksum(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ensure_table(conn) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "id TEXT PRIMARY KEY, "
            "checksum TEXT, "
            "applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now())"
        )
    )


def _migration_id(path: Path) -> str:
    return path.name


def run_migrations(database_url: str, migrations_dir: Path) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    files = sorted(migrations_dir.glob("*.sql"))
    with engine.begin() as conn:
        _ensure_table(conn)
        applied = {
            row[0]: row[1]
            for row in conn.execute(
                text("SELECT id, checksum FROM schema_migrations")
            ).fetchall()
        }
        for path in files:
            migration_id = _migration_id(path)
            sql = path.read_text(encoding="utf-8")
            checksum = _checksum(sql)
            if migration_id in applied:
                if applied[migration_id] != checksum:
                    raise SystemExit(
                        f"Migration checksum changed after apply: {migration_id}"
                    )
                print(f"[sql-migrations] skip {migration_id}")
                continue
            print(f"[sql-migrations] apply {migration_id}")
            conn.execute(text(sql))
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (id, checksum) VALUES (:id, :checksum)"
                ),
                {"id": migration_id, "checksum": checksum},
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--migrations-dir", default="server/migrations")
    args = parser.parse_args()
    run_migrations(args.database_url, Path(args.migrations_dir).expanduser().resolve())


if __name__ == "__main__":
    main()
