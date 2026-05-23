"""Shared polling loop for single-process local workers."""

from __future__ import annotations

import time
from collections.abc import Callable


def run_forever(callback: Callable[[], int], *, sleep_seconds: float = 2.0) -> None:
    while True:
        callback()
        time.sleep(sleep_seconds)
