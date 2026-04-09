"""Database connection and table setup for Agentic Ops Dashboard."""
from sqlalchemy import (
    Column, Integer, Text, Boolean, DateTime, ForeignKey, create_engine, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime, timezone

from server.config import DATABASE_URL

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
    output_path = Column(Text)
    output_content = Column(Text)
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

def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
