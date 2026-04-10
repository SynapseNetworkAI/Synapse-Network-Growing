---
id: analytics-tracking-impl-review
title: "Review: Synapse Analytics Tracking Plan Implementation"
role: dev_rel
status: review
created_at: 2026-04-10
updated_at: 2026-04-10
author: dev_rel_agent
target_repo: Synapse-Network
---

# Review: Synapse Analytics Tracking Plan Implementation

**Reviewer:** DevRel (Staff-Level DX Review)
**Scope:** All analytics code in `Synapse-Network` target project — frontend SDK, backend emitter, gateway events, events router, tests, health check script.
**Design Docs:**
- `docs/projects/frontend/Synapse_Analytics_Tracking_Plan.md`
- `roles/cro_optimizer/outputs/analytics-pipeline-impl/` (architecture, backend-emitter, frontend-sdk, testing-plan)

---

## Executive Summary

The implementation delivers a well-architected analytics pipeline with strong separation of concerns, privacy-first design, and comprehensive test coverage at unit and integration layers. However, **one critical frontend-backend contract mismatch** will cause all frontend events to fail at runtime, and several tracking plan events remain unimplemented.

**Verdict: Conditional Accept — fix the P0 bug before merge; P1/P2 items tracked for follow-up.**

---

## 1. Critical Issues (P0 — Must Fix Before Merge)

### 1.1 Frontend payload format does not match backend contract

| Item | Detail |
|------|--------|
| **File** | `services/user-front/src/lib/analytics.ts` line 274 |
| **Bug** | `flush()` sends `JSON.stringify(batch)` → a bare JSON array `[{event}, ...]` |
| **Expected** | Backend `EventBatchRequest` in `events.py` expects `{"events": [{event}, ...]}` |
| **Impact** | **100% of frontend events will receive HTTP 422** in production. Zero frontend tracking will work. |
| **Root Cause** | The design doc (`frontend-sdk.md`) correctly specifies `JSON.stringify({ events: batch })`, but the implementation omits the wrapper object. |

**Fix (1 line change in `analytics.ts`):**
```typescript
// Line 274: change
const payload = JSON.stringify(batch);
// to
const payload = JSON.stringify({ events: batch });
```

**Why the tests didn't catch it:** The frontend unit tests (`analytics.test.ts`) test the SDK's internal batching and fetch call structure, but they don't validate the body shape against the backend contract. The full-stack tests (`test_analytics_fullstack_unit.py`) manually construct the correct `{"events": [...]}` wrapper — they don't exercise the real frontend `flush()` method.

---

## 2. High Priority Issues (P1 — Should Fix Soon)

### 2.1 Missing `infra/analytics/` directory

The step output and testing plan reference:
- `infra/analytics/docker-compose.yml` (Kafka + ClickHouse + Kafka UI)
- `infra/analytics/clickhouse/init.sql` (ClickHouse schema auto-init)

**Status:** Neither file exists. The `infra/` directory only contains `docker/` and `postgres/`.

**Impact:** Developers cannot spin up the analytics infra locally. E2E tests (`test_analytics_e2e_pipeline.py`) are untestable without manual setup. This blocks DX for any developer who wants to verify the pipeline end-to-end.

**Recommendation:** Create `infra/analytics/docker-compose.yml` and `infra/analytics/clickhouse/init.sql` as described in the architecture design doc.

### 2.2 Missing tracking plan events — Gateway side

The tracking plan (§5.2–5.6) specifies these server-side events that have no implementation in `gateway_events.py`:

| Missing Event | Tracking Plan Section | Expected Source |
|---------------|----------------------|-----------------|
| `provider_first_revenue_received` | §5.5 | `gateway/` |
| `voucher_redeemed` | §5.2 | `gateway/` |
| `credential_created` | §5.2 | `gateway/` + `apps/frontend/` |
| `invoke_started` | §5.3 | `gateway/` |

`provider_first_revenue_received` is distinct from `provider_revenue_received` (which IS implemented) — it's the first-ever revenue event per provider with `time_since_listing_ms`, a critical activation metric.

### 2.3 Missing tracking plan events — Provider Service side

The tracking plan (§9.3) assigns these to `provider_service/`, but no provider-service analytics module exists:

| Missing Event | Expected Source |
|---------------|-----------------|
| `provider_secret_created` | `provider_service/` |
| `service_registered` | `provider_service/` + `gateway/` |
| `service_register_failed` | `provider_service/` |
| `service_status_changed` | `provider_service/` |
| `service_manifest_step_completed` | provider surface |

The design doc (`backend-emitter.md` §6) provides complete code for these, but they were not implemented in the actual provider service.

### 2.4 Missing `env` property in gateway events

The `_emit()` helper in `gateway_events.py` constructs properties with `role` and `surface` but does not inject `env`. The tracking plan (§3.2) lists `env` as a required common property for all events.

**Impact:** All gateway-emitted events will have empty `env` field in ClickHouse, breaking environment-based filtering in dashboards and health checks.

**Fix:** Add `"env": os.getenv("ENVIRONMENT", "local")` to the `props` dict in `_emit()`, or accept it as a parameter.

---

## 3. Medium Priority Issues (P2 — Track for Follow-up)

### 3.1 No SDK telemetry module

The tracking plan (§9.4) and design doc specify `sdk/python/synapse/telemetry.py` for SDK-side events (`service_search_executed`, `invoke_started`). This was not implemented.

**Impact:** Pure SDK users (no frontend) will have zero behavioral tracking. Discovery and invoke-intent metrics for SDK clients are missing.

### 3.2 No GA4 integration in layout

The design doc specifies GA4 `gtag.js` integration in `app/layout.tsx` for traffic attribution (§4 of frontend-sdk.md). Not implemented.

**Impact:** No traffic attribution data from Google Analytics. PostHog can partially cover this, but GA4 was explicitly chosen for acquisition/UTM attribution per the tracking plan (§1).

### 3.3 `sendBeacon` payload format

`sendBeacon` (line 280 in `analytics.ts`) sends the payload as a bare string via `navigator.sendBeacon(endpoint, payload)`. The Gateway expects `Content-Type: application/json`. `sendBeacon` with a string argument sends `text/plain`, which may cause FastAPI/Pydantic to reject the body.

**Recommendation:** Use `new Blob([payload], { type: 'application/json' })` — the design doc (`frontend-sdk.md`) actually specifies this pattern correctly. The implementation omitted it.

### 3.4 ClickHouse schema not deployed

The `architecture.md` defines `CREATE TABLE synapse_analytics.events`, `events_kafka`, and `events_kafka_mv`, but without `infra/analytics/clickhouse/init.sql`, these schemas exist only in documentation. The E2E tests assume they exist.

---

## 4. What's Working Well ✅

### 4.1 Core architecture — solid and well-layered

The emitter abstraction (`AnalyticsBackend` → `KafkaBackend` / `FileBackend` / `DualBackend`) is clean, testable, and follows the design spec faithfully. The `DualBackend` pattern with Kafka-primary + file-fallback ensures zero event loss during Kafka outages.

### 4.2 Privacy implementation — thorough

- `sha256_hash()` correctly normalizes (lowercase + strip) before hashing.
- All `gateway_events.py` functions hash wallet addresses before emission.
- The events router validates that `distinct_id` is not a raw `0x` address.
- Frontend SDK hashes wallet via `crypto.subtle.digest('SHA-256', ...)`.
- Full-stack tests explicitly assert no raw `0x` addresses leak anywhere.

**This exceeds the tracking plan requirement (§4).**

### 4.3 Event naming convention — consistent

All events follow the `object_action` pattern with past-tense verbs (`completed`, `failed`, `requested`), exactly matching the tracking plan (§3.1).

### 4.4 Frontend SDK — well-designed

- Singleton pattern with `init()` / `destroy()` lifecycle.
- Auto-inject common properties (UTM, session_id, surface, role, env).
- UTM persistence across SPA navigation via sessionStorage.
- Surface detection from URL pathname.
- Batch + timer flush with re-enqueue on failure.
- Max queue cap (100) prevents memory leaks.

### 4.5 Test coverage — comprehensive at unit/integration level

| Layer | Tests | Coverage |
|-------|-------|----------|
| Frontend unit (analytics.test.ts) | 8 | Event structure, session consistency, surface detection, UTM, identify/hash, batch behavior, error re-enqueue, page tracking |
| Backend unit (test_analytics_emitter_unit.py) | 8 | Event container, JSON serialization, FileBackend write/append/dirs, emitter emit/batch, privacy hash |
| Gateway events unit (test_gateway_events_unit.py) | 17 | All 12 event functions, noop safety, privacy, error resilience |
| Full-stack unit (test_analytics_fullstack_unit.py) | 12 | Frontend→router→file pipeline, consumer funnel, provider funnel, privacy deep scan |
| Kafka integration | 5 | Round-trip, ordering, multi-user partition, DualBackend fallback, Kafka preference |
| E2E pipeline | 5 | ClickHouse flow, consumer funnel query, provider funnel query, dedup, privacy in storage |

The gating strategy (`ANALYTICS_TEST_KAFKA`, `ANALYTICS_TEST_E2E`) is well-designed — unit tests run everywhere, infra-dependent tests are opt-in.

### 4.6 Gateway events module — correct fire-and-forget pattern

`gateway_events.py` uses module-level emitter reference with `set_emitter()` and wraps all emissions in try/except. Analytics failures cannot crash business logic. The error resilience test explicitly verifies this.

### 4.7 Events router — secure ingestion

- Event name whitelist (`ALLOWED_FRONTEND_EVENTS`) prevents arbitrary event injection.
- Raw wallet address rejection in `distinct_id` validator.
- Batch size limits (1–50) prevent abuse.
- Pydantic validation provides clear error messages.

### 4.8 Health check script — production-ready

`analytics_health_check.py` covers 6 critical checks: event flow, dedup, privacy, source coverage, critical events, invoke success rate. CLI with `--clickhouse-url` flag. Clear pass/fail output with exit codes for CI/cron integration.

---

## 5. Tracking Plan Coverage Matrix

### Phase 1 Events (minimum viable)

| Event | Tracking Plan | Frontend SDK | Backend Emitter | Gateway Events | Tests |
|-------|:-----:|:-----:|:-----:|:-----:|:-----:|
| `page_viewed` | ✅ | ✅ | — | — | ✅ |
| `cta_clicked` | ✅ | ✅ (whitelist) | — | — | ✅ |
| `wallet_connected` | ✅ | ✅ (whitelist) | — | — | ✅ |
| `consumer_signup_completed` | ✅ | ✅ (whitelist) | — | — | ✅ |
| `provider_signup_completed` | ✅ | ✅ (whitelist) | — | — | — |
| `deposit_completed` | ✅ | — | ✅ | ✅ | ✅ |
| `invoke_completed` | ✅ | — | ✅ | ✅ | ✅ |
| `service_registered` | ✅ | — | — | ❌ Missing | — |
| `provider_first_revenue_received` | ✅ | — | — | ❌ Missing | — |

### Phase 2 Events (optimization diagnostics)

| Event | Tracking Plan | Implemented | Tests |
|-------|:-----:|:-----:|:-----:|
| `wallet_connect_failed` | ✅ | ✅ (whitelist) | — |
| `deposit_failed` | ✅ | ✅ | ✅ |
| `invoke_failed` | ✅ | ✅ | ✅ |
| `budget_blocked` | ✅ | ✅ | ✅ |
| `service_register_failed` | ✅ | ❌ Missing | — |
| `provider_health_degraded` | ✅ | ❌ Missing | — |

### Phase 3 Events (revenue quality)

| Event | Tracking Plan | Implemented | Tests |
|-------|:-----:|:-----:|:-----:|
| `provider_revenue_received` | ✅ | ✅ | ✅ |
| `settlement_claim_completed` | ✅ | ✅ | ✅ |
| `withdrawal_completed` | ✅ | ✅ | ✅ |
| `refund_completed` | ✅ | ✅ | ✅ |
| `risk_rule_triggered` | ✅ | ✅ | ✅ |

**Overall coverage: ~75% of tracking plan events implemented with code, ~60% with tests.**

---

## 6. Recommended Action Items

### P0 — Block merge
- [ ] Fix `analytics.ts` `flush()` to send `{ events: batch }` instead of bare array
- [ ] Fix `sendBeacon` to use `Blob` with `application/json` content type
- [ ] Add a contract test (frontend payload → backend router) to prevent future drift

### P1 — Before launch
- [ ] Create `infra/analytics/docker-compose.yml` + `clickhouse/init.sql`
- [ ] Add `env` property to `gateway_events._emit()`
- [ ] Implement `provider_first_revenue_received` in `gateway_events.py`
- [ ] Implement `invoke_started` in `gateway_events.py`
- [ ] Implement `credential_created` in `gateway_events.py`

### P2 — Post-launch sprint
- [ ] Provider service analytics module (`provider_secret_created`, `service_registered`, `service_register_failed`, `service_status_changed`)
- [ ] SDK telemetry module (`sdk/python/synapse/telemetry.py`)
- [ ] GA4 integration in `app/layout.tsx`
- [ ] `voucher_redeemed` event when voucher feature is ready

---

## 7. Review Acceptance Check

| Criteria | Status |
|----------|--------|
| Design docs read and compared | ✅ |
| All implementation files reviewed | ✅ |
| Frontend SDK code reviewed | ✅ |
| Backend emitter code reviewed | ✅ |
| Gateway events module reviewed | ✅ |
| Events router code reviewed | ✅ |
| Privacy implementation reviewed | ✅ |
| Test coverage assessed | ✅ |
| Tracking plan coverage mapped | ✅ |
| Critical bugs identified | ✅ (P0: payload format mismatch) |
| Action items prioritized | ✅ |

**Review status: COMPLETE — Conditional Accept with P0 fix required.**
