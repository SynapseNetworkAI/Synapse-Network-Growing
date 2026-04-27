import json
import io
import urllib.error

import pytest

from server.services.social.x_client import XApiAuthError, XApiClient, XApiRateLimitError, XApiTransientError


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size: int = -1):
        return json.dumps(self.payload).encode("utf-8")


def test_x_client_reads_user_and_timeline(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        if "/users/by/username/OpenAI" in request.full_url:
            return FakeResponse({"data": {"id": "u1", "username": "OpenAI", "name": "OpenAI", "verified": True}})
        if "/users/u1/tweets" in request.full_url:
            return FakeResponse(
                {
                    "data": [
                        {
                            "id": "t1",
                            "text": "AI agents need reliable tools.",
                            "author_id": "u1",
                            "created_at": "2026-04-27T00:00:00Z",
                            "public_metrics": {"like_count": 10},
                        }
                    ]
                }
            )
        raise AssertionError(request.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    client = XApiClient("token")
    user = client.get_user_by_username("@OpenAI")
    posts = client.get_user_tweets(user.id, max_results=1)

    assert user.id == "u1"
    assert user.username == "OpenAI"
    assert posts[0].id == "t1"
    assert posts[0].public_metrics == {"like_count": 10}
    assert len(calls) == 2


def test_x_client_recent_search_handles_empty_results(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse({"meta": {"result_count": 0}}))

    assert XApiClient("token").recent_search("AI agents") == []
    assert XApiClient("token").recent_search("") == []


def test_x_client_validates_response_shapes(monkeypatch):
    client = XApiClient("token")

    with pytest.raises(XApiTransientError):
        client.get_user_by_username("")
    with pytest.raises(XApiTransientError):
        client.get_user_tweets("")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse({"data": {}}))
    with pytest.raises(XApiTransientError):
        client.get_user_by_username("OpenAI")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse({"data": {"not": "a-list"}}))
    with pytest.raises(XApiTransientError):
        client.get_user_tweets("u1")
    with pytest.raises(XApiTransientError):
        client.recent_search("AI agents")


def test_x_client_user_tweets_includes_pagination_token(monkeypatch):
    urls = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        return FakeResponse({"data": []})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    posts = XApiClient("token").get_user_tweets("u1", pagination_token="next-token")

    assert posts == []
    assert "pagination_token=next-token" in urls[0]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, XApiAuthError),
        (403, XApiAuthError),
        (429, XApiRateLimitError),
        (500, XApiTransientError),
    ],
)
def test_x_client_maps_http_errors(monkeypatch, status, expected):
    def fake_urlopen(_request, timeout):
        raise urllib.error.HTTPError("https://api.x.com/2/test", status, "failed", hdrs=None, fp=io.BytesIO(b'{"error":"failed"}'))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(expected):
        XApiClient("token").get_user_by_username("OpenAI")


def test_x_client_rejects_empty_token_and_bad_json(monkeypatch):
    with pytest.raises(XApiAuthError):
        XApiClient("")

    class BadResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int = -1):
            return b"not-json"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: BadResponse())

    with pytest.raises(XApiTransientError):
        XApiClient("token").get_user_by_username("OpenAI")
