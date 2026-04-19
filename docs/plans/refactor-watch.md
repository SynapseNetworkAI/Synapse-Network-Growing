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

1. [WARN] `scripts/generate_architecture_graph.py::detect_import_edges` line=307 metrics=(lines=56, branches=19, nesting=5, locals=16)
   - token: `hotspot-0e89c9d2bec2`
   - issues: `lines=56>40, branches=19>5, nesting=5>=4, locals=16>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-0e89c9d2bec2`
2. [WARN] `server/services/workflows/agent_first.py::reconcile_execution_state` line=1464 metrics=(lines=148, branches=23, nesting=10, locals=25)
   - token: `hotspot-248b67f5afe3`
   - issues: `lines=148>40, branches=23>5, nesting=10>=4, locals=25>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-248b67f5afe3`
3. [WARN] `server/services/reviews/company_review.py::_cross_project_bug_recoveries` line=303 metrics=(lines=64, branches=7, nesting=4, locals=14)
   - token: `hotspot-258fa257e3de`
   - issues: `lines=64>40, branches=7>5, nesting=4>=4, locals=14>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-258fa257e3de`
4. [WARN] `server/services/workflows/orchestrator/__init__.py::_soft_delete_requirement_tree` line=5743 metrics=(lines=57, branches=12, nesting=4, locals=12)
   - token: `hotspot-27e722eb8667`
   - issues: `lines=57>40, branches=12>5, nesting=4>=4, locals=12>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-27e722eb8667`
5. [WARN] `server/services/scheduling/portfolio_scheduler.py::execute_portfolio_rebalance` line=662 metrics=(lines=61, branches=8, nesting=4, locals=14)
   - token: `hotspot-33e6149a23cd`
   - issues: `lines=61>40, branches=8>5, nesting=4>=4, locals=14>8, missing_guiding_comment`
   - bundle command: `amem refactor-bundle . --token hotspot-33e6149a23cd`

## Suggested Action

1. Run `amem refactor-bundle .` to materialize the first hotspot into an executable planning bundle.
2. If a hotspot cannot be split yet, add a guiding comment that explains the main decision path and risk boundaries.
3. Re-run `amem doctor .` after the change and confirm `refactor_watch` findings shrink or disappear.
