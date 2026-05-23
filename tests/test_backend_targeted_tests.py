from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_DIR = ROOT / "scripts" / "ci"
sys.path.insert(0, str(CI_DIR))

SPEC = importlib.util.spec_from_file_location(
    "backend_targeted_tests", CI_DIR / "backend_targeted_tests.py"
)
assert SPEC is not None
backend_targeted_tests = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = backend_targeted_tests
SPEC.loader.exec_module(backend_targeted_tests)


def test_scheduling_changes_map_to_weekly_repo_hygiene_tests():
    plan = backend_targeted_tests.plan_targeted_tests(
        ["server/services/scheduling/repo_hygiene.py"]
    )

    assert plan.tests == ["tests/test_weekly_repo_hygiene_review.py"]
    assert plan.unmapped_files == []
    assert plan.reason == "mapped"


def test_weekly_repo_hygiene_ci_script_maps_to_same_tests():
    plan = backend_targeted_tests.plan_targeted_tests(
        ["scripts/ci/weekly_repo_hygiene_scan.py"]
    )

    assert plan.tests == ["tests/test_weekly_repo_hygiene_review.py"]


def test_changed_test_file_runs_itself():
    plan = backend_targeted_tests.plan_targeted_tests(
        ["tests/test_weekly_repo_hygiene_review.py"]
    )

    assert plan.tests == ["tests/test_weekly_repo_hygiene_review.py"]


def test_database_helpers_map_to_database_tests():
    plan = backend_targeted_tests.plan_targeted_tests(["server/database_retry.py"])

    assert plan.tests == [
        "tests/test_database_config.py",
        "tests/test_database_retry.py",
        "tests/test_postgres_migration.py",
    ]
    assert plan.unmapped_files == []


def test_unmapped_backend_file_keeps_static_quality_only_plan():
    plan = backend_targeted_tests.plan_targeted_tests(
        ["server/services/social/example.py"]
    )

    assert plan.tests == []
    assert plan.unmapped_files == ["server/services/social/example.py"]
    assert plan.reason == "no_mapped_tests_with_unmapped_files"


def test_main_can_write_json_and_print_tests(tmp_path, capsys):
    output_path = tmp_path / "plan.json"

    exit_code = backend_targeted_tests.main(
        [
            "--json",
            str(output_path),
            "--print-tests",
            "server/services/scheduling/repo_hygiene.py",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "tests/test_weekly_repo_hygiene_review.py"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["tests"] == ["tests/test_weekly_repo_hygiene_review.py"]
