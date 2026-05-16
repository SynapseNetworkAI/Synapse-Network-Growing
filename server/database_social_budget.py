"""PostgreSQL-compatible schema helpers for Social X read budget bookkeeping."""

from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy import Text
from sqlalchemy import func


_metadata = MetaData()

social_x_read_budget_events = Table(
    "social_x_read_budget_events",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("platform", Text, nullable=False, server_default="x"),
    Column("local_date", Text, nullable=False),
    Column("workflow_key", Text, nullable=False),
    Column("request_count", Integer, nullable=False, server_default="0"),
    Column("source_post_count", Integer, nullable=False, server_default="0"),
    Column("detail", Text),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Index("social_x_read_budget_date_idx", "local_date"),
    Index("social_x_read_budget_workflow_idx", "workflow_key"),
)


def _create_social_x_read_budget_table(bind) -> None:
    social_x_read_budget_events.create(bind=bind, checkfirst=True)
    for index in social_x_read_budget_events.indexes:
        index.create(bind=bind, checkfirst=True)


def ensure_social_x_read_budget_table(session) -> None:
    _create_social_x_read_budget_table(session.get_bind())


def migrate_social_x_read_budget(engine_, tables: set[str]) -> None:
    if "social_x_read_budget_events" in tables:
        return
    with engine_.connect() as conn:
        _create_social_x_read_budget_table(conn)
        conn.commit()
