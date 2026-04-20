# Planning Bundles

This directory is only a temporary staging area for new planning bundles before they are implemented or archived.

Rules:

1. Active architecture belongs in `../design-docs/`, not here.
2. Historical and strategic planning bundles belong in `../archive/plans/`.
3. Planning bundles should not override `../../ARCHITECTURE.md` or canonical design docs.
4. When a plan becomes implemented behavior, update `../design-docs/current-feature-inventory.md`.

Recommended flow:

1. Run `amem plan-init "<task-name>" .`
2. Fill `spec.md`, `plan.md`, `task-graph.md`, and `validation.md`
3. Run `amem plan-check .` before implementation is considered complete.
