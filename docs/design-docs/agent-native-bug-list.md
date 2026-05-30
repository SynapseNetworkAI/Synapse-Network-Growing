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

`agent_context` is the stable machine-readable contract for agents. It includes target project path, evidence, reproduction data, acceptance checks, linked requirement, and allowed next actions.

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
