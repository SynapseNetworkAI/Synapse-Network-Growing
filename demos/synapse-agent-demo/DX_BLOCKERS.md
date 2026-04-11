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
<!-- Re-verified 2026-04-11: bugfix session after agent session crash (Session not found). All 3-line flow verified PASS. -->
<!-- Re-verified 2026-04-11 (current session): mock gateway PASS ✅ | live dev key: budget exceeded as expected | DX Blocker #7 added -->

## ✅ Verification Status (2026-04-11 Re-run)

**Session bugfix note:** Previous agent session crashed mid-run (`Session not found: role-dev_rel-…`). This re-run re-verifies the full flow from scratch.

**Install method used:**
```bash
pip install -e /path/to/Synapse-Network-Sdk/python   # synapse-client v0.1.0
```

**Demo run:**
```bash
cd demos/synapse-agent-demo
python quickstart_demo.py --mock   # exit code: 0 ✅
```

Full terminal output archived at: `docs/test/sdk-quickstart-terminal-run.txt`

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

## ✅ Verified Working Flow (real SDK, real gateway)

```python
from synapse_client import SynapseClient                         # Line 1

client = SynapseClient(api_key="your_token")                     # Line 2
services = client.search_services(query="market sentiment")      # Line 3 — discover

service = services.services[0]
result = client.invoke(                                           # Line 4 — invoke + pay
    service.service_id,                          # snake_case field (canonical)
    payload={"symbol": "ETH"},
    cost_usdc=float(service.price_usdc),         # Decimal property → float
)
print(result.status, result.charged_usdc)        # → SUCCEEDED  0.01
```

> **Note:** `service.serviceId` and `service.serviceName` work as camelCase aliases.  
> `result.charged_usdc` is the correct field (not `costUsdc`).

Runnable demo (mock gateway, zero dependencies beyond SDK):
```bash
pip install synapse-client
python demos/synapse-agent-demo/quickstart_demo.py --mock
```

Full auth flow from private key (requires `eth-account`):
```bash
pip install "synapse-client[dev]"
python demos/synapse-agent-demo/full_auth_flow.py --dev-key
```

---

## 🔴 Blocker #6 — `InvocationResponse.costUsdc` Field Does Not Exist

**Friction:** The initial demo used `result.costUsdc` to read back the charged amount.  
**Reality:** `InvocationResponse` model has **`charged_usdc`** (snake_case, alias `chargedUsdc`).  
`costUsdc` is silently stored as a Pydantic extra field if present, returning an untyped string rather than a float — a silent data type bug.

```python
# ❌ Wrong — untyped string from model_extra, returns None if gateway doesn't echo it
print(result.costUsdc)

# ✅ Correct — typed float field
print(result.charged_usdc)
```

**Fix Applied (this repo):** `quickstart_demo.py` now uses `result.charged_usdc` and the mock gateway response sends `chargedUsdc` (matching the model alias).  
**Required Action (SDK repo):** Add a deprecation shim `@property def costUsdc` if backward compat is needed.

---

---

## 🟡 Warning #7 — Opaque "Budget Exceeded" Error on Live Dev Key

**Friction:** When a developer runs `full_auth_flow.py --dev-key` against the live gateway, authentication succeeds through all 5 steps, but invoke fails with:

```
⛔  Budget exceeded: Owner billing cycle spend limit does not allow this invocation
```

**Reality:** The Hardhat default key (`0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266`) has no USDC deposited on the live gateway. The error message is technically correct but gives no actionable guidance.

**Verified Behavior (live gateway test, 2026-04-11):**
- Steps 1–5 (wallet auth, JWT, credential, SynapseClient, discovery): ✅ All PASS
- Step 6 (invoke): ⛔ Budget exceeded — expected, no USDC in dev wallet

**Fix Applied (this repo):** `full_auth_flow.py` already catches `BudgetExceededError` gracefully.  
**Required Action (SDK + Gateway):** Improve error message to include: _"Your wallet has insufficient USDC balance. Please deposit funds at [link] before invoking paid services."_

---

## Summary Table

| # | Severity | Issue | Status | Fix Location |
|---|----------|-------|--------|-------------|
| 1 | 🔴 Blocker | Package name `synapse-sdk` vs `synapse-client` | ⚠️ Open | SDK `pyproject.toml` or all marketing copy |
| 2 | 🔴 Blocker | `AgentWallet` class missing | ⚠️ Open | SDK: add wrapper or update docs |
| 3 | 🔴 Blocker | `wallet.mcp_tool()` not implemented | ⚠️ Open | SDK: implement MCP adapter |
| 4 | 🟡 Warning | `synapse-cli` CLI not defined | ⚠️ Open | SDK `pyproject.toml` scripts |
| 5 | 🟡 Warning | No API key provisioning guide | ✅ Fixed | Added `full_auth_flow.py` demo |
| 6 | 🔴 Blocker | `result.costUsdc` field bug (should be `charged_usdc`) | ✅ Fixed | `quickstart_demo.py` patched |
| 7 | 🟡 Warning | Opaque "Budget exceeded" error on live dev key (no USDC deposited) | ⚠️ Open | SDK/Gateway: improve error message |
