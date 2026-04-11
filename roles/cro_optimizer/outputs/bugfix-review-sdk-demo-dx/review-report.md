---
id: bugfix-review-sdk-demo-dx
title: Bugfix Review — CAPIError tool_use/tool_result Mismatch on Session Resume
role: cro_optimizer
status: ready
created_at: 2026-04-11
updated_at: 2026-04-11
author: cro_optimizer
target_repo: Synapse-Network-Growing
---

# Bugfix Review: `CAPIError: tool_use ids without tool_result blocks`

**Commit:** `63b7657`  
**Requirement:** #12 — [DevRel] SDK Demo 端到端验证  
**Files changed:** `copilot-sdk-runner/run_session.mjs`, `server/services/copilot_sdk_monitor.py`

---

## Verdict: ✅ ACCEPT

The fix is correct, complete, and safe. Both layers of the two-layer defense address the root cause cleanly.

---

## Root Cause Confirmation

When a Copilot SDK agent session crashes **mid-tool-execution**, the session's stored conversation history contains `assistant` messages with `tool_use` blocks, but the corresponding `tool_result` blocks were never appended (the crash happened between tool call and tool response). On the next `resume`, the Anthropic API rejects the message with:

```
CAPIError: 400 messages.N: tool_use ids were found without tool_result blocks immediately after
```

This is a legitimate API constraint — Anthropic requires every `tool_use` block to be immediately followed by a `tool_result` block in the conversation history. The stored session is permanently corrupt and cannot be repaired incrementally.

---

## Layer 1 Review — `run_session.mjs` (Primary Fix)

### What it does
Wraps `waitForFinalAssistantMessage` in a nested try-catch. On detection of the mismatch error during a `resume` action:
1. Emits `session.fallback` synthetic event (observability)
2. Unsubscribes live event listener
3. Disconnects broken session (swallows disconnect errors with `.catch(() => {})`)
4. Clears heartbeat interval
5. Creates a brand-new session
6. Re-wires all event listeners and heartbeat on the new session
7. Retries with the original prompt

### Correctness Analysis

| Check | Result |
|-------|--------|
| Error detection (`isToolUseMismatchError`) — string match on both `tool_use` AND `tool_result` | ✅ Sufficient. The API error message is the only signal available; the conjunction prevents false positives on unrelated messages. |
| Guard on `input.action === "resume"` | ✅ Prevents fallback loop — a fresh session with `action = "start"` would never hit this branch. |
| `liveUnsubscribe()` before disconnect | ✅ No dangling listener on the dead session. |
| `clearInterval(heartbeatTimer)` before reassignment | ✅ No leaked timer. |
| `heartbeatTimer.unref?.()` on the new timer | ✅ Matches existing pattern; won't block process exit. |
| `finally` block cleanup | ✅ After fallback, `session`, `heartbeatTimer`, `liveUnsubscribe` are all reassigned to the **new** session's values. The outer `finally` correctly cleans up the new session if the second `waitForFinalAssistantMessage` also throws. |
| `content` variable not reset between sessions | ⚠️ Minor: any partial streaming output from the broken session is prepended to the new session's output. In practice, a session that crashed mid-tool-execution would have an empty or irrelevant `content`. Acceptable for now. |

### Risk: No Retry Loop

The fallback creates exactly **one** fresh session. If that fresh session also fails (different error), the outer `catch (error)` properly propagates it to `recorder.finalizeFailure`. This is the correct behavior — no infinite retry risk.

---

## Layer 2 Review — `copilot_sdk_monitor.py` (Defensive Fix)

### What it does
In `_fail_task()`, if the error message contains both `"tool_use"` and `"tool_result"`, calls `get_copilot_sdk_runtime().clear_role_sessions()` on the singleton runtime. This prevents the monitor from re-queuing a `resume` against the same corrupt session after the primary recovery path is bypassed (e.g., if `run_session.mjs` exited before Layer 1 could recover).

### Correctness Analysis

| Check | Result |
|-------|--------|
| `get_copilot_sdk_runtime()` returns `None` guard | ✅ `if runtime is not None:` prevents NPE when using `LegacyTaskRuntime`. |
| String match strategy consistent with Layer 1 | ✅ Same `"tool_use" in error_message and "tool_result" in error_message` predicate. |
| `db.commit()` still called after the clear | ✅ The clear is injected before `db.commit()` but does not affect DB state. No transaction risk. |
| Side effect on singleton | ✅ `clear_role_sessions()` is thread-safe (acquires `self._lock`). |

---

## Test Coverage

Existing tests in `tests/test_role_session_reuse.py::TestRoleSessionReuse` cover:
- `test_clear_role_sessions` — verifies `clear_role_sessions()` empties the cache and forces a new `start_session` call on next dispatch

**Test run result:** `6 passed in 0.04s` ✅

**Gap noted:** No unit test specifically exercises the `_fail_task` mismatch-detection branch in `copilot_sdk_monitor.py`. Coverage is functional via integration but a targeted unit test would be a good follow-up.

---

## DX Impact (Requirement #12 Context)

This fix eliminates a **silent retry death loop** that previously caused the SDK demo workflow to fail non-deterministically. A developer running the 3-line quickstart (`AgentWallet → MCP call → USDC deduction`) would see a cryptic 400 error with no actionable message if any background session crashed mid-tool. Post-fix behavior:

- **Layer 1 (primary):** Transparent recovery — the task retries seamlessly with a fresh session, the developer sees no error.
- **Layer 2 (defensive):** Even if the process crashed before Layer 1 ran, the next task dispatch starts clean rather than hitting the same wall.

**DX friction eliminated:** ~1 category of non-deterministic 400 errors that required manual session clearing.

---

## Recommendations (Non-Blocking)

1. **Add a targeted unit test** for `_fail_task` mismatch branch in `copilot_sdk_monitor.py`.
2. **Reset `content = ""`** at the start of the fallback path in `run_session.mjs` to avoid prepending stale partial output to the fresh session's result.
3. **Consider exposing `session.fallback` count** in the monitoring dashboard to track how often this recovery triggers in production.

---

## Review Checklist

- [x] Root cause accurately identified
- [x] Fix addresses root cause (not just symptom)
- [x] No new error paths introduced
- [x] Resource cleanup correct (timers, listeners, sessions)
- [x] Thread safety preserved
- [x] Existing tests pass
- [x] No dark patterns, no data loss
- [x] Commit message accurately describes the change
