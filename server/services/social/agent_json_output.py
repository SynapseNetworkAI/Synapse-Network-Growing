"""Robust JSON parsing for agent structured-output calls."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field


class AgentJsonOutput(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    cleaned_text: str
    excerpt: str


class AgentJsonParseError(ValueError):
    code = "agent_json_parse_failed"

    def __init__(self, message: str, *, excerpt: str) -> None:
        super().__init__(f"{self.code}: {message}")
        self.excerpt = excerpt


def parse_agent_json_output(raw_text: str) -> AgentJsonOutput:
    cleaned = _strip_json_wrapping(raw_text)
    try:
        loaded = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        json_object = _extract_first_json_object(cleaned)
        if not json_object:
            raise AgentJsonParseError(
                "Agent returned invalid or missing JSON object.",
                excerpt=bounded_excerpt(cleaned),
            ) from exc
        try:
            loaded = json.loads(json_object)
        except json.JSONDecodeError as nested_exc:
            raise AgentJsonParseError(
                "Agent returned a partial or malformed JSON object.",
                excerpt=bounded_excerpt(json_object),
            ) from nested_exc
        cleaned = json_object
    if not isinstance(loaded, dict):
        raise AgentJsonParseError(
            "Agent JSON must be an object.",
            excerpt=bounded_excerpt(cleaned),
        )
    return AgentJsonOutput(
        data=loaded,
        cleaned_text=cleaned,
        excerpt=bounded_excerpt(cleaned),
    )


def bounded_excerpt(value: str, *, max_chars: int = 900) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}... [Truncated]"


def _strip_json_wrapping(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    fenced = re.fullmatch(r"```(?:json|JSON)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    if text.lower().startswith("json"):
        candidate = text[4:].lstrip()
        if candidate.startswith("{"):
            text = candidate
    return text


def _extract_first_json_object(raw_text: str) -> str | None:
    text = str(raw_text or "")
    decoder = json.JSONDecoder()
    for match in re.finditer(r"{", text):
        start = match.start()
        try:
            loaded, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return text[start : start + end]
    return None
