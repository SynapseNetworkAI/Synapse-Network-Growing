# Bootstrap Checklist

- Project: `synapse-network-growing`
- Root: `/Users/cliff/workspace/agent/Synapse-Network-Growing`
- Overall: `PARTIAL`

## Checklist
- [x] Core - Core status=HEALTHY (ok=7, warn=0, fail=0, info=0)
- [ ] Planning - Planning status=ATTENTION (ok=1, warn=0, fail=1, info=0)
- [x] Integration - Integration status=HEALTHY (ok=2, warn=0, fail=0, info=0)
- [ ] Optional - Optional status=WATCH (ok=2, warn=5, fail=0, info=0)
- [ ] Final verification - re-run `amem doctor .` and confirm no remaining WARN / FAIL steps

## Action Sequence
1. Planning (required): Run `amem plan-check .`, then fill in or repair the missing planning bundle files.
2. Optional (recommended): Refactor flagged functions before adding more behavior, and add a short guiding comment when complex logic must remain in place.

## Onboarding Runbook
### Step 1: Planning / planning_bundle
- Priority: `required`
- Trigger: docs/plans/ai-company-ops-roadmap/README.md missing required phrases: planning bundle
- Action: Repair the planning bundle so the repository has a valid spec-first execution package.
- Command: `amem plan-check .`
- Verify with: `amem plan-check .`
- Next command: `amem doctor .`
- Safe To Auto Execute: `False`
- Approval Required: `True`
- Approval Reason: plan-check only diagnoses issues; actual planning repairs should be reviewed before editing tracked docs
- Done when: `amem doctor .` shows `[OK] planning_bundle`.

## Group Health
### Core
- Summary: Core status=HEALTHY (ok=7, warn=0, fail=0, info=0)
- [OK] `registry` registered as 'synapse-network-growing'
- [OK] `active` active=true
- [OK] `root` /Users/cliff/workspace/agent/Synapse-Network-Growing
- [OK] `python3.12` /opt/homebrew/bin/python3.12
- [OK] `mcp_package` mcp import OK
- [OK] `profile_manifest` applied profile 'python-service'
- [OK] `profile_consistency` profile 'python-service' consistency OK

### Planning
- Summary: Planning status=ATTENTION (ok=1, warn=0, fail=1, info=0)
- [OK] `planning_root` present: /Users/cliff/workspace/agent/Synapse-Network-Growing/docs/plans
- [FAIL] `planning_bundle` docs/plans/ai-company-ops-roadmap/README.md missing required phrases: planning bundle

### Integration
- Summary: Integration status=HEALTHY (ok=2, warn=0, fail=0, info=0)
- [OK] `bridge_instruction` /Users/cliff/workspace/agent/Synapse-Network-Growing/.github/instructions/agents-memory-bridge.instructions.md
- [OK] `mcp_config` agents-memory server configured -> /Users/cliff/workspace/agent/Synapse-Network-Growing/.vscode/mcp.json

### Optional
- Summary: Optional status=WATCH (ok=2, warn=5, fail=0, info=0)
- [OK] `copilot_activation` Agents-Memory activation block present -> /Users/cliff/workspace/agent/Synapse-Network-Growing/.github/copilot-instructions.md
- [OK] `agents_read_order` AGENTS.md references current bridge and 8 managed standard(s)
- [WARN] `refactor_watch` server/services/portfolio_scheduler.py::execute_portfolio_schedule high complexity (lines=44>40, branches=9>5, nesting=4>=4, locals=14>8, missing_guiding_comment)
- [WARN] `refactor_watch` server/services/workflow_orchestrator.py::_soft_delete_requirement_tree high complexity (lines=57>40, branches=12>5, nesting=4>=4, locals=12>8, missing_guiding_comment)
- [WARN] `refactor_watch` server/services/portfolio_scheduler.py::build_portfolio_schedule high complexity (lines=277>40, branches=17>5, nesting=4>=4, locals=45>8, missing_guiding_comment)
- [WARN] `refactor_watch` server/services/recurring_workflows.py::run_recurring_workflow high complexity (lines=94>40, branches=7>5, nesting=6>=4, locals=10>8, missing_guiding_comment)
- [WARN] `refactor_watch` server/services/workflow_orchestrator.py::_snapshot_file_changes high complexity (lines=105>40, branches=14>5, nesting=4>=4, locals=24>8, missing_guiding_comment)
