---
id: ai_visibility_probe_runbook
title: AI Visibility Probe Runbook
role: growth_lead
status: ready
created_at: 2026-06-04
updated_at: 2026-06-04
author: codex
target_repo: Synapse-Network-Growing
---

# AI Visibility Probe Runbook

Use this runbook after publishing a content feed experiment, for example the
`AI Agent Payments` docs and `www` landing pages. The goal is to record real
ChatGPT, Claude, and Grok answer-engine evidence without confusing it with local
page validation.

## What Counts As Evidence

External visibility evidence is a captured answer from an answer engine. A row
can count as `synapse_cited=true` only when the answer cites or links to an
official Synapse surface such as:

1. `https://www.synapse-network.ai/`
2. `https://www.synapse-network.ai/ai-agent-payments`
3. `https://docs.synapse-network.ai/ai-agent-payments`
4. `https://github.com/SynapseNetworkAI/...`
5. An official MCP Registry or directory listing.

Local validation rows such as `www_local_validation` and `docs_local_validation`
prove crawl assets are ready. They do not prove ChatGPT, Claude, or Grok can
find Synapse, and they do not increase external `cited_count`.

## Baseline Queries

Run the same query set for each platform and record one row per query/platform:

1. `What is Synapse Network for AI agents?`
2. `AI agent payment API`
3. `How can AI agents pay for APIs?`
4. `MCP server for paid API calls`
5. `AI agent USDC settlement layer`
6. `Synapse Network vs x402`
7. `How can API providers earn from AI agents?`

Recommended platforms:

1. `chatgpt`
2. `claude`
3. `grok`

Optional platforms:

1. `perplexity`
2. `google_ai`
3. `bing_copilot`
4. `gemini`

## Probe File

Create a JSONL file under `docs/archive/evidence/growth/ai-visibility/`.

Example:

```jsonl
{"query":"AI agent payment API","platform":"chatgpt","answer_summary":"ChatGPT described agent payment APIs but did not mention Synapse.","synapse_mentioned":false,"synapse_cited":false,"cited_urls":[],"competitor_mentions":["x402"],"missing_facts":["Synapse AI Agent Payments page not cited."],"next_action":"Submit live docs URL to indexing and feed GitHub README answer block.","feed_key":"agent_payment_category_pages","run_group":"2026-06-18-after-docs-launch","result_rank":0,"evidence_url":"docs/archive/evidence/growth/ai-visibility/chatgpt-ai-agent-payment-api.png","metadata":{"mode":"manual","answer_engine":"ChatGPT search"}}
{"query":"Synapse Network vs x402","platform":"claude","answer_summary":"Claude cited the Synapse docs comparison page.","synapse_mentioned":true,"synapse_cited":true,"cited_urls":["https://docs.synapse-network.ai/ai-agent-payments/synapse-vs-x402"],"competitor_mentions":["x402"],"missing_facts":[],"next_action":"Keep comparison page fresh and add third-party directory mentions.","feed_key":"agent_payment_category_pages","run_group":"2026-06-18-after-docs-launch","result_rank":1,"evidence_url":"docs/archive/evidence/growth/ai-visibility/claude-synapse-vs-x402.png","metadata":{"mode":"manual","answer_engine":"Claude web search"}}
```

## Dry Run

Validate the file first:

```bash
python scripts/growth/record_ai_visibility_probe.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch.jsonl
```

The output should show `status=succeeded`, `dry_run=true`, platforms, feed keys,
and run groups. If a row says `synapse_cited=true`, it must include either
`cited_urls` or `evidence_url`.

## Apply

Write validated rows into Growing:

```bash
python scripts/growth/record_ai_visibility_probe.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch.jsonl \
  --apply
```

By default the script writes to `http://localhost:9700/api`. Override with:

```bash
python scripts/growth/record_ai_visibility_probe.py probe.jsonl \
  --api-base http://localhost:9600/api \
  --apply
```

## Compare Results

Open `/growth?tab=ai-visibility` or use the API:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=agent_payment_category_pages&run_group=2026-06-18-after-docs-launch" \
  | python -m json.tool
```

Success criteria for a feed experiment:

1. `external_checks_count` includes real answer-engine rows.
2. `missing_platforms` shrinks for `chatgpt`, `claude`, and `grok`.
3. `mentioned_count` and `cited_count` improve against the previous run group.
4. At least one cited URL points to `www`, docs, GitHub, MCP Registry, or a
   trusted directory.
5. Results remain stable across three weekly runs before marking the goal as
   achieved.
