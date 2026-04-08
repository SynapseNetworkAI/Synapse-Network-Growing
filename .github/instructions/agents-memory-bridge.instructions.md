---
description: >
  Agents-Memory bridge. Apply to every code-changing session.
  Loads shared error memory at session start; records new errors at session end.
  Works across all projects registered in the Agents-Memory system.
applyTo: "**"
---

# Agents-Memory Bridge

## Session Protocol

### On Session Start (every coding session)

**Step 0 — Read onboarding state first (if present):**
Preferred via MCP:
```
memory_get_onboarding_next_action(project_root=".")
```
If the first step is blocking and execution is safe to automate, prefer:
```
memory_execute_onboarding_next_action(project_root=".", verify=true, approve_unsafe=false)
```

If you need the full state payload, then call:
```
memory_get_onboarding_state(project_root=".")
```

Fallback via file:
```
Read .agents-memory/onboarding-state.json
```
If the file exists:
- Check `project_bootstrap_ready`
- Check `project_bootstrap_complete`
- Check `recommended_next_command`
- Check `recommended_verify_command`
- Check `recommended_next_safe_to_auto_execute`
- Check `recommended_next_approval_required`
- If `project_bootstrap_ready` is `false`, finish the recommended onboarding step before deep code changes
- If `project_bootstrap_ready` is `true` but `project_bootstrap_complete` is `false`, treat the next step as recommended cleanup rather than a blocker
- If `recommended_next_approval_required` is `true`, do not auto-execute it without explicit human approval
- After executing a step, re-read `.agents-memory/onboarding-state.json` or call `memory_get_onboarding_next_action(project_root=".")` again

If the file does not exist yet:
```bash
python3 /Users/cliff/workspace/agent/Agents-Memory/scripts/memory.py doctor . --write-state --write-checklist
```
Then read `.agents-memory/onboarding-state.json` and follow the first pending step.

**Step 1 — Load hot-tier index (always):**
```
Read /Users/cliff/workspace/agent/Agents-Memory/index.md
```
This file is ≤ 400 tokens. It tells you:
- How many error records exist (determines search strategy)
- Which error categories have been seen most
- Which rules have been promoted to instruction files

**Step 2 — Load domain rules (before touching domain-specific code):**
```
# Finance code
Read /Users/cliff/workspace/agent/Agents-Memory/memory/rules.md (Finance section)

# Python / FastAPI
Read /Users/cliff/workspace/agent/Agents-Memory/memory/rules.md (Python section)

# TypeScript / Frontend
Read /Users/cliff/workspace/agent/Agents-Memory/memory/rules.md (TypeScript section)
```

**Step 3 — Search before writing (when you see a pattern):**
```bash
python3 /Users/cliff/workspace/agent/Agents-Memory/scripts/memory.py search <keyword>
```
Or via MCP tool: `memory_search(query="<keyword>")`

---

### On Session End (after any bug fix or unexpected behavior)

**Record any error that took more than one attempt to fix:**

**Option A — MCP tool (preferred, works inside agent tool calls):**
```
memory_record_error(
  project="synapse-network-growing",
  domain="python",               # finance | frontend | python | docs | config | infra
  category="logic-error",        # see CATEGORIES in memory.py
  severity="warning",            # critical | warning | info
  task="What were you doing",
  error_desc="What went wrong",
  root_cause="Why it happened",
  fix="How it was fixed",
  rule="Never do X, always do Y instead."
)
```

**Option B — CLI (when MCP not available):**
```bash
python3 /Users/cliff/workspace/agent/Agents-Memory/scripts/memory.py new
```

---

## Trigger Conditions

| Condition | Action |
|-----------|--------|
| Session starts with code changes | Load `index.md` |
| Session starts and `.agents-memory/onboarding-state.json` exists | Read state and follow `recommended_next_command` first when bootstrap is incomplete |
| Session starts and onboarding state is missing | Run `doctor . --write-state --write-checklist` before deep onboarding |
| Working on finance/payment code | Also load `rules.md` Finance section |
| Working on Python/FastAPI | Also load `rules.md` Python section |
| Fixed a bug (any kind) | Record via MCP or CLI |
| Same error seen twice | Increment `repeat_count` via `memory_increment_repeat(id)` |
| Record reaches repeat_count ≥ 2 | Promote to instruction file via `memory_promote(id)` |

---

## Error Category Quick Reference

| Category | When to use |
|----------|-------------|
| `type-error` | TypeScript narrowing, Python type annotation failure |
| `logic-error` | Wrong algorithm, edge case missed |
| `finance-safety` | Precision loss, missing audit trail, wrong Decimal usage |
| `arch-violation` | Bypassed layering, wrong service access pattern |
| `test-failure` | Test infrastructure broke, coverage gap |
| `docs-drift` | Code changed but docs not updated |
| `config-error` | DSN, env var, secret misconfiguration |
| `build-error` | Import failure, compilation error |
| `runtime-error` | Unexpected exception, unhandled case |
| `security` | Any access control, injection, or SSRF risk |

---

## MCP Server

If the Agents-Memory MCP server is running as a VS Code tool, you can call:
- `memory_get_index()` — get index.md content
- `memory_get_rules(domain)` — get domain rules
- `memory_search(query)` — search errors
- `memory_record_error(...)` — record a new error
- `memory_increment_repeat(id)` — bump repeat count
- `memory_list_projects()` — see all registered projects
- `memory_sync_stats()` — check record count and search strategy

MCP server config is typically installed into the target repository at `.vscode/mcp.json`.
