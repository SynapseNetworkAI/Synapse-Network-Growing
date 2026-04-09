---
id: analytics-backend-emitter
title: Backend Analytics Emitter — Gateway + Provider Service
role: cro_optimizer
status: draft
created_at: 2026-04-09
updated_at: 2026-04-09
author: cro_optimizer_agent
target_repo: Synapse-Network (services/gateway/, services/provider_service/)
---

# Backend Analytics Emitter

> Gateway 和 Provider Service 是计费与结算事件的 source of truth。
> 所有收入类、调用成功/失败类事件必须由服务端上报，前端不重复发送。

---

## 1. 核心模块：`src/services/analytics/emitter.py`

```python
"""
Synapse Analytics Event Emitter

职责：
  1. 提供统一的 emit() 接口，供 Gateway 各业务模块调用
  2. 将事件序列化后异步写入 Kafka topic
  3. 自动注入 event_id、timestamp、source、correlation_id
  4. 提供 fallback：Kafka 不可用时降级写入本地 JSONL 文件

放置路径：services/gateway/src/services/analytics/emitter.py
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("synapse.analytics")


class AnalyticsEvent:
    """Immutable event data container."""

    __slots__ = (
        "event_id", "event_name", "timestamp", "distinct_id",
        "source", "properties",
    )

    def __init__(
        self,
        event_name: str,
        distinct_id: str,
        source: str = "gateway",
        properties: Optional[dict[str, Any]] = None,
        event_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.event_id = event_id or str(uuid.uuid4())
        self.event_name = event_name
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.distinct_id = distinct_id
        self.source = source
        self.properties = properties or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "timestamp": self.timestamp,
            "distinct_id": self.distinct_id,
            "source": self.source,
            "properties": self.properties,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)


class AnalyticsEmitter:
    """
    Unified analytics event emitter.

    Supports two backends:
      - KafkaBackend: writes to Kafka topic (production)
      - FileBackend: writes to local JSONL file (dev / fallback)
    """

    def __init__(self, backend: "AnalyticsBackend"):
        self._backend = backend

    async def emit(
        self,
        event_name: str,
        distinct_id: str,
        properties: Optional[dict[str, Any]] = None,
        source: str = "gateway",
        correlation_id: Optional[str] = None,
    ) -> None:
        """Emit a single analytics event. Non-blocking, fire-and-forget."""
        props = dict(properties or {})
        if correlation_id:
            props["correlation_id"] = correlation_id

        event = AnalyticsEvent(
            event_name=event_name,
            distinct_id=distinct_id,
            source=source,
            properties=props,
        )

        try:
            await self._backend.send(event)
            logger.debug("analytics.emit ok: %s %s", event_name, event.event_id)
        except Exception:
            logger.exception("analytics.emit failed: %s", event_name)

    async def emit_batch(self, events: list[AnalyticsEvent]) -> None:
        """Emit a batch of events (used by the frontend event ingestion endpoint)."""
        for event in events:
            try:
                await self._backend.send(event)
            except Exception:
                logger.exception("analytics.emit_batch failed: %s", event.event_name)


# ─── Backend Interface ─────────────────────────────────────────

class AnalyticsBackend:
    """Abstract backend for event delivery."""
    async def send(self, event: AnalyticsEvent) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        pass


# ─── Kafka Backend ─────────────────────────────────────────────

class KafkaBackend(AnalyticsBackend):
    """
    Writes events to a Kafka topic using aiokafka.

    Requirements: pip install aiokafka
    """

    def __init__(
        self,
        bootstrap_servers: str = "localhost:9092",
        topic: str = "synapse.analytics.events",
    ):
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer = None

    async def _ensure_producer(self):
        if self._producer is None:
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap_servers,
                value_serializer=lambda v: v.encode("utf-8"),
                # Partition by distinct_id to keep user events ordered
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                compression_type="gzip",
                linger_ms=50,
                batch_size=32768,
            )
            await self._producer.start()
            logger.info("Kafka analytics producer started: %s", self._bootstrap_servers)

    async def send(self, event: AnalyticsEvent) -> None:
        await self._ensure_producer()
        await self._producer.send_and_wait(
            topic=self._topic,
            value=event.to_json(),
            key=event.distinct_id,
        )

    async def close(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None


# ─── File Backend (Dev / Fallback) ─────────────────────────────

class FileBackend(AnalyticsBackend):
    """
    Appends events as JSONL to a local file.
    Used for local development and as a fallback when Kafka is unavailable.
    """

    def __init__(self, path: str = "logs/analytics_events.jsonl"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def send(self, event: AnalyticsEvent) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")

    async def close(self) -> None:
        pass


# ─── Dual Backend (Production Recommended) ─────────────────────

class DualBackend(AnalyticsBackend):
    """
    Writes to Kafka as primary, falls back to file on Kafka failure.
    Ensures zero event loss even during Kafka outages.
    """

    def __init__(self, kafka: KafkaBackend, fallback: FileBackend):
        self._kafka = kafka
        self._fallback = fallback

    async def send(self, event: AnalyticsEvent) -> None:
        try:
            await self._kafka.send(event)
        except Exception:
            logger.warning(
                "Kafka unavailable, falling back to file: %s", event.event_name
            )
            await self._fallback.send(event)

    async def close(self) -> None:
        await self._kafka.close()
        await self._fallback.close()


# ─── Factory ───────────────────────────────────────────────────

def create_analytics_emitter(
    kafka_bootstrap_servers: Optional[str] = None,
    kafka_topic: str = "synapse.analytics.events",
    fallback_file: str = "logs/analytics_events.jsonl",
    environment: str = "local",
) -> AnalyticsEmitter:
    """
    Factory function to create the appropriate emitter based on environment.

    - local/test: FileBackend only
    - staging/prod: DualBackend (Kafka + File fallback)
    """
    if environment in ("staging", "prod") and kafka_bootstrap_servers:
        kafka = KafkaBackend(
            bootstrap_servers=kafka_bootstrap_servers,
            topic=kafka_topic,
        )
        fallback = FileBackend(path=fallback_file)
        backend = DualBackend(kafka=kafka, fallback=fallback)
        logger.info("Analytics: Kafka + File fallback (%s)", kafka_bootstrap_servers)
    else:
        backend = FileBackend(path=fallback_file)
        logger.info("Analytics: File-only mode (%s)", fallback_file)

    return AnalyticsEmitter(backend=backend)
```

---

## 2. 配置集成：`src/core/config.py` 新增字段

```python
# ── Analytics Pipeline ────────────────────────────────────────
# 在 Settings class 中新增以下字段:

class Settings:
    # ... existing fields ...

    # Analytics
    analytics_kafka_bootstrap_servers: str = os.getenv(
        "ANALYTICS_KAFKA_BOOTSTRAP_SERVERS", ""
    )
    analytics_kafka_topic: str = os.getenv(
        "ANALYTICS_KAFKA_TOPIC", "synapse.analytics.events"
    )
    analytics_fallback_file: str = os.getenv(
        "ANALYTICS_FALLBACK_FILE", "logs/analytics_events.jsonl"
    )
```

---

## 3. App Startup 集成：`src/app.py`

```python
# 在 lifespan 函数中初始化 analytics emitter:

from src.services.analytics.emitter import create_analytics_emitter

@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = create_storage(settings)
    app.state.storage = storage

    # Initialize analytics emitter
    app.state.analytics = create_analytics_emitter(
        kafka_bootstrap_servers=settings.analytics_kafka_bootstrap_servers or None,
        kafka_topic=settings.analytics_kafka_topic,
        fallback_file=settings.analytics_fallback_file,
        environment=settings.environment,
    )

    # ... existing startup code ...

    try:
        yield
    finally:
        # Cleanup analytics
        await app.state.analytics._backend.close()
        # ... existing shutdown code ...
```

---

## 4. 前端事件接收端点：`src/api/routers/events.py`

```python
"""
Frontend Event Ingestion Endpoint

前端 analytics.ts 将事件批量 POST 到此端点。
Gateway 验证 schema 后写入 Kafka。

路径: POST /api/v1/events
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, field_validator

from src.services.analytics.emitter import AnalyticsEvent

logger = logging.getLogger("synapse.analytics.ingest")
router = APIRouter(prefix="/api/v1", tags=["analytics"])


# ─── Request Schema ────────────────────────────────────────────

class EventPayload(BaseModel):
    event_id: str
    event_name: str
    timestamp: str
    distinct_id: str
    source: str = "frontend"
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        # Only allow known frontend event names (whitelist)
        allowed_prefixes = (
            "page_viewed", "cta_clicked",
            "wallet_connect_started", "wallet_connected", "wallet_connect_failed",
            "role_selected",
            "consumer_signup_completed", "consumer_console_viewed",
            "deposit_started", "deposit_permit_signed",
            "service_search_executed", "service_detail_viewed",
            "receipt_viewed",
            "provider_signup_completed", "provider_console_viewed",
            "service_manifest_step_completed",
            "withdrawal_requested",
            "$identify",
        )
        if v not in allowed_prefixes:
            raise ValueError(f"Unknown frontend event: {v}")
        return v

    @field_validator("distinct_id")
    @classmethod
    def validate_distinct_id(cls, v: str) -> str:
        # Ensure distinct_id is not a raw wallet address
        if v.startswith("0x") and len(v) == 42:
            raise ValueError("distinct_id must be hashed, not raw wallet address")
        return v


class EventBatchRequest(BaseModel):
    events: list[EventPayload] = Field(..., min_length=1, max_length=50)


class EventBatchResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[str] = Field(default_factory=list)


# ─── Endpoint ──────────────────────────────────────────────────

@router.post("/events", response_model=EventBatchResponse)
async def ingest_events(body: EventBatchRequest, request: Request) -> EventBatchResponse:
    """
    Accept a batch of frontend analytics events and write to Kafka.

    Rate limit: 50 events per request, recommended max 10 req/s per client.
    """
    emitter = request.app.state.analytics
    accepted = 0
    rejected = 0
    errors: list[str] = []

    events_to_send: list[AnalyticsEvent] = []
    for payload in body.events:
        try:
            event = AnalyticsEvent(
                event_id=payload.event_id,
                event_name=payload.event_name,
                timestamp=payload.timestamp,
                distinct_id=payload.distinct_id,
                source=payload.source,
                properties=payload.properties,
            )
            events_to_send.append(event)
            accepted += 1
        except Exception as e:
            rejected += 1
            errors.append(f"{payload.event_name}: {str(e)}")

    if events_to_send:
        await emitter.emit_batch(events_to_send)

    return EventBatchResponse(accepted=accepted, rejected=rejected, errors=errors)
```

### 注册路由

```python
# src/app.py 中新增:
from src.api.routers.events import router as events_router

app.include_router(events_router)
```

---

## 5. 业务埋点集成示例

### 5.1 Invoke 完成/失败（forwarding router）

```python
# src/api/routers/forwarding.py — 在调用完成后埋点

async def _emit_invoke_event(
    request: Request,
    event_name: str,
    consumer_wallet_hash: str,
    service_id: str,
    provider_id: str,
    quote_id: str,
    correlation_id: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Helper: emit invoke lifecycle events."""
    emitter = request.app.state.analytics
    props = {
        "role": "consumer",
        "surface": "gateway_api",
        "env": settings.environment,
        "service_id": service_id,
        "provider_id": provider_id,
        "quote_id": quote_id,
        **(extra or {}),
    }
    await emitter.emit(
        event_name=event_name,
        distinct_id=consumer_wallet_hash,
        properties=props,
        source="gateway",
        correlation_id=correlation_id,
    )


# 在 invoke 成功路径中:
await _emit_invoke_event(
    request, "invoke_completed",
    consumer_wallet_hash=sha256_hash(consumer_address),
    service_id=service_id,
    provider_id=provider_id,
    quote_id=quote_id,
    correlation_id=request_id,
    extra={
        "price_usdc": float(price_usdc),
        "latency_ms": int(latency_ms),
        "is_first_invoke": is_first_invoke,
    },
)

# 在 invoke 失败路径中:
await _emit_invoke_event(
    request, "invoke_failed",
    consumer_wallet_hash=sha256_hash(consumer_address),
    service_id=service_id,
    provider_id=provider_id,
    quote_id=quote_id,
    correlation_id=request_id,
    extra={
        "error_code": error_code,
        "failure_stage": failure_stage,
    },
)
```

### 5.2 Deposit 完成（deposit indexer）

```python
# src/services/platform/tasks/deposit_indexer.py — 在充值确认后

async def _on_deposit_confirmed(
    storage, analytics_emitter, wallet_address, amount_usdc, tx_hash, confirm_time_ms
):
    await analytics_emitter.emit(
        event_name="deposit_completed",
        distinct_id=sha256_hash(wallet_address),
        source="gateway",
        properties={
            "role": "consumer",
            "surface": "gateway_api",
            "amount_usdc": float(amount_usdc),
            "token_symbol": "USDC",
            "tx_hash": tx_hash,
            "time_to_confirm_ms": int(confirm_time_ms),
        },
    )
```

### 5.3 Budget Blocked

```python
# 在预算检查拦截处:
await emitter.emit(
    event_name="budget_blocked",
    distinct_id=sha256_hash(consumer_address),
    source="gateway",
    properties={
        "service_id": service_id,
        "required_usdc": float(required_usdc),
        "available_usdc": float(available_usdc),
        "error_code": "INSUFFICIENT_BUDGET",
    },
)
```

### 5.4 Provider 首次收入

```python
# 在结算逻辑中:
await emitter.emit(
    event_name="provider_first_revenue_received",
    distinct_id=sha256_hash(provider_address),
    source="gateway",
    properties={
        "role": "provider",
        "provider_id": sha256_hash(provider_address),
        "service_id": service_id,
        "gross_usdc": float(gross_usdc),
        "time_since_listing_ms": int(time_since_listing_ms),
    },
)
```

### 5.5 Settlement Claim

```python
# 在提现流程中:
await emitter.emit(
    event_name="settlement_claim_completed",
    distinct_id=sha256_hash(provider_address),
    source="gateway",
    properties={
        "role": "provider",
        "provider_id": sha256_hash(provider_address),
        "claim_usdc": float(claim_usdc),
        "tx_hash": tx_hash,
        "time_to_confirm_ms": int(confirm_time_ms),
    },
)
```

---

## 6. Provider Service 埋点：`provider_service/analytics.py`

```python
"""
Provider Service 事件发射。
复用相同的 AnalyticsEmitter，通过 source="provider_service" 标识来源。
"""

# 服务注册成功
await emitter.emit(
    event_name="service_registered",
    distinct_id=sha256_hash(provider_address),
    source="provider_service",
    properties={
        "role": "provider",
        "service_id": service_id,
        "pricing_model": pricing_model,
        "price_usdc": float(price_usdc),
        "manifest_version": manifest_version,
    },
)

# 服务注册失败
await emitter.emit(
    event_name="service_register_failed",
    distinct_id=sha256_hash(provider_address),
    source="provider_service",
    properties={
        "role": "provider",
        "error_code": error_code,
        "error_field": error_field,
    },
)

# Provider Secret 创建
await emitter.emit(
    event_name="provider_secret_created",
    distinct_id=sha256_hash(provider_address),
    source="provider_service",
    properties={
        "role": "provider",
        "is_first_secret": is_first_secret,
    },
)

# Provider 健康退化
await emitter.emit(
    event_name="provider_health_degraded",
    distinct_id=sha256_hash(provider_address),
    source="provider_service",
    properties={
        "role": "provider",
        "provider_id": sha256_hash(provider_address),
        "service_id": service_id,
        "failure_count": failure_count,
        "reason": reason,
    },
)
```

---

## 7. Python SDK Telemetry：`sdk/python/synapse/telemetry.py`

```python
"""
SDK-side telemetry for events that only happen in SDK context
(not through frontend or gateway).

Only emits:
  - service_search_executed
  - invoke_started (SDK-initiated)

Final state events (invoke_completed/failed) are NOT emitted by SDK.
Gateway is the sole source of truth for billing events.
"""

from __future__ import annotations

import json
import logging
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("synapse.sdk.telemetry")


class SDKTelemetry:
    """Lightweight telemetry for the Synapse Python SDK."""

    def __init__(
        self,
        kafka_bootstrap_servers: Optional[str] = None,
        topic: str = "synapse.analytics.events",
        enabled: bool = True,
    ):
        self._enabled = enabled
        self._topic = topic
        self._producer = None
        self._bootstrap_servers = kafka_bootstrap_servers

    async def _ensure_producer(self):
        if self._producer is None and self._bootstrap_servers:
            try:
                from aiokafka import AIOKafkaProducer
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=self._bootstrap_servers,
                    value_serializer=lambda v: v.encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks=1,
                    compression_type="gzip",
                )
                await self._producer.start()
            except ImportError:
                logger.debug("aiokafka not installed, SDK telemetry disabled")
                self._enabled = False
            except Exception:
                logger.debug("Kafka unavailable, SDK telemetry disabled")
                self._enabled = False

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.lower().encode()).hexdigest()

    async def emit(
        self,
        event_name: str,
        wallet_address: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled:
            return
        await self._ensure_producer()
        if self._producer is None:
            return

        distinct_id = self._hash(wallet_address)
        event = {
            "event_id": str(uuid.uuid4()),
            "event_name": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "distinct_id": distinct_id,
            "source": "sdk",
            "properties": {
                "role": "consumer",
                "surface": "sdk",
                **(properties or {}),
            },
        }

        try:
            await self._producer.send_and_wait(
                topic=self._topic,
                value=json.dumps(event, default=str),
                key=distinct_id,
            )
        except Exception:
            logger.debug("SDK telemetry send failed", exc_info=True)

    async def close(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._producer = None
```

---

## 8. 隐私工具函数

```python
# src/services/analytics/privacy.py

import hashlib


def sha256_hash(value: str) -> str:
    """Hash a wallet address or other PII for analytics use."""
    return hashlib.sha256(value.lower().strip().encode("utf-8")).hexdigest()
```

所有 `distinct_id` 和 `provider_id` 字段在写入前必须经过此函数，不得传原始钱包地址。
