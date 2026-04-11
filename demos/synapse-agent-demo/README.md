---
id: synapse_agent_demo_readme
title: Synapse Agent Demo README
role: dev_rel
status: ready
created_at: 2026-04-03
updated_at: 2026-04-11
author: AI-DevRel
target_repo: Synapse-Network-Sdk
---
# synapse-agent-demo

End-to-end demo of the Synapse Network Python SDK. Shows the 3-step consumer flow: **create client → discover service → invoke + pay USDC**.

> **Note (Harness Engineering Principle):**
> The official Client SDK documentation is NOT duplicated here. Single source of truth remains in the SDK repo.
> 👉 [Synapse-Network-Sdk README](../../../Synapse-Network-Sdk/README.md)

---

## ⚡ Quickstart (60 seconds, no gateway needed)

```bash
pip install synapse-client          # actual package name

cd demos/synapse-agent-demo
python quickstart_demo.py --mock    # runs against in-process mock gateway
```

Expected output:
```
✅  SynapseClient ready  |  budget ceiling: $5.00 USDC
✅  Found: 'Market Sentiment API'  |  price: $0.05 USDC/call
✅  Invocation SUCCEEDED  |  cost paid: $0.05  |  remaining: $4.95 USDC
```

## 🔌 Against a Live Gateway

```bash
export SYNAPSE_API_KEY=your_credential_key
export SYNAPSE_GATEWAY=https://your-gateway-url
python quickstart_demo.py
```

## 📋 The Actual 3-Line Pattern

```python
from synapse_client import SynapseClient

client   = SynapseClient(api_key="your_key")                    # 1. create wallet
services = client.search_services(query="market sentiment")     # 2. MCP discovery
result   = client.invoke(services.services[0].serviceId,        # 3. invoke + pay
               payload={"ticker": "AAPL"},
               cost_usdc=float(services.services[0].price_usdc))
```

## 🐛 DX Issues Found & Fixed

See [`DX_BLOCKERS.md`](./DX_BLOCKERS.md) for the full fix record. Summary:

| # | Issue | Severity |
|---|-------|----------|
| 1 | Package name: `synapse-sdk` ≠ `synapse-client` | 🔴 Blocker |
| 2 | `AgentWallet` class missing from SDK | 🔴 Blocker |
| 3 | `wallet.mcp_tool()` not implemented | 🔴 Blocker |
| 4 | `synapse-cli` CLI not defined | 🟡 Warning |
| 5 | No API key provisioning guide in docs | 🟡 Warning |
