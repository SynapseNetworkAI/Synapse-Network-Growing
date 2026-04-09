---
created_at: 2026-04-09
updated_at: 2026-04-09
doc_status: active
---

# Spec

## Goal

Close the remaining Phase 1 gaps between [docs/design-docs/requirement-pool-multi-agent-workflow-architecture.md](../design-docs/requirement-pool-multi-agent-workflow-architecture.md) and the current implementation.

## Remaining Gaps

- Requirement dependencies existed in the schema, but were not exposed in API, not enforced in workflow gating, and not visible in the UI.
- Requirement revision existed only as a terminal status hint, without a revision submission and re-planning loop.
- The org page still rendered a static CTO and hardcoded domain tree instead of only showing real agents discovered from `roles/*`.

## Acceptance Criteria

- A requirement can declare dependencies on other requirements and becomes `blocked` until all hard blockers are `done`.
- Blocked requirements cannot be planned or started.
- Once all blockers finish, dependent requirements automatically become `ready`.
- A requirement can enter `needs_revision`, accept a revised spec, and be replanned on a new plan version.
- The org page and `/api/org` only display real agents discovered from `roles/*`, optionally grouped dynamically by discovered metadata.
- Backend, frontend, and browser smoke coverage validate the new behavior.