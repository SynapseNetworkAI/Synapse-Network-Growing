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

1. [WARN] `server/services/portfolio_scheduler.py::execute_portfolio_schedule` line=537 metrics=(lines=44, branches=9, nesting=4, locals=14)
   - token: `hotspot-025a0c05b0ae`
   - issues: `lines=44>40, branches=9>5, nesting=4>=4, locals=14>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-025a0c05b0ae`
2. [WARN] `server/services/workflow_orchestrator.py::_soft_delete_requirement_tree` line=5351 metrics=(lines=57, branches=12, nesting=4, locals=12)
   - token: `hotspot-16cee63ef81e`
   - issues: `lines=57>40, branches=12>5, nesting=4>=4, locals=12>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-16cee63ef81e`
3. [WARN] `server/services/portfolio_scheduler.py::build_portfolio_schedule` line=217 metrics=(lines=277, branches=17, nesting=4, locals=45)
   - token: `hotspot-1c3308f24dbf`
   - issues: `lines=277>40, branches=17>5, nesting=4>=4, locals=45>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-1c3308f24dbf`
4. [WARN] `server/services/recurring_workflows.py::run_recurring_workflow` line=694 metrics=(lines=94, branches=7, nesting=6, locals=10)
   - token: `hotspot-37c0e63b7c2e`
   - issues: `lines=94>40, branches=7>5, nesting=6>=4, locals=10>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-37c0e63b7c2e`
5. [WARN] `server/services/workflow_orchestrator.py::_snapshot_file_changes` line=467 metrics=(lines=105, branches=14, nesting=4, locals=24)
   - token: `hotspot-496d4d30bc00`
   - issues: `lines=105>40, branches=14>5, nesting=4>=4, locals=24>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-496d4d30bc00`

## Suggested Action

1. Run `amem refactor-bundle .` to materialize the first hotspot into an executable planning bundle.
2. If a hotspot cannot be split yet, add a guiding comment that explains the main decision path and risk boundaries.
3. Re-run `amem doctor .` after the change and confirm `refactor_watch` findings shrink or disappear.
