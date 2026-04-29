from __future__ import annotations

import json
import re
import shlex
from typing import Any

from sqlalchemy.orm import Session

from server.database import RequirementRow, WorkflowRunRow


class AcceptanceValidationError(ValueError):
    """Raised when a requirement cannot safely enter execution."""


SAFE_REQUIRED_COMMAND_PREFIXES = (
    "/Users/cliff/workspace/agent/.venv/bin/python -m pytest",
    "/Users/cliff/workspace/agent/.venv/bin/python -m ruff check",
    "python -m pytest",
    "python -m ruff check",
    "pytest",
    "ruff check",
    "cd dashboard && npm test",
    "cd dashboard && npm run build",
    "cd dashboard && npm run lint",
    "cd dashboard && npm run test:e2e",
    "npm --prefix dashboard test",
    "npm --prefix dashboard run build",
    "npm --prefix dashboard run lint",
    "npm --prefix dashboard run test:e2e",
    "npm test",
    "npm run build",
    "npm run lint",
    "npm run test:e2e",
    "rg ",
    "diff-cover ",
    "git diff --check",
    "git diff --stat",
    "scripts/ci/agent_guardrails.sh",
)

SAFE_UVX_TOOLS = {"diff-cover"}
SAFE_ENV_ASSIGNMENT_NAMES = {"PYTHONPATH", "COVERAGE_FILE", "COVERAGE_DIR", "NODE_ENV", "CI"}
SAFE_EVIDENCE_PROJECT_ROOTS = {
    "/Users/cliff/workspace/agent/Synapse-Network-Growing",
    "/Users/cliff/workspace/agent/Synapse-Network",
    "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
    "/Users/cliff/workspace/agent/Synapse-Network-Provider",
    "/Users/cliff/workspace/agent/Agents-Memory",
}
ALLOWED_REQUIRED_EVIDENCE_TYPES = {
    "workflow_command_result",
    "project_change_summary",
    "git_diff_summary",
    "frontend_validation_result",
    "coverage_report",
    "docs_sync_review",
    "workflow_agent_raw_output",
}
ACCEPTANCE_COMMAND_TIMEOUT_HARD_CAP_SECONDS = 900
ACCEPTANCE_COMMAND_TIMEOUTS_SECONDS = {
    "rg": 60,
    "git_diff_check": 60,
    "git_diff_stat": 60,
    "diff-cover": 180,
    "pytest": 600,
    "ruff_check": 180,
    "npm": 600,
    "agent_guardrails": 300,
    "default": 300,
}

SHELL_CONTROL_TOKENS = {"&&", "||", ";", "|", "\n"}
SHELL_REDIRECTION_TOKENS = {">", ">>", "<", "<<", "<>", ">&", "<&"}
UNSAFE_EXECUTABLES: dict[str, str] = {
    "aws": "external cloud command is not allowed",
    "bash": "shell execution is not allowed",
    "chmod": "permission mutation command is not allowed",
    "chown": "ownership mutation command is not allowed",
    "cp": "copy command is not allowed",
    "curl": "external network command is not allowed",
    "deploy": "deploy must be human-gated",
    "docker": "container command is not allowed",
    "gcloud": "external cloud command is not allowed",
    "kubectl": "cluster command is not allowed",
    "mv": "mv mutates files",
    "rm": "rm is destructive",
    "rmdir": "rmdir is destructive",
    "rollback": "rollback must be human-gated",
    "scp": "remote copy command is not allowed",
    "sh": "shell execution is not allowed",
    "ssh": "remote shell command is not allowed",
    "wget": "external network command is not allowed",
}
UNSAFE_ARGUMENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdrop\b", re.IGNORECASE), "drop is a destructive database verb"),
    (re.compile(r"\btruncate\b", re.IGNORECASE), "truncate is a destructive database verb"),
    (re.compile(r"\bdelete\s+from\b", re.IGNORECASE), "delete from is a destructive database verb"),
    (re.compile(r"\bgit\s+(push|reset|checkout)\b", re.IGNORECASE), "git mutation command is not allowed"),
    (re.compile(r"\bnpm\s+publish\b", re.IGNORECASE), "npm publish is not allowed"),
)


def parse_shell_tokens(command: str) -> list[str]:
    """Tokenize a simple evidence command while preserving shell control punctuation."""

    if "$(" in command:
        raise AcceptanceValidationError(
            "Subshells '$()' are forbidden in evidence commands. Use direct allowlisted commands only."
        )
    command_with_explicit_newlines = command.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ; ")
    lexer = shlex.shlex(command_with_explicit_newlines, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise AcceptanceValidationError(f"required command cannot be parsed safely: {exc}.") from exc
    return tokens


def _escape_unescaped_backticks(command: str) -> str:
    """Treat planner-produced Markdown backticks as literal search text.

    The workflow runner executes acceptance commands through a shell. Backticks
    inside double-quoted rg patterns would otherwise be command substitution, so
    any accepted rg command is stored with literal backticks escaped.
    """

    escaped: list[str] = []
    previous = ""
    for char in str(command or ""):
        if char == "`" and previous != "\\":
            escaped.append("\\`")
        else:
            escaped.append(char)
        previous = char
    return "".join(escaped)


def _unsafe_executable_reason(token: str) -> str | None:
    executable = token.rsplit("/", 1)[-1].lower()
    return UNSAFE_EXECUTABLES.get(executable)


def _validate_shell_tokens(tokens: list[str]) -> None:
    if not tokens:
        raise AcceptanceValidationError("required command is empty.")

    expect_executable = True
    previous_control = "start"
    for token in tokens:
        if token in SHELL_REDIRECTION_TOKENS or set(token) <= {"<", ">"}:
            raise AcceptanceValidationError("shell redirection may mutate files.")
        if token in SHELL_CONTROL_TOKENS:
            expect_executable = True
            previous_control = token
            continue
        if expect_executable:
            reason = _unsafe_executable_reason(token)
            if reason:
                raise AcceptanceValidationError(
                    f"required command is unsafe: '{token}' is blocked when used as an executable command after '{previous_control}'. {reason}. "
                    "If you are searching for this text, pass it as a quoted argument to a safe command like 'rg'."
                )
            expect_executable = False

    if expect_executable:
        raise AcceptanceValidationError("required command ends with a shell control operator.")


def _contains_shell_control(tokens: list[str]) -> bool:
    return any(token in SHELL_CONTROL_TOKENS for token in tokens)


def _is_safe_env_assignment(token: str) -> bool:
    name, separator, _value = str(token or "").partition("=")
    return bool(separator) and name in SAFE_ENV_ASSIGNMENT_NAMES and re.match(r"^[A-Z_][A-Z0-9_]*$", name) is not None


def _strip_safe_env_assignment_tokens(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens) and _is_safe_env_assignment(tokens[index]):
        index += 1
    return tokens[index:]


def _validate_bound_uvx_command(tokens: list[str], normalized: str) -> bool:
    if not tokens or tokens[0] != "uvx":
        return False
    if _contains_shell_control(tokens):
        raise AcceptanceValidationError("uvx evidence commands may not be chained with shell control operators.")
    if len(tokens) < 2:
        raise AcceptanceValidationError("uvx evidence commands must name an approved tool.")

    from_package: str | None = None
    tool: str | None = None
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "--from":
            if index + 1 >= len(tokens):
                raise AcceptanceValidationError("uvx --from must name an approved package.")
            from_package = tokens[index + 1]
            index += 2
            continue
        if token.startswith("--from="):
            from_package = token.split("=", 1)[1]
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        tool = token
        break

    if not tool:
        raise AcceptanceValidationError("uvx evidence commands must name an approved tool.")
    if tool not in SAFE_UVX_TOOLS:
        raise AcceptanceValidationError(f"uvx tool '{tool}' is not in the safe command allowlist.")
    if from_package and from_package != tool:
        raise AcceptanceValidationError(
            f"uvx package '{from_package}' is not approved for tool '{tool}'. Use 'uvx {tool}' or 'uvx --from {tool} {tool}'."
        )
    return normalized.startswith("uvx ")


def _is_registered_project_path(path: str) -> bool:
    normalized = str(path or "").rstrip("/")
    if not normalized.startswith("/"):
        return False
    for root in SAFE_EVIDENCE_PROJECT_ROOTS:
        project_root = root.rstrip("/")
        if normalized == project_root or normalized.startswith(project_root + "/"):
            return True
    return False


def _ensure_relative_evidence_paths(tokens: list[str], *, label: str) -> None:
    for token in tokens:
        if token.startswith("-"):
            continue
        if token.startswith("/"):
            raise AcceptanceValidationError(f"{label} evidence paths must stay within the project; absolute paths are not allowed.")
        parts = [part for part in token.split("/") if part]
        if ".." in parts:
            raise AcceptanceValidationError(f"{label} evidence paths must stay within the project; parent traversal is not allowed.")


def _validate_project_cd_rg_command(tokens: list[str]) -> bool:
    """Allow read-only ripgrep checks scoped to a registered project root."""

    if len(tokens) < 5 or tokens[0] != "cd":
        return False
    if tokens[2:4] != ["&&", "rg"]:
        return False
    root = tokens[1].rstrip("/")
    if not _is_registered_project_path(root):
        raise AcceptanceValidationError(
            f"required command uses project root '{tokens[1]}' which is not a registered evidence project root."
        )
    if any(token in SHELL_CONTROL_TOKENS for token in tokens[3:]):
        raise AcceptanceValidationError("cd rg evidence commands may not chain after rg.")
    _ensure_relative_evidence_paths(tokens[4:], label="rg")
    return True


def _validate_project_cd_python_command(tokens: list[str]) -> bool:
    """Allow local Python compile/pytest checks inside registered project roots."""

    if len(tokens) < 6 or tokens[0] != "cd" or tokens[2] != "&&":
        return False
    root = tokens[1].rstrip("/")
    if not _is_registered_project_path(root):
        return False
    if any(token in SHELL_CONTROL_TOKENS for token in tokens[3:]):
        raise AcceptanceValidationError("cd python evidence commands may not chain after the Python command.")
    command_tokens = _strip_safe_env_assignment_tokens(tokens[3:])
    if len(command_tokens) < 3:
        return False
    executable = command_tokens[0].rsplit("/", 1)[-1]
    is_python = executable in {"python", "python3"} or command_tokens[0].endswith("/bin/python")
    if not is_python:
        return False
    if command_tokens[1:3] == ["-m", "pytest"]:
        _validate_pytest_scope(command_tokens, " ".join(tokens))
        _ensure_relative_evidence_paths([token for token in command_tokens[3:] if not token.startswith("-")], label="pytest")
        return True
    if command_tokens[1:3] == ["-m", "py_compile"]:
        compile_targets = command_tokens[3:]
        if not compile_targets:
            raise AcceptanceValidationError("py_compile evidence commands must name explicit Python files.")
        _ensure_relative_evidence_paths(compile_targets, label="py_compile")
        if not all(token.endswith(".py") for token in compile_targets):
            raise AcceptanceValidationError("py_compile evidence commands may only target explicit .py files.")
        return True
    return False


def _validate_project_cd_npm_command(tokens: list[str]) -> bool:
    """Allow local npm validation checks inside registered project roots."""

    if len(tokens) < 6 or tokens[0] != "cd" or tokens[2] != "&&":
        return False
    root = tokens[1].rstrip("/")
    if not _is_registered_project_path(root):
        return False
    if any(token in SHELL_CONTROL_TOKENS for token in tokens[3:]):
        raise AcceptanceValidationError("cd npm evidence commands may not chain after the npm command.")
    command_tokens = tokens[3:]
    if command_tokens[0] != "npm" or command_tokens[1] != "run":
        return False
    script = command_tokens[2] if len(command_tokens) > 2 else ""
    if script not in {"build", "lint", "test", "test:unit", "test:e2e", "typecheck"}:
        raise AcceptanceValidationError(f"npm script '{script}' is not in the safe evidence allowlist.")
    _ensure_relative_evidence_paths([token for token in command_tokens[3:] if token != "--" and not token.startswith("-")], label="npm")
    return True


def _pytest_args(executable_tokens: list[str]) -> list[str] | None:
    if not executable_tokens:
        return None
    first_basename = executable_tokens[0].rsplit("/", 1)[-1]
    if first_basename == "pytest":
        return executable_tokens[1:]
    if first_basename == "python" and executable_tokens[1:3] == ["-m", "pytest"]:
        return executable_tokens[3:]
    return None


def _validate_pytest_scope(executable_tokens: list[str], normalized: str) -> None:
    """Acceptance pytest commands must be targeted; full-suite regression belongs to the CI runner."""

    args = _pytest_args(executable_tokens)
    if args is None:
        return
    non_option_args = [token for token in args if not token.startswith("-")]
    has_targeted_selector = any(
        token.startswith("tests/test_")
        or token.startswith("server/tests/")
        or token.endswith("_test.py")
        or token.endswith(".py")
        or "::" in token
        for token in non_option_args
    )
    if not has_targeted_selector:
        raise AcceptanceValidationError(
            f"required command '{normalized}' is unsafe: acceptance pytest commands must target explicit test files or selectors. "
            "Use the final regression CI runner for full-suite pytest."
        )


def _command_mentions_any(command: str, needles: tuple[str, ...]) -> bool:
    lowered = str(command or "").lower()
    return any(needle in lowered for needle in needles)


def _required_evidence_support_error(evidence_type: str, commands: list[str], expected_outcome: str) -> str | None:
    """Reject Planner evidence asks that cannot be produced by the declared commands.

    This is intentionally small and conservative. It does not try to infer every
    possible artifact path; it only blocks common impossible matrices before they
    reach the workflow runner.
    """

    normalized = str(evidence_type or "").strip()
    if normalized == "workflow_command_result":
        return None
    if normalized == "frontend_validation_result":
        if any(_command_mentions_any(command, ("npm ", "npm --prefix dashboard", "cd dashboard && npm")) for command in commands):
            return None
        return "frontend_validation_result requires an npm/dashboard validation command."
    if normalized == "coverage_report":
        if any(_command_mentions_any(command, ("diff-cover", "coverage.xml", "--cov")) for command in commands):
            return None
        return "coverage_report requires a diff-cover, coverage.xml, or pytest --cov command."
    if normalized == "docs_sync_review":
        if any(_command_mentions_any(command, ("agent_guardrails.sh", "docs", "doc_sync", "docs-sync", "docs drift")) for command in commands):
            return None
        return "docs_sync_review requires a docs sync, docs drift, rg docs, or agent_guardrails command."
    if normalized == "project_change_summary":
        if expected_outcome == "code_delivery" or any(command in {"git diff --check", "git diff --stat"} for command in commands):
            return None
        return "project_change_summary requires code_delivery or git diff --check evidence."
    if normalized == "git_diff_summary":
        if expected_outcome == "code_delivery" or any(command in {"git diff --check", "git diff --stat"} for command in commands):
            return None
        return f"{normalized} requires code_delivery or git diff --check evidence."
    if normalized == "workflow_agent_raw_output":
        return None
    return None


def _timeout_payload(tool: str) -> dict[str, int | str]:
    timeout = int(ACCEPTANCE_COMMAND_TIMEOUTS_SECONDS.get(tool, ACCEPTANCE_COMMAND_TIMEOUTS_SECONDS["default"]))
    return {
        "tool": tool,
        "timeout_seconds": min(timeout, ACCEPTANCE_COMMAND_TIMEOUT_HARD_CAP_SECONDS),
    }


def classify_acceptance_command_timeout(command: str) -> dict[str, int | str]:
    """Classify a safe evidence command by executable tool, not fragile string prefix."""

    tokens = _strip_safe_env_assignment_tokens(parse_shell_tokens(command))
    if not tokens:
        return _timeout_payload("default")
    first = tokens[0]
    first_basename = first.rsplit("/", 1)[-1]

    if first_basename == "rg":
        return _timeout_payload("rg")
    if first_basename == "git" and tokens[1:3] == ["diff", "--check"]:
        return _timeout_payload("git_diff_check")
    if first_basename == "git" and tokens[1:3] == ["diff", "--stat"]:
        return _timeout_payload("git_diff_stat")
    if first_basename == "diff-cover":
        return _timeout_payload("diff-cover")
    if first_basename == "uvx":
        stripped = _strip_safe_env_assignment_tokens(tokens)
        if any(token == "diff-cover" for token in stripped[1:]):
            return _timeout_payload("diff-cover")
        return _timeout_payload("default")
    if first_basename == "pytest":
        return _timeout_payload("pytest")
    if first_basename == "python" and tokens[1:3] == ["-m", "pytest"]:
        return _timeout_payload("pytest")
    if first_basename == "ruff" and len(tokens) > 1 and tokens[1] == "check":
        return _timeout_payload("ruff_check")
    if first_basename == "python" and tokens[1:4] == ["-m", "ruff", "check"]:
        return _timeout_payload("ruff_check")
    if first_basename == "npm":
        return _timeout_payload("npm")
    if first_basename == "cd":
        for index, token in enumerate(tokens):
            if token in SHELL_CONTROL_TOKENS and index + 1 < len(tokens):
                command_tokens = _strip_safe_env_assignment_tokens(tokens[index + 1 :])
                if not command_tokens:
                    continue
                next_basename = command_tokens[0].rsplit("/", 1)[-1]
                if next_basename == "npm":
                    return _timeout_payload("npm")
                if next_basename == "rg":
                    return _timeout_payload("rg")
                if next_basename in {"python", "python3"} or command_tokens[0].endswith("/bin/python"):
                    if command_tokens[1:3] == ["-m", "pytest"]:
                        return _timeout_payload("pytest")
                    return _timeout_payload("default")
    if first.endswith("scripts/ci/agent_guardrails.sh") or first_basename == "agent_guardrails.sh":
        return _timeout_payload("agent_guardrails")
    return _timeout_payload("default")


def validate_required_command_safety(command: str) -> str:
    """Fail closed unless a planner-generated evidence command is explicitly safe."""

    raw_command = str(command or "")
    has_backticks = "`" in raw_command
    command_to_validate = _escape_unescaped_backticks(raw_command) if has_backticks else raw_command
    normalized = " ".join(command_to_validate.strip().split())
    if not normalized:
        raise AcceptanceValidationError("required command is empty.")
    tokens = parse_shell_tokens(command_to_validate)
    _validate_shell_tokens(tokens)
    executable_tokens = _strip_safe_env_assignment_tokens(tokens)
    executable_normalized = " ".join(executable_tokens)
    for pattern, reason in UNSAFE_ARGUMENT_PATTERNS:
        if pattern.search(normalized):
            raise AcceptanceValidationError(f"required command '{normalized}' is unsafe: {reason}.")
    is_bound_uvx = _validate_bound_uvx_command(executable_tokens, executable_normalized)
    is_project_cd_rg = _validate_project_cd_rg_command(executable_tokens)
    is_project_cd_python = _validate_project_cd_python_command(executable_tokens)
    is_project_cd_npm = _validate_project_cd_npm_command(executable_tokens)
    is_plain_rg = bool(executable_tokens and executable_tokens[0] == "rg")
    if has_backticks and not (is_plain_rg or is_project_cd_rg):
        raise AcceptanceValidationError(
            "Subshell backticks are forbidden in evidence commands. Backticks are only allowed as escaped literal rg search text."
        )
    _validate_pytest_scope(executable_tokens, normalized)
    if (
        not is_bound_uvx
        and not is_project_cd_rg
        and not is_project_cd_python
        and not is_project_cd_npm
        and not any(executable_normalized.startswith(prefix) for prefix in SAFE_REQUIRED_COMMAND_PREFIXES)
    ):
        raise AcceptanceValidationError(f"required command '{normalized}' is not in the safe command allowlist.")
    return normalized


DEFAULT_ACCEPTANCE_CONTRACT: dict[str, Any] = {
    "acceptance_owner_role": "tester",
    "review_owner_role": "reviewer",
    "acceptance_mode": "scheduled",
    "acceptance_trigger": "implementation_completed",
    "workflow_step_types": ["review", "test", "closeout"],
    "required_evidence_artifact_types": ["project_change_summary", "validation_plan"],
    "done_criteria": [],
    "verification_checks": [],
    "scope_constraints": [],
    "delivery_expectation": "",
    "risk_notes": [],
    "expected_evidence": [],
    "informational_lineage": [],
    "execution_acceptance_steps": [],
    "acceptance_kind": "business",
    "manual_review_prompt": "",
    "acceptance_override": False,
    "override_by": "",
    "override_reason": "",
    "override_at": "",
    "acceptance_index": {},
    "markdown": "",
}


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def normalize_acceptance_contract(raw: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(DEFAULT_ACCEPTANCE_CONTRACT)
    if isinstance(raw, dict):
        for key in {
            "acceptance_owner_role",
            "review_owner_role",
            "acceptance_mode",
            "acceptance_trigger",
        }:
            value = str(raw.get(key) or "").strip()
            if value:
                payload[key] = value
        acceptance_kind = str(raw.get("acceptance_kind") or "").strip()
        if acceptance_kind in {"business", "system_dogfood"}:
            payload["acceptance_kind"] = acceptance_kind
        expected_outcome = str(raw.get("expected_outcome") or "").strip().lower()
        if expected_outcome in {"code_delivery", "verification_only"}:
            payload["expected_outcome"] = expected_outcome
        for key in {"manual_review_prompt", "override_by", "override_reason", "override_at"}:
            value = str(raw.get(key) or "").strip()
            if value:
                payload[key] = value
        if "acceptance_override" in raw:
            payload["acceptance_override"] = bool(raw.get("acceptance_override"))
        for key in {"workflow_step_types", "required_evidence_artifact_types"}:
            values = [str(item).strip() for item in raw.get(key) or [] if str(item).strip()]
            if values:
                payload[key] = values
        for key in {"done_criteria", "scope_constraints", "risk_notes", "expected_evidence", "informational_lineage"}:
            values = [str(item).strip() for item in raw.get(key) or [] if str(item).strip()]
            if values:
                payload[key] = values
        verification_checks: list[dict[str, Any]] = []
        for item in raw.get("verification_checks") or []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            verification_checks.append(
                {
                    "label": label,
                    "command": str(item.get("command") or "").strip() or None,
                    "kind": str(item.get("kind") or "evidence").strip() or "evidence",
                }
            )
        if verification_checks:
            payload["verification_checks"] = verification_checks
        steps: list[dict[str, Any]] = []
        for item in raw.get("execution_acceptance_steps") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            expected_result = str(item.get("expected_result") or "").strip()
            if not title or not expected_result:
                continue
            step = dict(item)
            step["step_key"] = str(step.get("step_key") or title).strip()
            step["title"] = title
            step["expected_result"] = expected_result
            for list_key in {"required_commands", "required_evidence_types", "required_db_lineage"}:
                step[list_key] = [str(value).strip() for value in step.get(list_key) or [] if str(value).strip()]
            step["manual_review_prompt"] = str(step.get("manual_review_prompt") or "").strip()
            steps.append(step)
        if steps:
            payload["execution_acceptance_steps"] = steps
        delivery_expectation = str(raw.get("delivery_expectation") or "").strip()
        if delivery_expectation:
            payload["delivery_expectation"] = delivery_expectation
        acceptance_index = raw.get("acceptance_index")
        if isinstance(acceptance_index, dict):
            payload["acceptance_index"] = acceptance_index
        markdown = str(raw.get("markdown") or "").strip()
        if markdown:
            payload["markdown"] = markdown
    payload["acceptance_index"] = {
        **dict(payload.get("acceptance_index") or {}),
        "done_criteria_count": len(payload.get("done_criteria") or []),
        "scope_constraints_count": len(payload.get("scope_constraints") or []),
        "expected_evidence_count": len(payload.get("expected_evidence") or []),
        "execution_acceptance_step_count": len(payload.get("execution_acceptance_steps") or []),
    }
    return payload


def validate_acceptance_contract_for_execution(
    contract: dict[str, Any] | None,
    *,
    source: str,
    goal_key: str | None = None,
) -> dict[str, Any]:
    """Fail closed unless execution acceptance is evidence-bound.

    Human Override is a deliberate operator shortcut for manual requirements
    only; it still requires business confirmation after technical completion.
    """

    payload = normalize_acceptance_contract(contract or {})
    normalized_source = str(source or "").strip().lower()
    if bool(payload.get("acceptance_override")):
        prompt = str(payload.get("manual_review_prompt") or "").strip()
        if normalized_source not in {"manual", "operator", "human"}:
            raise AcceptanceValidationError("Human Override is only allowed for manually created requirements.")
        if not prompt:
            raise AcceptanceValidationError("Human Override requires manual_review_prompt.")
        return payload

    steps = payload.get("execution_acceptance_steps") or []
    expected_outcome = str(payload.get("expected_outcome") or "").strip().lower()
    if not isinstance(steps, list) or not steps:
        raise AcceptanceValidationError("execution_acceptance_steps must be non-empty.")
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise AcceptanceValidationError(f"execution_acceptance_steps[{index}] must be an object.")
        title = str(step.get("title") or "").strip()
        expected_result = str(step.get("expected_result") or "").strip()
        has_evidence = any(step.get(key) for key in ("required_commands", "required_evidence_types"))
        if not title or not expected_result:
            raise AcceptanceValidationError(f"execution_acceptance_steps[{index}] requires title and expected_result.")
        if not has_evidence:
            raise AcceptanceValidationError(
                f"execution_acceptance_steps[{index}] requires required_commands or required_evidence_types. required_db_lineage is informational in v1."
            )
        commands = [validate_required_command_safety(str(command)) for command in step.get("required_commands") or []]
        for evidence_type in step.get("required_evidence_types") or []:
            if str(evidence_type) not in ALLOWED_REQUIRED_EVIDENCE_TYPES:
                allowed = ", ".join(sorted(ALLOWED_REQUIRED_EVIDENCE_TYPES))
                raise AcceptanceValidationError(
                    f"execution_acceptance_steps[{index}] has unknown required_evidence_type '{evidence_type}'. Allowed evidence types: {allowed}."
                )
            support_error = _required_evidence_support_error(str(evidence_type), commands, expected_outcome)
            if support_error:
                raise AcceptanceValidationError(f"execution_acceptance_steps[{index}] evidence '{evidence_type}' is unsupported: {support_error}")
    if str(payload.get("acceptance_kind") or "business") == "system_dogfood":
        normalized_goal = str(goal_key or "").strip().lower()
        if normalized_goal != "goalb":
            raise AcceptanceValidationError("system_dogfood acceptance is only allowed for goalb.")
    return payload


def acceptance_contract_for_requirement(requirement: RequirementRow) -> dict[str, Any]:
    return normalize_acceptance_contract(
        _json_loads(getattr(requirement, "acceptance_contract_json", None), {})
    )


def list_acceptance_dispatch_candidates(db: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    """Return declarative workflow runs that may need operator validation attention.

    The legacy fixed-step acceptance dispatcher has been retired; this helper now
    exposes high-level workflow candidates only, without creating or dispatching
    hidden task/step records.
    """

    candidates: list[dict[str, Any]] = []
    requirements = db.query(RequirementRow).filter(
        RequirementRow.active_workflow_run_id.isnot(None)
    ).order_by(RequirementRow.id.asc()).all()
    for requirement in requirements:
        run = db.query(WorkflowRunRow).filter(
            WorkflowRunRow.id == requirement.active_workflow_run_id
        ).first()
        if run is None or str(run.status or "") in {"succeeded", "failed", "cancelled"}:
            continue
        contract = acceptance_contract_for_requirement(requirement)
        candidates.append(
            {
                "requirement_id": int(requirement.id),
                "requirement_title": str(requirement.title or ""),
                "workflow_run_id": int(run.id),
                "current_state": str(run.current_state or ""),
                "workflow_status": str(run.status or ""),
                "acceptance_owner_role": str(contract.get("acceptance_owner_role") or "tester"),
                "acceptance_mode": str(contract.get("acceptance_mode") or "scheduled"),
                "acceptance_trigger": "declarative_workflow_observation",
                "required_evidence_artifact_types": list(contract.get("required_evidence_artifact_types") or []),
            }
        )
        if len(candidates) >= limit:
            break
    return candidates[:limit]
