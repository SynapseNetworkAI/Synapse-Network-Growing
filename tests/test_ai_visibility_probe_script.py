import io
import json
import subprocess
import sys
import urllib.error
from pathlib import Path

import pytest

from scripts.growth import record_ai_visibility_probe as probe
from scripts.growth.record_ai_visibility_probe import (
    PostedVisibilityCheck,
    ProbeRecord,
    main,
    parse_json_or_jsonl,
    parse_probe_file,
    post_records,
    record_from_payload,
    validate_records,
)


def test_parse_json_array_and_validate_external_probe(tmp_path: Path):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            [
                {
                    "query": "AI agent payment API",
                    "platform": "chatgpt",
                    "answer_summary": "Synapse is cited.",
                    "synapse_mentioned": True,
                    "synapse_cited": True,
                    "cited_urls": ["https://www.synapse-network.ai/ai-agent-payments"],
                    "feed_key": "agent_payment_category_pages",
                    "run_group": "2026-06-18-after-docs-launch",
                    "evidence_url": "docs/archive/evidence/growth/chatgpt.png",
                }
            ]
        ),
        encoding="utf-8",
    )

    records = parse_probe_file(probe_path)

    assert records[0].platform == "chatgpt"
    assert validate_records(records) == []


def test_parse_jsonl_rows():
    rows = parse_json_or_jsonl(
        "\n".join(
            [
                json.dumps({"query": "AI agent payment API"}),
                json.dumps({"query": "Synapse Network vs x402"}),
            ]
        )
    )

    assert [row["query"] for row in rows] == [
        "AI agent payment API",
        "Synapse Network vs x402",
    ]


def test_parse_rejects_empty_malformed_and_non_object_rows():
    with pytest.raises(ValueError, match="probe file is empty"):
        parse_json_or_jsonl("")
    with pytest.raises(json.JSONDecodeError):
        parse_json_or_jsonl("{not json")
    with pytest.raises(ValueError, match="JSON array must contain objects only"):
        parse_json_or_jsonl(json.dumps([{"query": "ok"}, "bad"]))
    with pytest.raises(ValueError, match="JSONL line 1 must be an object"):
        parse_json_or_jsonl(json.dumps("bad"))
    with pytest.raises(ValueError, match="JSONL line 2 is invalid JSON"):
        parse_json_or_jsonl('{"query": "one"}\n{bad')


def test_record_from_payload_rejects_bad_metadata_and_field_shapes():
    with pytest.raises(ValueError, match="record 0: metadata must be an object"):
        record_from_payload(
            {
                "query": "AI payment",
                "platform": "chatgpt",
                "feed_key": "agent_payment_category_pages",
                "run_group": "baseline",
                "metadata": ["bad"],
            },
            index=0,
        )
    with pytest.raises(ValueError, match="query must be a string"):
        record_from_payload(
            {
                "query": 123,
                "platform": "chatgpt",
                "feed_key": "agent_payment_category_pages",
                "run_group": "baseline",
            },
            index=0,
        )
    with pytest.raises(ValueError, match="cited_urls must be a list of strings"):
        record_from_payload(
            {
                "query": "AI payment",
                "platform": "chatgpt",
                "feed_key": "agent_payment_category_pages",
                "run_group": "baseline",
                "cited_urls": [1],
            },
            index=0,
        )


def test_validation_rejects_validation_platforms_and_missing_citation_evidence(
    tmp_path: Path,
):
    probe_path = tmp_path / "probe.jsonl"
    probe_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "query": "How can AI agents pay for APIs locally?",
                        "platform": "www_local_validation",
                        "feed_key": "agent_payment_category_pages",
                        "run_group": "2026-06-04-local",
                    }
                ),
                json.dumps(
                    {
                        "query": "AI agent payment API live crawl",
                        "platform": "www_live_validation",
                        "feed_key": "agent_payment_category_pages",
                        "run_group": "2026-06-04-live-predeploy",
                    }
                ),
                json.dumps(
                    {
                        "query": "Synapse Network vs x402",
                        "platform": "claude",
                        "synapse_mentioned": True,
                        "synapse_cited": True,
                        "feed_key": "agent_payment_category_pages",
                        "run_group": "2026-06-18-after-docs-launch",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    records = parse_probe_file(probe_path)
    errors = validate_records(records)

    assert "record 0: validation platform is not external probe evidence" in errors
    assert "record 1: validation platform is not external probe evidence" in errors
    assert "record 2: synapse_cited=true requires cited_urls or evidence_url" in errors


def test_validation_rejects_duplicate_missing_and_unknown_platform():
    records = [
        ProbeRecord(query="", platform="", feed_key="", run_group="baseline"),
        ProbeRecord(
            query="AI payment",
            platform="unknown",
            feed_key="agent_payment_category_pages",
            run_group="baseline",
        ),
        ProbeRecord(
            query="AI payment",
            platform="unknown",
            feed_key="agent_payment_category_pages",
            run_group="baseline",
        ),
        ProbeRecord(
            query="AI payment live",
            platform="www_live_validation",
            feed_key="agent_payment_category_pages",
            run_group="baseline",
        ),
    ]

    errors = validate_records(records, allow_local_validation=True)

    assert "record 0: query is required" in errors
    assert "record 0: feed_key is required" in errors
    assert "record 0: platform is required" in errors
    assert "record 1: platform must be one of" in "\n".join(errors)
    assert "record 2: duplicate feed/run/platform/query" in errors
    assert not any("record 3:" in error for error in errors)


def test_cli_dry_run_outputs_summary(tmp_path: Path):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "query": "MCP server for paid API calls",
                "platform": "grok",
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-18-after-registry",
                "answer_summary": "No Synapse citation yet.",
                "synapse_mentioned": False,
                "synapse_cited": False,
                "next_action": "Feed registry listing evidence.",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/record_ai_visibility_probe.py",
            str(probe_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["dry_run"] is True
    assert payload["platforms"] == ["grok"]
    assert payload["feed_keys"] == ["mcp_paid_api_discovery"]


def test_main_apply_posts_records_and_reports_created_ids(
    tmp_path: Path, monkeypatch, capsys
):
    probe_path = tmp_path / "probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "query": "AI agent payment API",
                "platform": "chatgpt",
                "feed_key": "agent_payment_category_pages",
                "run_group": "after-docs",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "record_ai_visibility_probe.py",
            str(probe_path),
            "--apply",
            "--api-base",
            "https://ops.example/api",
        ],
    )
    monkeypatch.setattr(
        probe,
        "post_records",
        lambda api_base, records: [PostedVisibilityCheck(id=42)],
    )

    assert main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["created_ids"] == [42]
    assert payload["dry_run"] is False


def test_main_reports_validation_and_parse_errors(tmp_path: Path, monkeypatch, capsys):
    bad_probe = tmp_path / "bad.json"
    bad_probe.write_text(
        json.dumps(
            {
                "query": "AI agent payment API",
                "platform": "www_live_validation",
                "feed_key": "agent_payment_category_pages",
                "run_group": "baseline",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["record_ai_visibility_probe.py", str(bad_probe)])

    assert main() == 2
    validation_payload = json.loads(capsys.readouterr().err)
    assert validation_payload["errors"] == [
        "record 0: validation platform is not external probe evidence"
    ]

    missing_probe = tmp_path / "missing.json"
    monkeypatch.setattr(
        sys, "argv", ["record_ai_visibility_probe.py", str(missing_probe)]
    )
    assert main() == 1
    error_payload = json.loads(capsys.readouterr().err)
    assert error_payload["error_type"] == "FileNotFoundError"


def test_post_records_validates_url_posts_payload_and_maps_http_errors(monkeypatch):
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"id": 77, "ignored": true}'

    def fake_urlopen(request, timeout):
        assert timeout == 20
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)
    records = [
        ProbeRecord(
            query="AI payment",
            platform="chatgpt",
            feed_key="agent_payment_category_pages",
            run_group="baseline",
        )
    ]

    created = post_records("https://ops.example/api", records)

    assert created == [PostedVisibilityCheck(id=77)]
    assert captured_payloads[0]["query"] == "AI payment"
    with pytest.raises(ValueError, match="http or https"):
        post_records("file:///tmp/probe", records)
    with pytest.raises(ValueError, match="include a host"):
        post_records("https://", records)

    def failing_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            400,
            "Bad Request",
            hdrs=None,
            fp=io.BytesIO(b"bad probe"),
        )

    monkeypatch.setattr(probe.urllib.request, "urlopen", failing_urlopen)
    with pytest.raises(RuntimeError, match="bad probe"):
        post_records("https://ops.example/api", records)
