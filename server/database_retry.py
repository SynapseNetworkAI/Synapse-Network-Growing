from __future__ import annotations

"""Small retry helper for transient SQLite write locks."""

import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

T = TypeVar("T")


def is_sqlite_lock_error(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def run_with_sqlite_lock_retry(
    db: Session,
    operation: Callable[[], T],
    *,
    max_attempts: int = 2,
    sleep_seconds: float = 0.05,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    for attempt in range(max_attempts):
        try:
            return operation()
        except OperationalError as exc:
            if not is_sqlite_lock_error(exc):
                raise
            db.rollback()
            if attempt == max_attempts - 1:
                raise
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    raise RuntimeError("unreachable SQLite lock retry state")  # pragma: no cover
