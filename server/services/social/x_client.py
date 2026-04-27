"""Small X API v2 read client for Social Ops.

The client is intentionally narrow: it reads public watchlist timelines and
search results, but never performs write actions such as like/repost/reply.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


X_API_BASE_URL = "https://api.x.com/2"


def _bounded_excerpt(value: object, *, max_chars: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len("... [Truncated]")] + "... [Truncated]"


class XApiError(RuntimeError):
    """Base safe error for X API read operations."""


class XApiAuthError(XApiError):
    """X API returned 401/403 for a read request."""


class XApiRateLimitError(XApiError):
    """X API returned 429 for a read request."""


class XApiTransientError(XApiError):
    """X API read request failed with a retryable or unknown error."""


@dataclass(frozen=True)
class XUser:
    id: str
    username: str
    name: str | None = None
    verified: bool | None = None
    public_metrics: dict[str, Any] | None = None


@dataclass(frozen=True)
class XPost:
    id: str
    text: str
    author_id: str | None = None
    created_at: str | None = None
    conversation_id: str | None = None
    public_metrics: dict[str, Any] | None = None


class XApiClient:
    """Read-only X API v2 client backed by a short-lived OAuth access token."""

    def __init__(self, access_token: str, *, base_url: str = X_API_BASE_URL, timeout_seconds: int = 20):
        token = str(access_token or "").strip()
        if not token:
            raise XApiAuthError("X access token is empty.")
        self.access_token = token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))

    def get_user_by_username(self, username: str) -> XUser:
        handle = str(username or "").strip().lstrip("@")
        if not handle:
            raise XApiTransientError("X username is empty.")
        data = self._get_json(
            f"/users/by/username/{urllib.parse.quote(handle)}",
            {
                "user.fields": "username,name,verified,public_metrics",
            },
        )
        payload = data.get("data") if isinstance(data, dict) else None
        if not isinstance(payload, dict) or not payload.get("id"):
            raise XApiTransientError("X user lookup response did not include a user id.")
        return XUser(
            id=str(payload.get("id")),
            username=str(payload.get("username") or handle),
            name=str(payload.get("name") or "") or None,
            verified=bool(payload.get("verified")) if "verified" in payload else None,
            public_metrics=payload.get("public_metrics") if isinstance(payload.get("public_metrics"), dict) else None,
        )

    def get_user_tweets(self, user_id: str, *, max_results: int = 5, pagination_token: str | None = None) -> list[XPost]:
        uid = str(user_id or "").strip()
        if not uid:
            raise XApiTransientError("X user id is empty.")
        params: dict[str, str] = {
            "max_results": str(min(100, max(5, int(max_results)))),
            "tweet.fields": "created_at,public_metrics,author_id,conversation_id,entities",
            "expansions": "author_id",
            "user.fields": "username,name,verified,public_metrics",
            "exclude": "retweets,replies",
        }
        if pagination_token:
            params["pagination_token"] = str(pagination_token)
        data = self._get_json(f"/users/{urllib.parse.quote(uid)}/tweets", params)
        rows = data.get("data") if isinstance(data, dict) else None
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise XApiTransientError("X user timeline response data was not a list.")
        return [self._post_from_payload(row) for row in rows if isinstance(row, dict) and row.get("id")]

    def recent_search(self, query: str, *, max_results: int = 10) -> list[XPost]:
        q = str(query or "").strip()
        if not q:
            return []
        data = self._get_json(
            "/tweets/search/recent",
            {
                "query": q,
                "max_results": str(min(100, max(10, int(max_results)))),
                "tweet.fields": "created_at,public_metrics,author_id,conversation_id,entities",
                "expansions": "author_id",
                "user.fields": "username,name,verified,public_metrics",
            },
        )
        rows = data.get("data") if isinstance(data, dict) else None
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise XApiTransientError("X recent search response data was not a list.")
        return [self._post_from_payload(row) for row in rows if isinstance(row, dict) and row.get("id")]

    def _post_from_payload(self, row: dict[str, Any]) -> XPost:
        return XPost(
            id=str(row.get("id") or ""),
            text=str(row.get("text") or ""),
            author_id=str(row.get("author_id") or "") or None,
            created_at=str(row.get("created_at") or "") or None,
            conversation_id=str(row.get("conversation_id") or "") or None,
            public_metrics=row.get("public_metrics") if isinstance(row.get("public_metrics"), dict) else None,
        )

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - fixed X API host
                raw = response.read(65536).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read(4096).decode("utf-8", errors="replace")
            if exc.code == 429:
                raise XApiRateLimitError(f"X API rate limited the request: {_bounded_excerpt(raw)}") from exc
            if exc.code in {401, 403}:
                raise XApiAuthError(f"X API authentication failed with HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
            raise XApiTransientError(f"X API returned HTTP {exc.code}: {_bounded_excerpt(raw)}") from exc
        except Exception as exc:  # pragma: no cover - network dependent
            raise XApiTransientError(f"X API request failed: {_bounded_excerpt(str(exc))}") from exc
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise XApiTransientError("X API response was not JSON.") from exc
        if not isinstance(data, dict):
            raise XApiTransientError("X API response JSON was not an object.")
        return data
