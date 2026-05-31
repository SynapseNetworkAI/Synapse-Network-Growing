"""Tool catalog for the local Bug List MCP server."""

from __future__ import annotations

from typing import Any

READ_TOOLS = {"bugs_list", "bugs_get", "bugs_agent_queue"}
WRITE_TOOLS = {
    "bugs_intake",
    "bugs_claim",
    "bugs_claim_and_run",
    "bugs_materialize_requirement",
    "bugs_link_fix",
    "bugs_add_verification",
    "bugs_close",
    "bugs_reopen",
}


def _input_schema(
    required: list[str], properties: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


def _basic_fields(*names: str) -> dict[str, dict[str, str]]:
    return {name: {"type": "string"} for name in names}


BUG_LIST_TOOL_DEFINITIONS = [
    {
        "name": "bugs_list",
        "description": "List Bug List records with filters and pagination.",
        "inputSchema": _input_schema(
            [],
            {
                **_basic_fields("project_key", "status", "severity", "source_key", "q"),
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
            },
        ),
    },
    {
        "name": "bugs_get",
        "description": "Read one bug detail with agent_context, fix attempts, and events.",
        "inputSchema": _input_schema(["bug_id"], {"bug_id": {"type": "integer"}}),
    },
    {
        "name": "bugs_agent_queue",
        "description": "List bugs that are ready for agent remediation.",
        "inputSchema": _input_schema(
            [],
            {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer"},
            },
        ),
    },
    {
        "name": "bugs_intake",
        "description": "Create or dedupe a product bug report.",
        "inputSchema": _input_schema(
            ["project_key", "title", "summary", "severity"],
            {
                **_basic_fields(
                    "project_key",
                    "title",
                    "summary",
                    "severity",
                    "fingerprint",
                    "source_key",
                    "project_root_path",
                    "source_ref",
                    "environment",
                    "log_excerpt",
                    "stack_trace",
                ),
                "evidence": {"type": "array", "items": {"type": "object"}},
                "metadata": {"type": "object"},
            },
        ),
    },
    {
        "name": "bugs_claim",
        "description": "Claim a bug with a lease so only one agent fixes it at a time.",
        "inputSchema": _input_schema(
            ["bug_id", "agent_id"],
            {
                "bug_id": {"type": "integer"},
                "agent_id": {"type": "string"},
                "lease_minutes": {"type": "integer"},
            },
        ),
    },
    {
        "name": "bugs_claim_and_run",
        "description": "Claim a bug, materialize or reuse its requirement, and start the repair workflow.",
        "inputSchema": _input_schema(
            ["bug_id", "agent_id"],
            {
                "bug_id": {"type": "integer"},
                "agent_id": {"type": "string"},
                "lease_minutes": {"type": "integer"},
            },
        ),
    },
    {
        "name": "bugs_materialize_requirement",
        "description": "Materialize a bug into a bugfix requirement.",
        "inputSchema": _input_schema(["bug_id"], {"bug_id": {"type": "integer"}}),
    },
    {
        "name": "bugs_link_fix",
        "description": "Link branch, commit, PR, workflow, or requirement evidence.",
        "inputSchema": _input_schema(
            ["bug_id", "agent_id"],
            {
                "bug_id": {"type": "integer"},
                "agent_id": {"type": "string"},
                "branch_name": {"type": "string"},
                "commit_sha": {"type": "string"},
                "pr_url": {"type": "string"},
                "workflow_run_id": {"type": "integer"},
                "requirement_id": {"type": "integer"},
            },
        ),
    },
    {
        "name": "bugs_add_verification",
        "description": "Add validation commands and optional screenshot artifact refs.",
        "inputSchema": _input_schema(
            ["bug_id", "agent_id", "status", "summary", "commands"],
            {
                "bug_id": {"type": "integer"},
                "agent_id": {"type": "string"},
                "status": {"type": "string"},
                "summary": {"type": "string"},
                "commands": {"type": "array", "items": {"type": "object"}},
                "screenshots": {"type": "array", "items": {"type": "object"}},
            },
        ),
    },
    {
        "name": "bugs_close",
        "description": "Close a verified bug. Backend rejects missing evidence.",
        "inputSchema": _input_schema(
            ["bug_id", "actor", "resolution"],
            {
                "bug_id": {"type": "integer"},
                "actor": {"type": "string"},
                "resolution": {"type": "string"},
            },
        ),
    },
    {
        "name": "bugs_reopen",
        "description": "Reopen a bug while preserving lineage and fix history.",
        "inputSchema": _input_schema(
            ["bug_id", "actor", "reason"],
            {
                "bug_id": {"type": "integer"},
                "actor": {"type": "string"},
                "reason": {"type": "string"},
            },
        ),
    },
]
