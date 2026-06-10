import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.growth import generate_ai_visibility_source_host_feed_package as feed_cli


def test_generate_ai_visibility_source_host_feed_package_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    output_path = tmp_path / "source-host-feed.json"

    class FakePackage:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "package_type": "source_host_feed",
                "status": "ready_for_operator_feed",
                "feed_key": "mcp_paid_api_discovery",
                "drafts": [
                    {
                        "host": "mcpservers.org",
                        "draft_type": "directory_submission",
                    }
                ],
            }

    monkeypatch.setattr(
        feed_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        feed_cli,
        "_build_feed_package",
        lambda _db, **_kwargs: FakePackage(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_source_host_feed_package.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--run-group",
            "2026-06-06-source-host-feed",
            "--output",
            str(output_path),
        ],
    )

    assert feed_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["package_type"] == "source_host_feed"
    assert payload["drafts"][0]["host"] == "mcpservers.org"


def test_generate_ai_visibility_source_host_execution_checklist_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    from scripts.growth import (
        generate_ai_visibility_source_host_execution_checklist as checklist_cli,
    )

    output_path = tmp_path / "source-host-execution.json"

    class FakeChecklist:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "checklist_type": "source_host_feed_execution",
                "status": "ready_for_operator_execution",
                "items": [{"host": "mcpservers.org"}],
            }

    monkeypatch.setattr(
        checklist_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        checklist_cli,
        "_build_execution_checklist",
        lambda _db, **_kwargs: FakeChecklist(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_source_host_execution_checklist.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--output",
            str(output_path),
        ],
    )

    assert checklist_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["checklist_type"] == "source_host_feed_execution"
    assert payload["items"][0]["host"] == "mcpservers.org"


def test_offline_source_host_clis_do_not_require_ops_database_url(tmp_path: Path):
    diagnosis_path = tmp_path / "feed-diagnosis.json"
    package_path = tmp_path / "source-host-feed.json"
    checklist_path = tmp_path / "source-host-checklist.json"
    diagnosis_path.write_text(
        json.dumps(
            {
                "feed_key": "mcp_paid_api_discovery",
                "run_group": "2026-06-10-offline",
                "recommended_source_host_executions": [
                    {
                        "surface": "mcpservers",
                        "draft_type": "mcp_directory_listing",
                        "rationale": "MCPServers appeared in answer sources.",
                        "validation_command": "Record MCPServers confirmation.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.pop("OPS_DATABASE_URL", None)

    for script, output_path in (
        (
            "scripts/growth/generate_ai_visibility_source_host_feed_package.py",
            package_path,
        ),
        (
            "scripts/growth/generate_ai_visibility_source_host_execution_checklist.py",
            checklist_path,
        ),
    ):
        result = subprocess.run(
            [
                sys.executable,
                script,
                "--diagnosis-file",
                str(diagnosis_path),
                "--output",
                str(output_path),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    assert json.loads(package_path.read_text())["package_type"] == "source_host_feed"
    assert (
        json.loads(checklist_path.read_text())["checklist_type"]
        == "source_host_feed_execution"
    )


def test_generate_ai_visibility_source_host_live_spot_check_cli_writes_json(
    monkeypatch, tmp_path: Path
):
    from scripts.growth import (
        generate_ai_visibility_source_host_live_spot_check as spot_cli,
    )

    output_path = tmp_path / "source-host-live.json"

    class FakeSpotCheck:
        def model_dump(self, mode: str):  # noqa: ARG002
            return {
                "module_key": "ai_visibility",
                "check_type": "source_host_live_spot_check",
                "status": "ready_to_execute",
                "items": [{"host": "mcp.directory"}],
            }

    monkeypatch.setattr(
        spot_cli,
        "run_with_db",
        lambda callback: callback(object()),
    )
    monkeypatch.setattr(
        spot_cli,
        "_build_spot_check",
        lambda _db, **_kwargs: FakeSpotCheck(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_ai_visibility_source_host_live_spot_check.py",
            "--feed-key",
            "mcp_paid_api_discovery",
            "--execute",
            "--output",
            str(output_path),
        ],
    )

    assert spot_cli.main() == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["check_type"] == "source_host_live_spot_check"
    assert payload["items"][0]["host"] == "mcp.directory"


def test_generate_ai_visibility_source_host_live_spot_check_builds_from_service(
    monkeypatch,
):
    from scripts.growth import (
        generate_ai_visibility_source_host_live_spot_check as spot_cli,
    )
    from server.services.growth import ai_visibility_source_host_live_spot_check as svc

    class FakeSpotCheck:
        feed_key = "mcp_paid_api_discovery"

    monkeypatch.setattr(
        svc,
        "ai_visibility_source_host_live_spot_check",
        lambda db, **kwargs: (db, kwargs, FakeSpotCheck()),
    )

    db = object()
    result = spot_cli._build_spot_check(
        db,
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-source-host-feed",
        execute=True,
    )

    assert result[0] is db
    assert result[1]["execute"] is True
    assert result[1]["run_group"] == "2026-06-06-source-host-feed"
