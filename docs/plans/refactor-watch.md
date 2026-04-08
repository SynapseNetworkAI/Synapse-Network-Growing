# Refactor Watch

- Project: `synapse-network-growing`
- Root: `/Users/cliff/workspace/agent/Synapse-Network-Growing`

## Purpose

Track Python functions that are already high-complexity or are approaching the configured refactor thresholds.

## Thresholds

- Hard gate: more than 40 effective lines, more than 5 control-flow branches, nesting depth >= 4, or more than 8 local variables.
- Watch zone: around 30 effective lines, 4 branches, nesting depth 3, or 6 local variables.
- Complex logic should include a short guiding comment when it cannot be cleanly decomposed yet.

## Workflow Entry

- Primary command: `amem refactor-bundle .`
- Prefer stable targeting with: `amem refactor-bundle . --token <hotspot-token>`
- Fallback positional targeting: `amem refactor-bundle . --index <n>`
- The command creates or refreshes `docs/plans/refactor-<slug>/` using the first current hotspot as execution context.

## Hotspots

1. [WARN] `scripts/verify_frontmatter.py::main` line=42 metrics=(lines=21, branches=6, nesting=4, locals=9)
   - token: `hotspot-9c6441ed2adf`
   - issues: `branches=6>5, nesting=4>=4, locals=9>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-9c6441ed2adf`
2. [WARN] `scripts/verify_frontmatter.py::verify_file` line=10 metrics=(lines=23, branches=8, nesting=3, locals=6)
   - token: `hotspot-168b19b70934`
   - issues: `branches=8>5, nesting=3, locals=6, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-168b19b70934`
3. [WARN] `server/routers/agents.py::sync_agents` line=44 metrics=(lines=18, branches=3, nesting=3, locals=7)
   - token: `hotspot-15c51567619b`
   - issues: `nesting=3, locals=7, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-15c51567619b`

## Suggested Action

1. Run `amem refactor-bundle .` to materialize the first hotspot into an executable planning bundle.
2. If a hotspot cannot be split yet, add a guiding comment that explains the main decision path and risk boundaries.
3. Re-run `amem doctor .` after the change and confirm `refactor_watch` findings shrink or disappear.
