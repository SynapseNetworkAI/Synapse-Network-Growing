import json
import urllib.error
from io import BytesIO

from server.services.growth import ai_visibility_remote_mcp_metadata as metadata
from server.services.growth.ai_visibility_remote_mcp_metadata import (
    EXPECTED_NAME,
    EXPECTED_REPOSITORY,
    EXPECTED_SCHEMA,
    EXPECTED_SERVER_URL,
    remote_mcp_public_metadata_check,
)


def test_remote_mcp_public_metadata_check_blocks_stale_glama_json():
    result = remote_mcp_public_metadata_check(
        fetcher=lambda url: (
            200,
            json.dumps(
                {
                    "$schema": EXPECTED_SCHEMA,
                    "maintainers": [{"email": "support@synapse-network.ai"}],
                }
            ),
        )
    )

    assert result.ok is False
    assert result.status == "stale_or_incomplete"
    assert result.missing_fields == [
        "name",
        "serverUrl",
        "repository",
        "tools.discover_services",
        "tools.invoke_and_pay",
        "tools.get_receipt",
    ]
    assert "Remote MCP public metadata gate failed" in result.blocker
    assert "npm run test:e2e:remote:metadata" in result.blocker


def test_remote_mcp_public_metadata_check_accepts_complete_metadata():
    result = remote_mcp_public_metadata_check(
        fetcher=lambda url: (
            200,
            json.dumps(
                {
                    "$schema": EXPECTED_SCHEMA,
                    "name": EXPECTED_NAME,
                    "serverUrl": EXPECTED_SERVER_URL,
                    "repository": EXPECTED_REPOSITORY,
                    "tools": [
                        {"name": "discover_services"},
                        {"name": "invoke_and_pay"},
                        {"name": "get_receipt"},
                    ],
                }
            ),
        )
    )

    assert result.ok is True
    assert result.status == "ready"
    assert result.missing_fields == []
    assert result.observed["tools"] == [
        "discover_services",
        "invoke_and_pay",
        "get_receipt",
    ]


def test_remote_mcp_public_metadata_check_reports_fetch_failure():
    def fail_fetch(url):  # noqa: ARG001
        raise TimeoutError("network timeout")

    result = remote_mcp_public_metadata_check(fetcher=fail_fetch)

    assert result.ok is False
    assert result.status == "fetch_failed"
    assert result.http_status == 0
    assert "network timeout" in result.summary
    assert "fetch failed" in result.blocker


def test_remote_mcp_public_metadata_check_reports_http_and_json_failures():
    http_result = remote_mcp_public_metadata_check(
        fetcher=lambda url: (503, "temporarily unavailable")
    )
    json_result = remote_mcp_public_metadata_check(
        fetcher=lambda url: (200, "not-json")
    )

    assert http_result.status == "http_failed"
    assert http_result.missing_fields == ["metadata_http_2xx"]
    assert "HTTP 503" in http_result.blocker
    assert json_result.status == "invalid_json"
    assert json_result.missing_fields == ["valid_json"]
    assert "invalid JSON" in json_result.blocker


def test_remote_mcp_public_metadata_check_reports_non_object_payload():
    result = remote_mcp_public_metadata_check(
        fetcher=lambda url: (200, json.dumps(["unexpected"]))
    )

    assert result.status == "stale_or_incomplete"
    assert result.observed == {"type": "list"}
    assert "metadata_object" in result.missing_fields


def test_remote_mcp_public_metadata_check_accepts_string_tool_names():
    result = remote_mcp_public_metadata_check(
        fetcher=lambda url: (
            200,
            json.dumps(
                {
                    "name": EXPECTED_NAME,
                    "serverUrl": EXPECTED_SERVER_URL,
                    "repository": EXPECTED_REPOSITORY,
                    "tools": [
                        "discover_services",
                        "invoke_and_pay",
                        "get_receipt",
                    ],
                }
            ),
        )
    )

    assert result.ok is False
    assert result.missing_fields == ["$schema"]
    assert result.observed["tools"] == [
        "discover_services",
        "invoke_and_pay",
        "get_receipt",
    ]


def test_fetch_url_reads_public_metadata(monkeypatch):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

        def read(self, limit):
            assert limit == 100_000
            return b'{"ok": true}'

    monkeypatch.setattr(
        metadata.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )

    status, body = metadata._fetch_url(metadata.REMOTE_MCP_METADATA_URL)

    assert status == 200
    assert body == '{"ok": true}'


def test_fetch_url_returns_http_error_body(monkeypatch):
    def raise_http_error(request, timeout):  # noqa: ARG001
        raise urllib.error.HTTPError(
            url=metadata.REMOTE_MCP_METADATA_URL,
            code=404,
            msg="not found",
            hdrs={},
            fp=BytesIO(b"missing"),
        )

    monkeypatch.setattr(metadata.urllib.request, "urlopen", raise_http_error)

    status, body = metadata._fetch_url(metadata.REMOTE_MCP_METADATA_URL)

    assert status == 404
    assert body == "missing"
