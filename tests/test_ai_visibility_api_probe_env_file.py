import json
import subprocess
import sys
from pathlib import Path


def test_api_probe_cli_loads_env_file_without_printing_secret(tmp_path: Path):
    env_path = tmp_path / ".ai-visibility.env"
    env_path.write_text("OPENAI_API_KEY=file-openai-secret\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/run_ai_visibility_api_probe.py",
            "--platforms",
            "chatgpt",
            "--query",
            "AI agent payment API",
            "--env-file",
            str(env_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        env={},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["env_file_loaded"] is True
    assert "file-openai-secret" not in result.stdout


def test_api_probe_cli_loads_env_file_from_env_var(tmp_path: Path):
    env_path = tmp_path / ".ai-visibility.env"
    env_path.write_text("OPENAI_API_KEY=file-openai-secret\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/growth/run_ai_visibility_api_probe.py",
            "--platforms",
            "chatgpt",
            "--query",
            "AI agent payment API",
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        env={"AI_VISIBILITY_ENV_FILE": str(env_path)},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ready"
    assert payload["env_file_loaded"] is True
    assert "file-openai-secret" not in result.stdout
