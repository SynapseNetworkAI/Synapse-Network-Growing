Review report created at `roles/dev_rel/outputs/review-analytics-tracking-plan.md`.

## Summary

**Verdict: ✅ ACCEPT with 8 Required Fixes**

The analytics design is production-grade and maps accurately to the real Synapse codebase. Key findings:

### Architecture (Kafka + ClickHouse)
- ✅ Correct choice for M2M micropayment scale
- 🔧 Fix: ClickHouse needs `ReplacingMergeTree` for dedup (B3)
- 🔧 Fix: Document consumer group isolation (B4)

### Backend Emitter
- ✅ Clean Strategy pattern, DualBackend ensures zero event loss
- 🔧 Fix: Race condition in `KafkaBackend._ensure_producer()` — needs `asyncio.Lock` (B5)
- 🔧 Fix: `aiokafka` missing from requirements.txt (B6)
- 🔧 Fix: Hardcoded event whitelist → config-driven (B7)

### Frontend SDK
- ✅ Batch+timer flush, `sendBeacon`, UTM persistence all correct
- 🔧 Fix: `uuid` package missing — use native `crypto.randomUUID()` instead (B8)

### Testing Plan
- ✅ 4-layer pyramid with full coverage matrix, CI path-scoped
- 💡 Recommend: Add schema contract test, replace `sleep(10)` with polling

All 8 blockers are surgical fixes (~80 min total). No architectural rework needed.