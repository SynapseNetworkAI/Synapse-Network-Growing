"""Shared test fixtures for the Ops Dashboard API tests."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.database import Base, get_db, SessionLocal as _ProdSession
from server.main import app

# In-memory SQLite for tests — StaticPool ensures all connections share one DB
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(TEST_ENGINE, "connect")
def _enable_fk(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after."""
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=TEST_ENGINE)
    # Also patch SessionLocal used by task_runner to use test DB
    with patch("server.services.task_runner.SessionLocal", TestSession), patch(
        "server.services.copilot_sdk_monitor.SessionLocal", TestSession
    ), patch(
        "server.services.workflow_orchestrator.SessionLocal", TestSession
    ), patch("server.main.config.COPILOT_SDK_MONITOR_ENABLED", False), patch(
        "server.main.config.OPENAI_RESPONSES_MONITOR_ENABLED", False
    ):
        yield
    with TEST_ENGINE.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        inspector = inspect(conn)
        for table_name in inspector.get_table_names():
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    app.dependency_overrides.clear()


@pytest.fixture
def db_session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def synced_client(client):
    """Client with agents already synced."""
    client.post("/api/agents/sync")
    return client
