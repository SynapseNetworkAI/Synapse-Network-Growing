---
created_at: 2026-04-09
updated_at: 2026-04-09
doc_status: active
---

# Execution Plan

## Scope

- Backend requirement orchestration and API surface
- Requirement pool UI and org chart UI
- Backend API tests, frontend unit tests, and Playwright smoke coverage

## Design Notes

- Keep the existing workflow mainline intact and only add missing control-plane behavior.
- Implement requirement revision as an explicit, deterministic loop: `needs_revision` -> revise spec -> re-plan.
- Replace the org tree source with discovered roles rather than patching the old static hierarchy.

## Change Set

- Add dependency create/update/read support and automatic blocked/ready state recomputation.
- Add revision submission endpoint and reopen/replan behavior.
- Replace org API/tree rendering with roles-only dynamic grouping.
- Update tests to lock the new contract.

## Action Sequence Snapshot

```json
[
  "Document the remaining gaps and acceptance target.",
  "Implement dependency gating and revision lifecycle in the backend.",
  "Wire requirement pool UI to dependencies and revision actions.",
  "Replace static org hierarchy with roles-only rendering.",
  "Run backend, frontend, build, and Playwright validation."
]
```