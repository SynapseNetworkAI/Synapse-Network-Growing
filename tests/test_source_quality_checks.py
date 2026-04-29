from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from server.services.result_objects import (
    ServiceListResult,
    ServiceObjectResult,
    as_service_list,
    as_service_object,
    dump_service_result,
    service_list_result,
    service_object_result,
)


ROOT = Path(__file__).resolve().parents[1]
CI_DIR = ROOT / "scripts" / "ci"
sys.path.insert(0, str(CI_DIR))

SPEC = importlib.util.spec_from_file_location(
    "source_quality_checks", CI_DIR / "source_quality_checks.py"
)
assert SPEC is not None
source_quality_checks = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = source_quality_checks
SPEC.loader.exec_module(source_quality_checks)


def _codes(failures: list[object]) -> set[str]:
    return {getattr(failure, "code") for failure in failures}


def _messages(failures: list[object]) -> str:
    return "\n".join(getattr(failure, "message") for failure in failures)


def test_public_python_dict_return_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/planning/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any\n\ndef create_result() -> dict[str, Any]:\n    return {}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert "RAW_DICT_RETURN" in _codes(failures)
    assert "create_result" in _messages(failures)


def test_public_python_typing_dict_return_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/social/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any, Dict\n\n"
        "def create_result() -> Dict[str, Any]:\n"
        "    return {}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert "RAW_DICT_RETURN" in _codes(failures)


def test_public_python_mapping_return_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/releases/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any, Mapping\n\n"
        "def create_result() -> Mapping[str, Any]:\n"
        "    return {}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert "RAW_DICT_RETURN" in _codes(failures)


def test_public_python_list_of_dict_return_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/planning/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any\n\n"
        "def create_result() -> list[dict[str, Any]]:\n"
        "    return []\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert "RAW_DICT_RETURN" in _codes(failures)


def test_private_python_dict_return_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/planning/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any\n\ndef _build() -> dict[str, Any]:\n    return {}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert failures == []


def test_python_builder_payload_return_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/planning/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any\n\n"
        "def build_payload() -> dict[str, Any]:\n"
        "    return {}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert failures == []


def test_python_dict_parameters_and_model_fields_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/planning/example.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "from typing import Any\n"
        "from pydantic import BaseModel\n\n"
        "class Payload(BaseModel):\n"
        "    metadata: dict[str, object] = {}\n\n"
        "def build(payload: dict[str, Any]) -> Payload:\n"
        "    return Payload(metadata=payload)\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_python_path(path)

    assert failures == []


def test_ts_record_promise_return_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("dashboard/src/api.ts")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "export async function load(): Promise<Record<string, unknown>> {\n"
        "  return {};\n"
        "}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_ts_path(path)

    assert "RAW_RECORD_PROMISE_RETURN" in _codes(failures)
    assert "load" in _messages(failures)


def test_ts_direct_record_return_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("dashboard/src/api.ts")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "export function load(): Record<string, unknown> {\n  return {};\n}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_ts_path(path)

    assert "RAW_RECORD_PROMISE_RETURN" in _codes(failures)
    assert "load" in _messages(failures)


def test_ts_record_fields_and_parameters_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("dashboard/src/api.ts")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "type Props = { payload: Record<string, unknown> };\n"
        "export function save(payload: Record<string, unknown>): Promise<Response> {\n"
        "  return fetch('/api', { method: 'POST', body: JSON.stringify(payload) });\n"
        "}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_ts_path(path)

    assert failures == []


def test_changed_paths_include_core_and_changed_files(monkeypatch, tmp_path):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    (tmp_path / "server/services/planning").mkdir(parents=True, exist_ok=True)
    (tmp_path / "server/services/planning/core.py").write_text(
        "def ok() -> int:\n    return 1\n"
    )
    (tmp_path / "dashboard/src").mkdir(parents=True, exist_ok=True)
    (tmp_path / "dashboard/src/api.ts").write_text("export const ok = 1;\n")

    def fake_run_git(args: list[str]) -> str:
        if args[:2] == ["diff", "--name-only"]:
            return "dashboard/src/api.ts\n"
        if args[:2] == ["ls-files", "--others"]:
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(source_quality_checks, "run_git", fake_run_git)

    paths = source_quality_checks.paths_to_check("HEAD")

    assert Path("server/services/planning/core.py") in paths
    assert Path("dashboard/src/api.ts") in paths


def test_core_paths_include_core_file_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    (tmp_path / "server/routers").mkdir(parents=True, exist_ok=True)
    (tmp_path / "server/routers/planning.py").write_text(
        "def ok() -> int:\n    return 1\n", encoding="utf-8"
    )

    paths = source_quality_checks.paths_to_check(None)

    assert Path("server/routers/planning.py") in paths


def test_annotation_none_and_non_source_paths_are_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("README.md")
    (tmp_path / path).write_text("not source", encoding="utf-8")

    assert source_quality_checks._annotation_contains_raw_map(None) is False
    assert source_quality_checks.evaluate_path(path) == []


def test_python_syntax_error_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("server/services/planning/broken.py")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("def broken(:\n", encoding="utf-8")

    failures = source_quality_checks.evaluate_python_path(path)

    assert _codes(failures) == {"PYTHON_PARSE_ERROR"}
    assert failures[0].baseline_key.startswith("PYTHON_PARSE_ERROR:")


def test_ts_builder_record_promise_return_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    path = Path("dashboard/src/api.ts")
    abs_path = tmp_path / path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(
        "export async function build_payload(): Promise<Record<string, unknown>> {\n"
        "  return {};\n"
        "}\n",
        encoding="utf-8",
    )

    failures = source_quality_checks.evaluate_ts_path(path)

    assert failures == []


def test_evaluate_path_dispatches_python_and_ts(tmp_path, monkeypatch):
    monkeypatch.setattr(source_quality_checks, "ROOT", tmp_path)
    py_path = Path("server/services/planning/example.py")
    ts_path = Path("dashboard/src/api.ts")
    for path, text in (
        (py_path, "def build() -> int:\n    return 1\n"),
        (ts_path, "export function load(): number {\n  return 1;\n}\n"),
    ):
        abs_path = tmp_path / path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(text, encoding="utf-8")

    assert source_quality_checks.evaluate_path(py_path) == []
    assert source_quality_checks.evaluate_path(ts_path) == []


def test_load_baseline_handles_missing_and_existing_file(monkeypatch, tmp_path):
    baseline_path = tmp_path / "baseline.json"
    monkeypatch.setattr(source_quality_checks, "BASELINE_PATH", baseline_path)

    assert source_quality_checks._load_baseline() == set()

    baseline_path.write_text('{"allow": ["RAW_DICT_RETURN:a.py:1:build"]}')

    assert source_quality_checks._load_baseline() == {"RAW_DICT_RETURN:a.py:1:build"}


def test_main_reports_success_and_failure(monkeypatch, capsys):
    failure = source_quality_checks.SourceQualityFailure(
        code="RAW_DICT_RETURN",
        path="server/example.py",
        line=1,
        name="load",
        message="load returns a raw map.",
    )
    monkeypatch.setattr(
        source_quality_checks, "paths_to_check", lambda base: [Path("x.py")]
    )
    monkeypatch.setattr(source_quality_checks, "_load_baseline", lambda: set())
    monkeypatch.setattr(source_quality_checks, "evaluate_path", lambda path: [])

    assert source_quality_checks.main(["--base", "HEAD"]) == 0
    assert "[quality:source] ok" in capsys.readouterr().out

    monkeypatch.setattr(source_quality_checks, "evaluate_path", lambda path: [failure])

    assert source_quality_checks.main([]) == 1
    assert "RAW_DICT_RETURN" in capsys.readouterr().err


def test_service_result_wrappers_preserve_mapping_and_list_behavior():
    obj = ServiceObjectResult({"alpha": 1, "beta": {"nested": True}})
    items = list(obj.items())
    values = list(obj.values())

    assert obj["alpha"] == 1
    assert "alpha" in obj
    assert list(obj) == ["alpha", "beta"]
    assert len(obj) == 2
    assert obj.get("missing", "fallback") == "fallback"
    assert items[0] == ("alpha", 1)
    assert values[0] == 1
    assert list(obj.keys()) == ["alpha", "beta"]
    assert dump_service_result(obj) == {"alpha": 1, "beta": {"nested": True}}

    rows = ServiceListResult([obj, {"gamma": 3}])
    assert len(rows) == 2
    assert rows[0] is obj
    assert dump_service_result(rows) == [
        {"alpha": 1, "beta": {"nested": True}},
        {"gamma": 3},
    ]


def test_service_result_helpers_and_decorators_return_typed_objects():
    existing_obj = ServiceObjectResult({"ok": True})
    existing_list = ServiceListResult([1])

    assert as_service_object(existing_obj) is existing_obj
    assert as_service_object({"ok": True})["ok"] is True
    assert as_service_list(existing_list) is existing_list
    assert as_service_list([1])[0] == 1

    @service_object_result
    def build_object():
        return {"value": 1}

    @service_list_result
    def build_list():
        return [{"value": 1}]

    assert isinstance(build_object(), ServiceObjectResult)
    assert isinstance(build_list(), ServiceListResult)
