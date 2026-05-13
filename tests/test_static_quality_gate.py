from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_DIR = ROOT / "scripts" / "ci"
sys.path.insert(0, str(CI_DIR))
import quality_gate_utils

SPEC = importlib.util.spec_from_file_location(
    "static_quality_gate", CI_DIR / "static_quality_gate.py"
)
assert SPEC is not None
static_quality_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = static_quality_gate
SPEC.loader.exec_module(static_quality_gate)


def _write_lines(path: Path, count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"line {index}" for index in range(count)) + "\n")


def _codes(failures: list[object]) -> set[str]:
    return {getattr(failure, "code") for failure in failures}


def test_new_production_file_over_500_lines_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    path = Path("server/new_module.py")
    _write_lines(tmp_path / path, 501)

    failures = static_quality_gate.evaluate_path(path, {})

    assert "FILE_TOO_LONG" in _codes(failures)


def test_legacy_file_may_not_grow_past_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    path = Path("server/legacy_module.py")
    _write_lines(tmp_path / path, 601)

    failures = static_quality_gate.evaluate_path(path, {"server/legacy_module.py": 600})

    assert "LEGACY_FILE_GREW" in _codes(failures)


def test_legacy_file_can_shrink_without_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    path = Path("server/legacy_module.py")
    _write_lines(tmp_path / path, 599)

    failures = static_quality_gate.evaluate_path(path, {"server/legacy_module.py": 600})

    assert failures == []


def test_new_test_file_over_900_lines_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    path = Path("tests/test_large_flow.py")
    _write_lines(tmp_path / path, 901)

    failures = static_quality_gate.evaluate_path(path, {})

    assert "TEST_FILE_TOO_LONG" in _codes(failures)


def test_new_python_function_over_limit_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    path = Path("server/large_function.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "def too_long():\n" + "\n".join("    value = 1" for _ in range(121)) + "\n",
        encoding="utf-8",
    )

    failures = static_quality_gate.evaluate_path(path, {})

    assert "FUNCTION_TOO_LONG" in _codes(failures)


def test_load_baseline_and_filter_check_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    baseline_path = tmp_path / "quality" / "quality_baseline.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        '{"legacy_files": {"server/legacy.py": "700"}}', encoding="utf-8"
    )
    (tmp_path / "server").mkdir(parents=True, exist_ok=True)
    (tmp_path / "server" / "keep.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "server" / "skip.txt").write_text("skip\n", encoding="utf-8")
    (tmp_path / "server" / "__pycache__").mkdir(parents=True, exist_ok=True)
    (tmp_path / "server" / "__pycache__" / "skip.py").write_text(
        "print('skip')\n", encoding="utf-8"
    )

    baseline = static_quality_gate._load_baseline(baseline_path)
    filtered = static_quality_gate._filter_check_paths(
        {"server/keep.py", "server/skip.txt", "server/__pycache__/skip.py"}
    )

    assert baseline == {"server/legacy.py": 700}
    assert filtered == [Path("server/keep.py")]


def test_changed_paths_uses_git_diff_and_untracked(monkeypatch, tmp_path):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    (tmp_path / "server").mkdir(parents=True, exist_ok=True)
    (tmp_path / "server" / "changed.py").write_text("print('changed')\n")
    (tmp_path / "server" / "untracked.py").write_text("print('untracked')\n")

    def fake_run_git(args: list[str]) -> str:
        if args[:2] == ["diff", "--name-only"]:
            return "server/changed.py\n"
        if args[:2] == ["ls-files", "--others"]:
            return "server/untracked.py\n"
        raise AssertionError(args)

    monkeypatch.setattr(static_quality_gate, "run_git", fake_run_git)

    assert static_quality_gate.changed_paths("HEAD") == [
        Path("server/changed.py"),
        Path("server/untracked.py"),
    ]


def test_python_parse_error_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    path = Path("server/bad.py")
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text("def broken(:\n", encoding="utf-8")

    failures = static_quality_gate.evaluate_path(path, {})

    assert "PYTHON_PARSE_ERROR" in _codes(failures)


def test_main_print_changed_and_failure_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(static_quality_gate, "ROOT", tmp_path)
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text('{"legacy_files": {}}', encoding="utf-8")
    monkeypatch.setattr(
        static_quality_gate, "changed_paths", lambda _base: [Path("server/file.py")]
    )

    assert (
        static_quality_gate.main(
            ["--base", "HEAD", "--baseline", str(baseline_path), "--print-changed"]
        )
        == 0
    )
    assert "server/file.py" in capsys.readouterr().out

    failure = static_quality_gate.QualityFailure(
        "FILE_TOO_LONG", "server/file.py", "too long"
    )
    monkeypatch.setattr(static_quality_gate, "evaluate_path", lambda _path, _base: [])
    assert (
        static_quality_gate.main(["--base", "HEAD", "--baseline", str(baseline_path)])
        == 0
    )
    monkeypatch.setattr(
        static_quality_gate, "evaluate_path", lambda _path, _base: [failure]
    )
    assert (
        static_quality_gate.main(["--base", "HEAD", "--baseline", str(baseline_path)])
        == 1
    )
    assert "FILE_TOO_LONG" in capsys.readouterr().err


def test_run_git_helpers(monkeypatch):
    class Completed:
        def __init__(self, returncode: int, stdout: str, stderr: str = ""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        calls.append(args)
        return Completed(0, "alpha\n\n beta \n")

    monkeypatch.setattr(quality_gate_utils.subprocess, "run", fake_run)

    assert quality_gate_utils.run_git(["status"]) == "alpha\n\n beta \n"
    assert quality_gate_utils.run_git_lines(["status"]) == ["alpha", "beta"]
    assert calls[0][:2] == ["git", "status"]

    def failing_run(_args, **_kwargs):
        return Completed(1, "", "git failed")

    monkeypatch.setattr(quality_gate_utils.subprocess, "run", failing_run)

    try:
        quality_gate_utils.run_git(["bad"])
    except RuntimeError as exc:
        assert "git failed" in str(exc)
    else:
        raise AssertionError("run_git should fail on non-zero exit")
