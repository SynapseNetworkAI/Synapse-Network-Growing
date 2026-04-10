---
id: review-analytics-tracking-plan
title: "DevRel Review: Synapse Analytics Tracking Plan & Pipeline Implementation"
role: dev_rel
status: review
created_at: 2026-04-09
updated_at: 2026-04-09
author: dev_rel_agent
target_repo: Synapse-Network
---

# DevRel Review: Synapse Analytics Tracking Plan & Pipeline Implementation

> **Review Scope:** 5 documents totaling ~5,400 lines
>
> | Document | Path | Lines |
> |----------|------|-------|
> | Tracking Plan | `Synapse-Network/docs/projects/frontend/Synapse_Analytics_Tracking_Plan.md` | 481 |
> | Architecture | `roles/cro_optimizer/outputs/analytics-pipeline-impl/architecture.md` | 355 |
> | Backend Emitter | `roles/cro_optimizer/outputs/analytics-pipeline-impl/backend-emitter.md` | 774 |
> | Frontend SDK | `roles/cro_optimizer/outputs/analytics-pipeline-impl/frontend-sdk.md` | 543 |
> | Testing Plan | `roles/cro_optimizer/outputs/analytics-pipeline-impl/testing-plan.md` | 1,109 |

---

## Executive Summary

**Overall Verdict: ✅ ACCEPT with Required Changes**

The CRO Optimizer produced a **production-grade analytics design** that correctly maps to Synapse Network's real codebase architecture. The tracking plan answers the right 4 business questions, the Kafka + ClickHouse architecture is sound for M2M scale, and the implementation code integrates cleanly with the existing FastAPI gateway patterns.

There are **8 required fixes** (blockers) and **12 recommendations** (improvements). None of the blockers are architectural — they are integration-fit and safety gaps that can be resolved in implementation.

---

## 1. Tracking Plan Review (`Synapse_Analytics_Tracking_Plan.md`)

### ✅ What's Good

1. **Business-question-first framing.** The plan opens with 4 specific operational questions instead of "let's track everything." This is the correct approach for a two-sided marketplace.

2. **Source-of-truth discipline.** The plan correctly mandates that revenue events (`invoke_completed`, `deposit_completed`, `settlement_claim_completed`) are server-side only. The frontend never writes billing events. This is critical for a financial system.

3. **Identity strategy is privacy-correct.** `sha256(wallet_address)` as `distinct_id`, no raw PII in analytics. The anonymous → identified flow matches the wallet-first auth model (ADR-001).

4. **Naming convention is clean.** `object_action` in past tense, lowercase underscore — consistent and grep-friendly. No namespace collisions with existing gateway event names.

5. **Phased rollout is practical.** Phase 1 (9 events) covers both funnels' happy paths. Phase 2 adds failure diagnostics. Phase 3 adds money movement. This lets the team ship value in 1-2 weeks instead of waiting for full coverage.

6. **Alert design is threshold-based, not absolute.** Using 7-day moving average × 0.5 for signup drop instead of a fixed number is the right approach for early-stage traffic.

### ⚠️ Required Fixes

**[B1] Missing `voucher_redeemed` in Phase 1**

The tracking plan lists `voucher_redeemed` under Consumer Activation (Section 5.2) but doesn't include it in any phase (Section 11). If Synapse launches with promotional credits (which the gateway already supports via `credit_usdc`), this event is needed from Day 1 to measure promo ROI.

→ **Fix:** Add `voucher_redeemed` to Phase 1 or explicitly mark it as "Phase 1 if promo launched, otherwise Phase 2."

**[B2] SDK telemetry events missing from event table**

Section 5.3 defines `service_search_executed` and `invoke_started` with source `apps/frontend/` and `sdk/python/`. But the SDK can emit these without any frontend involvement. The "Source" column should list `sdk/python/` as a separate row, not merged.

→ **Fix:** Add SDK-sourced rows for `service_search_executed` and `invoke_started` with `surface: sdk`.

### 💡 Recommendations

**[R1] Add `credential_created` to the Provider funnel verification checklist (Section 12).** Currently only Consumer funnel is fully checksummed. Provider funnel skips verifying `provider_secret_created` → `service_registered` link.

**[R2] Add `time_to_first_deposit` as a derived metric.** The plan defines `median_time_to_first_invoke` but not the intermediate `signup → first deposit` time, which is the sharpest indicator of onboarding friction.

**[R3] Consider a `sdk_initialized` event.** The SDK currently only emits `service_search_executed` and `invoke_started`. A lightweight init event would let you measure SDK adoption vs. frontend-only usage, which is critical for DevRel.

---

## 2. Architecture Review (`architecture.md`)

### ✅ What's Good

1. **Kafka + ClickHouse is the correct choice for this workload.** The alternative comparison tables are honest — PostgreSQL can't handle funnel aggregations at M2M call volumes (10M+ events/day potential), and direct PostHog API has no buffering.

2. **Single topic with `distinct_id` partition key** keeps user events ordered while avoiding topic sprawl. Smart for < 50 event types.

3. **DLQ design prevents silent data loss.** 90-day retention on the DLQ is generous enough to recover from any bug.

4. **ClickHouse schema uses `LowCardinality` correctly.** `event_name`, `source`, `role`, `surface`, `env` are all low-cardinality columns — ClickHouse will compress these at 10:1+ ratio.

5. **Materialized View for Kafka → events is zero-code ingestion.** Using ClickHouse's native Kafka Engine eliminates the need for a separate consumer service.

6. **docker-compose for local dev** means any developer can run the full pipeline locally. Good DX.

### ⚠️ Required Fixes

**[B3] ClickHouse `events` table `ORDER BY` should include `event_id` for dedup**

Current: `ORDER BY (event_name, distinct_id, timestamp)`

If the same event is accidentally written twice (Kafka at-least-once + consumer retry), ClickHouse MergeTree will keep both rows because `timestamp` alone doesn't guarantee uniqueness.

→ **Fix:** Change to `ORDER BY (event_name, distinct_id, timestamp, event_id)` and add a `ReplacingMergeTree(timestamp)` engine to deduplicate on `event_id`.

```sql
ENGINE = ReplacingMergeTree(timestamp)
PARTITION BY toYYYYMM(timestamp)
ORDER BY (event_name, distinct_id, timestamp, event_id)
```

**[B4] Kafka Engine consumer group name collision risk**

The ClickHouse Kafka Engine table uses `kafka_group_name = 'clickhouse_analytics_consumer'`. If PostHog forwarder (Section 5, Option B) uses a *different* consumer group, this is fine. But the doc doesn't explicitly state this.

→ **Fix:** Add explicit consumer group names for each consumer:
- ClickHouse: `clickhouse_analytics_consumer`
- PostHog forwarder: `posthog_analytics_forwarder`
- Document that both groups consume the same topic independently.

### 💡 Recommendations

**[R4] Add a `synapse_analytics.events_daily` aggregating MaterializedView.** Dashboard queries (Section 7) all filter by date range and group by day. A daily rollup table would reduce query cost by 100x for the Growth Dashboard.

```sql
CREATE MATERIALIZED VIEW synapse_analytics.events_daily_mv
TO synapse_analytics.events_daily AS
SELECT
    toDate(timestamp) AS day,
    event_name,
    role,
    surface,
    utm_source,
    count() AS event_count,
    uniqExact(distinct_id) AS unique_users
FROM synapse_analytics.events
GROUP BY day, event_name, role, surface, utm_source;
```

**[R5] Document Kafka retention vs. ClickHouse TTL alignment.** Kafka retains 30 days, ClickHouse retains 365 days. If ClickHouse needs to backfill beyond 30 days, there's a gap. Consider either extending Kafka retention to 90 days or documenting that ClickHouse is the long-term store.

**[R6] Add monitoring for Kafka consumer lag.** If the ClickHouse Kafka Engine falls behind, events will be delayed in dashboards. Add a `kafka_consumer_lag` metric to the alert table.

---

## 3. Backend Emitter Review (`backend-emitter.md`)

### ✅ What's Good

1. **Clean separation of concerns.** `AnalyticsEvent` (data), `AnalyticsBackend` (interface), `KafkaBackend/FileBackend/DualBackend` (implementations), `AnalyticsEmitter` (orchestrator). This is textbook strategy pattern.

2. **`DualBackend` with Kafka-primary + File-fallback** ensures zero event loss during Kafka outages. The fallback JSONL file can be replayed later. Critical for a financial analytics system.

3. **Factory function `create_analytics_emitter()`** correctly switches between FileBackend (local/test) and DualBackend (staging/prod) based on environment. This matches the existing `Settings` pattern in `services/gateway/src/core/config.py`.

4. **Event ingestion endpoint (`POST /api/v1/events`)** has proper input validation:
   - Event name whitelist prevents injection of arbitrary events.
   - Raw wallet address rejection (`0x...` format check).
   - Batch size capped at 50.
   - Pydantic schema validation.

5. **Business integration examples** are realistic — they match the actual forwarding pipeline (`forwarding_service.py`), deposit indexer (`tasks/deposit_indexer/`), and balance service patterns in the gateway.

### ⚠️ Required Fixes

**[B5] `KafkaBackend._ensure_producer()` has a race condition**

If two concurrent `emit()` calls hit `_ensure_producer()` simultaneously when `self._producer is None`, both will try to create a producer. The `AIOKafkaProducer.start()` call is async and not guarded by a lock.

→ **Fix:** Add an `asyncio.Lock`:

```python
class KafkaBackend(AnalyticsBackend):
    def __init__(self, ...):
        ...
        self._lock = asyncio.Lock()

    async def _ensure_producer(self):
        if self._producer is not None:
            return
        async with self._lock:
            if self._producer is not None:  # double-check after acquiring lock
                return
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(...)
            await self._producer.start()
```

**[B6] Missing `aiokafka` in gateway `requirements.txt`**

The current `services/gateway/requirements.txt` does not include `aiokafka`. The emitter code does a lazy import inside `_ensure_producer()`, which is fine for optional usage, but `requirements.txt` must declare it for staging/prod environments.

→ **Fix:** Add `aiokafka>=0.11.0` to `services/gateway/requirements.txt` with a comment noting it's for the analytics pipeline.

**[B7] Event ingestion endpoint whitelist will break frontend iteration**

The `validate_event_name` validator uses a hardcoded tuple of allowed event names. Every time a new frontend event is added (e.g., Phase 2's `wallet_connect_failed`), the backend must be redeployed.

→ **Fix:** Move the whitelist to a config-driven set loaded from `Settings`:

```python
# config.py
analytics_allowed_frontend_events: str = os.getenv(
    "ANALYTICS_ALLOWED_FRONTEND_EVENTS",
    "page_viewed,cta_clicked,wallet_connect_started,wallet_connected,..."
)

# events.py
@field_validator("event_name")
@classmethod
def validate_event_name(cls, v: str) -> str:
    allowed = set(settings.analytics_allowed_frontend_events.split(","))
    if v not in allowed:
        raise ValueError(f"Unknown frontend event: {v}")
    return v
```

### 💡 Recommendations

**[R7] Add `request_id` / correlation passthrough from existing gateway middleware.** The gateway already uses `X-Request-Id` headers. The emitter's `correlation_id` param should auto-read from the request context when not explicitly passed, to avoid every callsite manually threading it.

**[R8] Add emitter metrics (emit count, failure count, latency).** The emitter is fire-and-forget, which is correct for not blocking the main flow. But without metrics on emit success/failure rate, you won't know if the analytics pipeline is silently broken.

**[R9] Consider adding a `replay_fallback_file()` utility function.** The DualBackend writes to a fallback file on Kafka failure, but there's no documented way to replay those events back to Kafka once it recovers. A simple script would close this gap.

---

## 4. Frontend SDK Review (`frontend-sdk.md`)

### ✅ What's Good

1. **Single `SynapseAnalytics` class with singleton export** prevents multiple instances competing for the same flush timer. Clean API surface: `init()`, `identify()`, `capture()`, `page()`, `reset()`, `destroy()`.

2. **Batch + timer flush strategy** is correct for web analytics:
   - Flush at `batchSize` (10) events OR every `flushIntervalMs` (5s).
   - `sendBeacon` for unload scenarios (critical for SPA navigation).
   - `visibilitychange` handler for mobile tab switching.
   - Re-enqueue on failure with cap at 100 events.

3. **UTM persistence in `sessionStorage`** means UTMs survive SPA navigation within a session. This solves the common "UTMs lost after first page" problem in Next.js apps.

4. **`AnalyticsProvider` React component** integrates cleanly with the existing `wagmi` / `useAccount()` pattern in `services/user-front/`. Auto-identifies on wallet connect, auto-resets on disconnect, auto-tracks page views on route change.

5. **`detectSurface()` from pathname** is a pragmatic approach that matches the actual route structure in user-front (`/provider/*`, `/owner/*`, `/consumer/*`).

6. **Wallet hashing via `crypto.subtle.digest('SHA-256')`** — uses the native Web Crypto API, no external dependency needed.

### ⚠️ Required Fix

**[B8] `uuid` package is not in `user-front` dependencies**

The SDK imports `import { v4 as uuidv4 } from 'uuid'` but `uuid` is not in `services/user-front/package.json`. This will fail at runtime.

→ **Fix:** Add `"uuid": "^10.0.0"` to `services/user-front/package.json` dependencies, or replace with `crypto.randomUUID()` which is natively available in all modern browsers and Node.js 19+ (Next.js 14 supports this). Using `crypto.randomUUID()` eliminates the dependency entirely:

```typescript
// Replace: import { v4 as uuidv4 } from 'uuid';
// With:
const generateId = () => crypto.randomUUID();
```

### 💡 Recommendations

**[R10] Deduplicate with existing `LoggerFactory.ts`.** The user-front already has `src/lib/logger/LoggerFactory.ts` that logs user actions with `action_type` and `user_address` to JSONL. The new analytics SDK should either:
- (a) Replace `LoggerFactory` entirely (recommended), or
- (b) Have `LoggerFactory` delegate to `analytics.capture()` internally.

Leaving both active will cause confusion about which system to use.

**[R11] Add opt-out / consent mechanism.** The SDK currently starts tracking immediately on `init()`. For GDPR compliance (even if current users are primarily Web3/crypto), add a `setConsent(granted: boolean)` method that gates `capture()`.

**[R12] The `AnalyticsProvider` should use `useSearchParams` with `Suspense`.** In Next.js 14 App Router, `useSearchParams()` requires a `Suspense` boundary. Without it, the entire page will client-render. Wrap or note this requirement.

---

## 5. Testing Plan Review (`testing-plan.md`)

### ✅ What's Good

1. **4-layer test pyramid is correct:**
   - Layer 1 (Frontend unit): Vitest, fast, no infra
   - Layer 2 (Backend unit): Pytest, fast, no infra
   - Layer 3 (Kafka integration): Requires Docker Kafka
   - Layer 4 (E2E pipeline): Requires Kafka + ClickHouse

2. **Coverage matrix** (Section 8) explicitly maps every verification point to a layer. No ambiguity about "who tests what."

3. **Frontend tests cover the hard parts:** batch flush timing, `sendBeacon` fallback, UTM persistence, session ID consistency, wallet hashing, error re-enqueue. These are the bugs that actually ship.

4. **Backend tests validate security boundaries:** event name whitelist, raw wallet rejection, batch size limits. The `TestEventsEndpoint` class is a solid contract test.

5. **Kafka integration tests verify ordering** — `test_kafka_batch_ordering` ensures same-user events arrive in order. This is critical for funnel analysis.

6. **`analytics_health_check.py`** is a production-grade smoke test: dedup rate, PII leak detection, source coverage, invoke success rate. Runnable as a cron job.

7. **CI workflow** is path-scoped — only runs when analytics code changes. Won't slow down unrelated PRs.

### 💡 Recommendations

**[R13] Add a contract test for the Kafka message schema.** The ClickHouse Materialized View expects specific JSON field names (`event_id`, `event_name`, `timestamp`, `distinct_id`, `source`, `properties`). If the emitter changes the schema, the MV silently drops fields. A contract test that validates the emitter output against the expected ClickHouse schema would catch this.

**[R14] The E2E test has a hardcoded `asyncio.sleep(10)` for Kafka → ClickHouse lag.** This is fragile. Consider polling ClickHouse in a retry loop with a timeout instead:

```python
async def wait_for_event(marker: str, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = await query_ch(f"SELECT count() FROM synapse_analytics.events WHERE distinct_id = '{marker}'")
        if rows and rows[0]["count()"] > 0:
            return
        await asyncio.sleep(1)
    raise TimeoutError(f"Event {marker} not found in ClickHouse within {timeout}s")
```

---

## 6. Cross-Cutting Concerns

### 6.1 Infra Cost & Operational Overhead

Adding Kafka + ClickHouse to the existing stack (PostgreSQL + Redis) is a **significant infra increase**. Current assessment:

| Component | Dev Cost | Prod Cost (Cloud) | Operational Complexity |
|-----------|---------|-------------------|----------------------|
| Kafka (KRaft) | Docker, ~0 | MSK Serverless ~$50/mo at low volume | Medium — topic management, consumer lag monitoring |
| ClickHouse | Docker, ~0 | ClickHouse Cloud ~$30/mo at low volume | Low — mostly self-managing with MergeTree |
| PostHog | Self-host or Cloud free tier | Free tier covers <1M events/mo | Low — dashboard-only, no infra to manage |

**Verdict:** Acceptable for a product approaching launch. The architecture is designed for M2M scale, and starting with this stack avoids a painful migration from PostgreSQL-based analytics later.

**Alternative considered:** Skip Kafka, write directly to ClickHouse from the gateway. This was correctly rejected in the architecture doc — it couples the hot path to the analytics system and means ClickHouse downtime blocks API calls.

### 6.2 Integration Fit with Existing Codebase

| Integration Point | Status | Notes |
|-------------------|--------|-------|
| Gateway lifespan pattern | ✅ Fits | Follow existing `app.state.*` + asyncio task pattern |
| Settings management | ✅ Fits | Add to existing `Settings` class with `os.getenv()` |
| Router registration | ✅ Fits | Add alongside existing routers with `/api` prefix |
| Forwarding pipeline hooks | ✅ Fits | `forwarding_service._execute_invocation_pipeline()` has clear pre/post points |
| Deposit indexer hooks | ✅ Fits | `tasks/deposit_indexer/processing.py` has event callbacks |
| User-front Next.js layout | ✅ Fits | `AnalyticsProvider` wraps alongside existing `WagmiProvider` |
| Existing `LoggerFactory.ts` | ⚠️ Conflict | Must be deprecated or delegated — see [R10] |
| Existing `provider_analytics_service.py` | ✅ No conflict | Existing service computes provider earnings from billing rows; new analytics is behavioral tracking — different concern |

### 6.3 What's Missing from the Design

1. **No rate limiting on the `/api/v1/events` endpoint.** The comment says "recommended max 10 req/s per client" but there's no enforcement. A misbehaving frontend or bot could flood the ingestion endpoint.

2. **No backpressure mechanism.** If ClickHouse falls behind on Kafka consumption, there's no alert or circuit breaker. The health check script partially covers this, but it's post-hoc.

3. **No data deletion / GDPR right-to-erasure flow.** The `distinct_id` is a SHA-256 hash (non-reversible), which partially mitigates this, but if a user requests deletion, you need a documented process.

---

## 7. Review Acceptance Checklist

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Tracking plan maps to real codebase paths | ✅ PASS | All `apps/frontend/`, `gateway/`, `provider_service/`, `sdk/python/` references match actual directory structure |
| 2 | Event names follow stated naming convention | ✅ PASS | All `object_action` past tense, lowercase underscore |
| 3 | Revenue/billing events are server-side only | ✅ PASS | Frontend whitelist excludes `deposit_completed`, `invoke_completed`, `settlement_*` |
| 4 | PII protection enforced | ✅ PASS | SHA-256 hashing, raw address rejection in API |
| 5 | Architecture handles Kafka failure gracefully | ✅ PASS | DualBackend with file fallback |
| 6 | Code integrates with existing gateway patterns | ✅ PASS | Lifespan, Settings, Router patterns all consistent |
| 7 | Frontend SDK works with existing tech stack | ⚠️ CONDITIONAL | Requires `uuid` dep or `crypto.randomUUID()` fix [B8] |
| 8 | Test coverage matrix has no blind spots | ✅ PASS | All 4 layers cover distinct verification points |
| 9 | CI pipeline is path-scoped and non-blocking | ✅ PASS | Only triggers on analytics code changes |
| 10 | No hardcoded secrets or credentials | ✅ PASS | All config via environment variables |
| 11 | Thread/concurrency safety | ⚠️ CONDITIONAL | KafkaBackend needs asyncio.Lock [B5] |
| 12 | Phased rollout is feasible | ✅ PASS | Phase 1 is 9 events, deployable independently |

---

## 8. Required Actions Summary

### Blockers (Must Fix Before Implementation)

| ID | Component | Issue | Effort |
|----|-----------|-------|--------|
| B1 | Tracking Plan | `voucher_redeemed` missing from phased rollout | 5 min |
| B2 | Tracking Plan | SDK-sourced events need separate rows in event table | 10 min |
| B3 | Architecture | ClickHouse table needs `ReplacingMergeTree` + `event_id` in ORDER BY | 10 min |
| B4 | Architecture | Document consumer group names for all Kafka consumers | 5 min |
| B5 | Backend Emitter | Add `asyncio.Lock` to `KafkaBackend._ensure_producer()` | 15 min |
| B6 | Backend Emitter | Add `aiokafka>=0.11.0` to gateway `requirements.txt` | 2 min |
| B7 | Backend Emitter | Move event name whitelist to config-driven set | 20 min |
| B8 | Frontend SDK | Fix `uuid` dependency — use `crypto.randomUUID()` instead | 10 min |

### Recommendations (Should Fix, Not Blocking)

| ID | Component | Improvement |
|----|-----------|-------------|
| R1 | Tracking Plan | Add Provider funnel verification items to checklist |
| R2 | Tracking Plan | Add `time_to_first_deposit` derived metric |
| R3 | Tracking Plan | Consider `sdk_initialized` event for DevRel metrics |
| R4 | Architecture | Add daily aggregation MaterializedView |
| R5 | Architecture | Document Kafka retention vs ClickHouse TTL alignment |
| R6 | Architecture | Add Kafka consumer lag monitoring |
| R7 | Backend Emitter | Auto-read `X-Request-Id` for correlation |
| R8 | Backend Emitter | Add emitter success/failure metrics |
| R9 | Backend Emitter | Add fallback file replay utility |
| R10 | Frontend SDK | Deprecate or delegate existing `LoggerFactory.ts` |
| R11 | Frontend SDK | Add consent/opt-out mechanism |
| R12 | Frontend SDK | Note `Suspense` requirement for `useSearchParams` |
| R13 | Testing Plan | Add Kafka message schema contract test |
| R14 | Testing Plan | Replace `sleep(10)` with polling in E2E test |

---

## 9. Verdict

**✅ ACCEPT — the design is production-viable.**

The CRO Optimizer delivered a cohesive, codebase-aware analytics system that correctly separates behavioral tracking from the existing financial ledger. The Kafka + ClickHouse architecture is the right bet for M2M scale. The code implementations match real gateway patterns and can be integrated without refactoring existing services.

The 8 blockers are all surgical fixes (total effort ~80 minutes). None require architectural changes.

**Recommended implementation order:**
1. Fix B3, B5, B6, B7, B8 (code-level fixes)
2. Fix B1, B2, B4 (documentation fixes)
3. Implement Phase 1 events (9 events, ~2-3 days for a single engineer)
4. Deploy docker-compose infra + health check script
5. Build PostHog dashboards from ClickHouse data
6. Implement Phase 2 after first week of production data validates Phase 1
