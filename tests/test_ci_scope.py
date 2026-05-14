from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CI_DIR = ROOT / "scripts" / "ci"
sys.path.insert(0, str(CI_DIR))

SPEC = importlib.util.spec_from_file_location("ci_scope", CI_DIR / "ci_scope.py")
assert SPEC is not None
ci_scope = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = ci_scope
SPEC.loader.exec_module(ci_scope)


def test_docs_only_scope():
    result = ci_scope.classify_paths(["docs/design-docs/example.md"])

    assert result.docs_only is True
    assert result.run_docs is True
    assert result.run_backend is False
    assert result.run_dashboard is False
    assert result.run_full is False


def test_dashboard_scope():
    result = ci_scope.classify_paths(["dashboard/src/pages/App.tsx"])

    assert result.scope == "dashboard"
    assert result.run_dashboard is True
    assert result.run_backend is False
    assert result.run_full is False


def test_backend_scope():
    result = ci_scope.classify_paths(["server/services/social/example.py"])

    assert result.scope == "backend"
    assert result.run_backend is True
    assert result.backend_mode == "targeted"
    assert result.run_backend_targeted is True
    assert result.run_backend_full is False
    assert result.run_dashboard is False
    assert result.run_full is False


def test_scheduling_backend_scope_uses_targeted_mode():
    result = ci_scope.classify_paths(["server/services/scheduling/repo_hygiene.py"])

    assert result.scope == "backend"
    assert result.run_backend is True
    assert result.backend_mode == "targeted"
    assert result.run_backend_targeted is True
    assert result.run_full is False


def test_backend_and_dashboard_scope():
    result = ci_scope.classify_paths(
        ["server/services/social/example.py", "dashboard/src/pages/App.tsx"]
    )

    assert result.scope == "backend_dashboard"
    assert result.run_backend is True
    assert result.backend_mode == "targeted"
    assert result.run_dashboard is True
    assert result.run_full is False


def test_backend_release_workflow_security_finance_changes_require_full_backend():
    for path in [
        "server/services/releases/example.py",
        "server/services/workflows/example.py",
        "server/services/security/example.py",
        "server/services/finance/example.py",
    ]:
        result = ci_scope.classify_paths([path])

        assert result.full_required is True
        assert result.run_full is True
        assert result.run_backend is True
        assert result.backend_mode == "full"
        assert result.run_backend_full is True
        assert result.run_backend_targeted is False


def test_security_scope():
    result = ci_scope.classify_paths([".secrets.baseline"])

    assert result.scope == "security"
    assert result.run_security is True
    assert result.run_full is False


def test_ci_workflow_change_requires_full_gate():
    result = ci_scope.classify_paths([".github/workflows/pr-ci.yml"])

    assert result.full_required is True
    assert result.run_full is True
    assert result.run_backend is True
    assert result.run_dashboard is True
    assert result.backend_mode == "full"


def test_ci_script_change_requires_full_gate():
    result = ci_scope.classify_paths(["scripts/ci/pr_checks.sh"])

    assert result.full_required is True
    assert result.run_full is True
    assert result.backend_mode == "full"


def test_scope_classifier_change_runs_self_test_not_full_dashboard_backend():
    result = ci_scope.classify_paths(
        ["scripts/ci/ci_scope.py", "tests/test_ci_scope.py"]
    )

    assert result.scope == "scope_self_test"
    assert result.full_required is False
    assert result.run_full is False
    assert result.run_scope_self_test is True
    assert result.run_backend is False
    assert result.run_dashboard is False
    assert result.backend_mode == "none"


def test_prompt_content_scope_uses_docs_style_checks():
    result = ci_scope.classify_paths([".agents/skills/social-content/SKILL.md"])

    assert result.scope == "prompt_content"
    assert result.prompt_content is True
    assert result.run_docs is True
    assert result.run_backend is False
    assert result.run_dashboard is False
    assert result.run_full is False


def test_dependency_changes_require_full_gate():
    result = ci_scope.classify_paths(["requirements.txt", "dashboard/yarn.lock"])

    assert result.full_required is True
    assert result.run_full is True
    assert result.backend_mode == "full"


def test_unknown_root_requires_full_gate():
    result = ci_scope.classify_paths(["new-root/file.txt"])

    assert result.full_required is True
    assert result.run_full is True


def test_force_full():
    result = ci_scope.classify_paths([], force_full=True)

    assert result.scope == "full"
    assert result.run_full is True
    assert result.backend_mode == "full"
    assert result.reason == "forced_full"


def test_empty_change_set_defaults_to_docs_only():
    result = ci_scope.classify_paths([])

    assert result.docs_only is True
    assert result.reason == "no_changed_files"
    assert result.run_backend is False
    assert result.run_dashboard is False


def test_scope_result_serializes_sorted_json():
    result = ci_scope.ScopeResult(changed_files=["b.py", "a.py"], backend=True)

    payload = json.loads(result.to_json())

    assert payload["backend"] is True
    assert payload["changed_files"] == ["b.py", "a.py"]
    assert list(json.loads(result.to_json()).keys()) == sorted(payload.keys())


def test_split_lines_deduplicates_trims_and_sorts():
    assert ci_scope._split_lines(" b.py\n\na.py\n b.py \n") == ["a.py", "b.py"]


def test_run_git_uses_fixed_git_command(monkeypatch):
    calls: list[dict[str, object]] = []

    def fake_check_output(argv, **kwargs):
        calls.append({"argv": argv, **kwargs})
        return "server/app.py\n"

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    assert (
        ci_scope.run_git(["diff", "--name-only", "origin/main", "--"])
        == "server/app.py\n"
    )
    assert calls == [
        {
            "argv": ["git", "diff", "--name-only", "origin/main", "--"],
            "cwd": ci_scope.ROOT,
            "text": True,
            "stderr": subprocess.DEVNULL,
        }
    ]


def test_changed_files_combines_diff_and_untracked(monkeypatch):
    def fake_run_git(args):
        if args[:2] == ["diff", "--name-only"]:
            return "docs/a.md\nserver/api.py\n"
        if args[:2] == ["ls-files", "--others"]:
            return "dashboard/src/App.tsx\nserver/api.py\n"
        raise AssertionError(f"unexpected git args: {args}")

    monkeypatch.setattr(ci_scope, "run_git", fake_run_git)

    assert ci_scope.changed_files("origin/main") == [
        "dashboard/src/App.tsx",
        "docs/a.md",
        "server/api.py",
    ]


def test_changed_files_without_base_reads_only_untracked(monkeypatch):
    calls: list[list[str]] = []

    def fake_run_git(args):
        calls.append(args)
        return "docs/new.md\n"

    monkeypatch.setattr(ci_scope, "run_git", fake_run_git)

    assert ci_scope.changed_files(None) == ["docs/new.md"]
    assert calls == [["ls-files", "--others", "--exclude-standard"]]


def test_write_github_outputs(monkeypatch, tmp_path):
    output_path = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_path))
    result = ci_scope.ScopeResult(
        changed_files=["docs/a.md"],
        docs_only=True,
        run_backend=False,
        reason="classified",
    )

    ci_scope._write_github_outputs(result)

    text = output_path.read_text(encoding="utf-8")
    assert 'changed_files=["docs/a.md"]' in text
    assert "docs_only=true" in text
    assert "run_backend=false" in text
    assert "reason=classified" in text


def test_write_github_outputs_noops_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    ci_scope._write_github_outputs(ci_scope.ScopeResult())


def test_main_writes_json_file(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "scope.json"
    monkeypatch.setattr(ci_scope, "changed_files", lambda base: ["docs/a.md"])

    exit_code = ci_scope.main(
        ["--base", "origin/main", "--json", str(output_path), "--github-output"]
    )

    assert exit_code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert stdout_payload["scope"] == "docs_only"
    assert file_payload == stdout_payload


def test_main_force_full_does_not_read_changed_files(monkeypatch, capsys):
    def fail_changed_files(base):
        raise AssertionError("force-full should not inspect git changes")

    monkeypatch.setattr(ci_scope, "changed_files", fail_changed_files)

    exit_code = ci_scope.main(["--force-full"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == "full"
    assert payload["run_full"] is True
