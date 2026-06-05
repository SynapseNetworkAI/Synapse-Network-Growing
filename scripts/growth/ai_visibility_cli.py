"""CLI helpers for AI visibility scripts."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def pydantic_payload(value) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value.dict()


def write_json_payload(payload: dict[str, Any], output: str | None) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    write_text_or_stdout(rendered, output=output)


def write_text_or_stdout(rendered: str, *, output: str | None) -> None:
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered.rstrip() + "\n", encoding="utf-8")
        return
    print(rendered)


def emit_failure(exc: Exception) -> None:
    print(
        json.dumps(
            {
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            }
        ),
        file=sys.stderr,
    )
