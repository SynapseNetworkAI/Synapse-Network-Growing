---
id: growth_acquisition_ai_discovery_modules
title: Growth Acquisition and AI Discovery Modules
role: growth_lead
status: ready
created_at: 2026-05-30
updated_at: 2026-06-04
author: codex
target_repo: Synapse-Network-Growing
---

# Growth Acquisition And AI Discovery Modules

## Purpose

Synapse Network is live at `https://www.synapse-network.ai/`. The next Company Ops surface should help the operator find two early markets and make Synapse discoverable to AI agents:

1. Investors who understand AI infrastructure, agent infrastructure, API marketplaces, payments, crypto rails, and developer platforms.
2. Provider users who already own APIs, MCP servers, data services, automation tools, search/browser tools, or AI utilities that agents could invoke.
3. AI search systems that need clear, crawlable, citation-ready explanations of what Synapse is.
4. MCP discovery surfaces where agents and model clients look for callable tools.

The planned route is `/growth`. It is a Human-Agent Control Plane, not an autonomous spam engine.

## Current Production Facts

1. `https://www.synapse-network.ai/` is the production marketing site and should be the canonical homepage in metadata, `robots.txt`, `llms.txt`, sitemap, docs, and distribution copy. `https://synapse-network.ai/*` should permanently redirect to the matching `www` URL so answer engines see one canonical host.
2. `https://www.synapse-network.ai/llms.txt` exists and should remain the canonical machine-readable product explainer.
3. Current public positioning should stay consistent with the product marketing context: Synapse is the settlement layer for AI agents, a way for agents to discover, invoke, and pay for APIs with budget isolation and USDC settlement.
4. Current robots policy broadly allows crawling while disallowing dashboard, provider, API, and Next.js data paths. The next production-site iteration should make AI crawler policy explicit instead of accidental.
5. Live baseline on 2026-06-04 found a P0 discovery gap: `www` is the confirmed official homepage, but the production sitemap was effectively empty, some canonical / `llms.txt` links still pointed at non-`www`, and the bare domain did not permanently redirect to `www`. AI Visibility must track this as a feed experiment until fixed and rechecked.
6. Live public search on 2026-06-05 surfaced `synapseproto.com` above the official Synapse Network site for AI-agent settlement wording. Treat Synapse Protocol as a brand-collision competitor in probe evidence; it must not count as a Synapse Network mention or citation.

## Operating Boundary

1. Growth is semi-automated: the system may research leads, score fit, draft messages, queue campaigns, and record events. It must not send unapproved outreach.
2. The operator approves a batch before messages are sent. The runner then sends one by one through an approved connector and writes append-only events.
3. No spam, bulk undifferentiated DM, fake personalization, platform rule bypass, CAPTCHA bypass, or hidden browser automation.
4. Every lead must have source evidence, why-this-person rationale, contact provenance, and `do_not_contact` support.
5. `/publishing` remains responsible for public social content and content distribution. `/growth` owns acquisition, outreach, AI discovery, and MCP listing pipelines.
6. Do not claim guaranteed revenue, guaranteed investor interest, guaranteed AI ranking, or guaranteed MCP listing.

## Workbench Shape

Route: `/growth`

Tabs:

1. `Sources`
2. `Investors`
3. `Providers`
4. `AI Visibility`
5. `MCP Discovery`

The first implementation adds the route to top navigation with V1 ledger APIs and real records. External sending and registry submission remain out of scope.

## Shared Data Objects

### GrowthLead

`GrowthLead` is the shared source of truth for investors and providers.

Core fields:

1. `id`
2. `lead_type = investor | provider`
3. `project_key`
4. `name`
5. `organization`
6. `role_title`
7. `public_profile_urls`
8. `contact_channels`
9. `source_kind`
10. `source_url`
11. `status`
12. `fit_score`
13. `confidence_score`
14. `risk_flags`
15. `evidence_json`
16. `metadata_json`
17. `next_action`
18. `last_contacted_at`
19. `created_at`
20. `updated_at`

Lead status:

```text
new
-> researched
-> drafted
-> approved
-> queued
-> sent
-> replied
-> interested | not_interested | do_not_contact | invalid
```

### GrowthCampaign

`GrowthCampaign` defines the audience, offer, channel rules, cadence, and KPI.

Useful fields:

1. `campaign_key`
2. `campaign_type = investor_radar | provider_acquisition | ai_visibility | mcp_discovery`
3. `audience`
4. `objective`
5. `offer`
6. `channel_policy_json`
7. `cadence_json`
8. `status = draft | active | paused | completed | archived`
9. `owner_role`
10. `success_metric`

### OutreachMessage

`OutreachMessage` is the draft and send unit.

Useful fields:

1. `lead_id`
2. `campaign_id`
3. `channel`
4. `subject`
5. `body`
6. `personalization_evidence_json`
7. `status = draft | needs_review | approved | queued | sent | failed | skipped`
8. `approved_by`
9. `sent_at`
10. `failure_reason`
11. Gmail draft evidence in `metadata_json`: `gmail_status`, `gmail_draft_id`, `draft_url`, `contact_email`, and `contact_provenance`. Gmail integration creates drafts only after operator approval; it never sends email automatically.

### OutreachEvent

Append-only event log for outreach lifecycle.

Event types:

```text
lead_imported
lead_researched
lead_scored
message_drafted
message_approved
message_queued
message_sent
reply_received
follow_up_scheduled
do_not_contact_set
message_failed
```

### GrowthSourceConfig

`GrowthSourceConfig` controls provider and investor discovery inputs. V1 focuses on provider acquisition.

Useful fields:

1. `config_key`
2. `name`
3. `config_type = github_provider_search | github_mcp_repos | mcp_directory_watch | api_provider_sites | package_ecosystem | manual_seed_list`
4. `status = enabled | paused | archived`
5. `query_json`
6. `cadence_json`
7. `thresholds_json`
8. `last_run_at`
9. `last_result_json`

Supported provider acquisition source pools:

1. `github_mcp_repos`: GitHub repos and topics for MCP servers, agent tools, API SDKs, search/scrape/browser/database/security/finance-data tools.
2. `mcp_directories`: MCP Registry, Smithery, MCP Find, MCP directories, PulseMCP, Glama, and similar discovery surfaces.
3. `api_provider_sites`: public API/pricing/docs websites for data or automation providers.
4. `package_ecosystem`: npm, PyPI, Go, Java, and .NET packages with MCP, agent, API, SDK, or tooling signals.
5. `manual_seed_list`: operator-provided URLs used as a safe bootstrap and correction path.

Contact discovery uses public evidence only. Priority order is official partner/contact pages, docs/package metadata support or partnerships addresses, then public GitHub profile email. Commit email is low confidence and must not be used when it is a `noreply.github.com` or privacy-protected address. Leads without trusted contact email can be created and scored, but they must not enter Gmail draft creation.

### GrowthResearchRun

`GrowthResearchRun` stores each source execution and makes automation observable.

Useful fields:

1. `source_config_id`
2. `status`
3. `dry_run`
4. `candidate_count`
5. `created_count`
6. `reused_count`
7. `drafted_count`
8. `error_summary`
9. `result_json`

### DiscoveryListing

`DiscoveryListing` tracks MCP and AI discovery submissions.

Useful fields:

1. `surface = official_mcp_registry | glama | smithery | mcp_so | pulsemcp | awesome_list | github_topic`
2. `target_repo`
3. `package_name`
4. `listing_url`
5. `status = candidate | package_ready | registry_submitted | listed | verified | needs_fix`
6. `submission_evidence_json`
7. `verification_evidence_json`
8. `last_checked_at`
9. `failure_reason`

### AIVisibilityCheck

`AIVisibilityCheck` stores answer-engine monitoring results.

Useful fields:

1. `query`
2. `platform = chatgpt | perplexity | google_ai | bing_copilot | claude | other`
3. `answer_summary`
4. `synapse_mentioned`
5. `synapse_cited`
6. `cited_urls`
7. `competitor_mentions`
8. `missing_facts`
9. `run_at`
10. `next_action`
11. `feed_key`
12. `run_group`
13. `result_rank`
14. `evidence_url`
15. `metadata_json`

## Module 1: Investor Radar

### Goal

Find pre-seed and seed investors who are likely to understand Synapse as an AI agent settlement layer, then create a high-quality, semi-automated outreach queue.

### ICP

Priority investors:

1. Pre-seed or seed stage.
2. AI infrastructure, agent infrastructure, devtools, fintech, crypto rails, marketplace, or API economy thesis.
3. Portfolio includes companies adjacent to MCP, agent tooling, data APIs, LLM infrastructure, payments, stablecoins, Web3 developer tooling, or API marketplaces.
4. Publicly active in developer infrastructure or agent economy discussions.
5. Has a warm path from existing founder network, GitHub, X, LinkedIn, Product Hunt, founder communities, or portfolio overlap.

### Public Data Sources

1. NFX Signal for investor discovery.
2. OpenVC / SearchVC style public investor databases.
3. Crunchbase or equivalent public company and investment metadata where available.
4. GitHub, X, LinkedIn, personal sites, newsletters, podcasts, and public investment theses.
5. Synapse internal evidence: product milestones, production site, SDK releases, provider onboarding, MCP listing status.

v1 should support CSV and manual import first. Paid data vendors and automated scraping should be separate later integrations.

### Scorecard

Investor fit fields:

1. `stage_fit`
2. `sector_fit`
3. `portfolio_fit`
4. `geo_fit`
5. `warm_path_score`
6. `recent_activity_score`
7. `thesis_match`
8. `risk_flags`
9. `evidence_quality`

Example scoring interpretation:

```text
80-100: draft personalized outreach immediately
60-79: research one more evidence item before drafting
40-59: keep as future nurture
0-39: skip unless operator manually overrides
```

### Outreach Positioning

Do not start with a hard fundraising ask unless the operator explicitly configures a fundraising campaign.

Default ask:

```text
Would this be worth a look?
We are building Synapse, a settlement layer for AI agents to discover, invoke, and pay for APIs with budget isolation and USDC settlement.
```

Message ingredients:

1. One-line reason for contacting this investor.
2. One-line Synapse explanation.
3. Proof point: production site, SDK release, provider runtime, MCP server, settlement rail, or first provider target.
4. Low-friction ask: interested in a short note, demo, or feedback call?

### Investor Flow

```text
import leads
-> enrich public evidence
-> score fit
-> draft message
-> operator review
-> approve batch
-> send one by one
-> record reply / interest / do_not_contact
-> schedule follow-up only when policy allows
```

### Investor Metrics

1. Researched leads.
2. Approved messages.
3. Sent messages.
4. Reply rate.
5. Interested replies.
6. Intro calls booked.
7. Follow-up conversion.
8. Do-not-contact rate.

## Module 2: Provider Acquisition

### Goal

Find the first provider users who can list services on Synapse and earn when agents invoke their APIs.

### ICP

Priority provider users:

1. AI/API developers.
2. Owners of MCP servers, data APIs, browser/search tools, LLM/RAG services, automation APIs, scraping alternatives, workflow tools, testing tools, analytics tools, or developer utility APIs.
3. Builders who already publish SDKs, examples, docs, or API keys.
4. People with public GitHub repos under topics such as `mcp-server`, `model-context-protocol`, `api`, `llm`, `rag`, `search`, `browser-automation`, `agent-tools`, or `developer-tools`.
5. Product Hunt makers, DEV/Hashnode technical authors, open-source maintainers, and API marketplace providers.

### Value Proposition

Provider-facing pitch:

```text
Register your API as a callable Synapse service.
Agents can discover it, invoke it, and pay per use in USDC.
Early providers get technical onboarding help, lower or 0% early fees, and discovery placement.
```

Important boundaries:

1. Do not promise revenue.
2. Do not imply agent traffic exists before it is measured.
3. Explain that provider onboarding requires API reliability, pricing clarity, and safe billing limits.

### Provider Scorecard

Provider lead fields:

1. `service_relevance`
2. `api_readiness`
3. `mcp_readiness`
4. `pricing_fit`
5. `agent_usefulness`
6. `integration_effort`
7. `maintainer_activity`
8. `docs_quality`
9. `security_risk`
10. `contact_quality`

### Provider Flow

```text
discover provider lead
-> identify service candidate
-> score fit and onboarding effort
-> draft recruiting message
-> operator approve
-> send
-> reply received
-> onboarding checklist created
-> service listed
-> first invocation
-> first revenue event
```

### Provider Onboarding Checklist

1. Public service name and category.
2. API endpoint or MCP server URL.
3. Auth model.
4. Pricing model.
5. Free or smoke-test call.
6. Rate limits.
7. Failure modes.
8. Provider payout wallet.
9. Terms and acceptable use.
10. Example agent invocation.

### Provider Metrics

1. Leads researched.
2. Messages sent.
3. Replies.
4. Provider signups.
5. Services listed.
6. First successful invocation.
7. First paid invocation.
8. Provider activation time.

## Module 3: AI Search Optimization

### Goal

Make ChatGPT, Perplexity, Google AI features, Bing/Copilot, and other answer engines understand and cite Synapse for relevant agent economy queries.

### Principles

1. Keep `llms.txt` concise, current, and canonical.
2. Publish crawlable pages with extractable answer blocks.
3. Use normal SEO foundations: crawlability, indexability, internal links, sitemap, clear titles, structured data, and fast pages.
4. Separate search/discovery crawler policy from training crawler policy. For example, OpenAI documents `OAI-SearchBot` and `GPTBot` as distinct controls.
5. Do not optimize by cloaking. The public page and machine-readable summary should agree.

### Site Task Checklist

Production-site tasks for `Synapse-Network`:

1. Update homepage answer block:
   - What is Synapse Network?
   - Who uses it?
   - What problem does it solve?
   - How do agents pay providers?
2. Add or strengthen provider page:
   - `Register your API`
   - `Earn per invocation`
   - `USDC settlement`
   - `Budget and rate safety`
3. Add or strengthen MCP page:
   - What Synapse MCP server exposes.
   - How agents connect.
   - Required environment variables.
   - Billing and safety boundaries.
4. Add SDK quickstart page:
   - Python and TypeScript first.
   - Free service smoke path.
   - Production gateway URL.
5. Add FAQ page:
   - Is Synapse a marketplace?
   - How do providers earn?
   - How do agents avoid runaway spend?
   - Does Synapse custody funds?
   - What is the difference from RapidAPI, Stripe, and an MCP directory?
6. Add comparison pages:
   - `Synapse vs RapidAPI for AI agents`
   - `Synapse vs Stripe for agent payments`
   - `Synapse vs MCP directory`
7. Add schema markup:
   - `Organization`
   - `SoftwareApplication` or `Product`
   - `FAQPage`
   - `Article`
   - `BreadcrumbList`
8. Ensure sitemap includes growth-critical pages.
9. Ensure robots policy intentionally allows search and citation crawlers while excluding private app surfaces.

### Query Set

Track these weekly:

1. `AI agent payment layer`
2. `MCP monetization platform`
3. `how can AI agents pay for APIs`
4. `agent API marketplace`
5. `USDC micropayments for agents`
6. `API marketplace for AI agents`
7. `settlement layer for AI agents`
8. `MCP server billing`

The baseline query set for GPT, Claude, and Grok should also include:

1. `What is Synapse Network for AI agents?`
2. `AI agent payment API`
3. `How can AI agents pay for APIs?`
4. `MCP server for paid API calls`
5. `AI agent USDC settlement layer`
6. `Synapse Network vs x402`
7. `How can API providers earn from AI agents?`

### AI Visibility Flow

```text
define query set
-> run manual or connector-assisted checks
-> record answer, citation URLs, competitors, missing facts
-> create site/content tasks
-> update site or docs
-> recheck weekly
```

### AI Visibility Metrics

1. Synapse mentioned.
2. Synapse cited.
3. Number of cited Synapse URLs.
4. Competitor mentions.
5. Missing fact categories.
6. Crawler access health.
7. Query trend over time.

### AI Visibility Optimization Plan

Growing exposes `GET /api/growth/ai-visibility/optimization-plan` as the operator-facing plan source for continuous agent SEO. It is a structured read-only plan, while `AIVisibilityCheck` remains the run ledger. `GET /api/growth/ai-visibility/docs-blueprint` exports the page-level `AI Agent Payments` docs blueprint with titles, canonical URLs, definition blocks, fact tables, FAQ prompts, schema types, Stitch/Figma component notes, MDX skeletons, and validation commands. `GET /api/growth/ai-visibility/design-handoff` exports the Stitch-to-Figma handoff with Figma file name, frame prompts, reusable component specs, design tokens, import steps, implementation notes, and acceptance checks. `GET /api/growth/ai-visibility/feed-package` turns each planned feed experiment into an executable operator package: publish assets, Stitch/Figma design prompt, local validation commands, probe-template command, success metrics, and next actions. `GET /api/growth/ai-visibility/comparisons` groups checks by `feed_key + run_group` so the operator can compare GPT, Claude, and Grok search outcomes after each feed experiment. `GET /api/growth/ai-visibility/weekly-report` is the continuous optimization gate: it summarizes coverage, blockers, stable positive run count, recommended feed key, and the next probe-template command. It must keep `goal_achieved=false` until external GPT/Claude/Grok evidence and stability requirements pass.

Comparison counts intentionally separate feed validation from external search truth. Platforms such as `www_local_validation`, `docs_local_validation`, and `www_live_validation` prove that pages, `llms.txt`, sitemap, canonical metadata, bare-domain redirect state, docs robots answer-engine crawler policy, live crawl state, and screenshots are ready or blocked, but they do not prove that ChatGPT, Claude, or Grok can find Synapse. These `*_validation` rows increase `local_validation_count`; only real answer-engine rows increase external `mentioned_count` and `cited_count`. `public_web_search` is allowed as a diagnostic external row for ordinary search-result rank and competitor drift, but it does not count as ChatGPT, Claude, or Grok target-platform coverage and cannot satisfy the final visibility goal by itself.

This should be a dedicated Growth submodule, not a one-off docs task. The operator surface is `Growth -> AI Visibility`, with data stored as:

1. Product docs blueprint: `AI Agent Payments` page specs, reusable docs-front components, MDX skeletons, schema types, Stitch notes, Figma components, and validation commands.
2. Stitch/Figma handoff: Figma file name, frame-specific Stitch prompts, reusable component specs, design tokens, import steps, and acceptance checks.
3. Product feed packages: docs, www pages, `llms.txt`, sitemap, robots policy, schema, GitHub READMEs, MCP listings, public social/source posts, validation commands, and a probe-template command.
4. Search probes: one `AIVisibilityCheck` row per platform/query/run group.
5. Comparisons: grouped by `feed_key + run_group`, separating local feed validation from GPT, Claude, Grok, Perplexity, Google AI, Bing/Copilot, or diagnostic `public_web_search` truth.
6. Delta scoring: each run group compares against the previous run group for the same `feed_key`, exposing mention delta, citation delta, comparison status, and whether the feed was effective.
7. Weekly report gate: `goal_achieved`, stable positive runs, missing platforms, blockers, and the recommended next probe command.
8. Next actions: content, docs, MCP registry, GitHub, social distribution, or crawler-access tasks that the operator can turn into requirements.

Optimization loop:

```text
live baseline
-> fix crawl/canonical/source docs
-> create feed experiment
-> export feed package
-> publish docs/site/GitHub/MCP registry assets
-> import public web search snapshot when available
-> probe ChatGPT, Claude, and Grok
-> record AIVisibilityCheck evidence
-> compare against previous run
-> open next content or platform task
```

P0 feed experiments:

1. `brand_disambiguation_www`: make `https://www.synapse-network.ai/` and docs show up for brand queries, permanently redirect the bare domain to `www`, and distinguish Synapse Network from unrelated `synapse.network` results.
2. `agent_payment_category_pages`: publish answer-ready docs and homepage pages for AI agent payment APIs, paid API calls, USDC settlement, receipts, and budget isolation.
3. `mcp_paid_api_discovery`: make the Remote MCP endpoint and package visible in MCP Registry, Smithery, Glama, docs, and GitHub surfaces.

Comparison rules:

1. Use the same `feed_key` for all checks generated by one content feed experiment.
2. Use the same `run_group` for one search-testing round, for example `2026-06-04-baseline` or `2026-06-18-after-docs-launch`.
3. Record one `AIVisibilityCheck` per platform/query result, including evidence URL or screenshot path when available.
4. Treat missing GPT, Claude, or Grok rows as missing platform evidence, not as a pass.
5. Only mark an experiment effective when the comparison shows improved mention/citation counts against the previous run group.
6. Use `GET /api/growth/ai-visibility/feed-package` or `scripts/growth/generate_ai_visibility_feed_package.py` to export the bounded feed package before publishing assets.
7. Use `docs/ops/11_AI_Visibility_Probe_Runbook.md`, `scripts/growth/generate_ai_visibility_probe_template.py`, and `scripts/growth/record_ai_visibility_probe.py` to generate, validate, and record manual ChatGPT, Claude, and Grok probe rows.
8. Use `scripts/growth/import_ai_visibility_public_search_snapshot.py` to convert ordinary public web search snapshots into `public_web_search` rows for competitor/rank drift. These rows inform next actions but do not cover target answer-engine platforms.

Comparison statuses:

1. `needs_external_probe`: local feed evidence exists, but no real answer-engine rows exist for the run group.
2. `baseline`: first external run for a feed key.
3. `improved`: mention or citation count increased against the previous run group.
4. `flat`: external results did not move.
5. `regressed`: mention or citation count decreased and needs immediate diagnosis.

Agent search optimization is continuous. A single sitemap or docs deploy only proves that we fed better source material. It does not prove answer engines have crawled, selected, cited, and retained the new facts. Each feed experiment should run through:

1. Baseline: record current GPT, Claude, and Grok answers before a feed.
2. Feed: publish one bounded asset bundle, such as `agent_payment_category_pages`.
3. Local validation: confirm `www`, bare-domain redirect, docs, schema, sitemap, `llms.txt`, user-front robots access, and docs-front robots access for answer-engine crawlers.
4. External probe: rerun the same query set in the same platforms.
5. Comparison: check mention/citation deltas, missing platforms, competitors, and missing facts.
6. Weekly report: review blockers and recommended next feed/probe command.
7. Follow-up: create the next content or distribution requirement only from evidence, not from guesses.
8. Stability: require three weekly positive runs before calling a visibility goal achieved.

Product documentation design:

1. Add a major docs category named `AI Agent Payments`.
2. Create citation-ready pages for `/ai-agent-payments`, `/agent-payment-api`, `/agent-pays-for-llm-calls`, `/provider-monetization`, `/receipts-and-budget-isolation`, `/synapse-vs-x402`, and `/faq`.
3. Every page should include a 40-60 word standalone definition, machine-readable facts table, user path, payment flow, comparison block, FAQ, schema markup, last updated date, and links to source surfaces.
4. Use `GET /api/growth/ai-visibility/docs-blueprint` or `scripts/growth/generate_ai_visibility_docs_blueprint.py` to export the current page-level implementation blueprint before editing `Synapse-Network` docs-front.

Stitch and Figma workflow:

1. Use Stitch to design the docs landing page and comparison blocks from the plan's `design_plan.stitch_prompt`.
2. Export `GET /api/growth/ai-visibility/design-handoff` or `scripts/growth/generate_ai_visibility_design_handoff.py` before generating the Stitch exploration so the frame names, component specs, and acceptance checks stay stable.
3. Import the Stitch exploration into Figma as visual guidance.
4. Normalize typography, spacing, and reusable docs-front components in Figma.
5. Implement the final source of truth in MDX / production site code, `llms.txt`, sitemap, and schema. Figma must not become the canonical content source.
6. After implementation, record the feed as local validation rows first, then run external GPT / Claude / Grok probes after the content is live.

Success requires repeated external evidence, not a one-off local change: brand queries should cite `www`, docs, GitHub, or MCP registry; at least half of the priority category queries should mention Synapse on two target platforms; and results should hold for three weekly runs.

## Module 4: MCP Discovery Distribution

### Goal

Make Synapse MCP discoverable where agents and model clients look for MCP servers.

### Discovery Surfaces

Priority surfaces:

1. Official MCP Registry.
2. Glama.
3. Smithery.
4. MCP.so.
5. PulseMCP.
6. Awesome MCP lists.
7. GitHub topics and README discovery.

### Package Readiness Checklist

Synapse MCP server repo must have:

1. Production README.
2. Clear one-line description.
3. Tool list and schemas.
4. `server.json` or registry-compatible manifest when required.
5. Auth and environment variable docs.
6. Safety boundaries.
7. Pricing and billing explanation.
8. Production gateway URL.
9. Free/smoke example.
10. Demo GIF or screenshot.
11. `llms.txt` and docs links.
12. License.
13. Verified package ownership marker when required by the registry.

### Official MCP Registry Flow

```text
package_ready
-> generate or validate server.json
-> verify package ownership
-> authenticate publisher
-> submit with mcp-publisher
-> poll registry status
-> verify listing URL
-> record evidence
```

The official registry should be treated like an app-store surface for MCP servers: no fake listings, no unverified ownership, no stale tool schemas.

### Third-Party Directory Flow

```text
prepare README and manifest
-> submit GitHub repo or package URL
-> record submission evidence
-> wait for indexing or review
-> verify listing page
-> record live URL
-> create needs_fix record when schema, auth, or docs are rejected
```

### MCP Discovery Metrics

1. Candidate surfaces.
2. Package-ready surfaces.
3. Submitted surfaces.
4. Listed surfaces.
5. Verified live listing URLs.
6. Rejection reasons.
7. Discovery traffic or referrals where measurable.

## Future API Surface

Growth APIs should be agent-readable but write-protected by operator or local runner authorization.

Suggested endpoints:

1. `GET /api/growth/campaigns`
2. `POST /api/growth/campaigns`
3. `GET /api/growth/leads`
4. `POST /api/growth/leads`
5. `POST /api/growth/leads/import`
6. `GET /api/growth/leads/{id}`
7. `POST /api/growth/leads/{id}/draft-message`
8. `POST /api/growth/messages/{id}/approve`
9. `POST /api/growth/messages/{id}/queue`
10. `POST /api/growth/messages/{id}/mark-sent`
11. `POST /api/growth/messages/{id}/reply`
12. `POST /api/growth/leads/{id}/do-not-contact`
13. `GET /api/growth/ai-visibility/checks`
14. `POST /api/growth/ai-visibility/checks`
15. `GET /api/growth/ai-visibility/optimization-plan`
16. `GET /api/growth/ai-visibility/comparisons`
17. `GET /api/growth/discovery-listings`
18. `POST /api/growth/discovery-listings`
19. `PATCH /api/growth/discovery-listings/{id}`
20. `GET /api/growth/source-configs`
21. `POST /api/growth/source-configs`
22. `PATCH /api/growth/source-configs/{id}`
23. `POST /api/growth/source-configs/{id}/run`
24. `GET /api/growth/source-configs/{id}/runs`
25. `GET /api/growth/research-runs/{id}`

## UI Design

### Shared Header

Header cards:

1. `Investor leads`
2. `Provider leads`
3. `Approved messages`
4. `Replies`
5. `AI citations`
6. `MCP listings`

Primary actions:

1. `Import leads`
2. `Run research`
3. `Draft messages`
4. `Approve batch`
5. `Run AI visibility check`
6. `Add discovery listing`

### Investors Tab

Default table columns:

1. Investor
2. Firm
3. Stage fit
4. Sector fit
5. Warm path
6. Status
7. Last touch
8. Next action

Detail modal:

1. Evidence.
2. Portfolio overlap.
3. Fit score.
4. Draft messages.
5. Events.

### Providers Tab

Default table columns:

1. Provider lead
2. Service candidate
3. API readiness
4. MCP readiness
5. Monetization fit
6. Status
7. Next action

Detail modal:

1. Service profile.
2. Integration difficulty.
3. Draft outreach.
4. Onboarding checklist.
5. Events.

### AI Visibility Tab

Default table columns:

1. Query.
2. Platform.
3. Synapse mentioned.
4. Synapse cited.
5. Cited URL.
6. Competitors.
7. Last checked.
8. Next content task.

### MCP Discovery Tab

Default table columns:

1. Surface.
2. Package.
3. Status.
4. Listing URL.
5. Last checked.
6. Failure reason.
7. Next action.

## Safety And Compliance Rules

1. `do_not_contact` is global and overrides campaigns.
2. No unapproved message send.
3. No undisclosed automation on platforms that prohibit it.
4. No scraping behind login unless the operator exports data or connects an approved API.
5. No storing raw platform tokens, email passwords, or API secrets in lead metadata.
6. No fake send events. A sent event requires connector result, operator manual confirmation, or imported evidence.
7. No fake listing events. A listed event requires a live URL or registry API response.
8. No fake AI visibility wins. A citation requires a captured answer and cited URL.
9. Every generated message must include a concrete reason for contacting the lead.
10. Follow-up cadence must be bounded and stop on reply, bounce, do-not-contact, or operator pause.

## Implementation Phases

### Phase 1: Docs And Manual Ledger

1. Add this design document.
2. Add `/growth` to feature inventory as planned, not runtime.
3. Allow CSV/manual imports later.
4. Store AI visibility and discovery listing checks manually later.

### Phase 2: Read/Write APIs And Page

1. Add database tables.
2. Add `/api/growth/*`.
3. Add `/growth` route with four tabs.
4. Add filters, pagination, detail modals, and event logs.

### Phase 3: Research And Drafting Agents

1. Investor research atom.
2. Provider research atom.
3. Outreach draft atom.
4. AI visibility check atom.
5. MCP listing readiness scanner.

### Phase 4: Approved Sending And Listings

1. Add approved batch runner.
2. Add Gmail/email connector first, then other channels only when policy allows.
3. Add MCP registry submission runner.
4. Add listing verification runner.

## Validation Plan

Docs validation:

1. This document contains all four modules.
2. `current-feature-inventory.md` mentions Growth as a planned canonical module without claiming runtime exists.
3. `context-loading-map.md` routes growth, investor, provider acquisition, AI SEO, and MCP registry work to this document.

Future runtime validation:

1. `/growth` can search and paginate investor/provider leads.
2. A lead can generate a draft message but cannot send without approval.
3. An approved batch sends one by one and writes `OutreachEvent`.
4. AI Visibility stores query, platform, answer summary, citation status, cited URL, competitors, feed key, run group, result rank, evidence URL, and next action.
5. MCP Discovery tracks registry submission status and live listing URL.
6. Production `llms.txt` and robots policy can be checked from the Ops Console.

External validation:

1. `curl https://www.synapse-network.ai/llms.txt` returns current product facts and uses `www` links.
2. `curl https://www.synapse-network.ai/robots.txt` shows intentional crawler policy and a non-empty `www` sitemap URL.
3. `curl -I https://synapse-network.ai/` returns a permanent redirect whose `Location` starts with `https://www.synapse-network.ai/`.
4. Official MCP Registry can search or resolve the Synapse MCP server after submission.
5. At least one third-party MCP directory shows a verified Synapse listing.
6. Outreach metrics record real sends and replies only.

## References

1. [OpenAI crawler documentation](https://platform.openai.com/docs/bots)
2. [Google AI features and Search documentation](https://developers.google.com/search/docs/appearance/ai-features)
3. [Perplexity robots.txt behavior](https://www.perplexity.ai/help-center/pt/articles/10354969)
4. [llms.txt proposal](https://llmstxt.org/)
5. [Official MCP Registry](https://prod.registry.modelcontextprotocol.io/)
6. [Official MCP Registry API reference](https://registry.modelcontextprotocol.io/docs)
7. [MCP Registry remote server publishing](https://modelcontextprotocol.io/registry/remote-servers)
8. [Glama MCP directory](https://glama.ai/mcp)
9. [Smithery](https://smithery.ai/)
10. [MCP.so](https://mcp.so/)
11. [NFX Signal](https://signal.nfx.com/)
12. [Product Hunt launch guide](https://www.producthunt.com/launch)
