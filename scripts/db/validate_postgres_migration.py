#!/usr/bin/env python3
"""Validate that a SQLite Ops DB was copied into Postgres."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


@dataclass(frozen=True)
class TableCheck:
    table_name: str
    sqlite_count: int
    postgres_count: int
    ok: bool


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
        ).fetchall()
    ]


def _row_count_sqlite(conn: sqlite3.Connection, table_name: str) -> int:
    return int(conn.execute(f"select count(*) from {_quote(table_name)}").fetchone()[0])  # nosec B608


def _row_count_postgres(engine, table_name: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(f"select count(*) from {_quote(table_name)}")  # nosec B608
            ).scalar_one()
        )


def _sample_hash_sqlite(conn: sqlite3.Connection, table_name: str) -> str:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"select * from {_quote(table_name)} order by 1 limit 5"  # nosec B608
    ).fetchall()
    return hashlib.sha256(
        json.dumps([dict(row) for row in rows], sort_keys=True, default=str).encode()
    ).hexdigest()


def _sample_hash_postgres(engine, table_name: str) -> str:
    with engine.connect() as conn:
        rows = (
            conn.execute(text(f"select * from {_quote(table_name)} order by 1 limit 5"))  # nosec B608
            .mappings()
            .all()
        )
    return hashlib.sha256(
        json.dumps([dict(row) for row in rows], sort_keys=True, default=str).encode()
    ).hexdigest()


def validate(
    sqlite_path: Path, postgres_url: str, *, check_hashes: bool
) -> list[TableCheck]:
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    engine = create_engine(postgres_url, pool_pre_ping=True)
    pg_tables = set(inspect(engine).get_table_names())
    checks: list[TableCheck] = []
    missing = []
    for table_name in _sqlite_tables(sqlite_conn):
        if table_name not in pg_tables:
            missing.append(table_name)
            checks.append(
                TableCheck(
                    table_name, _row_count_sqlite(sqlite_conn, table_name), -1, False
                )
            )
            continue
        sqlite_count = _row_count_sqlite(sqlite_conn, table_name)
        postgres_count = _row_count_postgres(engine, table_name)
        ok = sqlite_count == postgres_count
        if ok and check_hashes and sqlite_count:
            ok = _sample_hash_sqlite(sqlite_conn, table_name) == _sample_hash_postgres(
                engine, table_name
            )
        checks.append(TableCheck(table_name, sqlite_count, postgres_count, ok))
    if missing:
        print(f"[postgres-validation] missing tables: {', '.join(missing)}")
    return checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", required=True)
    parser.add_argument("--postgres-url", required=True)
    parser.add_argument("--check-hashes", action="store_true")
    args = parser.parse_args()
    checks = validate(
        Path(args.sqlite).expanduser().resolve(),
        args.postgres_url,
        check_hashes=args.check_hashes,
    )
    failed = [check for check in checks if not check.ok]
    for check in checks:
        status = "ok" if check.ok else "FAILED"
        print(
            f"[postgres-validation] {status} {check.table_name}: sqlite={check.sqlite_count} postgres={check.postgres_count}"
        )
    if failed:
        raise SystemExit(
            f"Postgres migration validation failed for {len(failed)} table(s)"
        )
    print(f"[postgres-validation] ok: {len(checks)} tables")


if __name__ == "__main__":
    main()
