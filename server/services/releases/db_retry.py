"""Small DB write retry helpers for release synchronization."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


T = TypeVar("T")


def _is_sqlite_locked_error(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


def commit_with_sqlite_lock_retry(
    db: Session,
    apply_changes: Callable[[], T],
    *,
    attempts: int = 5,
) -> T:
    """Apply and commit writes, retrying transient SQLite writer contention."""

    last_error: OperationalError | None = None
    for attempt in range(max(1, attempts)):
        try:
            result = apply_changes()
            db.commit()
            return result
        except OperationalError as exc:
            if not _is_sqlite_locked_error(exc) or attempt >= attempts - 1:
                raise
            last_error = exc
            db.rollback()
            time.sleep(0.15 * (attempt + 1))
    if last_error is not None:  # pragma: no cover - loop always raises above.
        raise last_error
    return apply_changes()  # pragma: no cover - attempts is normalized to at least one.
