---
id: analytics-pipeline-architecture
title: Synapse Analytics Pipeline — Server-Side Architecture Design
role: cro_optimizer
status: draft
created_at: 2026-04-09
updated_at: 2026-04-09
author: cro_optimizer_agent
target_repo: Synapse-Network
---

# Synapse Analytics Pipeline — Server-Side Architecture Design

## 1. 架构总览

```
┌─────────────────┐     ┌───────────────┐     ┌─────────────┐
│  user-front      │────▶│  Gateway API   │────▶│   Kafka      │
│  (Next.js)       │     │  (FastAPI)     │     │  (Events     │
│                  │     │                │     │   Topic)     │
│  lib/analytics.ts│     │  analytics/    │     └──────┬──────┘
│       │          │     │  emitter.py    │            │
│       ▼          │     └───────────────┘            ▼
│  POST /events    │     ┌───────────────┐     ┌─────────────┐
│  (batch)         │     │ provider_svc   │────▶│  ClickHouse  │
│                  │     │ (FastAPI)      │     │  (Analytics  │
└─────────────────┘     └───────────────┘     │   Storage)   │
                                               └──────┬──────┘
┌─────────────────┐                                   │
│  SDK (Python)    │──── Kafka (same topic) ──────────┘
│  telemetry.py    │                                   │
└─────────────────┘                                   ▼
                                               ┌─────────────┐
                                               │  PostHog     │
                                               │  (Dashboards │
                                               │   + Funnels) │
                                               └─────────────┘
```

### 数据流

1. **前端 → Gateway**: 前端 `lib/analytics.ts` 将事件通过 `POST /api/v1/events` 批量提交到 Gateway。
2. **Gateway 内部事件**: Gateway 业务逻辑（invoke、deposit、settlement）在处理完成后，直接写入 Kafka。
3. **Provider Service 事件**: 服务注册、secret 创建等，同样写入 Kafka。
4. **SDK 事件**: Python SDK 的 `service_search_executed`、`invoke_started` 通过内置 telemetry 模块异步写入 Kafka。
5. **Kafka → ClickHouse**: Kafka Consumer (或 ClickHouse Kafka Engine) 实时消费事件写入 ClickHouse。
6. **ClickHouse → PostHog**: PostHog 配置为从 ClickHouse 读取自定义事件（PostHog 自身底层就是 ClickHouse），或通过 PostHog Capture API 二次写入。

---

## 2. 为什么选 Kafka + ClickHouse

### 2.1 Kafka（消息中间件）

| 考量 | 结论 |
|------|------|
| **解耦** | 事件生产者（Gateway/Frontend/SDK）与消费者（ClickHouse/PostHog）完全解耦。Gateway 不因分析系统故障而阻塞交易。 |
| **削峰填谷** | M2M 调用场景下，agent 并发可以瞬间产生大量 invoke 事件。Kafka 天然缓冲。 |
| **多消费者** | 同一事件可以被 ClickHouse、PostHog、告警系统、实时仪表盘同时消费。 |
| **重放能力** | 数据修复或新增消费者时可以重放历史事件。 |
| **成本** | 自托管 KRaft 模式无需 ZooKeeper，3 节点即可。云托管可用 Confluent Cloud / AWS MSK Serverless。 |

**替代方案对比：**

| 方案 | 问题 |
|------|------|
| 直接写 ClickHouse | Gateway 与分析系统耦合，写入失败影响主流程 |
| Redis Streams | 持久化和多消费者能力弱，不适合分析级数据 |
| RabbitMQ | 吞吐量不如 Kafka，不支持 consumer group 重平衡 |
| 直接写 PostHog API | 单点依赖，无法缓冲高并发，无重放能力 |

### 2.2 ClickHouse（分析存储）

| 考量 | 结论 |
|------|------|
| **列式存储** | 漏斗分析、聚合查询（COUNT/SUM/GROUP BY）性能远超行式数据库。 |
| **压缩比** | 事件数据大量重复字段（event_name, surface, role），列式压缩比可达 10:1。 |
| **实时写入** | 支持从 Kafka 直接消费写入（Kafka Table Engine），零额外开发。 |
| **查询兼容** | 标准 SQL 语法，学习成本低。PostHog 底层就是 ClickHouse。 |
| **成本** | 开源免费。云托管可用 ClickHouse Cloud（按查询量计费）。 |

**替代方案对比：**

| 方案 | 问题 |
|------|------|
| PostgreSQL | 行式存储，大量事件聚合查询慢，需要额外 OLAP 层 |
| TimescaleDB | 比裸 PG 好，但列式性能仍不如 ClickHouse |
| BigQuery | 成本高，延迟高，不适合实时仪表盘 |
| Druid | 运维复杂度远高于 ClickHouse |

---

## 3. Kafka Topic 设计

### 3.1 单一主题 + 分区键

```
Topic: synapse.analytics.events
  Partitions: 12 (可扩展)
  Replication Factor: 3
  Retention: 30 days
  Partition Key: sha256(distinct_id)[:8]  -- 保证同一用户事件有序
```

**为什么不按 event_name 分多 topic：**
- 事件总数 < 50 种，不需要按类型隔离。
- 单 topic 简化 consumer 管理。
- ClickHouse Kafka Engine 一次配置即可消费所有事件。

### 3.2 消息格式 (JSON)

```json
{
  "event_id": "uuid-v4",
  "event_name": "invoke_completed",
  "timestamp": "2026-04-09T15:00:00.000Z",
  "distinct_id": "sha256_wallet_hash",
  "source": "gateway",
  "properties": {
    "role": "consumer",
    "surface": "gateway_api",
    "env": "prod",
    "chain_id": 42161,
    "service_id": "svc_abc123",
    "provider_id": "0xdef456...",
    "quote_id": "q_789",
    "price_usdc": 0.05,
    "latency_ms": 342,
    "is_first_invoke": true,
    "session_id": "sess_xyz",
    "correlation_id": "corr_123"
  }
}
```

### 3.3 Dead Letter Topic

```
Topic: synapse.analytics.events.dlq
  Partitions: 3
  Retention: 90 days
```

消费失败（schema 验证不过、ClickHouse 写入异常）的事件进 DLQ，不丢弃。

---

## 4. ClickHouse Schema 设计

### 4.1 主事件表

```sql
CREATE TABLE synapse_analytics.events
(
    event_id       UUID,
    event_name     LowCardinality(String),
    timestamp      DateTime64(3, 'UTC'),
    distinct_id    String,
    source         LowCardinality(String),  -- 'frontend' | 'gateway' | 'provider_service' | 'sdk'

    -- Common properties (提频字段列式提升)
    role           LowCardinality(String) DEFAULT '',
    surface        LowCardinality(String) DEFAULT '',
    env            LowCardinality(String) DEFAULT 'prod',
    chain_id       UInt32 DEFAULT 0,
    session_id     String DEFAULT '',
    page_path      String DEFAULT '',
    correlation_id String DEFAULT '',

    -- UTM
    utm_source     LowCardinality(String) DEFAULT '',
    utm_medium     LowCardinality(String) DEFAULT '',
    utm_campaign   String DEFAULT '',
    utm_content    String DEFAULT '',

    -- Flexible properties (低频 / 业务专属)
    properties     String DEFAULT '{}'  -- JSON string, 用 JSONExtract* 查询
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (event_name, distinct_id, timestamp)
TTL timestamp + INTERVAL 365 DAY
SETTINGS index_granularity = 8192;
```

### 4.2 Kafka Engine 表（自动消费）

```sql
CREATE TABLE synapse_analytics.events_kafka
(
    raw String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'synapse.analytics.events',
    kafka_group_name = 'clickhouse_analytics_consumer',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 3;
```

### 4.3 Materialized View（Kafka → events）

```sql
CREATE MATERIALIZED VIEW synapse_analytics.events_kafka_mv
TO synapse_analytics.events AS
SELECT
    JSONExtractString(raw, 'event_id')                           AS event_id,
    JSONExtractString(raw, 'event_name')                         AS event_name,
    parseDateTimeBestEffort(JSONExtractString(raw, 'timestamp')) AS timestamp,
    JSONExtractString(raw, 'distinct_id')                        AS distinct_id,
    JSONExtractString(raw, 'source')                             AS source,
    JSONExtractString(raw, 'properties', 'role')                 AS role,
    JSONExtractString(raw, 'properties', 'surface')              AS surface,
    JSONExtractString(raw, 'properties', 'env')                  AS env,
    JSONExtractUInt(raw,   'properties', 'chain_id')             AS chain_id,
    JSONExtractString(raw, 'properties', 'session_id')           AS session_id,
    JSONExtractString(raw, 'properties', 'page_path')            AS page_path,
    JSONExtractString(raw, 'properties', 'correlation_id')       AS correlation_id,
    JSONExtractString(raw, 'properties', 'utm_source')           AS utm_source,
    JSONExtractString(raw, 'properties', 'utm_medium')           AS utm_medium,
    JSONExtractString(raw, 'properties', 'utm_campaign')         AS utm_campaign,
    JSONExtractString(raw, 'properties', 'utm_content')          AS utm_content,
    JSONExtractRaw(raw,    'properties')                         AS properties
FROM synapse_analytics.events_kafka;
```

### 4.4 常用查询示例

**Consumer 激活漏斗：**

```sql
SELECT
    event_name,
    uniqExact(distinct_id) AS users
FROM synapse_analytics.events
WHERE event_name IN (
    'page_viewed', 'wallet_connected', 'consumer_signup_completed',
    'deposit_completed', 'credential_created', 'invoke_completed'
)
AND timestamp >= today() - 7
AND env = 'prod'
GROUP BY event_name
ORDER BY users DESC;
```

**每日 GMV：**

```sql
SELECT
    toDate(timestamp) AS day,
    sum(JSONExtractFloat(properties, 'price_usdc')) AS gmv_usdc,
    count() AS invoke_count
FROM synapse_analytics.events
WHERE event_name = 'invoke_completed'
AND env = 'prod'
AND timestamp >= today() - 30
GROUP BY day
ORDER BY day;
```

---

## 5. PostHog 集成策略

### 选项 A：PostHog 直连 ClickHouse（推荐）

PostHog 自身底层是 ClickHouse。如果使用 self-hosted PostHog，可以直接让 PostHog 读取 `synapse_analytics.events` 作为 external data source。这样 PostHog 的 Funnel、Retention、Session Replay 全部可用，不需要双写。

### 选项 B：Kafka Consumer → PostHog Capture API

如果使用 PostHog Cloud，部署一个轻量 consumer 将事件转发到 PostHog Capture API：

```python
# analytics_consumer/posthog_forwarder.py
import posthog
from kafka import KafkaConsumer
import json

posthog.project_api_key = 'phc_xxx'
posthog.host = 'https://us.i.posthog.com'

consumer = KafkaConsumer(
    'synapse.analytics.events',
    bootstrap_servers='kafka:9092',
    group_id='posthog_forwarder',
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

for msg in consumer:
    evt = msg.value
    posthog.capture(
        distinct_id=evt['distinct_id'],
        event=evt['event_name'],
        properties=evt.get('properties', {}),
        timestamp=evt.get('timestamp'),
    )
```

### GA4 归因

GA4 只用于前端页面级流量归因。通过 `gtag.js` 自动采集 `page_view`，不需要经过 Kafka。GA4 数据不进 ClickHouse，两套系统独立运行。

---

## 6. 基础设施部署建议

### 开发环境 (docker-compose)

```yaml
version: '3.8'
services:
  kafka:
    image: bitnami/kafka:3.7
    ports: ["9092:9092"]
    environment:
      KAFKA_CFG_NODE_ID: 0
      KAFKA_CFG_PROCESS_ROLES: controller,broker
      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE: "true"

  clickhouse:
    image: clickhouse/clickhouse-server:24.3
    ports: ["8123:8123", "9000:9000"]
    volumes:
      - ./clickhouse/init.sql:/docker-entrypoint-initdb.d/init.sql

  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports: ["8080:8080"]
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
```

### 生产环境建议

| 组件 | 推荐 | 备选 |
|------|------|------|
| Kafka | Confluent Cloud / AWS MSK Serverless | Self-hosted KRaft 3-node |
| ClickHouse | ClickHouse Cloud | Self-hosted 2-shard + 2-replica |
| PostHog | PostHog Cloud | Self-hosted (Helm chart) |

---

## 7. 安全与隐私

1. **Kafka TLS**: 生产环境必须启用 SASL_SSL。
2. **ClickHouse 访问控制**: 分析查询用只读账户，Kafka consumer 用写入账户。
3. **PII 处理**: 钱包地址在写入 Kafka 前 `sha256` 哈希。不传原始地址。
4. **数据保留**: ClickHouse TTL 365 天，Kafka retention 30 天。
5. **网络隔离**: Kafka 和 ClickHouse 不暴露公网，通过 VPC peering 或 internal LB 访问。
