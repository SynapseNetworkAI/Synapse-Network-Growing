Done. Here's what was implemented:

## Backend Analytics Implementation ✅

All 48 existing analytics unit tests pass unchanged.

### Files Changed/Created

**1. `infra/docker/local/docker-compose.yml`** — Added 3 new services:
- `kafka` (bitnami/kafka:3.7, KRaft mode, no ZooKeeper, port 9092)
- `kafka-ui` (provectuslabs/kafka-ui, port 8080, depends on kafka health)  
- `clickhouse` (clickhouse-server:24.3, HTTP port 8123, native 9100 to avoid minio collision)

**2. `infra/clickhouse/init/01_analytics_schema.sql`** — Auto-executed on first boot:
- `synapse_analytics.events` — MergeTree table, partitioned by month, TTL 365 days
- `synapse_analytics.events_kafka` — Kafka Engine consumer table
- `synapse_analytics.events_kafka_mv` — Materialized View to wire Kafka → events automatically

**3. `services/gateway/requirements.txt`** — Added `aiokafka>=0.11.0` (required by `KafkaBackend`)

**4. `docs/ops/08_Analytics_Pipeline_Operations.md`** — Full ops runbook:
- Startup commands, health verification, E2E curl tests
- ClickHouse funnel/GMV/error-code queries
- Alert thresholds table
- Data retention policy
- Production upgrade path

The backend analytics code (emitter, gateway_events, events router, privacy hashing) was already fully implemented and wired into the forwarding, deposit, and withdrawal services in prior commits.