---
name: bug-list-agent
description: Use when an agent needs to read, claim, fix, verify, close, or reopen Synapse product bugs through the Bug List APIs or the local MCP adapter.
metadata:
  version: 1.0.0
---

# Bug List Agent

Use this skill when working on product bugs in Synapse Company Ops. `/bugs` is the agent-native bug backlog and fix evidence ledger; `/errors` is only the runtime error fingerprint surface.

## Hard Boundaries

- Do not write `bug_records`, `bug_fix_attempts`, or `bug_events` directly.
- Do not close a bug without commit or PR evidence, validation commands, and verification result.
- Do not fake screenshots or artifact paths. UI/page/frontend/browser bugs need real screenshot or artifact references.
- Do not claim a bug if another active fix attempt already exists.
- Do not put tokens, private keys, cookies, or secrets into bug evidence.

## Local Setup

Use the local Ops API and an operator-local `OPS_AGENT_BUG_API_TOKEN`.
Set the token in your shell, keychain, or ignored repo `.env`; do not paste the
token value into prompts, bug evidence, PRs, or tracked files.

The MCP adapter is local-only and uses stdio:

```bash
python scripts/mcp/bug_list_server.py
```

The adapter exposes only Bug List tools. It is not a shell, SQL client, or arbitrary HTTP proxy.

Register the skill and MCP server with local Codex:

```bash
python scripts/mcp/register_bug_list_codex.py --force
codex mcp get synapse-bug-list
```

The registration script links this skill into `~/.codex/skills/bug-list-agent` and registers the stdio MCP server as `synapse-bug-list`. It may create a local `OPS_AGENT_BUG_API_TOKEN` in ignored `.env` when one does not already exist; the value is redacted from output.

## Recommended Agent Flow

1. Read the queue with `bugs_agent_queue`.
2. Read full context with `bugs_get`.
3. Claim the bug with `bugs_claim`.
4. Fix the code on a branch and create a commit or PR.
5. Link branch, commit, PR, requirement, or workflow evidence with `bugs_link_fix`.
6. Run validation and capture screenshots when relevant.
7. Add verification with `bugs_add_verification`.
8. Close with `bugs_close` only when evidence is complete; otherwise use `bugs_reopen`.

Always keep these identifiers in your working notes: `bug_id`, `project_key`, branch, commit or PR, validation commands, validation result, and screenshot paths.

## Curl Examples

List bugs:

```bash
curl "$OPS_BASE_URL/api/bugs?project_key=growing&status=ready_for_agent&limit=20"
```

Read the agent queue:

```bash
curl "$OPS_BASE_URL/api/bugs/agent-queue?limit=10"
```

Read one bug:

```bash
curl "$OPS_BASE_URL/api/bugs/123"
```

Create or dedupe a bug through the token-gated agent action:

```bash
curl -X POST "$OPS_BASE_URL/api/bugs/agent-actions/intake" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Bug-Token: $OPS_AGENT_BUG_API_TOKEN" \
  -d '{
    "source_key": "manual_bug_report",
    "project_key": "growing",
    "title": "Publishing modal clips reply candidates",
    "summary": "The X reply task detail modal hides the fifth candidate on narrow screens.",
    "severity": "normal",
    "fingerprint": "publishing-reply-modal-clips-candidates",
    "metadata": {
      "repro_steps": ["Open /publishing?tab=tasks", "Open X Week 1 Reply Block Day 5"]
    }
  }'
```

Claim a bug:

```bash
curl -X POST "$OPS_BASE_URL/api/bugs/agent-actions/123/claim" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Bug-Token: $OPS_AGENT_BUG_API_TOKEN" \
  -d '{"agent_id":"codex","lease_minutes":120}'
```

MCP tools use the same token-gated agent-action routes for writes:

- `bugs_intake`
- `bugs_claim`
- `bugs_materialize_requirement`
- `bugs_link_fix`
- `bugs_add_verification`
- `bugs_close`
- `bugs_reopen`

Link a fix:

```bash
curl -X POST "$OPS_BASE_URL/api/bugs/agent-actions/123/link-fix" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Bug-Token: $OPS_AGENT_BUG_API_TOKEN" \
  -d '{
    "agent_id": "codex",
    "branch_name": "codex/fix-reply-modal",
    "commit_sha": "abc1234",
    "pr_url": "https://github.com/SynapseNetworkAI/Synapse-Network-Growing/pull/123"
  }'
```

Add verification:

```bash
curl -X POST "$OPS_BASE_URL/api/bugs/agent-actions/123/verification" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Bug-Token: $OPS_AGENT_BUG_API_TOKEN" \
  -d '{
    "agent_id": "codex",
    "status": "verified",
    "summary": "Targeted tests and browser screenshot passed.",
    "commands": [
      {"cmd": "npm --prefix dashboard test -- --run BugsPage", "status": "passed"}
    ],
    "screenshots": [
      {"path": "docs/archive/evidence/bugs/reply-modal-fixed.png", "label": "Fixed modal"}
    ]
  }'
```

Close a verified bug:

```bash
curl -X POST "$OPS_BASE_URL/api/bugs/agent-actions/123/close" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Bug-Token: $OPS_AGENT_BUG_API_TOKEN" \
  -d '{"actor":"codex","resolution":"verified"}'
```

Reopen a regression:

```bash
curl -X POST "$OPS_BASE_URL/api/bugs/agent-actions/123/reopen" \
  -H "Content-Type: application/json" \
  -H "X-Growing-Agent-Bug-Token: $OPS_AGENT_BUG_API_TOKEN" \
  -d '{"actor":"codex","reason":"Regression reproduced after deploy smoke."}'
```

## Failure Policy

- `already_claimed`: stop and pick another queue item.
- `missing_evidence`: add real commit, command, and screenshot evidence before closing.
- `auth_required`: configure only local env or keychain credentials; never commit tokens.
- `ops_api_unavailable`: do not create local shadow state. Retry after the Ops API is healthy.
