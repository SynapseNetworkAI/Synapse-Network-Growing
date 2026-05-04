"""GitHub workflow schema checks for scheduled job releases."""

from __future__ import annotations

from server.services.releases.github_cli import run_gh_text
from server.services.releases.scheduled_job_catalog import (
    SCHEDULED_JOBS_REPO,
    SCHEDULED_JOBS_WORKFLOW_FILE,
)


def ensure_scheduled_job_workflow_accepts_inputs(inputs: dict[str, str]) -> None:
    """Fail closed before dispatching inputs unknown to GitHub workflow_dispatch."""

    status, workflow_yaml, error = run_gh_text(
        [
            "workflow",
            "view",
            SCHEDULED_JOBS_WORKFLOW_FILE,
            "--repo",
            SCHEDULED_JOBS_REPO,
            "--yaml",
        ],
        timeout=30,
    )
    if status != "ok" or not workflow_yaml:
        raise ValueError(
            "Scheduled jobs workflow schema could not be verified before dispatch: "
            f"{error or 'empty workflow yaml'}"
        )
    supported_inputs = workflow_dispatch_input_names(workflow_yaml)
    unexpected = sorted(set(inputs) - supported_inputs)
    if unexpected:
        raise ValueError(
            "Scheduled jobs workflow on SynapseNetworkAI/Synapse-Network main does "
            f"not accept input(s): {', '.join(unexpected)}. Merge the target repo "
            f"{SCHEDULED_JOBS_WORKFLOW_FILE} update before publishing Cloud Run Jobs."
        )


def workflow_dispatch_input_names(workflow_yaml: str) -> set[str]:
    """Parse top-level workflow_dispatch input names from a small GitHub YAML file."""

    names: set[str] = set()
    workflow_indent = -1
    inputs_indent = -1
    section = "root"
    for line in workflow_yaml.splitlines():
        stripped = line.strip()
        if _is_ignorable_yaml_line(stripped):
            continue
        indent = _yaml_indent(line)
        if _starts_workflow_dispatch(stripped):
            section = "workflow_dispatch"
            workflow_indent = indent
            continue
        if _left_workflow_dispatch(section, indent, workflow_indent):
            section = "root"
        if section == "root":
            continue
        if _starts_inputs(stripped):
            section = "inputs"
            inputs_indent = indent
            continue
        if _left_inputs(section, indent, inputs_indent):
            section = "workflow_dispatch"
        if _is_input_name(section, indent, inputs_indent, stripped):
            names.add(stripped[:-1])
    return names


def _is_ignorable_yaml_line(stripped: str) -> bool:
    return not stripped or stripped.startswith("#")


def _yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _starts_workflow_dispatch(stripped: str) -> bool:
    return stripped == "workflow_dispatch:"


def _starts_inputs(stripped: str) -> bool:
    return stripped == "inputs:"


def _left_workflow_dispatch(section: str, indent: int, workflow_indent: int) -> bool:
    return section != "root" and indent <= workflow_indent


def _left_inputs(section: str, indent: int, inputs_indent: int) -> bool:
    return section == "inputs" and indent <= inputs_indent


def _is_input_name(
    section: str, indent: int, inputs_indent: int, stripped: str
) -> bool:
    return (
        section == "inputs" and indent == inputs_indent + 2 and stripped.endswith(":")
    )
