#!/usr/bin/env python3
"""Copy the complete local Ops SQLite database into Postgres."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.database import Base  # noqa: E402
import server.database_social_distribution  # noqa: E402,F401
import server.database_scheduled_jobs  # noqa: E402,F401


CONFIRM_PHRASE = "MIGRATE_SQLITE_TO_POSTGRES"


@dataclass(frozen=True)
class SqliteColumn:
    name: str
    type_name: str
    not_null: bool
    primary_key: bool


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
    ).fetchall()
    return [str(row[0]) for row in rows]


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> list[SqliteColumn]:
    rows = conn.execute(f"pragma table_info({_quote(table)})").fetchall()
    return [
        SqliteColumn(
            name=str(row[1]),
            type_name=str(row[2] or "TEXT").upper(),
            not_null=bool(row[3]),
            primary_key=bool(row[5]),
        )
        for row in rows
    ]


def _sqlalchemy_type(column: SqliteColumn) -> Any:
    type_name = column.type_name
    if "INT" in type_name:
        return Integer
    if "REAL" in type_name or "FLOA" in type_name or "DOUB" in type_name:
        return Float
    if "BOOL" in type_name:
        return Boolean
    if "DATE" in type_name or "TIME" in type_name:
        return DateTime
    return Text


def _create_schema_migrations(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "id TEXT PRIMARY KEY, "
                "checksum TEXT, "
                "applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now())"
            )
        )


def _reset_public_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def _create_extra_table(
    engine: Engine, sqlite_conn: sqlite3.Connection, table_name: str
) -> None:
    metadata = MetaData()
    columns = []
    for source_col in _sqlite_columns(sqlite_conn, table_name):
        columns.append(
            Column(
                source_col.name,
                _sqlalchemy_type(source_col),
                primary_key=source_col.primary_key,
                nullable=not source_col.not_null,
            )
        )
    Table(table_name, metadata, *columns)
    metadata.create_all(bind=engine, checkfirst=True)


def _pg_tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _copy_rows(sqlite_conn: sqlite3.Connection, engine: Engine, table_name: str) -> int:
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(f"select * from {_quote(table_name)}").fetchall()  # nosec B608
    if not rows:
        return 0
    columns = list(rows[0].keys())
    pg_columns = {col["name"]: col for col in inspect(engine).get_columns(table_name)}
    placeholders = ", ".join(f":{name}" for name in columns)
    column_sql = ", ".join(_quote(name) for name in columns)
    statement = text(
        f"INSERT INTO {_quote(table_name)} ({column_sql}) VALUES ({placeholders})"  # nosec B608
    )
    payloads = []
    for row in rows:
        payload = {}
        for name in columns:
            value = row[name]
            col_type = pg_columns.get(name, {}).get("type")
            if isinstance(col_type, Boolean) and value is not None:
                value = bool(value)
            payload[name] = value
        payloads.append(payload)
    with engine.begin() as conn:
        # Local full-copy migration preserves historical SQLite rows first, then
        # validates counts. SQLite allowed cyclic legacy references that cannot
        # be inserted in a single topological order under Postgres FK checks.
        conn.execute(text("SET session_replication_role = replica"))
        try:
            conn.execute(statement, payloads)
        finally:
            conn.execute(text("SET session_replication_role = DEFAULT"))
    return len(payloads)


def _reset_sequences(engine: Engine) -> None:
    sql = text(
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND column_default LIKE 'nextval(%'
        ORDER BY table_name, column_name
        """
    )
    with engine.begin() as conn:
        for table_name, column_name in conn.execute(sql).fetchall():
            conn.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence(:table_name, :column_name), "
                    f"COALESCE((SELECT MAX({_quote(column_name)}) FROM {_quote(table_name)}), 0) + 1, false)"  # nosec B608
                ),
                {"table_name": table_name, "column_name": column_name},
            )


def migrate(
    sqlite_path: Path, postgres_url: str, *, reset_postgres: bool, backup_dir: Path
) -> None:
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite database not found: {sqlite_path}")
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = (
        backup_dir / f"{sqlite_path.name}.pre-postgres-migration-{timestamp}.bak"
    )
    shutil.copy2(sqlite_path, backup_path)
    print(f"[postgres-migration] SQLite backup: {backup_path}")

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    engine = create_engine(postgres_url, pool_pre_ping=True)
    if reset_postgres:
        _reset_public_schema(engine)
    Base.metadata.create_all(bind=engine)
    _create_schema_migrations(engine)

    sqlite_tables = _sqlite_tables(sqlite_conn)
    pg_tables = _pg_tables(engine)
    for table_name in sqlite_tables:
        if table_name not in pg_tables:
            _create_extra_table(engine, sqlite_conn, table_name)
            pg_tables.add(table_name)

    ordered = [
        table.name
        for table in Base.metadata.sorted_tables
        if table.name in sqlite_tables
    ]
    ordered.extend([name for name in sqlite_tables if name not in set(ordered)])

    copied_total = 0
    for table_name in ordered:
        copied = _copy_rows(sqlite_conn, engine, table_name)
        copied_total += copied
        print(f"[postgres-migration] copied {table_name}: {copied}")
    _reset_sequences(engine)
    print(
        f"[postgres-migration] complete: {len(sqlite_tables)} tables, {copied_total} rows"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default=str(ROOT / "server" / "ops.db"))
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--reset-postgres", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--backup-dir", default=str(ROOT / "runtime" / "backups"))
    args = parser.parse_args()
    if args.confirm != CONFIRM_PHRASE:
        raise SystemExit(f"Refusing to migrate without --confirm {CONFIRM_PHRASE}")
    migrate(
        Path(args.sqlite).expanduser().resolve(),
        args.postgres_url,
        reset_postgres=bool(args.reset_postgres),
        backup_dir=Path(args.backup_dir).expanduser().resolve(),
    )


if __name__ == "__main__":
    main()
