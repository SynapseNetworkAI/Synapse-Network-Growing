Done. Here's what was implemented:

## Phase 1 Analytics — 4 Missing Events Implemented

**43 tests pass (27 gateway + 16 provider), 0 failures.**

### What was added

**Synapse-Network / Gateway** — `gateway_events.py`:
- `emit_provider_first_revenue_received()` — fires once when a provider receives their first payment; properties include `is_first_revenue: True`, hashed `provider_id`, `gross_usdc`, optional `time_since_listing_ms`

**Synapse-Network-Provider** — new `app/services/analytics/` package:
- `emitter.py` — full `AnalyticsEmitter` + `FileBackend` + `KafkaBackend` (with `asyncio.Lock`, fixing review blocker B5) + `DualBackend` factory
- `privacy.py` — `sha256_hash()` utility
- `provider_events.py` — typed emitter helpers:
  - `emit_service_registered()` — Provider funnel activation milestone
  - `emit_service_register_failed()` — onboarding friction diagnostic
  - `emit_provider_health_degraded()` — circuit-breaker health alert with hashed `provider_id`

**New test file** `tests/test_provider_analytics.py` — 16 tests covering all 3 new provider emitters (event name, properties, privacy/hashing, no-op safety, funnel sequence).

Phase 1 now has all 9 required events implemented across both services.