Review complete. Here's the summary:

---

## Review: 埋点实现 — ✅ ACCEPTED

**All 34 tests pass** (17 backend integration + 17 frontend contract).

### P0 Bugs — All Resolved ✅
| Fix | Status |
|-----|--------|
| `analytics.ts` flush sent bare array → now `{events: chunk}` with 50-event chunking | ✅ Fixed |
| `sendBeacon` content-type → now uses `Blob({type: 'application/json'})` | ✅ Fixed |
| `env` missing from gateway events → now injected via `os.getenv()` | ✅ Fixed |
| Analytics infra docker-compose missing → now exists in both `infra/docker/local/` and `services/gateway/infra/analytics/` | ✅ Fixed |

### What's Working Well
- Clean `AnalyticsBackend` abstraction (Kafka → File fallback, no event loss)
- Privacy: SHA-256 wallet hashing throughout, router rejects raw `0x` addresses
- Events router has allowlist + batch size limits (1–50)
- `analytics.ts` SDK: UTM persistence, surface detection, auto-flush, memory cap
- `AnalyticsProvider.tsx` wired to wagmi + Next.js routing
- `analytics_health_check.py` — 6 checks, CI-ready exit codes
- Ops doc at `docs/ops/08_Analytics_Pipeline_Operations.md`

### Remaining P1 (pre-launch)
- `provider_first_revenue_received` (distinct from `provider_revenue_received`, needs `time_since_listing_ms`)
- `invoke_started` (needed for `quote_to_invoke_start_rate` metric)
- `credential_created`

### P2 (post-launch)
- Provider service analytics module, SDK telemetry, GA4 integration