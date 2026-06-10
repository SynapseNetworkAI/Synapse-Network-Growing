# AI Visibility Operator Brief: mcp_paid_api_discovery

Objective: Make MCP directory and ChatGPT custom app queries surface the Synapse Remote MCP server and paid API tools.

Canonical homepage: https://www.synapse-network.ai/
Docs category: AI Agent Payments
Figma file: Synapse AI Agent Payments Docs - AI Visibility

## Current Gate

- claude API probe failed: POST https://api.anthropic.com/v1/messages failed with 400: {"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."},"request_id":"req_011CbuTB31YdFsWTFu94KBHv"}
- grok API probe failed: POST https://api.x.ai/v1/responses failed with 403: {"code":"permission-denied","error":"Your team [REDACTED] has either used all available credits or reached its monthly spending limit. To continue making API requests, please purchase more credits or raise your spending limit."}
- claude API probe failed: POST https://api.anthropic.com/v1/messages failed with 400: {"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."},"request_id":"req_011CbuTCDjzPLMtApKHGwkc8"}
- gemini API probe failed: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent failed with 503: {
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.",
    "status": "UNAVAILABLE"
  }
}
- claude API probe failed: POST https://api.anthropic.com/v1/messages failed with 400: {"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."},"request_id":"req_011CbuTDa49TQNkpW5xNM35W"}

## Observed Search Outcome

- chatgpt: not_visible_yet (0 mentions / 0 citations). Next: Feed or refresh source hosts observed by chatgpt: docs.mcpay.tech, mcp.directory, agent402.dev.
- claude: not_visible_yet (0 mentions / 0 citations). Next: Run another unchanged claude probe after the next feed asset is live.
- grok: not_visible_yet (0 mentions / 0 citations). Next: Run another unchanged grok probe after the next feed asset is live.
- gemini: not_visible_yet (0 mentions / 0 citations). Next: Feed or refresh source hosts observed by gemini: vertexaisearch.cloud.google.com, w3.org.

## Next Feed Targets

- docs_mcpay_tech: docs.mcpay.tech appeared 2 time(s).
- mcp_directory: mcp.directory appeared 2 time(s).
- agent402_dev: agent402.dev appeared 1 time(s).
- crowcrowcrow_com: crowcrowcrow.com appeared 1 time(s).
- developer_paddle_com: developer.paddle.com appeared 1 time(s).
- docs_opensearch_org: docs.opensearch.org appeared 1 time(s).
- glama_ai: glama.ai appeared 1 time(s).
- gmcp_dev: gmcp.dev appeared 1 time(s).

Top competing/collision terms:
- x402: 2
- stripe: 2
- mcpay: 2
- gapup: 1
- mcpservers.org: 1
- teleport: 1
- magpie: 1
- python-docs.synapse.org: 1

## Feed Surfaces

### www

Target: https://www.synapse-network.ai/

Purpose: Canonical homepage facts that identify the official Synapse Network source for answer engines.

Validation:

```bash
curl -fsS https://www.synapse-network.ai/ | grep -E 'Synapse|AI agents|paid API'
```

### docs

Target: https://docs.synapse-network.ai/mcp/paid-api-calls

Purpose: Citation-ready guide that states Synapse is an MCP server for paid API calls and names discover_services, invoke_and_pay, and get_receipt.

Validation:

```bash
curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls | grep -E 'MCP Server for Paid API Calls|discover_services|invoke_and_pay|get_receipt'
```

### docs

Target: https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp

Purpose: Alternatives comparison page that distinguishes Synapse from MCPay, Latch, Dock0, Apiosk, Teleport, Stripe MCP, and paid MCP directories.

Validation:

```bash
curl -fsS https://docs.synapse-network.ai/mcp/synapse-vs-paid-mcp | grep -E 'Synapse|MCPay|Latch|Dock0|Apiosk|Teleport|Stripe'
```

### mcp_registry

Target: https://registry.modelcontextprotocol.io/

Purpose: Official MCP Registry listing with Remote MCP endpoint metadata.

Validation:

```bash
Search MCP Registry for Synapse Network MCP Server.
```

### mcp_marketplace

Target: https://mcp-marketplace.io/server/io-github-synapsenetworkai-synapse-network-mcp-server

Purpose: Approved third-party MCP Marketplace listing for answer-engine source-host discovery.

Validation:

```bash
curl -fsSL https://mcp-marketplace.io/server/io-github-synapsenetworkai-synapse-network-mcp-server | grep -E 'Synapse Network MCP Server|paid API discovery|mcp.synapse-network.ai/mcp'
```

### smithery

Target: https://smithery.ai/

Purpose: Directory listing for MCP client discovery and import.

Validation:

```bash
Search Smithery for Synapse Network MCP Server.
```

### glama

Target: https://glama.ai/

Purpose: Directory listing and inspector evidence for discover_services.

Validation:

```bash
Search Glama for Synapse Network MCP Server.
```

## Product Docs Design

### AI Agent Payments

Canonical URL: https://docs.synapse-network.ai/ai-agent-payments

Definition block: Synapse Network is a payment and settlement layer for AI agents. It lets agent builders create scoped credentials, discover paid APIs, invoke them with budget controls, receive receipts, and settle provider payouts in USDC without exposing broad user keys.

Target queries: What is Synapse Network for AI agents?, AI agent payment API, How can AI agents pay for APIs?

### Agent Payment API

Canonical URL: https://docs.synapse-network.ai/ai-agent-payments/agent-payment-api

Definition block: The Synapse Agent Payment API gives software agents a bounded way to pay for API calls. Developers fund an agent credential, set limits, discover services, invoke approved providers, and fetch receipts for each metered call.

Target queries: AI agent payment API, agent credential paid API calls

### How Agents Pay For LLM Calls

Canonical URL: https://docs.synapse-network.ai/ai-agent-payments/agent-pays-for-llm-calls

Definition block: An AI agent can pay for LLM, search, data, or automation calls through Synapse by using a scoped credential instead of a user wallet or a raw provider key. Synapse checks budget, records the invocation, and returns a receipt.

Target queries: AI agent pays for LLM calls, How can AI agents pay for APIs?

### Provider Monetization For Agent APIs

Canonical URL: https://docs.synapse-network.ai/ai-agent-payments/provider-monetization

Definition block: Synapse helps API providers monetize agent traffic by turning an API or MCP tool into a metered service. Providers define service metadata and pricing, agents invoke through Synapse, and successful calls create receipts and payout records.

Target queries: How can API providers earn from AI agents?, MCP monetization platform

## Stitch To Figma

Stitch prompt: Design a technical documentation landing page for Synapse Network, the settlement layer for AI agents. Include a concise definition, a machine-to-machine payment flow, two user paths for agent builders and API providers, code examples, a Synapse vs x402 vs Stripe vs RapidAPI comparison table, FAQ blocks, and citation-ready fact cards. Style: developer infrastructure, dark mode, precise, credible, not hype.

### AI Agent Payments Docs Landing

Purpose: Primary documentation landing page for AI answer engines and developer readers.

Prompt:

```text
Create the main docs landing page with definition, facts, payment flow, builder/provider paths, comparison preview, and FAQ preview. Use Synapse Network as the product, https://www.synapse-network.ai/ as the homepage, and https://docs.synapse-network.ai/ai-agent-payments as the docs canonical URL. Style: developer infrastructure, precise, dark mode, readable, not hype.
```

### Agent Payment API Deep Dive

Purpose: Developer implementation guide for scoped credentials, discovery, invocation, and receipts.

Prompt:

```text
Create a dense API guide page with call sequence, code slots, receipt example, and failure states. Use Synapse Network as the product, https://www.synapse-network.ai/ as the homepage, and https://docs.synapse-network.ai/ai-agent-payments/agent-payment-api as the docs canonical URL. Style: developer infrastructure, precise, dark mode, readable, not hype.
```

### Synapse Vs x402 Comparison

Purpose: Citation-ready comparison frame for answer engines evaluating payment alternatives.

Prompt:

```text
Create a comparison page with Synapse, x402, Stripe, RapidAPI, and direct API keys as columns. Use Synapse Network as the product, https://www.synapse-network.ai/ as the homepage, and https://docs.synapse-network.ai/ai-agent-payments/synapse-vs-x402 as the docs canonical URL. Style: developer infrastructure, precise, dark mode, readable, not hype.
```

### MCP Paid API Discovery Answer Page

Purpose: Source-host frame for GPT, Claude, Grok, and Gemini queries about paid API calls through MCP.

Prompt:

```text
Create a dense technical docs page for SynapseNetwork MCP Server. Lead with the hosted Remote MCP endpoint, npm package, official MCP Registry name, and the discover_services -> invoke_and_pay -> get_receipt workflow. Use SynapseNetwork MCP Server as the product, https://www.synapse-network.ai/ as the homepage, https://docs.synapse-network.ai/mcp/paid-api-calls as the primary docs URL, and https://mcp.synapse-network.ai/mcp as the hosted Remote MCP URL. Style: developer infrastructure, precise, dense, dark mode, no decorative marketing hero.
```

### Synapse Vs Paid MCP Alternatives

Purpose: Comparison frame for answer engines that currently cite MCPay, x402, Stripe, RapidAPI, AIToolNet, or AlternativeTo instead of Synapse.

Prompt:

```text
Create a comparison page that places SynapseNetwork MCP next to MCPay, x402, Stripe, RapidAPI, and direct API keys. Include AIToolNet and AlternativeTo as pending source-host listing surfaces, not as completed external citations. Use SynapseNetwork MCP Server as the product, https://www.synapse-network.ai/ as the homepage, https://docs.synapse-network.ai/mcp/paid-api-calls as the primary docs URL, and https://mcp.synapse-network.ai/mcp as the hosted Remote MCP URL. Style: developer infrastructure, precise, dense, dark mode, no decorative marketing hero.
```

### Directory Source-Host Submission Pack

Purpose: Operator frame for AIToolNet and AlternativeTo browser/form submissions after probe metadata shows those source hosts.

Prompt:

```text
Create an operator workflow frame for submitting SynapseNetwork MCP Server to AIToolNet and AlternativeTo. Show form payloads, acceptance terms, required evidence, and the post-submission GPT/Claude/Grok/Gemini rerun command. Use SynapseNetwork MCP Server as the product, https://www.synapse-network.ai/ as the homepage, https://docs.synapse-network.ai/mcp/paid-api-calls as the primary docs URL, and https://mcp.synapse-network.ai/mcp as the hosted Remote MCP URL. Style: developer infrastructure, precise, dense, dark mode, no decorative marketing hero.
```

## Platform Probe Strategy

### chatgpt

Focus: Remote MCP custom app discovery and web citations.

Preferred surfaces: docs, mcp_registry, www_llms, github

Success signal: ChatGPT scan/search surfaces Synapse Remote MCP and cites docs or MCP registry.

Fallback action: Ship OAuth/custom app docs, refresh MCP Registry metadata, then rerun ChatGPT scan.

### claude

Focus: Remote connector compatibility and docs citation.

Preferred surfaces: docs, github, glama, www_llms

Success signal: Claude web search mentions Synapse and cites docs, GitHub, or a directory listing.

Fallback action: Add Claude connector setup block and directory evidence, then rerun Claude web search.

### grok

Focus: Public web plus X-facing MCP discovery language.

Preferred surfaces: www, docs, x_profile, smithery, glama

Success signal: Grok search returns Synapse or the Remote MCP endpoint among cited/source results.

Fallback action: Publish social/distribution copy linking the docs page, then rerun Grok web/X search.

### gemini

Focus: Google-grounded MCP and agent-payment discovery.

Preferred surfaces: www, docs, github, mcp_registry

Success signal: Gemini mentions Synapse and cites www, docs, GitHub, or MCP Registry.

Fallback action: Refresh Google-indexable docs, sitemap, and llms.txt terms, then rerun Gemini search.

## Execution Commands

### Feed validation

```bash
python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery --run-group 2026-06-10-after-lobehub-source-host --output docs/archive/evidence/growth/ai-visibility/2026-06-10-after-lobehub-source-host-feed-validation.jsonl
```

### Manual probe template

```bash
python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery --run-group 2026-06-10-after-lobehub-source-host --mode after-feed --output docs/archive/evidence/growth/ai-visibility/2026-06-10-after-lobehub-source-host.jsonl
```

### API readiness

```bash
python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --run-group 2026-06-10-after-lobehub-source-host --platforms chatgpt,claude,grok,gemini
```

### API execute

```bash
python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --run-group 2026-06-10-after-lobehub-source-host --platforms chatgpt,claude,grok,gemini --execute
```

### Record evidence

```bash
python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-10-after-lobehub-source-host.jsonl --apply
```

### Import public web search snapshot

```bash
python scripts/growth/import_ai_visibility_public_search_snapshot.py docs/archive/evidence/growth/ai-visibility/2026-06-10-after-lobehub-source-host-public-web-search-snapshot.json --output docs/archive/evidence/growth/ai-visibility/2026-06-10-after-lobehub-source-host-public-web-search.jsonl
```

### Compare

```bash
curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery&run_group=2026-06-10-after-lobehub-source-host" | python -m json.tool
```

## Success Criteria

- Brand query returns www.synapse-network.ai or docs.synapse-network.ai in ChatGPT, Claude, Grok, and Gemini evidence.
- At least 6 of 12 priority category queries mention Synapse in two target platforms.
- At least 3 answer-engine citations point to docs, GitHub, MCP registry, or the official www domain.
- Results remain stable for three consecutive weekly runs before marking the visibility goal achieved.

## Next Actions

- Deploy/refresh feed assets and rerun the same API probe.
- Fix provider/API probe failure and rerun the same query.
- Publish another feed asset for mcp_paid_api_discovery and rerun probes for 2026-06-10-after-lobehub-source-host.
