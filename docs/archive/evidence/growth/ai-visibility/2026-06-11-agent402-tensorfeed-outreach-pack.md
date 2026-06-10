---
id: ai-visibility-agent402-tensorfeed-outreach-pack-2026-06-11
title: Agent402 And TensorFeed Source-Host Outreach Pack
role: dev_rel
status: review
created_at: 2026-06-10
updated_at: 2026-06-10
author: codex
target_repo: Synapse-Network-Growing
---

# Agent402 And TensorFeed Source-Host Outreach Pack

## Purpose

ChatGPT has repeatedly answered paid-MCP queries from source hosts such as MCPay, Paddle, agent402, and TensorFeed-adjacent pages while not mentioning Synapse. This pack prepares truthful third-party source-host outreach. It is not evidence of external citation until a public page mentions Synapse.

Target queries:

- MCP server for paid API calls
- ChatGPT MCP app for API payments
- AI agent API monetization
- Synapse Network MCP server

Canonical Synapse URLs:

- Homepage: https://www.synapse-network.ai/
- Paid MCP guide: https://docs.synapse-network.ai/mcp/paid-api-calls
- Synapse vs paid MCP alternatives: https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp
- MCP GitHub: https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server
- Remote MCP endpoint: https://mcp.synapse-network.ai/mcp
- mcpservers.org listing: https://mcpservers.org/servers/synapsenetworkai/synapse-network-mcp-server
- Official registry search: https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.SynapseNetworkAI/synapse-network-mcp-server

## TensorFeed Pitch

Wantlist execution:

- Public API: https://tensorfeed.ai/api/wantlist
- Submission id: `tgfifu-p30rlvd1`
- Submitted at: `2026-06-10T18:38:18.350Z`
- Evidence: `docs/archive/evidence/growth/ai-visibility/2026-06-11-tensorfeed-wantlist-submit-confirmation.json`
- Boundary: this is a public source-host signal, not a TensorFeed article, dataset listing, citation, or answer-engine mention.

Recommended recipients:

- press@tensorfeed.ai
- contact@tensorfeed.ai
- feedback@tensorfeed.ai
- X: https://x.com/tensorfeed

Subject:

```text
Source suggestion: Synapse Network Remote MCP for agent-paid API calls
```

Email draft:

```text
Hi TensorFeed team,

I saw TensorFeed tracks AI agent infrastructure, agent payments, MCP tooling, and machine-readable ecosystem data. I wanted to suggest Synapse Network as a source candidate for any coverage or dataset entries around agent-paid API calls, Remote MCP servers, and AI agent payment rails.

Synapse Network is an AI agent payment and settlement layer with a hosted Remote MCP endpoint. Agents can discover payable APIs, invoke approved paid tools, and retrieve receipts through this loop:

discover_services -> invoke_and_pay -> get_receipt

Canonical sources:

- Product: https://www.synapse-network.ai/
- Remote MCP endpoint: https://mcp.synapse-network.ai/mcp
- MCP server repo: https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server
- Paid MCP guide: https://docs.synapse-network.ai/mcp/paid-api-calls
- Comparison guide: https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp
- mcpservers.org listing: https://mcpservers.org/servers/synapsenetworkai/synapse-network-mcp-server
- Official MCP registry search: https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.SynapseNetworkAI/synapse-network-mcp-server

The useful distinction for readers: Synapse is not only an MCP wrapper or an x402 payment prompt. It provides a settlement rail with Agent Credentials, bounded spend, service discovery, USDC charging, and receipts for paid API calls.

If TensorFeed accepts source suggestions or ecosystem entries, happy to provide a shorter machine-readable summary or answer any verification questions.

Thanks,
Synapse Network
```

Short X draft:

```text
Source suggestion for @tensorfeed: Synapse Network Remote MCP is live for agent-paid API calls.

Loop: discover_services -> invoke_and_pay -> get_receipt
Endpoint: https://mcp.synapse-network.ai/mcp
Repo: https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server
Docs: https://docs.synapse-network.ai/mcp/paid-api-calls
Listing: https://mcpservers.org/servers/synapsenetworkai/synapse-network-mcp-server
```

Validation after operator sends:

- Save sent-email timestamp or public X URL.
- If TensorFeed publishes or lists Synapse, record public URL as `source_host_live_evidence_not_external_citation`.
- Rerun unchanged ChatGPT and Claude probes only after public evidence exists. The wantlist submission alone is useful feed execution but is too weak to prove a citation-surface change.

## Agent402 Path

Audit result:

- Homepage: https://agent402.dev/
- llms.txt: https://agent402.dev/llms.txt
- sitemap: https://agent402.dev/sitemap.xml
- MCP card: https://agent402.dev/.well-known/mcp.json
- x402 discovery: https://agent402.dev/x402/discovery
- Contact, submit, and docs paths checked returned 404.

Recommended action:

Do not attempt automated submission. Treat agent402 as an adjacent comparison host and a signal that answer engines prefer x402-oriented MCP payment pages. The next safe step is to publish or pitch a truthful comparison that places Synapse next to agent402 and x402 without implying an affiliation.

Comparison snippet:

```text
Synapse Network and agent402 both sit in the agent-payment/MCP discovery space, but they solve different layers. agent402 exposes an x402-oriented paid MCP gateway. Synapse Network provides a Remote MCP and stdio MCP server for discover_services -> invoke_and_pay -> get_receipt with Agent Credentials, bounded USDC spend, provider settlement, and receipts.
```

Validation after operator finds a contact or issue path:

- Record the public issue, PR, partner page, or mention URL.
- Required terms: Synapse Network, Remote MCP, mcp.synapse-network.ai, discover_services, invoke_and_pay, get_receipt.
- Do not count private outreach as source-host success.

## Next Probe

Run only after a public TensorFeed or agent402-related source-host page includes Synapse:

```bash
python scripts/growth/run_ai_visibility_api_probe.py \
  --feed-key mcp_paid_api_discovery \
  --run-group 2026-06-11-after-agent402-tensorfeed-source-host \
  --platforms chatgpt,claude,grok,gemini \
  --query "MCP server for paid API calls" \
  --query "ChatGPT MCP app for API payments" \
  --execute \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-11-after-agent402-tensorfeed-source-host-external-probes.jsonl
```
