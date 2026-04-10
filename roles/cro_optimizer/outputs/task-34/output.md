All **24 tests pass** (8 frontend + 16 backend). Here's what was implemented:

### Frontend (`services/user-front/src/`)
| File | Purpose |
|---|---|
| `lib/analytics.ts` | Core SDK — `capture()`, `identify()`, `page()`, batch flush, UTM persistence, SHA-256 wallet hashing |
| `lib/analytics-provider.tsx` | React provider — auto page_viewed on route change, auto identify on wallet connect |
| `lib/__tests__/analytics.test.ts` | 8 vitest tests covering event structure, session, UTM, identity, batching, error handling |

### Backend (`services/gateway/`)
| File | Purpose |
|---|---|
| `src/services/analytics/emitter.py` | `AnalyticsEvent`, `FileBackend`, `KafkaBackend`, `DualBackend`, factory |
| `src/services/analytics/privacy.py` | `sha256_hash()` for PII protection |
| `src/api/routers/events.py` | `POST /api/v1/events` — whitelist validation, raw-wallet rejection, batch limits |
| `src/core/config.py` | +3 analytics config fields |
| `src/app.py` | Emitter init in lifespan + events router registration |
| `tests/unit/test_analytics_emitter_unit.py` | 10 tests for emitter, backends, privacy |
| `tests/unit/test_events_router_unit.py` | 6 tests for endpoint validation |

Pre-existing test failures in the gateway (missing venv deps) and 4 frontend tests (React DOM issues) are **not caused by these changes**.