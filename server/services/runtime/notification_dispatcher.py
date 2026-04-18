"""Background dispatcher loop for queued notifications."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from server import config
from server.database import NotificationEventRow, NotificationFingerprintRow, SessionLocal
from server.logging_utils import log_event
from server.services.runtime.notification_queue import dispatch_notification_queue

logger = logging.getLogger("ops-dashboard.notification_dispatcher")


class NotificationDispatcher:
    """Small in-process worker that drains notification_events periodically."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] = SessionLocal,
        interval_seconds: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = max(1, int(interval_seconds or config.NOTIFICATION_DISPATCH_INTERVAL_SECONDS))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_tick_at: datetime | None = None
        self._last_dispatch_count = 0
        self._last_error: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ops-notification-dispatcher",
            daemon=True,
        )
        self._thread.start()
        log_event(logger, "notification_dispatcher_started", interval_seconds=self._interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        log_event(logger, "notification_dispatcher_stopped")

    def status_snapshot(self, db: Session | None = None) -> dict[str, object]:
        own_session = False
        if db is None:
            db = self._session_factory()
            own_session = True
        try:
            queued_count = db.query(NotificationEventRow).filter(NotificationEventRow.status == "queued").count()
            dead_letter_count = db.query(NotificationEventRow).filter(NotificationEventRow.status == "dead_letter").count()
            open_fingerprint_count = db.query(NotificationFingerprintRow).filter(NotificationFingerprintRow.status == "open").count()
            suppressed_fingerprint_count = (
                db.query(NotificationFingerprintRow)
                .filter(NotificationFingerprintRow.suppressed_count > 0)
                .count()
            )
        finally:
            if own_session:
                db.close()
        return {
            "enabled": bool(config.NOTIFICATION_DISPATCHER_ENABLED),
            "running": bool(self._thread is not None and self._thread.is_alive() and not self._stop_event.is_set()),
            "interval_seconds": int(self._interval_seconds),
            "last_tick_at": self._last_tick_at.isoformat() if self._last_tick_at else None,
            "last_dispatch_count": int(self._last_dispatch_count),
            "last_error": self._last_error,
            "queued_count": int(queued_count),
            "dead_letter_count": int(dead_letter_count),
            "open_fingerprint_count": int(open_fingerprint_count),
            "suppressed_fingerprint_count": int(suppressed_fingerprint_count),
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            db: Session | None = None
            try:
                self._last_tick_at = datetime.now(timezone.utc)
                db = self._session_factory()
                processed = dispatch_notification_queue(db, limit=50)
                db.commit()
                self._last_dispatch_count = len(processed)
                self._last_error = None
            except Exception as exc:  # noqa: BLE001 - worker must keep running
                self._last_error = str(exc)
                log_event(
                    logger,
                    "notification_dispatcher_failed",
                    level=logging.ERROR,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                )
                if db is not None:
                    db.rollback()
            finally:
                if db is not None:
                    db.close()
            self._stop_event.wait(self._interval_seconds)
