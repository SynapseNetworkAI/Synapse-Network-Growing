---
id: dx_blockers_sdk_quickstart
title: DX Fix Record — SDK 3-Line Quickstart Validation
role: dev_rel
status: ready
created_at: 2026-04-11
updated_at: 2026-04-11
author: DevRel-Agent
target_repo: Synapse-Network-Sdk
---

# DX Blockers — SDK Quickstart End-to-End Validation

Validated: `pip install synapse-client` → 3-line consumer flow (discover → invoke → deduct)

---

## 🔴 Blocker #1 — Package Name Mismatch

**Friction:** All marketing copy, README drafts, and task specs reference `pip install synapse-sdk`.  
**Reality:** The actual PyPI-publishable package is named **`synapse-client`**.

```bash
# ❌ What marketing says (does NOT exist on PyPI)
pip install synapse-sdk

# ✅ What actually works
pip install synapse-client
```

**Fix Applied (this repo):** All demo scripts and README updated to use `synapse-client`.  
**Required Action (SDK repo):** Either rename the package in `pyproject.toml` to `synapse-sdk`, OR update all marketing copy to use `synapse-client`. **Pick one and lock it.**

---

## 🔴 Blocker #2 — `AgentWallet` Class Does Not Exist

**Friction:** The hero demo script (`scripts/hero_demo_script.md`) and the SDK README use:
```python
from synapse_client import AgentWallet
wallet = AgentWallet.connect(budget=5.00)
```

**Reality:** No `AgentWallet` class exists in `synapse_client`. The real entry point is:
```python
from synapse_client import SynapseClient
client = SynapseClient(api_key="your_key")
```

**Fix Applied (this repo):** Demo script uses `SynapseClient` directly.  
**Required Action (SDK repo):** Add an `AgentWallet` thin wrapper to `synapse_client/__init__.py` as a convenience alias with `connect(budget=...)` factory if the marketing API is the intended DX — or update all docs to drop `AgentWallet`.

---

## 🔴 Blocker #3 — `wallet.mcp_tool()` Does Not Exist

**Friction:** Hero demo shows:
```python
tools = [wallet.mcp_tool("market_data_api")]
agent = CodeAgent(tools=tools)
```

**Reality:** `SynapseClient` has no `.mcp_tool()` method. MCP integration is not yet surfaced in the Python SDK.

**Fix Applied (this repo):** Demo shows the real flow: `search_services()` → `invoke()` directly.  
**Required Action (SDK repo):** Implement `SynapseClient.as_mcp_tool(service_id)` or equivalent that wraps a discovered service as an MCP-compatible tool callable. This is the #1 DX improvement for agent framework integration.

---

## 🟡 Warning #4 — `synapse-cli init` Command Does Not Exist

**Friction:** Hero demo script references:
```bash
synapse-cli init --budget 5.00
```

**Reality:** No CLI entrypoint is defined in `pyproject.toml` or the SDK.

**Required Action (SDK repo):** Either add a `[project.scripts]` entry to `pyproject.toml` for `synapse-cli`, or remove all CLI references from demo scripts.

---

## 🟡 Warning #5 — No `SYNAPSE_API_KEY` Provisioning Flow

**Friction:** `SynapseClient` requires an API key on init, but there is no documented flow to generate one from scratch (no `SynapseAuth.register()` demo, no link to gateway admin).

**Fix Applied (this repo):** Demo gracefully fails with a clear error message + suggestion to use `--mock` mode.  
**Required Action (Gateway/Docs):** Add "Getting Your API Key" section to the SDK README pointing to the admin console or `SynapseAuth` credential issuance flow.

---

## ✅ Verified Working Flow (3 lines, real SDK)

```python
from synapse_client import SynapseClient                        # Line 1

client = SynapseClient(api_key="your_key")                      # Line 2
services = client.search_services(query="market sentiment")     # Line 3 — discover

service = services.services[0]
result = client.invoke(                                          # Line 4 — invoke + pay
    service.serviceId,
    payload={"ticker": "AAPL"},
    cost_usdc=float(service.price_usdc),
)
print(result.status, result.costUsdc)  # → SUCCEEDED  0.05
```

Runnable demo (mock gateway, zero dependencies beyond SDK):
```bash
pip install synapse-client
python demos/synapse-agent-demo/quickstart_demo.py --mock
```

---

## Summary Table

| # | Severity | Issue | Fix Location |
|---|----------|-------|-------------|
| 1 | 🔴 Blocker | Package name `synapse-sdk` vs `synapse-client` | SDK `pyproject.toml` or all marketing copy |
| 2 | 🔴 Blocker | `AgentWallet` class missing | SDK: add wrapper or update docs |
| 3 | 🔴 Blocker | `wallet.mcp_tool()` not implemented | SDK: implement MCP adapter |
| 4 | 🟡 Warning | `synapse-cli` CLI not defined | SDK `pyproject.toml` scripts |
| 5 | 🟡 Warning | No API key provisioning guide | Docs / README |
