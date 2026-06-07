"""Database helpers for AI visibility CLI exporters."""

from __future__ import annotations

import os
from typing import Callable, TypeVar

T = TypeVar("T")

DEFAULT_LOCAL_OPS_DATABASE_URL = (
    "postgresql+psycopg://synapse_growing:synapse_growing_dev"
    "@127.0.0.1:54329/synapse_growing_local"
)


def run_with_db(callback: Callable[[object], T]) -> T:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("OPS_DATABASE_URL", DEFAULT_LOCAL_OPS_DATABASE_URL)
    from server.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        return callback(db)
    finally:
        db.close()
