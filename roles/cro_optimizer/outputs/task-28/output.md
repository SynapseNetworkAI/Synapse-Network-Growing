Done. Delivered 4 files under `roles/cro_optimizer/outputs/analytics-pipeline-impl/`:

| File | Content |
|------|---------|
| **architecture.md** | Kafka + ClickHouse pipeline design — topic schema, ClickHouse table DDL (MergeTree + Kafka Engine + Materialized View), PostHog integration, docker-compose, security |
| **frontend-sdk.md** | `lib/analytics.ts` — batch emitter with sendBeacon fallback, `AnalyticsProvider` React component, UTM persistence, wallet hash, business event examples, GA4 for attribution only |
| **backend-emitter.md** | `AnalyticsEmitter` with Kafka/File/Dual backends, `POST /api/v1/events` endpoint with event whitelist + PII rejection, integration examples for invoke/deposit/settlement/budget, SDK telemetry module |
| **testing-plan.md** | 4-layer strategy: L1 Vitest frontend → L2 pytest backend → L3 Kafka integration → L4 E2E ClickHouse flow; health check script, CI workflow, coverage matrix |

**Key architecture decisions:**
- **Kafka** for decoupling + buffering M2M burst traffic; **ClickHouse** for columnar analytics at scale
- **DualBackend** pattern: Kafka primary + JSONL fallback ensures zero event loss
- Frontend events POSTed to Gateway → Kafka (no direct 3rd-party SDK coupling)
- All wallet addresses SHA-256 hashed before entering the pipeline