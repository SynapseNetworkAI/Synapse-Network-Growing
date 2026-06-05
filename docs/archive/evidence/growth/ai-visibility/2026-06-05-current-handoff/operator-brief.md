# Synapse AI Visibility Optimization Brief

Generated: 2026-06-05T02:12:56.416167+00:00
Official homepage: https://www.synapse-network.ai/
Objective: Make Synapse Network discoverable and citable in ChatGPT, Claude, and Grok for AI agent payments, paid API calls, MCP tooling, and provider monetization queries.

## Current Gate

- Status: optimizing
- Stable positive runs: 0/3
- Target platforms: chatgpt, claude, grok
- Recommended feed: brand_disambiguation_www

## Blockers

- Official https://docs.synapse-network.ai/mcp/paid-api-calls result was not visible in the inspected top web search results.
- Unrelated Synapse Network crypto/fundraising results still compete with the official https://www.synapse-network.ai/ canonical identity.
- Production docs and www llms feed need to publish the MCP paid API calls guide before the next answer-engine probe.
- Publish MCP paid API docs and www llms feed, submit or verify MCP directory listings, then rerun public web plus ChatGPT/Claude/Grok probes with screenshot evidence.
- Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.
- Production https://www.synapse-network.ai/llms.txt does not yet include the MCP paid API calls guide or remote MCP endpoint.
- Local deploy runner cannot access fabled-archive-494108-k5 until gcloud credentials are refreshed with gcloud auth login or an accessible account is selected.
- Refresh gcloud credentials for cliff@synapse-network.ai or select an authenticated account with fabled-archive-494108-k5 access, then rerun Growing local release tasks for docs-front and user-front staging before promoting production.
- Fewer than three stable positive external runs have been recorded.
- Official https://www.synapse-network.ai/ result was not visible in the inspected top web search results for the category query.
- AI Agent Payments and MCP paid API pages need more indexing time and external citation surfaces.
- Publish MCP paid API docs/llms updates, submit official MCP directory surfaces, and rerun public web plus GPT/Claude/Grok probes after recrawl.

## Next Actions

- Resolve latest validation blockers before the next external probe.
- Run and record missing platform probes: grok.
- Publish MCP paid API docs and www llms feed, submit or verify MCP directory listings, then rerun public web plus ChatGPT/Claude/Grok probes with screenshot evidence.
- Publish MCP paid API docs/llms updates, submit official MCP directory surfaces, and rerun public web plus GPT/Claude/Grok probes after recrawl.
- Enable the Codex Chrome Extension in the selected Chrome profile or provide OPENAI_API_KEY, ANTHROPIC_API_KEY, and XAI_API_KEY, then run the generated GPT/Claude/Grok probe template.
- Official https://www.synapse-network.ai/ result was not visible in the inspected top web search results for the category query.
- AI Agent Payments and MCP paid API pages need more indexing time and external citation surfaces.
- No real ChatGPT/Claude/Grok answer screenshots were captured in this run.
- Codex Chrome Extension unavailable in the selected Chrome profile, and API keys were not available for paid answer-engine probes.
- Complete missing external probes: claude, grok.
- Official https://docs.synapse-network.ai/mcp/paid-api-calls result was not visible in the inspected top web search results.
- Unrelated Synapse Network crypto/fundraising results still compete with the official https://www.synapse-network.ai/ canonical identity.

## Feed Cycle Matrix

### brand_disambiguation_www

- Status: feed_blocked
- Latest run: 2026-06-05-brand-current-validation-refresh
- External platforms: -
- Missing platforms: chatgpt, claude, grok
- Mention/citation count: 0/0
- Feed validation: `python scripts/growth/run_ai_visibility_feed_validation.py --feed-key brand_disambiguation_www --run-group 2026-06-05-brand_disambiguation_www-weekly --output docs/archive/evidence/growth/ai-visibility/2026-06-05-brand_disambiguation_www-weekly-feed-validation.jsonl`
- API readiness: `python scripts/growth/run_ai_visibility_api_probe.py --feed-key brand_disambiguation_www --run-group 2026-06-05-brand_disambiguation_www-weekly --platforms chatgpt,claude,grok`
- Compare: `curl -fsS 'http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=brand_disambiguation_www&run_group=2026-06-05-brand_disambiguation_www-weekly' | python -m json.tool`

### agent_payment_category_pages

- Status: partial_external_probe
- Latest run: 2026-06-05-api-probe-post-hotfix
- External platforms: chatgpt
- Missing platforms: claude, grok
- Mention/citation count: 2/0
- Feed validation: `python scripts/growth/run_ai_visibility_feed_validation.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-feed-validation.jsonl`
- API readiness: `python scripts/growth/run_ai_visibility_api_probe.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --platforms chatgpt,claude,grok`
- Compare: `curl -fsS 'http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=agent_payment_category_pages&run_group=2026-06-05-agent_payment_category_pages-weekly' | python -m json.tool`

### mcp_paid_api_discovery

- Status: feed_blocked
- Latest run: 2026-06-05-public-web-search-synapse-mcp-validation
- External platforms: -
- Missing platforms: chatgpt, claude, grok
- Mention/citation count: 0/0
- Feed validation: `python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-mcp_paid_api_discovery-weekly --output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp_paid_api_discovery-weekly-feed-validation.jsonl`
- API readiness: `python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-mcp_paid_api_discovery-weekly --platforms chatgpt,claude,grok`
- Compare: `curl -fsS 'http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery&run_group=2026-06-05-mcp_paid_api_discovery-weekly' | python -m json.tool`

## Product Docs And Design

- Docs category: AI Agent Payments
- Stitch/Figma file: Synapse AI Agent Payments Docs - AI Visibility
- Product docs and Figma handoff remain source-backed by the Growing AI Visibility module.

## Release Unblock

- Status: blocked_until_gcloud_auth
- Target commit: d8b5371e11fea2d962dcc656b9b8d08d0c1379d9
- Services: docs-front, user-front
- Release snapshot: blocked
- Release readiness: ready_for_release_runner_after_gcloud_auth
- External probe gate: blocked_until_feed_ready
- Ready platforms: chatgpt, claude
- Missing platforms: grok
- Partial probe command: `python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-current-operator-brief-external-probe --platforms chatgpt,claude`
- Production feed validation must pass before GPT/Claude/Grok probes count as success evidence.
