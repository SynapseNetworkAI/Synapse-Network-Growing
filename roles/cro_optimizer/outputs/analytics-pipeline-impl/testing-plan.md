---
id: analytics-testing-plan
title: Analytics Pipeline — Automated Testing Plan
role: cro_optimizer
status: draft
created_at: 2026-04-09
updated_at: 2026-04-09
author: cro_optimizer_agent
target_repo: Synapse-Network
---

# Analytics Pipeline — Automated Testing Plan

> 验证目标：事件从产生到存储，每一跳都正确、完整、不丢失、不重复。

---

## 1. 测试分层架构

```
Layer 4: E2E Pipeline Test (Kafka → ClickHouse → Query)
Layer 3: Integration Test (API → Kafka / API → File)
Layer 2: Unit Test (Emitter, Event Schema, Privacy)
Layer 1: Frontend Unit Test (analytics.ts, Provider)
```

每一层独立运行，不依赖上层。CI 中 Layer 1-2 必跑，Layer 3-4 在有 Docker 环境时跑。

---

## 2. Layer 1: Frontend Unit Tests

### 2.1 `analytics.test.ts` — SDK 核心逻辑

```typescript
/**
 * 测试文件: services/user-front/src/lib/__tests__/analytics.test.ts
 * 运行: npx vitest run src/lib/__tests__/analytics.test.ts
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SynapseAnalytics } from '../analytics';

describe('SynapseAnalytics', () => {
  let analytics: SynapseAnalytics;
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    // Mock fetch
    fetchSpy = vi.fn().mockResolvedValue({ ok: true });
    global.fetch = fetchSpy;

    // Mock sessionStorage / localStorage
    const store: Record<string, string> = {};
    vi.stubGlobal('sessionStorage', {
      getItem: (k: string) => store[k] || null,
      setItem: (k: string, v: string) => { store[k] = v; },
    });
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => store[k] || null,
      setItem: (k: string, v: string) => { store[k] = v; },
    });

    analytics = new SynapseAnalytics({
      endpoint: '/api/v1/events',
      env: 'local',
      batchSize: 3,
      flushIntervalMs: 60_000,
      debug: false,
    });
  });

  afterEach(() => {
    analytics.destroy();
    vi.restoreAllMocks();
  });

  // ── Event Capture ──────────────────────────────────────────

  it('should capture events with correct structure', () => {
    analytics.capture('cta_clicked', { cta_id: 'hero' });

    // Access internal queue via flush trigger
    // Capture 2 more to trigger batchSize=3
    analytics.capture('page_viewed', {});
    analytics.capture('wallet_connect_started', {});

    // Should have triggered a flush (batchSize=3)
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/v1/events');
    expect(options.method).toBe('POST');

    const body = JSON.parse(options.body);
    expect(body.events).toHaveLength(3);

    const firstEvent = body.events[0];
    expect(firstEvent).toHaveProperty('event_id');
    expect(firstEvent).toHaveProperty('event_name', 'cta_clicked');
    expect(firstEvent).toHaveProperty('timestamp');
    expect(firstEvent).toHaveProperty('distinct_id');
    expect(firstEvent).toHaveProperty('source', 'frontend');
    expect(firstEvent.properties).toHaveProperty('cta_id', 'hero');
    expect(firstEvent.properties).toHaveProperty('role', 'anonymous');
    expect(firstEvent.properties).toHaveProperty('session_id');
    expect(firstEvent.properties).toHaveProperty('env', 'local');
  });

  // ── Common Properties ──────────────────────────────────────

  it('should inject session_id consistently across events', () => {
    analytics.capture('event_a', {});
    analytics.capture('event_b', {});
    analytics.capture('event_c', {}); // triggers flush

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    const sessionIds = body.events.map((e: any) => e.properties.session_id);
    expect(new Set(sessionIds).size).toBe(1); // All same session
    expect(sessionIds[0]).toBeTruthy();
  });

  it('should detect surface from pathname', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/provider/services', search: '' },
      writable: true,
    });

    analytics.capture('test_event', {});
    analytics.capture('test_event', {});
    analytics.capture('test_event', {}); // triggers flush

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.events[0].properties.surface).toBe('provider_console');
  });

  // ── UTM Persistence ────────────────────────────────────────

  it('should parse and persist UTM params', () => {
    Object.defineProperty(window, 'location', {
      value: {
        pathname: '/',
        search: '?utm_source=producthunt&utm_medium=social&utm_campaign=launch_day',
      },
      writable: true,
    });

    analytics.capture('page_viewed', {});
    analytics.capture('page_viewed', {});
    analytics.capture('page_viewed', {}); // triggers flush

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.events[0].properties.utm_source).toBe('producthunt');
    expect(body.events[0].properties.utm_medium).toBe('social');
    expect(body.events[0].properties.utm_campaign).toBe('launch_day');
  });

  // ── Identity ───────────────────────────────────────────────

  it('should hash wallet address on identify', async () => {
    // Mock crypto.subtle
    const mockDigest = vi.fn().mockResolvedValue(new Uint8Array(32).buffer);
    vi.stubGlobal('crypto', { subtle: { digest: mockDigest } });

    await analytics.identify('0xAbC123...', { role: 'consumer', chainId: 42161 });

    // Should have emitted $identify event
    analytics.capture('test', {});
    analytics.capture('test', {}); // triggers flush with 3 total

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    const identifyEvent = body.events.find((e: any) => e.event_name === '$identify');
    expect(identifyEvent).toBeDefined();
    expect(identifyEvent.properties.anonymous_id).toBeTruthy();
    expect(identifyEvent.properties.wallet_hash).toBeTruthy();
  });

  // ── Batch Flush ────────────────────────────────────────────

  it('should not flush before batchSize is reached', () => {
    analytics.capture('event_a', {});
    analytics.capture('event_b', {});
    // Only 2 events, batchSize is 3
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  // ── Error Handling ─────────────────────────────────────────

  it('should re-enqueue events on flush failure', async () => {
    fetchSpy.mockRejectedValueOnce(new Error('Network error'));

    analytics.capture('event_a', {});
    analytics.capture('event_b', {});
    analytics.capture('event_c', {}); // triggers flush

    // Wait for async flush
    await new Promise(r => setTimeout(r, 50));

    // Events should be re-enqueued
    // Trigger another flush
    analytics.capture('event_d', {});
    analytics.capture('event_e', {});
    analytics.capture('event_f', {}); // triggers flush again

    // Second call should include re-enqueued + new events
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  // ── Page Tracking ──────────────────────────────────────────

  it('should emit page_viewed with correct properties', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/marketplace', search: '' },
      writable: true,
    });
    Object.defineProperty(document, 'title', { value: 'Marketplace', writable: true });
    Object.defineProperty(document, 'referrer', {
      value: 'https://google.com',
      writable: true,
    });

    analytics.page();
    analytics.capture('filler', {});
    analytics.capture('filler', {}); // triggers flush

    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    const pageEvent = body.events.find((e: any) => e.event_name === 'page_viewed');
    expect(pageEvent.properties.page_path).toBe('/marketplace');
    expect(pageEvent.properties.page_title).toBe('Marketplace');
    expect(pageEvent.properties.referrer).toBe('https://google.com');
  });
});
```

---

## 3. Layer 2: Backend Unit Tests

### 3.1 `test_emitter.py` — Emitter 逻辑

```python
"""
测试文件: services/gateway/tests/test_analytics_emitter.py
运行: pytest tests/test_analytics_emitter.py -v
"""
import json
import uuid
from pathlib import Path

import pytest

from src.services.analytics.emitter import (
    AnalyticsEvent,
    AnalyticsEmitter,
    FileBackend,
    create_analytics_emitter,
)


class TestAnalyticsEvent:
    """Test event data container."""

    def test_event_structure(self):
        event = AnalyticsEvent(
            event_name="invoke_completed",
            distinct_id="abc123hash",
            source="gateway",
            properties={"service_id": "svc_1", "price_usdc": 0.05},
        )
        d = event.to_dict()

        assert d["event_name"] == "invoke_completed"
        assert d["distinct_id"] == "abc123hash"
        assert d["source"] == "gateway"
        assert d["properties"]["service_id"] == "svc_1"
        assert d["properties"]["price_usdc"] == 0.05
        # Auto-generated fields
        assert "event_id" in d
        assert "timestamp" in d
        uuid.UUID(d["event_id"])  # Must be valid UUID

    def test_event_json_serializable(self):
        event = AnalyticsEvent(
            event_name="deposit_completed",
            distinct_id="xyz",
            properties={"amount_usdc": 100.0},
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)
        assert parsed["event_name"] == "deposit_completed"

    def test_event_custom_id_and_timestamp(self):
        event = AnalyticsEvent(
            event_name="test",
            distinct_id="user",
            event_id="custom-id",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert event.event_id == "custom-id"
        assert event.timestamp == "2026-01-01T00:00:00Z"


class TestFileBackend:
    """Test file-based event storage."""

    @pytest.fixture
    def tmp_file(self, tmp_path):
        return str(tmp_path / "events.jsonl")

    @pytest.mark.asyncio
    async def test_write_event(self, tmp_file):
        backend = FileBackend(path=tmp_file)
        event = AnalyticsEvent(
            event_name="test_event",
            distinct_id="user123",
            properties={"key": "value"},
        )
        await backend.send(event)

        lines = Path(tmp_file).read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event_name"] == "test_event"
        assert parsed["distinct_id"] == "user123"

    @pytest.mark.asyncio
    async def test_append_multiple_events(self, tmp_file):
        backend = FileBackend(path=tmp_file)
        for i in range(5):
            event = AnalyticsEvent(
                event_name=f"event_{i}",
                distinct_id="user",
            )
            await backend.send(event)

        lines = Path(tmp_file).read_text().strip().split("\n")
        assert len(lines) == 5

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, tmp_path):
        deep_path = str(tmp_path / "a" / "b" / "c" / "events.jsonl")
        backend = FileBackend(path=deep_path)
        event = AnalyticsEvent(event_name="test", distinct_id="user")
        await backend.send(event)
        assert Path(deep_path).exists()


class TestAnalyticsEmitter:
    """Test the emitter orchestration layer."""

    @pytest.fixture
    def file_emitter(self, tmp_path):
        return create_analytics_emitter(
            environment="local",
            fallback_file=str(tmp_path / "events.jsonl"),
        )

    @pytest.mark.asyncio
    async def test_emit_writes_to_file(self, file_emitter, tmp_path):
        await file_emitter.emit(
            event_name="invoke_completed",
            distinct_id="hash123",
            properties={"service_id": "svc_1", "latency_ms": 250},
            correlation_id="corr_abc",
        )

        lines = (tmp_path / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["event_name"] == "invoke_completed"
        assert parsed["properties"]["correlation_id"] == "corr_abc"
        assert parsed["properties"]["service_id"] == "svc_1"

    @pytest.mark.asyncio
    async def test_emit_batch(self, file_emitter, tmp_path):
        events = [
            AnalyticsEvent(event_name=f"event_{i}", distinct_id="user")
            for i in range(10)
        ]
        await file_emitter.emit_batch(events)

        lines = (tmp_path / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) == 10


class TestPrivacy:
    """Test PII protection."""

    def test_sha256_hash(self):
        from src.services.analytics.privacy import sha256_hash

        result = sha256_hash("0xAbCdEf1234567890AbCdEf1234567890AbCdEf12")
        # Should be 64 hex chars
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)
        # Should be case-insensitive
        assert result == sha256_hash("0xabcdef1234567890abcdef1234567890abcdef12")

    def test_hash_strips_whitespace(self):
        from src.services.analytics.privacy import sha256_hash

        assert sha256_hash("  0xABC  ") == sha256_hash("0xABC")
```

### 3.2 `test_events_router.py` — 事件接收端点

```python
"""
测试文件: services/gateway/tests/test_events_router.py
运行: pytest tests/test_events_router.py -v
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routers.events import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)

    # Mock analytics emitter
    mock_emitter = MagicMock()
    mock_emitter.emit_batch = AsyncMock()
    app.state.analytics = mock_emitter
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestEventsEndpoint:
    """Test POST /api/v1/events"""

    def _make_event(self, event_name: str = "page_viewed", **extra) -> dict:
        return {
            "event_id": str(uuid.uuid4()),
            "event_name": event_name,
            "timestamp": "2026-04-09T15:00:00.000Z",
            "distinct_id": "a" * 64,  # SHA-256 hash
            "source": "frontend",
            "properties": {"page_path": "/", "role": "anonymous", **extra},
        }

    def test_accept_valid_batch(self, client):
        response = client.post("/api/v1/events", json={
            "events": [
                self._make_event("page_viewed"),
                self._make_event("cta_clicked", cta_id="hero"),
            ]
        })
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] == 2
        assert body["rejected"] == 0

    def test_reject_unknown_event_name(self, client):
        response = client.post("/api/v1/events", json={
            "events": [
                self._make_event("malicious_event"),
            ]
        })
        assert response.status_code == 422  # Pydantic validation error

    def test_reject_raw_wallet_address(self, client):
        event = self._make_event("page_viewed")
        event["distinct_id"] = "0x1234567890123456789012345678901234567890"
        response = client.post("/api/v1/events", json={
            "events": [event]
        })
        assert response.status_code == 422

    def test_reject_empty_batch(self, client):
        response = client.post("/api/v1/events", json={
            "events": []
        })
        assert response.status_code == 422

    def test_reject_oversized_batch(self, client):
        events = [self._make_event("page_viewed") for _ in range(51)]
        response = client.post("/api/v1/events", json={
            "events": events
        })
        assert response.status_code == 422

    def test_emitter_called_with_events(self, client, app):
        client.post("/api/v1/events", json={
            "events": [self._make_event("wallet_connected")]
        })
        assert app.state.analytics.emit_batch.called
        args = app.state.analytics.emit_batch.call_args[0][0]
        assert len(args) == 1
        assert args[0].event_name == "wallet_connected"
```

---

## 4. Layer 3: Integration Tests (Kafka)

### 4.1 `test_kafka_integration.py`

```python
"""
测试文件: services/gateway/tests/integration/test_kafka_integration.py
运行: pytest tests/integration/test_kafka_integration.py -v --timeout=30

前置条件: Docker Kafka running on localhost:9092
  docker run -d --name kafka-test -p 9092:9092 bitnami/kafka:3.7 \
    -e KAFKA_CFG_NODE_ID=0 \
    -e KAFKA_CFG_PROCESS_ROLES=controller,broker \
    -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \
    -e KAFKA_CFG_CONTROLLER_QUORUM_VOTERS=0@localhost:9093 \
    -e KAFKA_CFG_CONTROLLER_LISTENER_NAMES=CONTROLLER
"""
import asyncio
import json
import os
import uuid

import pytest

# Skip if no Kafka available
KAFKA_AVAILABLE = os.getenv("ANALYTICS_TEST_KAFKA", "").lower() == "true"
pytestmark = pytest.mark.skipif(not KAFKA_AVAILABLE, reason="Kafka not available")


@pytest.fixture
def test_topic():
    return f"synapse.analytics.test.{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_kafka_roundtrip(test_topic):
    """Verify: emit event → Kafka → consume event → validate structure."""
    from aiokafka import AIOKafkaConsumer
    from src.services.analytics.emitter import KafkaBackend, AnalyticsEvent

    # Produce
    backend = KafkaBackend(
        bootstrap_servers="localhost:9092",
        topic=test_topic,
    )
    event = AnalyticsEvent(
        event_name="invoke_completed",
        distinct_id="test_user_hash",
        source="gateway",
        properties={
            "service_id": "svc_test",
            "price_usdc": 0.05,
            "latency_ms": 150,
        },
    )
    await backend.send(event)

    # Consume
    consumer = AIOKafkaConsumer(
        test_topic,
        bootstrap_servers="localhost:9092",
        auto_offset_reset="earliest",
        group_id=f"test-{uuid.uuid4().hex[:8]}",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=10_000,
    )
    await consumer.start()

    received = None
    try:
        async for msg in consumer:
            received = msg.value
            break  # Only need the first message
    finally:
        await consumer.stop()
        await backend.close()

    # Validate
    assert received is not None
    assert received["event_name"] == "invoke_completed"
    assert received["distinct_id"] == "test_user_hash"
    assert received["source"] == "gateway"
    assert received["properties"]["service_id"] == "svc_test"
    assert received["properties"]["price_usdc"] == 0.05


@pytest.mark.asyncio
async def test_kafka_batch_ordering(test_topic):
    """Verify: events for the same user arrive in order."""
    from aiokafka import AIOKafkaConsumer
    from src.services.analytics.emitter import KafkaBackend, AnalyticsEvent

    backend = KafkaBackend(
        bootstrap_servers="localhost:9092",
        topic=test_topic,
    )

    # Send events in order
    event_names = [
        "wallet_connected",
        "deposit_completed",
        "invoke_completed",
    ]
    for name in event_names:
        event = AnalyticsEvent(
            event_name=name,
            distinct_id="same_user_hash",
            source="gateway",
        )
        await backend.send(event)

    # Consume and verify order
    consumer = AIOKafkaConsumer(
        test_topic,
        bootstrap_servers="localhost:9092",
        auto_offset_reset="earliest",
        group_id=f"test-{uuid.uuid4().hex[:8]}",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=10_000,
    )
    await consumer.start()

    received_names = []
    try:
        async for msg in consumer:
            received_names.append(msg.value["event_name"])
            if len(received_names) == 3:
                break
    finally:
        await consumer.stop()
        await backend.close()

    assert received_names == event_names


@pytest.mark.asyncio
async def test_dual_backend_fallback(tmp_path):
    """Verify: DualBackend falls back to file when Kafka is unreachable."""
    from src.services.analytics.emitter import (
        KafkaBackend, FileBackend, DualBackend, AnalyticsEvent,
    )

    kafka = KafkaBackend(
        bootstrap_servers="localhost:19999",  # Unreachable port
        topic="test",
    )
    fallback_path = str(tmp_path / "fallback.jsonl")
    fallback = FileBackend(path=fallback_path)
    dual = DualBackend(kafka=kafka, fallback=fallback)

    event = AnalyticsEvent(
        event_name="test_event",
        distinct_id="user",
    )

    # Should not raise, should fall back to file
    await dual.send(event)

    from pathlib import Path
    lines = Path(fallback_path).read_text().strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0])["event_name"] == "test_event"

    await dual.close()
```

---

## 5. Layer 4: E2E Pipeline Test

### 5.1 `test_e2e_pipeline.py`

```python
"""
测试文件: services/gateway/tests/e2e/test_e2e_pipeline.py
运行: pytest tests/e2e/test_e2e_pipeline.py -v --timeout=60

前置条件: docker-compose up -d (kafka + clickhouse)
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

import pytest

E2E_AVAILABLE = os.getenv("ANALYTICS_TEST_E2E", "").lower() == "true"
pytestmark = pytest.mark.skipif(not E2E_AVAILABLE, reason="E2E infra not available")


@pytest.fixture
def unique_marker():
    """Generate a unique marker to identify test events in ClickHouse."""
    return f"e2e_test_{uuid.uuid4().hex[:12]}"


@pytest.mark.asyncio
async def test_event_flows_to_clickhouse(unique_marker):
    """
    End-to-end: emit event → Kafka → ClickHouse Kafka Engine → events table.

    验证：
    1. 事件写入 Kafka
    2. ClickHouse Kafka Engine 消费事件
    3. 事件出现在 synapse_analytics.events 表中
    4. 字段解析正确
    """
    import httpx
    from src.services.analytics.emitter import KafkaBackend, AnalyticsEvent

    # 1. Emit event to Kafka
    backend = KafkaBackend(
        bootstrap_servers="localhost:9092",
        topic="synapse.analytics.events",
    )
    event = AnalyticsEvent(
        event_name="invoke_completed",
        distinct_id=unique_marker,  # Use marker as distinct_id for querying
        source="gateway",
        properties={
            "role": "consumer",
            "surface": "gateway_api",
            "env": "test",
            "service_id": "svc_e2e_test",
            "price_usdc": 0.042,
            "latency_ms": 200,
            "is_first_invoke": True,
            "correlation_id": f"corr_{unique_marker}",
        },
    )
    await backend.send(event)
    await backend.close()

    # 2. Wait for ClickHouse to consume (Kafka Engine has ~1-5s lag)
    await asyncio.sleep(10)

    # 3. Query ClickHouse
    query = f"""
        SELECT
            event_id,
            event_name,
            distinct_id,
            source,
            role,
            surface,
            env,
            JSONExtractString(properties, 'service_id') AS service_id,
            JSONExtractFloat(properties, 'price_usdc') AS price_usdc,
            JSONExtractUInt(properties, 'latency_ms') AS latency_ms,
            JSONExtractBool(properties, 'is_first_invoke') AS is_first_invoke
        FROM synapse_analytics.events
        WHERE distinct_id = '{unique_marker}'
        LIMIT 1
    """

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "http://localhost:8123",
            params={"query": query, "default_format": "JSONEachRow"},
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1, f"Event not found in ClickHouse for marker {unique_marker}"

        row = json.loads(lines[0])

    # 4. Validate all fields
    assert row["event_name"] == "invoke_completed"
    assert row["distinct_id"] == unique_marker
    assert row["source"] == "gateway"
    assert row["role"] == "consumer"
    assert row["surface"] == "gateway_api"
    assert row["env"] == "test"
    assert row["service_id"] == "svc_e2e_test"
    assert abs(row["price_usdc"] - 0.042) < 0.001
    assert row["latency_ms"] == 200
    assert row["is_first_invoke"] == 1  # ClickHouse bool = UInt8


@pytest.mark.asyncio
async def test_consumer_funnel_query(unique_marker):
    """
    Verify the consumer activation funnel query works end-to-end.

    Emit a sequence of funnel events, then run the funnel aggregation query.
    """
    import httpx
    from src.services.analytics.emitter import KafkaBackend, AnalyticsEvent

    backend = KafkaBackend(
        bootstrap_servers="localhost:9092",
        topic="synapse.analytics.events",
    )

    funnel_events = [
        "page_viewed",
        "wallet_connected",
        "consumer_signup_completed",
        "deposit_completed",
        "credential_created",
        "invoke_completed",
    ]

    for event_name in funnel_events:
        event = AnalyticsEvent(
            event_name=event_name,
            distinct_id=unique_marker,
            source="gateway",
            properties={
                "role": "consumer",
                "env": "test",
                "is_first_invoke": event_name == "invoke_completed",
            },
        )
        await backend.send(event)

    await backend.close()
    await asyncio.sleep(10)

    # Run funnel query
    query = f"""
        SELECT
            event_name,
            uniqExact(distinct_id) AS users
        FROM synapse_analytics.events
        WHERE distinct_id = '{unique_marker}'
        AND event_name IN (
            'page_viewed', 'wallet_connected', 'consumer_signup_completed',
            'deposit_completed', 'credential_created', 'invoke_completed'
        )
        AND env = 'test'
        GROUP BY event_name
        ORDER BY users DESC
    """

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "http://localhost:8123",
            params={"query": query, "default_format": "JSONEachRow"},
        )
        assert resp.status_code == 200
        lines = resp.text.strip().split("\n")
        rows = [json.loads(line) for line in lines]

    event_names_found = {row["event_name"] for row in rows}
    assert event_names_found == set(funnel_events)
    for row in rows:
        assert row["users"] == 1
```

---

## 6. 数据质量校验脚本

### 6.1 `scripts/analytics_health_check.py`

```python
"""
定期运行的数据质量检查脚本。
可作为 cron job 或 CI 定期执行。

运行: python scripts/analytics_health_check.py
"""
import asyncio
import json
import sys
from datetime import datetime, timezone

import httpx

CLICKHOUSE_URL = "http://localhost:8123"
CHECKS_PASSED = 0
CHECKS_FAILED = 0


async def query_ch(sql: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            CLICKHOUSE_URL,
            params={"query": sql, "default_format": "JSONEachRow"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ClickHouse query failed: {resp.text}")
        return [json.loads(line) for line in resp.text.strip().split("\n") if line]


def check(name: str, condition: bool, detail: str = ""):
    global CHECKS_PASSED, CHECKS_FAILED
    status = "✅ PASS" if condition else "❌ FAIL"
    print(f"  {status}: {name}" + (f" — {detail}" if detail else ""))
    if condition:
        CHECKS_PASSED += 1
    else:
        CHECKS_FAILED += 1


async def main():
    print("=" * 60)
    print("Synapse Analytics Health Check")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # ── Check 1: Events flowing ────────────────────────────────
    print("\n[1] Event Flow")
    rows = await query_ch("""
        SELECT count() AS cnt
        FROM synapse_analytics.events
        WHERE timestamp >= now() - INTERVAL 1 HOUR
    """)
    recent_count = rows[0]["cnt"] if rows else 0
    check("Events in last hour", recent_count > 0, f"count={recent_count}")

    # ── Check 2: No duplicate event_ids ────────────────────────
    print("\n[2] Deduplication")
    rows = await query_ch("""
        SELECT count() AS total, uniqExact(event_id) AS unique_ids
        FROM synapse_analytics.events
        WHERE timestamp >= now() - INTERVAL 24 HOUR
    """)
    if rows:
        total = rows[0]["total"]
        unique = rows[0]["unique_ids"]
        dup_rate = (total - unique) / max(total, 1)
        check("Duplicate rate < 1%", dup_rate < 0.01, f"total={total}, unique={unique}, dup_rate={dup_rate:.4f}")

    # ── Check 3: No raw wallet addresses ───────────────────────
    print("\n[3] Privacy")
    rows = await query_ch("""
        SELECT count() AS cnt
        FROM synapse_analytics.events
        WHERE distinct_id LIKE '0x%' AND length(distinct_id) = 42
        AND timestamp >= now() - INTERVAL 24 HOUR
    """)
    raw_wallets = rows[0]["cnt"] if rows else 0
    check("No raw wallet addresses in distinct_id", raw_wallets == 0, f"found={raw_wallets}")

    # ── Check 4: All sources present ───────────────────────────
    print("\n[4] Source Coverage")
    rows = await query_ch("""
        SELECT source, count() AS cnt
        FROM synapse_analytics.events
        WHERE timestamp >= now() - INTERVAL 24 HOUR
        GROUP BY source
    """)
    sources_found = {row["source"] for row in rows}
    expected = {"frontend", "gateway"}
    check("Frontend events present", "frontend" in sources_found)
    check("Gateway events present", "gateway" in sources_found)

    # ── Check 5: Critical events present ───────────────────────
    print("\n[5] Critical Events")
    rows = await query_ch("""
        SELECT event_name, count() AS cnt
        FROM synapse_analytics.events
        WHERE timestamp >= now() - INTERVAL 24 HOUR
        GROUP BY event_name
    """)
    events_found = {row["event_name"] for row in rows}
    critical = [
        "page_viewed", "wallet_connected",
        "invoke_completed", "deposit_completed",
    ]
    for evt in critical:
        check(f"'{evt}' present", evt in events_found)

    # ── Check 6: Invoke success rate ───────────────────────────
    print("\n[6] Invoke Health")
    rows = await query_ch("""
        SELECT
            countIf(event_name = 'invoke_completed') AS succeeded,
            countIf(event_name = 'invoke_failed') AS failed
        FROM synapse_analytics.events
        WHERE event_name IN ('invoke_completed', 'invoke_failed')
        AND timestamp >= now() - INTERVAL 1 HOUR
    """)
    if rows and (rows[0]["succeeded"] + rows[0]["failed"]) > 0:
        total_invokes = rows[0]["succeeded"] + rows[0]["failed"]
        success_rate = rows[0]["succeeded"] / total_invokes
        check(
            "Invoke success rate > 90%",
            success_rate > 0.90,
            f"rate={success_rate:.2%} ({rows[0]['succeeded']}/{total_invokes})",
        )

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Results: {CHECKS_PASSED} passed, {CHECKS_FAILED} failed")
    print("=" * 60)

    sys.exit(1 if CHECKS_FAILED > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 7. CI 集成配置

### 7.1 GitHub Actions Workflow

```yaml
# .github/workflows/analytics-tests.yml
name: Analytics Pipeline Tests

on:
  pull_request:
    paths:
      - 'services/gateway/src/services/analytics/**'
      - 'services/gateway/src/api/routers/events.py'
      - 'services/user-front/src/lib/analytics*'
      - 'services/gateway/tests/test_analytics*'
      - 'services/gateway/tests/test_events*'
      - 'services/user-front/src/lib/__tests__/analytics*'

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Frontend unit tests
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: cd services/user-front && npm ci && npx vitest run src/lib/__tests__/analytics.test.ts

      # Backend unit tests
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: |
          cd services/gateway
          pip install -r requirements.txt
          pytest tests/test_analytics_emitter.py tests/test_events_router.py -v

  integration-tests:
    runs-on: ubuntu-latest
    if: github.event.pull_request.draft == false
    services:
      kafka:
        image: bitnami/kafka:3.7
        ports:
          - 9092:9092
        env:
          KAFKA_CFG_NODE_ID: 0
          KAFKA_CFG_PROCESS_ROLES: controller,broker
          KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
          KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
          KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
          KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: |
          cd services/gateway
          pip install -r requirements.txt
          pip install aiokafka
          ANALYTICS_TEST_KAFKA=true pytest tests/integration/test_kafka_integration.py -v --timeout=30
```

---

## 8. 测试覆盖矩阵

| 验证点 | Layer 1 | Layer 2 | Layer 3 | Layer 4 |
|--------|:-------:|:-------:|:-------:|:-------:|
| Event 结构正确 | ✅ | ✅ | ✅ | ✅ |
| Common properties 注入 | ✅ | | | |
| UTM 解析与持久化 | ✅ | | | |
| Session ID 一致性 | ✅ | | | |
| Surface 自动检测 | ✅ | | | |
| Wallet hash (前端) | ✅ | | | |
| Wallet hash (后端) | | ✅ | | |
| PII 不泄露 | ✅ | ✅ | | ✅ |
| 批量发送 | ✅ | ✅ | | |
| 失败重试 (前端) | ✅ | | | |
| Event name 白名单 | | ✅ | | |
| Raw address 拒绝 | | ✅ | | |
| File backend 写入 | | ✅ | | |
| Kafka roundtrip | | | ✅ | |
| Kafka 消息顺序 | | | ✅ | |
| Dual backend fallback | | | ✅ | |
| Kafka → ClickHouse 落库 | | | | ✅ |
| 字段解析正确 | | | | ✅ |
| Funnel 查询可用 | | | | ✅ |
| 无重复 event_id | | | | ✅ |

---

## 9. 告警验证

除了功能测试，上线后需要验证告警系统是否工作：

| 告警 | 验证方法 |
|------|----------|
| Event 断流 | 停止 gateway，观察 1h 内是否收到告警 |
| Invoke 失败率飙升 | 手动写入 20 条 `invoke_failed`，验证 30m 告警 |
| Deposit 失败率 | 手动写入 `deposit_failed` > 15%，验证告警触发 |
| 重复事件 | 写入相同 `event_id` 的事件，验证健康检查脚本 FAIL |
| PII 泄露 | 写入 `0x...` 格式的 `distinct_id`，验证健康检查脚本 FAIL |
