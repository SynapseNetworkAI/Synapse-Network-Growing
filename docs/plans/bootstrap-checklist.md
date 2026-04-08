# Bootstrap Checklist

- Project: `synapse-network-growing`
- Root: `/Users/cliff/workspace/agent/Synapse-Network-Growing`
- Overall: `READY`

## Checklist
- [x] Core - Core status=HEALTHY (ok=7, warn=0, fail=0, info=0)
- [x] Planning - Planning status=HEALTHY (ok=2, warn=0, fail=0, info=0)
- [x] Integration - Integration status=HEALTHY (ok=2, warn=0, fail=0, info=0)
- [ ] Optional - Optional status=WATCH (ok=2, warn=3, fail=0, info=0)
- [x] Final verification - latest `amem doctor .` already reflects the current healthy state

## Action Sequence
1. Optional (recommended): Refactor flagged functions before adding more behavior, and add a short guiding comment when complex logic must remain in place.
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
- Summary: Planning status=HEALTHY (ok=2, warn=0, fail=0, info=0)
- [OK] `planning_root` present: /Users/cliff/workspace/agent/Synapse-Network-Growing/docs/plans
- [OK] `planning_bundle` 0 planning bundle(s) passed plan-check

### Integration
- Summary: Integration status=HEALTHY (ok=2, warn=0, fail=0, info=0)
- [OK] `bridge_instruction` /Users/cliff/workspace/agent/Synapse-Network-Growing/.github/instructions/agents-memory-bridge.instructions.md
- [OK] `mcp_config` agents-memory server configured -> /Users/cliff/workspace/agent/Synapse-Network-Growing/.vscode/mcp.json

### Optional
- Summary: Optional status=WATCH (ok=2, warn=3, fail=0, info=0)
- [OK] `copilot_activation` Agents-Memory activation block present -> /Users/cliff/workspace/agent/Synapse-Network-Growing/.github/copilot-instructions.md
- [OK] `agents_read_order` AGENTS.md references current bridge and 8 managed standard(s)
- [WARN] `refactor_watch` scripts/verify_frontmatter.py::main high complexity (branches=6>5, nesting=4>=4, locals=9>8, missing_guiding_comment)
- [WARN] `refactor_watch` scripts/verify_frontmatter.py::verify_file high complexity (branches=8>5, nesting=3, locals=6, missing_guiding_comment)
- [WARN] `refactor_watch` server/routers/agents.py::sync_agents high complexity (nesting=3, locals=7, missing_guiding_comment)
