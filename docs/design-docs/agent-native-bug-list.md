---
id: agent-native-bug-list
title: Agent Native Bug List
role: dev_rel
status: ready
created_at: 2026-05-30
updated_at: 2026-05-30
author: codex
target_repo: Synapse-Network-Growing
---

# Agent Native Bug List

## Purpose

`/bugs` is the agent-native bug backlog and fix evidence ledger. It turns product bugs into structured work that agents can read, claim, fix, verify, and close through APIs instead of scraping UI text or writing directly to the database.

The flow is:

```text
Bug Intake
-> Bug List
-> Agent Queue
-> Bugfix Requirement / Workflow
-> Fix Attempt
-> Verification Evidence
-> Verified / Closed
```

`/errors` remains the runtime error fingerprint surface. `/bugs` is the product bug backlog and remediation control plane.

## Data Model

`bug_records` remains the source of truth for the current bug:

- project and source binding
- severity and status
- fingerprint and dedupe key
- evidence and scorecard
- converted requirement lineage
- latest fix projection in metadata

`bug_fix_attempts` records each remediation attempt:

- active agent claim
- branch, commit, PR, requirement, workflow run
- verification commands
- screenshot or artifact references
- terminal verification status

`bug_events` is append-only event history:

- intake
- dedupe
- claim
- requirement materialization
- fix linkage
- verification
- close / reopen

Screenshots and large artifacts are not stored as database blobs. The database stores only paths, URLs, labels, and metadata.

## Status Model

Bug statuses:

- `open`
- `triaged`
- `ready_for_agent`
- `fixing`
- `fixed_pending_verification`
- `verified`
- `closed`
- `reopened`
- `duplicate`
- `wontfix`

Fix attempt statuses:

- `claimed`
- `fixing`
- `fixed_pending_verification`
- `verified`
- `failed`
- `abandoned`

Only one active fix attempt is allowed per bug. An active attempt is `claimed`, `fixing`, or `fixed_pending_verification`.

## Agent API Contract

Agents must use `/api/bugs/*`; they must not write bug tables directly.

Read APIs:

- `GET /api/bugs`
- `GET /api/bugs/{id}`
- `GET /api/bugs/agent-queue`

Write APIs:

- `POST /api/bugs/intake`
- `POST /api/bugs/{id}/claim`
- `POST /api/bugs/{id}/materialize-requirement`
- `POST /api/bugs/{id}/link-fix`
- `POST /api/bugs/{id}/verification`
- `POST /api/bugs/{id}/close`
- `POST /api/bugs/{id}/reopen`

Agent MCP writes use token-gated aliases:

- `POST /api/bugs/agent-actions/intake`
- `POST /api/bugs/agent-actions/{id}/claim`
- `POST /api/bugs/agent-actions/{id}/materialize-requirement`
- `POST /api/bugs/agent-actions/{id}/link-fix`
- `POST /api/bugs/agent-actions/{id}/verification`
- `POST /api/bugs/agent-actions/{id}/close`
- `POST /api/bugs/agent-actions/{id}/reopen`

`agent_context` is the stable machine-readable contract for agents. It includes target project path, evidence, reproduction data, acceptance checks, linked requirement, and allowed next actions.

## Agent Access: Skill + MCP

Bug List exposes two agent access layers:

1. Repo-local skill: `.agents/skills/bug-list-agent/SKILL.md`
   - Human-readable operating guide for Codex, Claude Code, and local agents.
   - Documents the safe flow: queue, detail, claim, fix, link evidence, verify, close or reopen.
   - Includes curl examples for every supported Bug List action.

2. Local MCP server: `scripts/mcp/bug_list_server.py`
   - Stdio-only adapter for agents that support MCP tools.
   - Wraps only allowlisted `/api/bugs/*` routes.
   - Does not expose shell, SQL, arbitrary HTTP proxying, or direct database writes.
   - Uses `OPS_BASE_URL` for the local Ops API and `OPS_AGENT_BUG_API_TOKEN` for write tools.

Local Codex registration is handled by `scripts/mcp/register_bug_list_codex.py --force`. The script links the skill into `~/.codex/skills/bug-list-agent`, registers the `synapse-bug-list` stdio MCP server, and redacts the local token from output. Registration smoke is covered by `scripts/e2e/bug_list_codex_registration_e2e.py`; live lifecycle smoke is covered by `scripts/e2e/bug_list_mcp_live_e2e.py`.

MCP tools:

- `bugs_list`
- `bugs_get`
- `bugs_agent_queue`
- `bugs_intake`
- `bugs_claim`
- `bugs_materialize_requirement`
- `bugs_link_fix`
- `bugs_add_verification`
- `bugs_close`
- `bugs_reopen`

The MCP adapter is only a machine interface over the canonical API. It does not create a second bug state machine. Backend close and claim rules remain authoritative.

## Verification Rules

Closing a bug requires:

- a verified fix attempt
- commit or PR evidence
- verification command evidence
- screenshot evidence when the bug is UI/page/frontend/browser related

If evidence is missing, close fails closed.

## UI Contract

`/bugs` appears in the primary top navigation as `Bug List`.

The page shows:

- open / ready / fixing / pending verification / verified / critical metrics
- filters for project, status, severity, source, and search
- bug table with project, severity, status, occurrence count, fix branch, commit, and next action
- centered detail modal with Summary, Evidence, Agent Context, Fix Attempts, Verification, and Events

The UI is a Human-Agent Control Plane. Raw JSON appears only as bounded evidence snippets, not as the primary operator surface.
