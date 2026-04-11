---
id: review-analytics-phase1-missing-events
title: "Code Review: Analytics Phase 1 Missing Events (4 emitters)"
role: dev_rel
status: review
created_at: 2026-04-11
updated_at: 2026-04-11
author: dev_rel_agent
target_repo: Synapse-Network / Synapse-Network-Provider
---

# Code Review: Analytics Phase 1 Missing Events

> **Requirement:** Implement the 4 ❌ Missing events from `review-analytics-tracking-plan.md`:
> `service_registered`, `provider_first_revenue_received`, `service_register_failed`, `provider_health_degraded`

---

## 1. Files Reviewed

| File | Repo | Role |
|------|------|------|
| `services/gateway/src/services/analytics/gateway_events.py` | Synapse-Network | New: `emit_provider_first_revenue_received()` |
| `services/gateway/src/services/analytics/emitter.py` | Synapse-Network | **Not modified** — KafkaBackend race condition remains |
| `app/services/analytics/provider_events.py` | Synapse-Network-Provider | New: `emit_service_registered()`, `emit_service_register_failed()`, `emit_provider_health_degraded()` |
| `app/services/analytics/emitter.py` | Synapse-Network-Provider | New: full `AnalyticsEmitter` + `KafkaBackend` (with `asyncio.Lock`) + `FileBackend` + `DualBackend` + factory |
| `app/services/analytics/privacy.py` | Synapse-Network-Provider | New: `sha256_hash()` |
| `tests/test_provider_analytics.py` | Synapse-Network-Provider | New: 16 unit tests for all 3 new provider emitters |
| `tests/unit/test_analytics_fullstack_unit.py` | Synapse-Network | Extended: `TestProviderFirstRevenueReceived` class (5 new tests) |

---

## 2. Test Results (Executed)

```
Synapse-Network Gateway — all analytics test files
  test_analytics_emitter_unit.py       10 passed
  test_analytics_fullstack_unit.py     27 passed  (+5 for new event)
  test_gateway_events_unit.py          20 passed  (all pre-existing tests regression-free)
  test_events_router_unit.py            6 passed  (all pre-existing tests regression-free)
  Gateway total:                        63 passed

Synapse-Network-Provider — provider analytics tests
  test_provider_analytics.py           16 passed
  Provider total:                       16 passed

Grand total: 79 passed, 0 failed, 0 errors
```

> `test_gateway_events_unit.py` (20 tests) and `test_events_router_unit.py` (6 tests) were both verified
> to pass after gateway_events.py was modified — confirming zero regressions to existing emitters.

---

## 3. Review Findings

### PASS

- P1: All 4 new emitters use correct snake_case event names matching the tracking plan exactly
- P2: All emitters hash `provider_address` via `sha256_hash()` as `distinct_id` — no raw `0x...` addresses leak
- P3: `emit_provider_health_degraded` double-hashes: both `distinct_id` and `properties.provider_id` are hashed
- P4: `emit_provider_first_revenue_received` marks `is_first_revenue: True`; `time_since_listing_ms` is omitted entirely when `None` (not null-serialized)
- P5: Provider `KafkaBackend._ensure_producer()` uses `asyncio.Lock` — concurrent initialization race condition fixed for new code
- P6: `role: "provider"` is hard-coded in Provider `_emit()` default and injected into every event's properties dict
- P7: `env: os.getenv("ENVIRONMENT", "local")` is injected into every provider event, matching the gateway pattern (provider_events.py line 62)
- P8: All emitters are fire-and-forget: silent no-op when `_emitter is None`, exceptions caught/logged, never re-raised
- P9: `DualBackend` (Provider) falls back to `FileBackend` on Kafka failure — events are never silently dropped
- P10: `privacy.py` normalizes input (`.strip().lower()`) before hashing — `0xABC` and `0xabc` produce the same digest
- P11: `_reset_emitter` autouse fixture provides correct test isolation
- P12: All 3 Provider test classes verify: event name, required properties, PII hashing, no-op when emitter is None
- P13: `manifest_version` defaults to `"1"` in `emit_service_registered()` — backward-compatible
- P14: All pre-existing gateway event tests pass with zero regressions (20 + 6 tests confirmed)

---

### BLOCK — Must Fix Before Merge

**BLOCK-1: Gateway `KafkaBackend._ensure_producer()` has no `asyncio.Lock`**

The Provider's new `emitter.py` correctly fixes the B5 race condition with `asyncio.Lock`. The Gateway's `emitter.py` — which handles all production-volume financial events — was **not updated** with the same fix.

```python
# gateway/src/services/analytics/emitter.py  lines 123-136 — UNFIXED
async def _ensure_producer(self):
    if self._producer is None:           # race: two concurrent awaits both see None,
        from aiokafka import AIOKafkaProducer  #   creating duplicate producers and
        self._producer = AIOKafkaProducer(...)  #  duplicate event delivery
        await self._producer.start()
```

```python
# provider/app/services/analytics/emitter.py — CORRECT fix already applied
async def _ensure_producer(self):
    import asyncio
    if self._lock is None:
        self._lock = asyncio.Lock()
    async with self._lock:
        if self._producer is None:
            ...
```

For financial analytics events (`invoke_completed`, `deposit_completed`, `settlement_claim_completed`), duplicate delivery can cause double-counting in billing dashboards.

**Required fix:** Port the `asyncio.Lock` pattern to `services/gateway/src/services/analytics/emitter.py`.

---

### WARN — Non-Blocking, Should Fix in Follow-up

**W1: New Provider emitters not yet wired to business logic**

All three provider emitters exist only in the analytics package — no service registration handler or health monitor calls them. Events will not fire in production.

```bash
grep -rn "emit_service_registered\|emit_service_register_failed\|emit_provider_health_degraded" \
  Synapse-Network-Provider/app/ | grep -v "analytics/"
# → (no output)
```

**W2: `emit_provider_first_revenue_received` not wired to Gateway settlement path**

The emitter is implemented and tested but no invoice settlement code checks the first-revenue condition and calls it. Docstring correctly warns callers are responsible, but no call-site exists yet.

**W3: New gateway function tests placed in wrong file**

`TestProviderFirstRevenueReceived` (5 tests) was added to `test_analytics_fullstack_unit.py`. The established pattern: every gateway event helper has its unit tests in `test_gateway_events_unit.py`. The 13th helper (`emit_provider_first_revenue_received`) is the only exception.

**W4: Provider `emitter.py` duplicates Gateway `emitter.py`**

This is intentional (no cross-repo import). But this PR is a live example of the risk: the `asyncio.Lock` fix was applied to one copy and missed in the other.

---

## 4. Phase 1 Event Coverage

| Event Name | Emitter File | Status |
|-----------|-------------|--------|
| `wallet_connected` | frontend SDK | existing |
| `consumer_signup_completed` | frontend SDK | existing |
| `deposit_completed` | `gateway_events.py` | existing |
| `invoke_completed` | `gateway_events.py` | existing |
| `invoke_failed` | `gateway_events.py` | existing |
| `service_registered` | `provider_events.py` | **newly implemented** |
| `service_register_failed` | `provider_events.py` | **newly implemented** |
| `provider_first_revenue_received` | `gateway_events.py` | **newly implemented** |
| `provider_health_degraded` | `provider_events.py` | **newly implemented** |

**Phase 1: 9/9 events implemented.**

---

## 5. Verdict

**BLOCKED**

79/79 tests pass with zero regressions. The 4 new emitters are structurally correct: proper event names, PII hashing, `role`/`env` injection, fire-and-forget error handling, and isolated tests.

One blocking issue: the `asyncio.Lock` fix (original blocker B5) was applied only to the new Provider `KafkaBackend` but not back-ported to the Gateway `KafkaBackend`, which handles all production financial events. This is a 10-minute fix.

---

## 6. Action Items

| Priority | Blocking | Action | Owner |
|----------|----------|--------|-------|
| HIGH | YES | **BLOCK-1:** Add `asyncio.Lock` to Gateway `KafkaBackend._ensure_producer()` in `services/gateway/src/services/analytics/emitter.py` | gateway team |
| MED | no | **W1:** Wire `emit_service_registered` / `emit_service_register_failed` into Provider registration handler | provider team |
| MED | no | **W2:** Wire `emit_provider_first_revenue_received` into Gateway invoice settlement path | gateway team |
| LOW | no | **W3:** Move `TestProviderFirstRevenueReceived` tests to `test_gateway_events_unit.py` | gateway team |
| LOW | no | **W4:** Add sync comment to both `emitter.py` copies; open ticket for `synapse-analytics-core` shared package | platform team |
