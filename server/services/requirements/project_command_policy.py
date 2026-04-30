from __future__ import annotations

SAFE_EVIDENCE_PROJECT_ROOTS = {
    "/Users/cliff/workspace/agent/Synapse-Network-Growing",
    "/Users/cliff/workspace/agent/Synapse-Network",
    "/Users/cliff/workspace/agent/Synapse-Network-Sdk",
    "/Users/cliff/workspace/agent/Synapse-Network-Provider",
    "/Users/cliff/workspace/agent/Agents-Memory",
}
SAFE_ENV_ASSIGNMENT_NAMES = {
    "PYTHONPATH",
    "COVERAGE_FILE",
    "COVERAGE_DIR",
    "NODE_ENV",
    "CI",
}
SHELL_CONTROL_TOKENS = {"&&", "||", ";", "|", "\n"}


class ProjectCommandValidationError(ValueError):
    pass


def escape_unescaped_backticks(command: str) -> str:
    escaped: list[str] = []
    previous = ""
    for char in str(command or ""):
        if char == "`" and previous != "\\":
            escaped.append("\\`")
        else:
            escaped.append(char)
        previous = char
    return "".join(escaped)


def _strip_safe_env_assignment_tokens(tokens: list[str]) -> list[str]:
    stripped = list(tokens)
    while stripped:
        token = stripped[0]
        if "=" not in token or token.startswith("="):
            break
        name, _value = token.split("=", 1)
        if name not in SAFE_ENV_ASSIGNMENT_NAMES:
            break
        stripped.pop(0)
    return stripped


def _is_registered_project_path(path: str) -> bool:
    normalized = str(path or "").rstrip("/")
    return normalized.startswith("/") and any(
        normalized == root.rstrip("/") or normalized.startswith(root.rstrip("/") + "/")
        for root in SAFE_EVIDENCE_PROJECT_ROOTS
    )


def _ensure_relative_evidence_paths(tokens: list[str], *, label: str) -> None:
    for token in tokens:
        if token.startswith("-"):
            continue
        if token.startswith("/"):
            raise ProjectCommandValidationError(
                f"{label} evidence paths must stay within the project; absolute paths are not allowed."
            )
        if ".." in [part for part in token.split("/") if part]:
            raise ProjectCommandValidationError(
                f"{label} evidence paths must stay within the project; parent traversal is not allowed."
            )


def _project_command_tail(
    tokens: list[str], *, min_length: int = 6
) -> list[str] | None:
    if len(tokens) < min_length or tokens[0] != "cd" or tokens[2] != "&&":
        return None
    if not _is_registered_project_path(tokens[1]):
        return None
    return tokens[3:]


def _ensure_no_tail_chaining(tokens: list[str], *, label: str) -> None:
    if any(token in SHELL_CONTROL_TOKENS for token in tokens):
        raise ProjectCommandValidationError(
            f"cd {label} evidence commands may not chain after the {label} command."
        )


def _validate_project_root(tokens: list[str]) -> None:
    if not _is_registered_project_path(tokens[1]):
        raise ProjectCommandValidationError(
            f"required command uses project root '{tokens[1]}' which is not a registered evidence project root."
        )


def _validate_project_cd_rg_command(tokens: list[str]) -> bool:
    if len(tokens) < 5 or tokens[0] != "cd" or tokens[2:4] != ["&&", "rg"]:
        return False
    _validate_project_root(tokens)
    _ensure_no_tail_chaining(tokens[3:], label="rg")
    _ensure_relative_evidence_paths(tokens[4:], label="rg")
    return True


def _is_python_executable(command_tokens: list[str]) -> bool:
    executable = command_tokens[0].rsplit("/", 1)[-1] if command_tokens else ""
    return executable in {"python", "python3"} or bool(
        command_tokens and command_tokens[0].endswith("/bin/python")
    )


def _validate_py_compile_targets(command_tokens: list[str]) -> None:
    compile_targets = command_tokens[3:]
    if not compile_targets:
        raise ProjectCommandValidationError(
            "py_compile evidence commands must name explicit Python files."
        )
    _ensure_relative_evidence_paths(compile_targets, label="py_compile")
    if not all(token.endswith(".py") for token in compile_targets):
        raise ProjectCommandValidationError(
            "py_compile evidence commands may only target explicit .py files."
        )


def _validate_project_cd_python_command(tokens: list[str]) -> bool:
    tail = _project_command_tail(tokens)
    if tail is None:
        return False
    _ensure_no_tail_chaining(tail, label="python")
    command_tokens = _strip_safe_env_assignment_tokens(tail)
    if not _is_python_executable(command_tokens) or len(command_tokens) < 3:
        return False
    if command_tokens[1:3] == ["-m", "pytest"]:
        _ensure_relative_evidence_paths(
            [token for token in command_tokens[3:] if not token.startswith("-")],
            label="pytest",
        )
        return True
    if command_tokens[1:3] == ["-m", "py_compile"]:
        _validate_py_compile_targets(command_tokens)
        return True
    return False


def _validate_project_cd_npm_command(tokens: list[str]) -> bool:
    tail = _project_command_tail(tokens)
    if tail is None:
        return False
    _ensure_no_tail_chaining(tail, label="npm")
    if len(tail) < 3 or tail[0:2] != ["npm", "run"]:
        return False
    script = tail[2]
    if script not in {"build", "lint", "test", "test:unit", "test:e2e", "typecheck"}:
        raise ProjectCommandValidationError(
            f"npm script '{script}' is not in the safe evidence allowlist."
        )
    _ensure_relative_evidence_paths(
        [arg for arg in tail[3:] if arg != "--" and not arg.startswith("-")],
        label="npm",
    )
    return True


def validate_project_cd_command(tokens: list[str]) -> tuple[bool, bool, bool]:
    return (
        _validate_project_cd_rg_command(tokens),
        _validate_project_cd_python_command(tokens),
        _validate_project_cd_npm_command(tokens),
    )
