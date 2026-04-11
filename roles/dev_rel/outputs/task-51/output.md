✅ **Done.** Here's the complete delivery:

---

## What was built

**`demos/synapse-agent-demo/quickstart_demo.py`** — Runnable end-to-end demo:
```bash
pip install synapse-client
python quickstart_demo.py --mock   # zero deps, works right now
```
Verified output: `SUCCEEDED | $0.05 USDC deducted | $4.95 remaining`

**`demos/synapse-agent-demo/DX_BLOCKERS.md`** — Fix record with 5 issues:

| # | Issue | Severity |
|---|-------|----------|
| 1 | `pip install synapse-sdk` doesn't exist — real package is `synapse-client` | 🔴 Blocker |
| 2 | `AgentWallet` class missing — SDK uses `SynapseClient` | 🔴 Blocker |
| 3 | `wallet.mcp_tool()` not implemented in SDK | 🔴 Blocker |
| 4 | `synapse-cli` CLI entrypoint not defined | 🟡 Warning |
| 5 | No API key provisioning guide | 🟡 Warning |

**Root cause of all 3 blockers:** Marketing-facing API surface (`AgentWallet`, `synapse-sdk`, `mcp_tool`) was written ahead of SDK implementation. SDK team needs to either build the facade or align all copy to the real API.