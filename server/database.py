"""Database connection and table setup for Agentic Ops Dashboard."""
import logging
from sqlalchemy import (
    Column, Integer, Text, Boolean, DateTime, ForeignKey, create_engine, event, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

from server.config import DATABASE_URL

logger = logging.getLogger("ops-dashboard.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _enable_fk(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


# ── ORM Models ────────────────────────────────────────────────

class AgentRow(Base):
    __tablename__ = "agents"

    id = Column(Text, primary_key=True)
    display_name = Column(Text, nullable=False)
    goal = Column(Text, nullable=False)
    group = Column(Text, default="")  # content | growth | optimization
    persona_path = Column(Text)
    skills = Column(Text, default="[]")  # JSON array
    created_at = Column(DateTime, default=utcnow)

    tasks = relationship("TaskRow", back_populates="agent")


class TaskRow(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description = Column(Text, nullable=False)
    agent_id = Column(Text, ForeignKey("agents.id"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    requires_approval = Column(Boolean, default=False)
    priority = Column(Text, default="normal")
    skill_name = Column(Text)
    context_files = Column(Text)  # JSON array of relative paths
    output_path = Column(Text)
    output_content = Column(Text)
    execution_time_ms = Column(Integer)
    created_at = Column(DateTime, default=utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    agent = relationship("AgentRow", back_populates="tasks")
    approvals = relationship("ApprovalRow", back_populates="task")
    logs = relationship("TaskLogRow", back_populates="task", order_by="TaskLogRow.created_at")


class ApprovalRow(Base):
    __tablename__ = "approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    status = Column(Text, nullable=False, default="pending")
    reviewer = Column(Text)
    comment = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    decided_at = Column(DateTime)

    task = relationship("TaskRow", back_populates="approvals")


class TaskLogRow(Base):
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    event_type = Column(Text, nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime, default=utcnow)

    task = relationship("TaskRow", back_populates="logs")


# ── Init ──────────────────────────────────────────────────────

def _migrate(engine_):
    """Add missing columns to existing tables (lightweight migration)."""
    insp = inspect(engine_)
    tables = insp.get_table_names()

    if "agents" in tables:
        existing = {c["name"] for c in insp.get_columns("agents")}
        if "group" not in existing:
            logger.info("Migrating: adding 'group' column to agents table")
            with engine_.connect() as conn:
                conn.execute(text("ALTER TABLE agents ADD COLUMN \"group\" TEXT DEFAULT ''"))
                conn.commit()

    if "tasks" in tables:
        existing = {c["name"] for c in insp.get_columns("tasks")}
        new_cols = {
            "skill_name": "TEXT",
            "context_files": "TEXT",
            "execution_time_ms": "INTEGER",
        }
        for col, col_type in new_cols.items():
            if col not in existing:
                logger.info("Migrating: adding '%s' column to tasks table", col)
                with engine_.connect() as conn:
                    conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}"))
                    conn.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
