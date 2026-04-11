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

## 🔑 Getting an API Key (full auth flow)

If you're starting from a private key (no existing credential):

```bash
pip install "synapse-client[dev]"   # adds eth-account for wallet auth
python full_auth_flow.py --dev-key  # local dev with Hardhat default key
```

This runs the full chain: wallet identity → gateway challenge/verify → issue credential token → discover → invoke.

## 📋 The Actual 3-Line Pattern

```python
from synapse_client import SynapseClient

client   = SynapseClient(api_key="your_key")                    # 1. create wallet
services = client.search_services(query="market sentiment")     # 2. MCP discovery
result   = client.invoke(services.services[0].service_id,       # 3. invoke + pay
               payload={"symbol": "ETH"},
               cost_usdc=float(services.services[0].price_usdc))
print(result.status, result.charged_usdc)                       # SUCCEEDED  0.01
```

> **Field names that matter:**  
> - `service.service_id` (not `.id`) — canonical service identifier  
> - `service.price_usdc` — `Decimal` property from `service.pricing.amount`  
> - `result.charged_usdc` (not `.costUsdc`) — amount deducted on success

## 🐛 DX Issues Found & Fixed

See [`DX_BLOCKERS.md`](./DX_BLOCKERS.md) for the full fix record. Summary:

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | Package name: `synapse-sdk` ≠ `synapse-client` | 🔴 Blocker | ⚠️ Open (SDK) |
| 2 | `AgentWallet` class missing from SDK | 🔴 Blocker | ⚠️ Open (SDK) |
| 3 | `wallet.mcp_tool()` not implemented | 🔴 Blocker | ⚠️ Open (SDK) |
| 4 | `synapse-cli` CLI not defined | 🟡 Warning | ⚠️ Open (SDK) |
| 5 | No API key provisioning guide | 🟡 Warning | ✅ Fixed (`full_auth_flow.py`) |
| 6 | `result.costUsdc` bug (should be `charged_usdc`) | 🔴 Blocker | ✅ Fixed (demo patched) |

