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
- The homepage still mixed static organization visuals into the COO workflow surface, instead of focusing on operating review and rituals.

## Acceptance Criteria

- A requirement can declare dependencies on other requirements and becomes `blocked` until all hard blockers are `done`.
- Blocked requirements cannot be planned or started.
- Once all blockers finish, dependent requirements automatically become `ready`.
- A requirement can enter `needs_revision`, accept a revised spec, and be replanned on a new plan version.
- The homepage removes static org visualization and stays focused on COO dashboard workflows.
- Backend, frontend, and browser smoke coverage validate the new behavior.
