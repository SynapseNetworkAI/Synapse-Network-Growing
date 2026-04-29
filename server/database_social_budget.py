"""SQLite migrations for Social X read budget bookkeeping."""

from __future__ import annotations

from sqlalchemy import text


def _create_social_x_read_budget_table(conn) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS social_x_read_budget_events "
            "(id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL DEFAULT 'x', "
            "local_date TEXT NOT NULL, workflow_key TEXT NOT NULL, "
            "request_count INTEGER NOT NULL DEFAULT 0, source_post_count INTEGER NOT NULL DEFAULT 0, "
            "detail TEXT, created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS social_x_read_budget_date_idx "
            "ON social_x_read_budget_events(local_date)"
        )
    )
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS social_x_read_budget_workflow_idx "
            "ON social_x_read_budget_events(workflow_key)"
        )
    )


def ensure_social_x_read_budget_table(session) -> None:
    _create_social_x_read_budget_table(session)


def migrate_social_x_read_budget(engine_, tables: set[str]) -> None:
    if "social_x_read_budget_events" in tables:
        return
    with engine_.connect() as conn:
        _create_social_x_read_budget_table(conn)
        conn.commit()
