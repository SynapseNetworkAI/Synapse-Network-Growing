from __future__ import annotations

from sqlalchemy.exc import OperationalError

from server.database_retry import run_with_sqlite_lock_retry


class FakeSession:
    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1


def _operational_error(message: str) -> OperationalError:
    return OperationalError("select 1", {}, RuntimeError(message))


def test_sqlite_lock_rolls_back_then_retries_successfully():
    db = FakeSession()
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _operational_error("database is locked")
        return "ok"

    result = run_with_sqlite_lock_retry(
        db,  # type: ignore[arg-type]
        operation,
        max_attempts=2,
        sleep_seconds=0,
    )

    assert result == "ok"
    assert calls == 2
    assert db.rollbacks == 1


def test_non_lock_operational_error_is_not_swallowed():
    db = FakeSession()

    def operation() -> str:
        raise _operational_error("no such table: requirements")

    try:
        run_with_sqlite_lock_retry(
            db,  # type: ignore[arg-type]
            operation,
            max_attempts=2,
            sleep_seconds=0,
        )
    except OperationalError as exc:
        assert "no such table" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("expected OperationalError")
    assert db.rollbacks == 0
