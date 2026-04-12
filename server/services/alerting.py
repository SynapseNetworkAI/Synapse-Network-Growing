"""Outgoing alert helpers."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from server import config

logger = logging.getLogger("ops-dashboard.alerting")


def send_lark_text_alert(
    text: str,
    *,
    webhook_url: str | None = None,
    keyword: str | None = None,
    timeout_sec: int = 10,
) -> tuple[bool, str | None]:
    target = (webhook_url or config.LARK_BOT_WEBHOOK_URL or "").strip()
    if not target:
        return False, "Lark webhook not configured"

    prefix = (keyword or config.LARK_BOT_KEYWORD or "告警").strip() or "告警"
    body_text = text.strip()
    if prefix and prefix not in body_text:
        body_text = f"{prefix}\n{body_text}"

    payload = json.dumps(
        {
            "msg_type": "text",
            "content": {"text": body_text},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        target,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
        logger.info("event=lark_alert_sent bytes=%s", len(payload))
        return True, response_text
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.warning("event=lark_alert_failed status=%s detail=%s", exc.code, detail[:500])
        return False, detail or f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("event=lark_alert_failed detail=%s", str(exc))
        return False, str(exc)
