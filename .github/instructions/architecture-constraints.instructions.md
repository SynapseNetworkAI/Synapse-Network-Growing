---
description: >
  Synapse architecture constraints. Apply before changing workflow,
  planning, scheduler, release, notification, runtime, security, auth,
  finance, settlement, or production-delivery code.
applyTo: "**"
---

# Architecture Constraints

Before substantial edits in this repository, read:

1. `ARCHITECTURE.md`
2. `docs/design-docs/system-design-principles.md`
3. `docs/design-docs/context-loading-map.md`

`system-design-principles.md` is the short always-load entrypoint. Use `context-loading-map.md` to load only the matching detailed principle docs. If the task touches workflow factory, planning lifecycle, recurring jobs, notifications, release/deploy, auth, finance, settlement, runtime, or production safety, also read the relevant design doc linked from `ARCHITECTURE.md`.

Hard rules:

1. Do not create a God Agent that owns global control flow.
2. Complex workflow control must be declarative state machine behavior, not hidden Python `if/else` orchestration.
3. Agents may produce structured output; deterministic runner owns state transitions.
4. Planner Sweep creates `RequirementCandidate` records, not official requirements, unless explicitly materialized after approval.
5. Drop Goal never triggers rollback, revert, database deletion, unpublish, or delivered release mutation.
6. Funds, settlement, contract, auth, production deploy, external paid spend, and self-modifying deployment require human gate.
7. Every automation must be observable through structured state, artifacts, run history, logs, or Ops Console.
