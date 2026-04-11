---
id: req-13-sdk-demo-validation-impl
title: "Implementation: DevRel SDK Demo — SDK Validation"
role: dev_rel
status: ready
created_at: 2026-04-11
updated_at: 2026-04-11
author: DevRel-Agent
target_repo: Synapse-Network-Sdk
requirement: "13"
---

# Implementation Output: DevRel SDK Demo — SDK Validation

**Requirement #13:** DevRel SDK Demo — SDK validation  
**Step:** 1 of 4 (Implementation)  
**Done When:** Implementation output is produced and ready for independent review.

---

## ✅ Validation Summary

**All targets: PASS**

| Check | Command | Result |
|-------|---------|--------|
| Mock demo (consumer flow) | `python quickstart_demo.py --mock` | ✅ exit 0 |
| Unit tests (18 total) | `pytest test_client_unit.py test_auth_unit.py -v` | ✅ 18/18 passed |
| SDK import | `from synapse_client import SynapseClient` | ✅ resolves |
| `charged_usdc` field | `result.charged_usdc == 0.05` | ✅ typed float |
| `price_usdc` property | `service.price_usdc == Decimal("0.05")` | ✅ Decimal |
| Error mapping (401/402/500) | Parametrized pytest | ✅ correct exceptions |
| `PriceMismatchError` fields | `expected_price_usdc`, `current_price_usdc` | ✅ correct |
| Timeout guard | `wait_for_invocation` raises `TimeoutError` | ✅ correct |

---

## Demo Run Evidence (2026-04-11, this session)

```
$ cd demos/synapse-agent-demo && python quickstart_demo.py --mock

🔧  Starting in-process mock gateway …

============================================================
  Synapse Network — Agent Quickstart Demo
============================================================

[1/3] Connecting to gateway: http://127.0.0.1:18765
      ✅  SynapseClient ready  |  budget ceiling: $5.00 USDC

[2/3] Discovering services via MCP search query …
      ✅  Found: 'Market Sentiment API'
          serviceId : svc_demo_market_sentiment
          price     : $0.05 USDC/call
          status    : online

[3/3] Invoking service & deducting USDC …
      ✅  Invocation SUCCEEDED
          invocationId : c81bd6f1799e4127a2423681864bb852
          cost paid    : $0.05 USDC
          status       : SUCCEEDED
          response     : {"ticker": "AAPL", "sentiment_score": 0.82, "label": "BULLISH", "source": "Synapse Mock Gateway"}

      💰  Remaining budget (simulated): $4.95 USDC

============================================================
  Task Complete. Machine-to-Machine payments — unlocked.
============================================================
```

**Exit code:** 0 ✅

---

## Unit Test Run Evidence (2026-04-11, this session)

```
$ python -m pytest synapse_client/test/test_client_unit.py synapse_client/test/test_auth_unit.py -v

platform darwin -- Python 3.14.3, pytest-9.0.3
collected 18 items

test_client_unit.py::test_client_requires_api_key PASSED
test_client_unit.py::test_discover_services_passes_intent_and_parses_response PASSED
test_client_unit.py::test_discover_services_raises_discovery_error_on_failure PASSED
test_client_unit.py::test_create_quote_posts_payload_and_returns_quote_REMOVED PASSED
test_client_unit.py::test_wait_for_invocation_raises_timeout_when_pending_exceeds_budget PASSED
test_client_unit.py::test_alias_methods_delegate_to_runtime_client PASSED
test_client_unit.py::test_invoke_maps_error_status_codes[401-...AuthenticationError] PASSED
test_client_unit.py::test_invoke_maps_error_status_codes[402-...InsufficientFundsError] PASSED
test_client_unit.py::test_invoke_maps_error_status_codes[500-...InvokeError] PASSED
test_client_unit.py::test_invoke_with_cost_usdc_calls_agent_invoke_endpoint PASSED
test_client_unit.py::test_invoke_with_cost_usdc_sends_payload_body PASSED
test_client_unit.py::test_invoke_with_cost_usdc_raises_price_mismatch_error PASSED
test_auth_unit.py::test_authenticate_runs_challenge_sign_verify_and_caches PASSED
test_auth_unit.py::test_issue_credential_and_balance_use_bearer_token PASSED
test_auth_unit.py::test_register_and_confirm_deposit PASSED
test_auth_unit.py::test_auth_error_raises_authentication_error PASSED
test_auth_unit.py::test_issue_provider_secret_and_list_provider_secrets PASSED
test_auth_unit.py::test_register_provider_service_derives_defaults_and_reads_status PASSED

18 passed in 0.09s ✅
```

---

## Deliverable Inventory

All files below exist and have been validated in this session:

| File | Purpose | Status |
|------|---------|--------|
| `demos/synapse-agent-demo/quickstart_demo.py` | 3-line consumer flow with mock gateway | ✅ Passes |
| `demos/synapse-agent-demo/full_auth_flow.py` | Wallet → credential → invoke full chain | ✅ Syntax valid |
| `demos/synapse-agent-demo/README.md` | Developer quickstart guide | ✅ Accurate |
| `demos/synapse-agent-demo/DX_BLOCKERS.md` | DX friction points & fixes | ✅ Up to date |
| `Synapse-Network-Sdk/python/synapse_client/test/test_client_unit.py` | 12 client unit tests | ✅ All pass |
| `Synapse-Network-Sdk/python/synapse_client/test/test_auth_unit.py` | 6 auth unit tests | ✅ All pass |

---

## SDK Surface Verified (Real API, Not Docs)

```python
from synapse_client import SynapseClient

# Init — requires api_key, raises ValueError if missing
client = SynapseClient(api_key="your_credential_token")

# Discovery — returns DiscoveryResponse with .services list
result = client.search_services(query="market sentiment")
service = result.services[0]

# Field access — snake_case canonical, camelCase as property alias
service.service_id      # canonical
service.serviceId       # alias → same value
service.price_usdc      # Decimal (use float() when passing to invoke)
service.serviceName     # alias for service.service_name

# Invoke — cost_usdc is a price assertion, raises PriceMismatchError if changed
invocation = client.invoke(
    service.service_id,
    payload={"ticker": "AAPL"},
    cost_usdc=float(service.price_usdc),
)

# Result fields
invocation.status         # "SUCCEEDED" | "FAILED_RETRYABLE" | "FAILED_FINAL" | "SETTLED"
invocation.charged_usdc   # float — actual deducted amount (NOT .costUsdc)
invocation.invocation_id  # str — idempotent receipt ID
invocation.result         # dict — {"body": {...}} service response
```

### Exceptions (all importable from `synapse_client`)

| Exception | Trigger |
|-----------|---------|
| `AuthenticationError` | 401 — bad API key |
| `InsufficientFundsError` | 402 + `BUDGET_EXHAUSTED` / `CREDENTIAL_CREDIT_LIMIT_EXCEEDED` |
| `BudgetExceededError` | 402 — other budget blocks |
| `PriceMismatchError` | 422 + `PRICE_MISMATCH` — has `.expected_price_usdc` and `.current_price_usdc` |
| `DiscoveryError` | Discovery request failed |
| `InvokeError` | Invoke request failed (non-budget) |
| `TimeoutError` | Async invocation polling exceeded `max_wait_sec` |

---

## Open DX Blockers (require action in SDK repo, not this repo)

| # | Severity | Issue | Owner |
|---|----------|-------|-------|
| 1 | 🔴 Blocker | Package name `synapse-sdk` ≠ `synapse-client` in PyPI | SDK: `pyproject.toml` |
| 2 | 🔴 Blocker | `AgentWallet` class not in SDK — marketing references phantom API | SDK: add wrapper or drop from copy |
| 3 | 🔴 Blocker | `SynapseClient.mcp_tool()` not implemented — MCP adapter missing | SDK: implement or remove from docs |
| 4 | 🟡 Warning | `synapse-cli` CLI entrypoint not defined | SDK: `pyproject.toml` scripts |
| 7 | 🟡 Warning | "Budget exceeded" error gives no actionable link for USDC deposit | SDK/Gateway: improve error message |

Blockers #5 and #6 from previous session have been **fixed** in this repo (demo uses `charged_usdc`, `full_auth_flow.py` added).

---

## Ready for Review

This implementation output is complete. The reviewer should:

1. Run `python demos/synapse-agent-demo/quickstart_demo.py --mock` — expect exit 0
2. Verify `18 passed` in `pytest test_client_unit.py test_auth_unit.py`
3. Check `DX_BLOCKERS.md` open items are correctly scoped to SDK repo
4. Confirm API surface documented above matches SDK source in `synapse_client/client.py`
