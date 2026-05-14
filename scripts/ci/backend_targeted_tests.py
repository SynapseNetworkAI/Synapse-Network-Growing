#!/usr/bin/env python3
"""Map backend changed files to the smallest useful pytest set."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field


SCHEDULING_TESTS = ("tests/test_weekly_repo_hygiene_review.py",)

TARGETED_TEST_MAPPINGS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        (
            "server/services/scheduling/",
            "scripts/ci/weekly_repo_hygiene_scan.py",
        ),
        SCHEDULING_TESTS,
    ),
)


@dataclass(frozen=True)
class TargetedTestPlan:
    changed_files: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    unmapped_files: list[str] = field(default_factory=list)
    reason: str = "mapped"

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True)


def _dedupe_sorted(items: list[str]) -> list[str]:
    return sorted({item for item in items if item})


def _tests_for_path(path: str) -> list[str]:
    if path.startswith("tests/") and path.endswith(".py"):
        return [path]
    for prefixes, tests in TARGETED_TEST_MAPPINGS:
        if any(path.startswith(prefix) for prefix in prefixes):
            return list(tests)
    return []


def plan_targeted_tests(paths: list[str]) -> TargetedTestPlan:
    tests: list[str] = []
    unmapped: list[str] = []
    for path in paths:
        mapped = _tests_for_path(path)
        if mapped:
            tests.extend(mapped)
        elif path.endswith(".py"):
            unmapped.append(path)

    selected_tests = _dedupe_sorted(tests)
    unmapped_files = _dedupe_sorted(unmapped)
    reason = "mapped" if selected_tests else "no_mapped_tests"
    if unmapped_files:
        reason = f"{reason}_with_unmapped_files"
    return TargetedTestPlan(
        changed_files=_dedupe_sorted(paths),
        tests=selected_tests,
        unmapped_files=unmapped_files,
        reason=reason,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--json", dest="json_path", default=None)
    parser.add_argument("--print-tests", action="store_true")
    args = parser.parse_args(argv)

    plan = plan_targeted_tests(args.paths)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            fh.write(plan.to_json() + "\n")
    if args.print_tests:
        for test in plan.tests:
            print(test)
    elif not args.json_path:
        print(plan.to_json())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
