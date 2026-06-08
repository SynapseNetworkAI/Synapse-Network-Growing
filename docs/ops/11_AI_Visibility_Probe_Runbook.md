---
id: ai_visibility_probe_runbook
title: AI Visibility Probe Runbook
role: growth_lead
status: ready
created_at: 2026-06-04
updated_at: 2026-06-05
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

## Platform Probe Notes

Use the same user question on every platform. Do not improve the prompt for one
platform and compare it against a weaker prompt on another platform.

1. ChatGPT: use ChatGPT search or an OpenAI Responses API search-capable probe.
   Evidence should note whether `OAI-SearchBot` can access the target URL and
   whether the answer cites `www`, docs, GitHub, or registry surfaces.
2. Claude: use Claude web search. Evidence should note whether the result is
   a search result, an on-demand URL fetch, or model memory. Claude crawler
   access should include `Claude-SearchBot` and `Claude-User` checks.
3. Grok: use Grok with web search, and optionally X Search when measuring
   public social feed impact. Record source URLs returned by Grok citations.

If a platform cannot be tested manually in the UI, use the platform API only
when the required API key is available locally. Do not store API keys, cookies,
session exports, or account tokens in probe files or Bug List evidence.

## Feed Experiment Cadence

One optimization cycle should use a single `feed_key` and at least two
`run_group` values:

1. `YYYY-MM-DD-baseline` before publishing the feed.
2. `YYYY-MM-DD-after-<asset>` after the feed is live and locally validated.

Examples:

1. `brand_disambiguation_www`: homepage metadata, About answer block, GitHub
   org README, X profile bio, and canonical `llms.txt`. Treat
   `synapsenetwork.xyz` and unrelated `synapse.network` results as
   brand-collision competitors in `competitor_mentions` until ChatGPT, Claude,
   and Grok prefer `https://www.synapse-network.ai/`.
2. `agent_payment_category_pages`: AI Agent Payments docs category, `/ai-agent-payments`,
   `/agent-payment-api`, FAQ, schema, and sitemap.
3. `mcp_paid_api_discovery`: MCP Registry, MCP Marketplace, Smithery, Glama, GitHub README,
   and Remote MCP docs.

Do not mark a feed effective just because local validation passed. It is
effective only when external `mentioned_count` or `cited_count` improves against
the prior run group and the screenshot/source evidence supports the row.

## Probe File

Create a JSONL file under `docs/archive/evidence/growth/ai-visibility/`.

Export the product docs blueprint before implementing the `AI Agent Payments`
category in docs-front:

```bash
python scripts/growth/generate_ai_visibility_docs_blueprint.py \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-docs-blueprint.json
```

The blueprint includes the page list, canonical docs URLs, extractable
definition blocks, facts tables, FAQ prompts, schema types, Stitch/Figma notes,
MDX skeletons, and validation commands. It is also available from Growing:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/docs-blueprint" \
  | python -m json.tool
```

Export the Stitch-to-Figma handoff before creating the design exploration:

```bash
python scripts/growth/generate_ai_visibility_design_handoff.py \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-design-handoff.json
```

The handoff includes frame-specific Stitch prompts, the Figma file name,
component specs, design tokens, import steps, implementation notes, and
acceptance checks. It is also available from Growing:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/design-handoff" \
  | python -m json.tool
```

Export the feed package before publishing or probing. This keeps the operator,
content implementer, and reviewer aligned on the exact assets and checks for one
optimization cycle:

```bash
python scripts/growth/generate_ai_visibility_feed_package.py \
  --feed-key agent_payment_category_pages \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-feed-package.json
```

The same package is available from Growing:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/feed-package?feed_key=agent_payment_category_pages" \
  | python -m json.tool
```

After a real answer-engine probe captures `source_hosts`, export the source-host
feed package. This converts the hosts that ChatGPT, Claude, Grok, or Gemini
actually cited into operator-reviewed directory submissions, owned comparison
updates, and contextual partner/guest-post drafts:

```bash
python scripts/growth/generate_ai_visibility_source_host_feed_package.py \
  --feed-key agent_payment_category_pages \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-source-host-feed-package.json
```

The same draft package is available from Growing:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/source-host-feed-package?feed_key=agent_payment_category_pages" \
  | python -m json.tool
```

Export the matching execution checklist when the operator is ready to act. This
keeps directory submissions, owned comparison updates, partner-review work,
required evidence, validation commands, and post-feed probes in one place:

```bash
python scripts/growth/generate_ai_visibility_source_host_execution_checklist.py \
  --feed-key agent_payment_category_pages \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-source-host-execution-checklist.json
```

Growing exposes the same checklist:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/source-host-execution-checklist?feed_key=agent_payment_category_pages" \
  | python -m json.tool
```

Each feed package includes `platform_strategies` for ChatGPT, Claude, and Grok.
Use those entries to vary the feed surfaces without changing the measurement
question: for example ChatGPT may prioritize Remote MCP custom-app metadata and
the official MCP Registry, Claude may prioritize docs/GitHub/directory evidence,
and Grok may prioritize fresh public web plus X-linked canonical URLs.

Run live feed validation before spending time or API tokens on answer-engine
probes:

```bash
python scripts/growth/run_ai_visibility_feed_validation.py \
  --feed-key agent_payment_category_pages \
  --run-group 2026-06-18-after-docs-launch \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch-feed-validation.jsonl
```

Feed validation checks public readiness surfaces such as bare-domain redirect,
`robots.txt`, `llms.txt`, sitemap, GitHub organization profile, `www` category
pages, docs pages, Remote MCP readiness/auth boundaries, and the official MCP
Registry listing freshness for the `mcp_paid_api_discovery` feed. The MCP feed
also checks that npm has published `@synapse-network-ai/mcp-server@0.1.4`, because
the official Registry refuses refreshed metadata until the referenced npm package
version exists. If npm still reports only an older version, configure npm
Trusted Publisher for `SynapseNetworkAI/Synapse-Network-MCP-Server`
`publish-mcp.yml` or provide a publish-capable `NPM_TOKEN`, run Publish MCP
Server with `expected_version=0.1.4`, then refresh the official MCP Registry with
`mcp-publisher`. It emits `*_live_validation` rows. These rows are useful
blockers and readiness evidence, but they are not GPT/Claude/Grok answer
evidence and do not count toward external citation success. The brand feed row
also includes
`metadata.ai_crawler_policy`,
which records whether answer-engine search crawlers such as `OAI-SearchBot`,
`ChatGPT-User`, `GPTBot`, `ClaudeBot`, `Claude-User`, `Claude-SearchBot`,
`anthropic-ai`, `PerplexityBot`, `Bingbot`, and `Google-Extended` are explicitly
named or blocked. Wildcard
`User-agent: * Allow: /` is acceptable readiness evidence, but explicit search
crawler policy is still a recommended feed improvement.

For release-gated feeds, export a read-only release blocker snapshot before
creating or retrying release tasks:

```bash
python scripts/growth/generate_ai_visibility_release_snapshot.py \
  --feed-key mcp_paid_api_discovery \
  --run-group 2026-06-18-before-prod \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-before-prod-release-snapshot.json
```

The snapshot combines the release unblock plan, live feed readiness, GCloud
project access checks, and GPT/Claude/Grok API-key readiness. It does not create
release tasks, deploy, or call paid answer-engine APIs.

For operator handoff, export the full bundle. This writes `manifest.json`,
`release-snapshot.json`, `live-readiness.json`, `external-probe-gate.json`, and
`operator-brief.md` into one evidence directory:

```bash
python scripts/growth/generate_ai_visibility_handoff_bundle.py \
  --feed-key mcp_paid_api_discovery \
  --run-group 2026-06-18-before-prod \
  --output-dir docs/archive/evidence/growth/ai-visibility/2026-06-18-before-prod-handoff
```

Use the bundle after `gcloud auth login` and before creating release tasks. The
manifest is a recovery checklist: it records current blockers, release/readiness
status, ready and missing GPT/Claude/Grok platforms, and the exact feed
validation, probe, record, and comparison commands. It remains read-only; it
does not deploy and does not call paid model APIs.

The same read-only handoff manifest is available in Growing for the operator UI
and quick terminal checks:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/handoff-bundle?feed_key=mcp_paid_api_discovery" \
  | python -m json.tool
```

Apply feed validation rows only with the explicit local-validation allowance:

```bash
python scripts/growth/record_ai_visibility_probe.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch-feed-validation.jsonl \
  --allow-local-validation \
  --apply
```

Summarize a cycle before deciding the next feed. This works for local feed
validation files and for external ChatGPT/Claude/Grok probe files:

```bash
python scripts/growth/summarize_ai_visibility_cycle.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch-feed-validation.jsonl \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch-cycle-summary.json
```

When an earlier baseline file exists, compare it in the same command:

```bash
python scripts/growth/summarize_ai_visibility_cycle.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch.jsonl \
  --previous docs/archive/evidence/growth/ai-visibility/2026-06-04-baseline.jsonl \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch-cycle-summary.json
```

The summary reports whether the cycle is `feed_blocked`,
`ready_for_external_probe`, `partial_external_probe`, `citation_observed`,
`mention_observed`, or `not_visible_yet`. Use `feed_blocked` as a hard stop for
external answer-engine probes; fix the public feed first. The summary also
copies the relevant ChatGPT, Claude, and Grok `platform_strategies` for the feed
so the next operator sees exactly which surfaces to feed and which queries to
rerun. When `--previous` is supplied, the summary includes mention and citation
deltas plus `improved`, `flat`, or `regressed` comparison status. This is an
evidence comparison only; it does not replace fresh answer-engine probes.
`feed_improvements` lists non-blocking optimizations such as making wildcard
robots access explicit for answer-engine search bots.

Generate a starter template before running the external probes:

```bash
python scripts/growth/generate_ai_visibility_probe_template.py \
  --feed-key agent_payment_category_pages \
  --run-group 2026-06-18-after-docs-launch \
  --mode after-feed \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-after-docs-launch.jsonl
```

The template uses `https://www.synapse-network.ai/` as the canonical homepage,
creates one row for each baseline query on `chatgpt`, `claude`, and `grok`, and
pre-fills screenshot evidence paths. Each row's `metadata` includes
`platform_entry_url`, `question_to_ask`, and `evidence_capture` so the operator
can run the same question on each answer engine without changing the prompt.
After running each platform probe, fill in `answer_summary`,
`synapse_mentioned`, `synapse_cited`, `cited_urls`, `competitor_mentions`,
`missing_facts`, and `next_action`.

## Optional API Probe Runner

Use the API runner only when local API keys are available and the operator is
ready to spend provider tokens. It fails closed by default and does not call
OpenAI, Anthropic, xAI, or Gemini unless `--execute` is present.

Readiness check:

```bash
python scripts/growth/run_ai_visibility_api_probe.py \
  --feed-key agent_payment_category_pages \
  --run-group 2026-06-18-api-probe \
  --platforms chatgpt,claude,grok,gemini
```

When `--query` is omitted, the runner uses the full baseline query set so one
round creates comparable ChatGPT, Claude, Grok, and Gemini evidence for every
priority question. Add `--query` only for focused diagnostics; do not treat a
single-query diagnostic run as a full feed comparison.

The output should be `status=ready` when the requested platform keys exist, or
`status=blocked` with missing env names such as `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `XAI_API_KEY`, or `GEMINI_API_KEY or GENIMI_API_KEY`. It
must never print key values.

If the current Codex shell cannot see operator-provided keys, put only the
needed answer-engine keys in a local, untracked dotenv file and pass it
explicitly:

```bash
python scripts/growth/run_ai_visibility_api_probe.py \
  --feed-key agent_payment_category_pages \
  --run-group 2026-06-18-api-probe \
  --platforms chatgpt,claude,grok,gemini \
  --env-file /path/to/local-ai-visibility.env
```

The same path can be supplied with `AI_VISIBILITY_ENV_FILE`. The runner reports
only `env_file_loaded=true|false` plus missing key names; it never prints key
values. Paid calls still require `--execute`.

The Growing gate at `/api/growth/ai-visibility/external-probe-gate` also
reports `ready_platforms`, `missing_platforms`, and
`manual_probe_template_command`. `manual_ready_to_execute=true` means the feed is
ready for manual ChatGPT, Claude, Grok, and Gemini UI checks even when API
execution is blocked by missing keys. If API keys are missing, run the manual
template command, use the generated rows as a checklist in each UI, fill in answer
summaries, citations, and screenshot paths, then apply the JSONL with
`record_ai_visibility_probe.py`. When the feed is ready but only some keys exist,
the gate returns `ready_for_partial_external_probes` and shows
`partial_api_readiness_command` / `partial_api_execute_command` for the configured
platforms. Use partial API probes only for focused diagnostics. Full success
still requires comparable ChatGPT, Claude, Grok, and Gemini evidence for the
same feed and run group when Gemini is configured.

Execute paid probes:

```bash
python scripts/growth/run_ai_visibility_api_probe.py \
  --feed-key agent_payment_category_pages \
  --run-group 2026-06-18-api-probe \
  --platforms chatgpt,claude,grok,gemini \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-api-probe.jsonl \
  --execute
```

Provider behavior:

1. `chatgpt` uses OpenAI Responses API with `web_search` and source includes.
   The default model is `gpt-4o-mini` because it works with ordinary Responses
   API access; set `OPENAI_AI_VISIBILITY_MODEL` explicitly only after verifying
   the account can call the requested model with `web_search`.
2. `claude` uses Anthropic Messages API with the `web_search_20250305` server
   tool.
3. `grok` uses xAI Responses API with `web_search`; xAI's old Chat Completions
   live search path is not used.
4. `gemini` uses Gemini `generateContent` with `google_search` grounding. Set
   either `GEMINI_API_KEY` or the local compatibility alias `GENIMI_API_KEY`.

The runner emits the same JSONL contract as the manual template. A completed API
row still needs operator review before being treated as launch evidence, because
the public ChatGPT/Claude/Grok/Gemini UI may rank sources differently from API
search.

## Browser Probe Fallback

When provider API keys are unavailable, run the generated manual template in the
logged-in ChatGPT, Claude, and Grok browser UIs. Capture a screenshot for each
platform/query row and preserve the unchanged question text from
`metadata.question_to_ask`.

Browser probes are valid external evidence only when the actual answer-engine UI
returns an answer. Tooling readiness or login state is only validation evidence.
Record browser blockers as `browser_probe_validation` rows with
`--allow-local-validation`; do not post them as `chatgpt`, `claude`, or `grok`
rows.

Common browser blockers:

1. The selected Chrome profile does not have the Codex Chrome Extension enabled.
2. The answer-engine page requires login, CAPTCHA, plan upgrade, or workspace
   approval before search can run.
3. The page cannot use web/search mode for the requested query.

For a Chrome profile mismatch, fix the browser setup first: either enable the
Codex Chrome Extension in the selected Chrome profile or open Chrome with the
extension-enabled profile. Do not use browser blocker rows as visibility
success evidence.

`GET /api/growth/ai-visibility/weekly-report` promotes recent validation
blockers into `blockers` and adds a validation-first `next_action`, so operators
can see browser profile, login, API key, and feed readiness blockers directly in
the Growth AI Visibility panel.
For final proof, keep the UI screenshot path in `evidence_url`.

## Public Web Search Snapshots

Ordinary public web search is useful for competitor and rank drift, but it is
not a substitute for ChatGPT, Claude, or Grok answer evidence. Capture public web
results as a snapshot JSON with `feed_key`, `run_group`, `observed_at`, and a
`queries[]` array. Each query should include whether Synapse appeared in the
returned result set plus the observed adjacent competitors.

Convert that snapshot to diagnostic probe rows:

```bash
python scripts/growth/import_ai_visibility_public_search_snapshot.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-public-web-search-snapshot.json \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-public-web-search.jsonl
```

Then dry-run and record it through the normal recorder:

```bash
python scripts/growth/record_ai_visibility_probe.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-public-web-search.jsonl

python scripts/growth/record_ai_visibility_probe.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-public-web-search.jsonl \
  --apply
```

These rows use platform `public_web_search`. They appear in comparisons and
scorecards so the operator can see competitors and next actions, but they do not
cover the target GPT/Claude/Grok platforms and cannot close the visibility goal.

## Post-Probe Source-Host Diagnosis

When a complete ChatGPT, Claude, Grok, and Gemini probe returns zero Synapse
mentions or citations, do not blindly repeat the same probe. Generate a
source-host diagnosis first:

```bash
python scripts/growth/generate_ai_visibility_feed_diagnosis.py \
  docs/archive/evidence/growth/ai-visibility/2026-06-18-api-probe.jsonl \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-feed-diagnosis.json \
  --recommendations-output docs/archive/evidence/growth/ai-visibility/2026-06-18-source-host-recommendations.jsonl
```

The diagnosis emits `recommended_source_host_executions` for source hosts such as
the Official MCP Registry, MCP Marketplace, GitHub README, Smithery, Glama, X citation threads,
and docs disambiguation pages. These rows are operator intent and planning
evidence only; they are not external answer-engine citations. After the selected
source hosts are actually live and independently verifiable, rerun the same
four-platform API probe and compare the new run group against the prior one.

Record each live source-host execution before rerunning paid probes:

```bash
python scripts/growth/record_ai_visibility_source_host_execution.py \
  --feed-key mcp_paid_api_discovery \
  --run-group 2026-06-18-after-github-source-host \
  --surface github_readme \
  --source-url https://raw.githubusercontent.com/SynapseNetworkAI/Synapse-Network-MCP-Server/main/README.md \
  --required-term "Answer Engine Source Block" \
  --required-term "MCP server for paid API calls" \
  --required-term "RapidAPI" \
  --required-term "Project Synapse" \
  --target-platform chatgpt \
  --target-platform claude \
  --target-platform grok \
  --target-platform gemini \
  --target-query "MCP server for paid API calls" \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-github-readme-source-host.json
```

The source-host evidence proves that a public feed surface is live and contains
the intended terms. It still does not prove ChatGPT, Claude, Grok, or Gemini
used that surface; only the subsequent answer-engine probe can prove a mention
or citation.

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

Export the weekly optimization gate after applying probe rows:

```bash
python scripts/growth/export_ai_visibility_weekly_report.py \
  --output docs/archive/evidence/growth/ai-visibility/2026-06-18-weekly-report.json
```

The same report is available from Growing:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/weekly-report" \
  | python -m json.tool
```

Generate the next optimization cycle package from current ledger state:

```bash
curl -fsS \
  "http://localhost:9700/api/growth/ai-visibility/next-cycle" \
  | python -m json.tool
```

The next-cycle package includes the recommended `feed_key`, run group,
output path, validation commands, manual template command, optional API
readiness and execute commands, apply command, comparison command, weekly report
export command, blockers, and missing GPT/Claude/Grok platforms. Use it as the
operator checklist for the next feed/probe/compare loop.

Do not mark the goal achieved unless the weekly report returns
`goal_achieved=true`. The report intentionally fails closed until GPT, Claude,
and Grok coverage, citation evidence, and three stable positive weekly runs are
present.

Success criteria for a feed experiment:

1. `external_checks_count` includes real answer-engine rows.
2. `missing_platforms` shrinks for `chatgpt`, `claude`, and `grok`.
3. `mentioned_count` and `cited_count` improve against the previous run group.
4. At least one cited URL points to `www`, docs, GitHub, MCP Registry, or a
   trusted directory.
5. Results remain stable across three weekly runs before marking the goal as
   achieved.
