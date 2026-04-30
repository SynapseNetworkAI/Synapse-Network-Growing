import pytest

from server.services.requirements.acceptance import (
    AcceptanceValidationError,
    classify_acceptance_command_timeout,
    validate_acceptance_contract_for_execution,
    validate_required_command_safety,
)
from server.services.requirements.evidence_support_policy import (
    required_evidence_support_error,
)
from server.services.requirements.project_command_policy import (
    ProjectCommandValidationError,
    validate_project_cd_command,
)


def test_project_scoped_sdk_commands_are_allowed_and_sanitized():
    commands = {
        'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "quickstart|receipt|agent demo" README.md python/README.md docs/quality-gates.md': 'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "quickstart|receipt|agent demo" README.md python/README.md docs/quality-gates.md',
        'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "Public Preview default: SDK examples use `staging`|Agent Quickstart" README.md': 'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "Public Preview default: SDK examples use \\`staging\\`|Agent Quickstart" README.md',
        "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/python && .venv/bin/python -m py_compile examples/consumer_wallet_to_invoke.py examples/smoke_test.py": "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/python && .venv/bin/python -m py_compile examples/consumer_wallet_to_invoke.py examples/smoke_test.py",
        "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/python && .venv/bin/python -m pytest synapse_client/test/test_client_unit.py -q": "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/python && .venv/bin/python -m pytest synapse_client/test/test_client_unit.py -q",
        "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/typescript && npm run test:unit -- tests/unit/client.test.ts": "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/typescript && npm run test:unit -- tests/unit/client.test.ts",
    }
    for command, expected in commands.items():
        assert validate_required_command_safety(command) == expected


def test_project_scoped_commands_reject_escape_or_mutation_attempts():
    blocked_commands = [
        ('cd /tmp && rg -n "quickstart" README.md', "project root"),
        (
            'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "quickstart" /etc/passwd',
            "stay within the project",
        ),
        (
            'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "quickstart" README.md && rm -rf .',
            "rm",
        ),
        (
            "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/python && .venv/bin/python -m py_compile /tmp/evil.py",
            "stay within the project",
        ),
        (
            "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/typescript && npm run publish",
            "npm script 'publish'",
        ),
    ]
    for command, expected_message in blocked_commands:
        with pytest.raises(AcceptanceValidationError, match=expected_message):
            validate_required_command_safety(command)


def test_project_command_policy_rejects_low_level_unsafe_tails():
    sdk_root = "/Users/cliff/workspace/agent/Synapse-Network-Sdk"

    with pytest.raises(ProjectCommandValidationError, match="parent traversal"):
        validate_project_cd_command(
            ["cd", sdk_root, "&&", "rg", "-n", "quickstart", "../README.md"]
        )

    with pytest.raises(ProjectCommandValidationError, match="may not chain"):
        validate_project_cd_command(
            ["cd", sdk_root, "&&", "rg", "-n", "quickstart", "README.md", "&&"]
        )

    with pytest.raises(ProjectCommandValidationError, match="explicit Python files"):
        validate_project_cd_command(
            ["cd", f"{sdk_root}/python", "&&", ".venv/bin/python", "-m", "py_compile"]
        )

    with pytest.raises(
        ProjectCommandValidationError, match="only target explicit .py files"
    ):
        validate_project_cd_command(
            [
                "cd",
                f"{sdk_root}/python",
                "&&",
                ".venv/bin/python",
                "-m",
                "py_compile",
                "README.md",
            ]
        )

    assert validate_project_cd_command(
        [
            "cd",
            f"{sdk_root}/python",
            "&&",
            "UNSAFE_ENV=1",
            ".venv/bin/python",
            "-m",
            "pytest",
            "tests/test_client.py",
        ]
    ) == (False, False, False)
    assert validate_project_cd_command(
        ["cd", f"{sdk_root}/python", "&&", ".venv/bin/python", "-m", "compileall", "."]
    ) == (False, False, False)


def test_required_command_and_manual_override_edge_cases():
    with pytest.raises(AcceptanceValidationError, match="required command is empty"):
        validate_required_command_safety("   ")
    with pytest.raises(AcceptanceValidationError, match="destructive"):
        validate_required_command_safety('rg -n "drop table" docs')
    with pytest.raises(AcceptanceValidationError, match="only allowed for manually"):
        validate_acceptance_contract_for_execution(
            {
                "acceptance_override": True,
                "manual_review_prompt": "Reviewed by operator.",
            },
            source="planner_candidate",
        )
    with pytest.raises(AcceptanceValidationError, match="manual_review_prompt"):
        validate_acceptance_contract_for_execution(
            {"acceptance_override": True},
            source="manual",
        )

    assert required_evidence_support_error("custom_business_artifact", [], "") is None


def test_project_scoped_commands_have_correct_timeouts():
    cases = {
        "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/python && .venv/bin/python -m pytest synapse_client/test/test_client_unit.py -q": (
            "pytest",
            600,
        ),
        "cd /Users/cliff/workspace/agent/Synapse-Network-Sdk/typescript && npm run test:unit -- tests/unit/client.test.ts": (
            "npm",
            600,
        ),
        'cd /Users/cliff/workspace/agent/Synapse-Network-Sdk && rg -n "quickstart|receipt" README.md python/README.md': (
            "rg",
            60,
        ),
    }
    for command, (tool, timeout_seconds) in cases.items():
        assert classify_acceptance_command_timeout(command) == {
            "tool": tool,
            "timeout_seconds": timeout_seconds,
        }
