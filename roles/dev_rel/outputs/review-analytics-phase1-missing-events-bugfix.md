---
id: review-analytics-phase1-missing-events-bugfix
title: "Code Review: Analytics Phase 1 Missing Events — Bugfix Implementation"
role: dev_rel
status: review
created_at: 2026-04-11
updated_at: 2026-04-11
author: dev_rel_agent
target_repo: Synapse-Network
---

# Code Review: Analytics Phase 1 Missing Events — Bugfix Implementation

> **Requirement #16:** Implement 4 ❌ Missing gateway emitters from `review-analytics-tracking-plan.md`:
> `service_registered`, `provider_first_revenue_received`, `service_register_failed`, `provider_health_degraded`
>
> **Acceptance criteria:** `pytest services/gateway/tests/ -v` all green covering all 4 events.

---

## 1. Files Reviewed

| File | Change |
|------|--------|
| `services/gateway/src/services/analytics/gateway_events.py` | 4 new emitter functions added (+ 3 duplicate definitions, see BLOCK-1) |
| `services/gateway/src/services/provider/registry/registration.py` | Wires `emit_service_registered` + `emit_service_register_failed` |
| `services/gateway/src/services/platform/service_health_probe.py` | Wires `emit_provider_health_degraded` |
| `services/gateway/src/services/owner/forwarding_service.py` | Wires `emit_provider_first_revenue_received` |
| `services/gateway/src/services/platform/tasks/consumer_withdraw_processor.py` | Adds analytics emit for `withdrawal_completed` |
| `services/gateway/src/services/owner/finance_refund_exec_mixin.py` | Adds analytics emit for `refund_completed` |
| `services/gateway/tests/unit/test_analytics_missing_events_unit.py` | **NEW** — 19 unit tests for all 4 events |

---

## 2. Test Results (Executed)

```
Gateway analytics tests (venv: Python 3.11)
  test_analytics_missing_events_unit.py   19 passed  ← all 4 new events
  test_analytics_emitter_unit.py          10 passed
  test_analytics_fullstack_unit.py        27 passed
  test_gateway_events_unit.py             20 passed
  test_registry_registration_unit.py       4 passed
  test_service_registration_unit.py       10 passed
  test_service_health_monitor_unit.py      1 passed
  ─────────────────────────────────────
  Targeted analytics suite total:         91 passed, 0 failed
```

```
Full gateway test suite
  334 passed, 18 failed (pre-existing 15 + 3 newly introduced), 17 skipped
```

> **Note on pre-existing baseline:** Running the same test suite against HEAD *without* the WD changes
> produces 15 failed (consumer_withdraw: 13, finance_runtime: 2). The bugfix changes
> introduce 3 additional failures in `test_consumer_withdraw_unit.py` (see BLOCK-2).

---

## 3. Review Findings

### ✅ PASS

- **P1:** All 4 event names match the tracking plan exactly: `service_registered`, `service_register_failed`, `provider_first_revenue_received`, `provider_health_degraded`
- **P2:** All emitters hash `provider_address` for both `distinct_id` (passed to `_emit()`) and `properties.provider_id` — no raw `0x…` wallet addresses leak
- **P3:** `emit_provider_first_revenue_received` sets `is_first_revenue: True` and conditionally omits `time_since_listing_ms` when `None` (not null-serialized) — clean optional field pattern
- **P4:** All 4 emitters set `role="provider"` correctly
- **P5:** All 4 emitters are fire-and-forget: silent no-op when `_emitter is None`; exceptions silently swallowed at the `_emit()` level — calling business logic is never disrupted
- **P6:** Call sites are correct:
  - `registration.py`: emits `service_registered` after `context._save_service_registry_rows()` — post-persistence, correct sequencing
  - `registration.py`: emits `service_register_failed` in the `ValueError` catch on `ensure_unique_service_id` — correct failure signal
  - `service_health_probe.py`: emits on health transition to `degraded` or `unhealthy` — not on every probe tick
  - `forwarding_service.py`: emits `provider_first_revenue_received` after checking prior settled rows
- **P7:** 19 new unit tests cover all required behaviors: payload validation, PII hashing, noop-when-no-emitter, and error resilience (backend down) for all 4 events
- **P8:** `autouse` `reset_emitter` fixture provides correct test isolation — emitter is `None` before and after each test

---

### 🔴 BLOCK — Must Fix Before Merge

**BLOCK-1: Duplicate function definitions in `gateway_events.py`**

`emit_service_registered`, `emit_service_register_failed`, and `emit_provider_health_degraded` are each **defined twice** in `gateway_events.py`. Python silently uses the last definition; the first is dead code.

```python
# Lines 322–362: FIRST definition of emit_service_registered (dead — overridden below)
async def emit_service_registered(provider_address, *, service_id, service_name="", ...):
    ...

# Lines 390–408: SECOND definition (active — this is what callers get)
async def emit_service_registered(provider_address, *, service_id, service_name="", ...):
    ...
```

The duplicate signatures have subtle differences that indicate two separate authoring passes were concatenated without cleanup:

| Function | First signature | Second signature |
|---------|----------------|-----------------|
| `emit_service_register_failed` | `(error_code, reason="")` | `(error_code, service_name="", reason="")` + conditional reason |
| `emit_provider_health_degraded` | `overall_status` required | `overall_status="degraded"` defaulted |

**Required fix:** Remove the first (dead) definition block (lines ~322–383 of `gateway_events.py`). Keep the second definitions, which are what the unit tests validate.

---

**BLOCK-2: 3 new test regressions introduced in `test_consumer_withdraw_unit.py`**

Before this change: 13 failing in `test_consumer_withdraw_unit.py` (pre-existing).
After this change: 16 failing — 3 tests that were previously passing now fail.

The 3 newly failing tests are in `TestConsumerWithdrawBalanceDecrease`:
- `test_audit_log_created`
- `test_available_decreases_after_requested_withdrawal`
- `test_partial_withdrawal_leaves_correct_available_balance`

Failure message:
```
TypeError: InMemoryGatewayStateRepo.read_consumer_refund_rows() got an unexpected keyword argument 'owner_wallet'
```

This error path is triggered by changes to `finance_refund_exec_mixin.py` (the new `refund_completed` analytics emit added in this PR). The analytics emit itself is fine, but its addition caused previously dormant test paths to execute additional code that exposes the pre-existing `read_consumer_refund_rows` mock incompatibility.

**Required fix:** Either update `InMemoryGatewayStateRepo.read_consumer_refund_rows()` to accept `owner_wallet`, or mock/isolate the analytics emit in the affected tests so they don't traverse the broken path. Regression must be zeroed before merge.

---

### ⚠️ WARN — Non-Blocking, Fix in Follow-up

**W1: Inline `asyncio.get_running_loop()` pattern in sync call sites**

`consumer_withdraw_processor.py` and `finance_refund_exec_mixin.py` emit analytics using:

```python
import asyncio
from src.services.analytics.gateway_events import emit_withdrawal_completed
try:
    loop = asyncio.get_running_loop()
    loop.create_task(emit_withdrawal_completed(...))
except RuntimeError:
    pass
```

This pattern is fragile — `RuntimeError` silently swallows the failure when there's no running event loop, which is common in background processor contexts. The established pattern in the codebase uses `await emit_*()` directly inside async functions. This workaround suggests the call sites may be sync functions that should be made async, or the emit should use `asyncio.ensure_future()` with proper loop handling. Track as a follow-up.

**W2: Missing `service_name` in `emit_service_register_failed` call site**

`registration.py` calls `emit_service_register_failed(owner_wallet, error_code="SERVICE_ID_CONFLICT", reason=str(exc))` without passing `service_name`. The second (active) definition accepts `service_name=""` as optional, so this doesn't break, but the event will lack a `service_name` field for debugging/filtering duplicate service registration conflicts.

**W3: No E2E smoke path for `service_register_failed` and `provider_health_degraded`**

The E2E test file (`test_analytics_e2e_pipeline.py`) covers `service_registered` and `provider_first_revenue_received`. No E2E path exists for the failure/health paths. These are harder to exercise end-to-end and are lower priority, but should be tracked.

---

## 4. Event Coverage Summary

| Event | Emitter | Call Site Wired | Tests |
|-------|---------|----------------|-------|
| `service_registered` | `gateway_events.py` | ✅ `registration.py` | ✅ 4 unit tests |
| `service_register_failed` | `gateway_events.py` | ✅ `registration.py` | ✅ 3 unit tests |
| `provider_first_revenue_received` | `gateway_events.py` | ✅ `forwarding_service.py` | ✅ 4 unit tests |
| `provider_health_degraded` | `gateway_events.py` | ✅ `service_health_probe.py` | ✅ 4 unit tests |

All 4 Phase 1 missing events are implemented and wired.

---

## 5. Verdict

**❌ BLOCKED**

The 4 analytics emitters are correctly implemented, wired to the right call sites, and validated by 19 unit tests that all pass. However:

1. **BLOCK-1** (`gateway_events.py` has 3 pairs of duplicate function definitions) — dead code that will cause maintainability confusion and must be removed.
2. **BLOCK-2** (3 new test regressions in `test_consumer_withdraw_unit.py`) — acceptance criterion requires zero new failures. This is violated.

Both are straightforward fixes (< 1 hour combined). Once resolved and re-verified green, this is ready to merge.

---

## 6. Action Items

| Priority | Blocking | Action |
|----------|----------|--------|
| HIGH | **YES** | **BLOCK-1:** Remove first (dead) definitions of `emit_service_registered`, `emit_service_register_failed`, `emit_provider_health_degraded` from `gateway_events.py` (lines ~322–383) |
| HIGH | **YES** | **BLOCK-2:** Fix 3 new regressions in `test_consumer_withdraw_unit.py::TestConsumerWithdrawBalanceDecrease` — update `InMemoryGatewayStateRepo` mock or isolate analytics emit |
| MED | no | **W1:** Refactor sync analytics emit in `consumer_withdraw_processor.py` and `finance_refund_exec_mixin.py` to use proper async pattern |
| LOW | no | **W2:** Pass `service_name` to `emit_service_register_failed` at call site in `registration.py` |
| LOW | no | **W3:** Add E2E smoke path for `service_register_failed` and `provider_health_degraded` |
