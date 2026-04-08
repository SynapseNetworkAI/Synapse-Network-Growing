<!-- agents-memory:start -->
# Agents-Memory Auto-Activation

When working in this repository, treat Agents-Memory as mandatory session context for coding, debugging, code review, refactors, migrations, and docs-sync work.

## Required startup sequence

1. Before any substantial analysis or edits, call `memory_get_onboarding_next_action(project_root=".")` if the `agents-memory` MCP server is available.
   If the first step is safe to automate, prefer `memory_execute_onboarding_next_action(project_root=".", verify=true, approve_unsafe=false)` so the system records execution and verification back into onboarding state.
   If you need full context, then call `memory_get_onboarding_state(project_root=".")`.
   If MCP tools are unavailable, read `.agents-memory/onboarding-state.json` directly if it exists.
   If `project_bootstrap_ready` is `false`, follow `recommended_next_command`, then verify with `recommended_verify_command` before continuing.
   If `recommended_next_approval_required` is `true`, pause for explicit human approval before executing it.
   If `project_bootstrap_ready` is `true` but `project_bootstrap_complete` is `false`, treat `recommended_next_command` as a recommended follow-up instead of a blocker.
   If the file is missing, run `python3 /Users/cliff/workspace/agent/Agents-Memory/scripts/memory.py doctor . --write-state --write-checklist`.
2. Call `memory_get_index()` if the `agents-memory` MCP server is available.
3. Before touching domain-specific code, call `memory_get_rules(domain)` with the closest matching domain:
   - `python` for Python, FastAPI, backend, repository, or migration work
   - `frontend` for TypeScript, React, Next.js, or UI work
   - `finance` for balance, billing, settlement, ledger, withdraw, refund, or reconciliation work
   - `docs` for README, AGENTS, instruction, contract, workflow, or runbook updates
4. When the task resembles a previous failure pattern, call `memory_search(query)` before writing code.

## Error capture protocol

- Use `project="synapse-network-growing"` when calling `memory_record_error(...)` for this repository.
- If the same error pattern happens again, prefer `memory_increment_repeat(id)` instead of creating a duplicate record.
- Record a new error after any bug fix that took more than one attempt or exposed a reusable lesson.

## Fallback when MCP is unavailable

Use the CLI directly:

```bash
python3 /Users/cliff/workspace/agent/Agents-Memory/scripts/memory.py search <keyword>
python3 /Users/cliff/workspace/agent/Agents-Memory/scripts/memory.py new
```

## Notes

- This file is the strongest repository-wide auto-activation mechanism officially supported by GitHub Copilot custom instructions.
- It improves default tool usage on every repository-scoped request, but it does not hard-enforce MCP tool execution when the platform chooses not to use tools.
<!-- agents-memory:end -->
