---
id: synapse_fullchain_tracking_plan
title: Synapse Network — Full-Chain Analytics Tracking Plan
role: cro_optimizer
skill: analytics-tracking
status: draft
created_at: 2026-04-08
updated_at: 2026-04-08
author: CRO Optimizer Agent
---

# Synapse Network — 全链路埋点方案 (Full-Chain Analytics Tracking Plan)

## 1. Objective

为 Synapse Network 的 **Consumer 漏斗** 与 **Provider 漏斗** 建立完整的事件追踪体系，覆盖从首次访问到持续活跃的全部关键节点。每个事件服务于一个明确的决策：找到漏斗最大 drop-off、量化优化效果、驱动增长实验。

---

## 2. Instrumentation Scope

### Consumer Funnel

```
Landing Page Visit → Wallet Connect → Role Select (Consumer)
→ Dashboard First View → First Deposit (USDC) → Credential Created
→ Service Discovered → First API Invoke → Repeat Usage
```

### Provider Funnel

```
Landing Page Visit → Wallet Connect → Role Select (Provider)
→ Secret Created → Service Manifest Built → Service Deployed (Registered)
→ First Agent Call Received → First Payout Claimed
```

---

## 3. Naming Convention

| Rule | Example |
|------|---------|
| `object_action` format, lowercase + underscore | `wallet_connected` |
| Use past tense for completed actions | `signup_completed`, not `signup` |
| Use `_started` / `_completed` / `_failed` suffixes for multi-step flows | `deposit_started` → `deposit_completed` |
| Context goes in properties, not event name | `cta_clicked { location: "hero" }` not `hero_cta_clicked` |

---

## 4. Recommended Tool Stack

| Layer | Tool | Rationale |
|-------|------|-----------|
| Event Collector | **Segment** (or self-hosted Jitsu) | Single API → fan-out to all destinations; SDK for web + Python |
| Product Analytics | **Mixpanel** or **PostHog** | Funnel analysis, retention, cohort; dev-friendly |
| Web Analytics | **GA4** (via Segment) | SEO attribution, campaign-level traffic |
| Tag Manager | **GTM** (marketing site only) | Marketing pixel management without deploys |
| Error Tracking | **Sentry** (already likely in stack) | Correlate errors with funnel drop-off |

> **Note:** PostHog (open-source, self-hostable) is the recommended default for early-stage — covers product analytics + session replay + feature flags in one tool, minimizing vendor count.

---

## 5. Event Catalog

### 5.1 Shared / Cross-Funnel Events

| # | Event Name | Trigger | Properties | Decision It Informs |
|---|-----------|---------|------------|---------------------|
| S1 | `page_viewed` | Any page load (SPA route change) | `page_path`, `page_title`, `referrer`, `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` | Traffic source × page performance |
| S2 | `cta_clicked` | Any CTA button click | `button_text`, `cta_location` (hero / nav / pricing / footer), `page_path`, `destination_url` | Which CTA placements convert best |
| S3 | `wallet_connect_started` | User clicks "Connect Wallet" | `page_path`, `wallet_provider` (MetaMask / Rainbow / WalletConnect) | Wallet UX friction measurement |
| S4 | `wallet_connected` | Wallet successfully connected + challenge signed | `wallet_address` (hashed), `wallet_provider`, `chain_id`, `is_new_user` (bool) | **Registration conversion rate**; wallet provider distribution |
| S5 | `wallet_connect_failed` | Connection or sig rejected / error | `wallet_provider`, `error_type` (user_rejected / timeout / network_error) | Identify broken wallet paths |
| S6 | `role_selected` | User chooses Consumer or Provider role | `role` (CONSUMER / PROVIDER), `is_first_selection` (bool) | Role split ratio; re-selection frequency |
| S7 | `error_occurred` | Unhandled UI error or API 4xx/5xx | `error_type`, `error_message`, `page_path`, `api_endpoint` | Correlate errors with drop-off |

---

### 5.2 Consumer Registration & Wallet Setup

| # | Event Name | Trigger | Properties | Decision It Informs |
|---|-----------|---------|------------|---------------------|
| C1 | `signup_completed` | New Consumer identity created (first wallet connect + CONSUMER role) | `wallet_provider`, `referral_source`, `utm_source`, `utm_medium`, `utm_campaign` | **Top-of-funnel registration rate** |
| C2 | `dashboard_first_viewed` | Consumer lands on `/dashboard/overview` for the first time | `time_since_signup_ms` | Time-to-dashboard; onboarding friction |
| C3 | `onboarding_hub_viewed` | Consumer views `/dashboard/buy` (the onboarding hub) | `wallet_balance_usdc` (bucketed: 0 / <5 / <50 / 50+) | How many users explore onboarding |
| C4 | `deposit_started` | User initiates deposit flow (clicks Deposit button) | `deposit_amount_usdc`, `token`, `chain_id` | Deposit intent volume |
| C5 | `deposit_permit_signed` | ERC-20 permit signature completed | `deposit_amount_usdc`, `token` | Permit step completion rate |
| C6 | `deposit_completed` | On-chain deposit confirmed + synced | `deposit_amount_usdc`, `token`, `tx_hash`, `time_to_confirm_ms` | **首充转化率 (First deposit CVR)**; avg deposit size |
| C7 | `deposit_failed` | Deposit tx reverted or sync failed | `deposit_amount_usdc`, `error_type` (insufficient_gas / reverted / sync_timeout) | Identify deposit failure causes |
| C8 | `voucher_redeemed` | User redeems a credit voucher | `voucher_code`, `credit_amount_usdc` | Promo effectiveness |

---

### 5.3 Consumer First API Call

| # | Event Name | Trigger | Properties | Decision It Informs |
|---|-----------|---------|------------|---------------------|
| C9 | `credential_created` | User creates an API credential at `/dashboard/credentials` | `credential_scope` (all / specific_service), `has_budget_limit` (bool), `budget_usdc`, `has_rpm_limit` (bool) | Credential gating as activation signal |
| C10 | `service_discovered` | User views a service detail (UI) or SDK `search_services()` returns results | `discovery_method` (ui_browse / ui_search / sdk_search), `query`, `results_count`, `page_path` | Discovery UX effectiveness |
| C11 | `service_detail_viewed` | User clicks into a specific service | `service_id`, `service_name`, `service_price_usdc`, `provider_address` (hashed) | Service interest heatmap |
| C12 | `api_invoke_started` | SDK `invoke()` called or UI "Try It" initiated | `service_id`, `service_name`, `cost_usdc`, `invoke_method` (sdk / ui) | Intent-to-invoke volume |
| C13 | `api_invoke_completed` | Invocation succeeds (status: SUCCEEDED / SETTLED) | `service_id`, `service_name`, `cost_usdc`, `latency_ms`, `is_first_invoke` (bool), `invoke_method` | **首次 API 调用转化率**; service quality |
| C14 | `api_invoke_failed` | Invocation fails (FAILED_*, timeout, 4xx) | `service_id`, `error_type` (insufficient_funds / budget_exceeded / price_mismatch / provider_error / timeout), `cost_usdc` | Failure root-cause triage |

---

### 5.4 Provider Registration & Activation

| # | Event Name | Trigger | Properties | Decision It Informs |
|---|-----------|---------|------------|---------------------|
| P1 | `provider_signup_completed` | New Provider identity (first wallet connect + PROVIDER role) | `wallet_provider`, `referral_source`, `utm_source`, `utm_medium`, `utm_campaign` | **Provider registration rate** |
| P2 | `provider_console_first_viewed` | Provider lands on `/provider/console` first time | `time_since_signup_ms` | Time-to-console |
| P3 | `provider_secret_created` | Provider creates signing secret at `/provider/secrets` | `is_first_secret` (bool) | Secret step completion (prerequisite gate) |
| P4 | `service_deploy_started` | Provider opens `/provider/services/deploy` | `entry_point` (console_cta / services_page / direct_url) | Deploy funnel top |
| P5 | `service_manifest_step_completed` | Provider completes a manifest builder section | `step_name` (basic_info / pricing / routing / health_check), `step_number` | Which manifest step causes drop-off |
| P6 | `service_registered` | Service manifest submitted and accepted | `service_id`, `service_name`, `price_usdc`, `has_health_check` (bool), `routing_target_count` | **Provider 注册 (service listing) CVR** |
| P7 | `service_register_failed` | Manifest submission rejected | `error_type`, `error_field` | Registration failure causes |
| P8 | `service_status_toggled` | Provider toggles service active/inactive | `service_id`, `new_status` (active / inactive) | Service lifecycle monitoring |

---

### 5.5 Provider First Call Received

| # | Event Name | Trigger | Properties | Decision It Informs |
|---|-----------|---------|------------|---------------------|
| P9 | `provider_first_call_received` | First invocation routed to provider's service | `service_id`, `service_name`, `call_revenue_usdc`, `time_since_registration_ms` | **Provider 首次被调用转化率**; time-to-first-revenue |
| P10 | `provider_call_received` | Any invocation routed (after first) | `service_id`, `call_revenue_usdc`, `caller_address` (hashed) | Call volume, revenue per provider |
| P11 | `provider_settlement_claimed` | Provider claims on-chain settlement | `settlement_amount_usdc`, `tx_hash`, `services_count` | Payout activation rate |
| P12 | `provider_health_check_failed` | Service health check fails | `service_id`, `failure_type`, `consecutive_failures` | Provider service quality |

---

## 6. Funnel Definitions (for Analytics Tool)

### Funnel A: Consumer Registration → First API Call

```
Step 1: page_viewed { page_path: "/" }           — Landing page visit
Step 2: wallet_connected                          — Wallet auth
Step 3: signup_completed { role: CONSUMER }       — Consumer signup
Step 4: deposit_completed                         — First deposit (首充)
Step 5: credential_created                        — API key created
Step 6: api_invoke_completed { is_first_invoke: true } — First API call
```

**Key Metrics:**
| Metric | Formula | Target |
|--------|---------|--------|
| Visit → Signup CVR | signup_completed / unique page_viewed(/) | > 5% |
| Signup → First Deposit CVR | deposit_completed / signup_completed | > 30% |
| Deposit → First Call CVR | first api_invoke_completed / deposit_completed | > 50% |
| End-to-End Activation | first api_invoke_completed / unique page_viewed(/) | > 1% |
| Time to First Call | median(api_invoke_completed.timestamp − signup_completed.timestamp) | < 30 min |

### Funnel B: Provider Registration → First Call Received

```
Step 1: page_viewed { page_path: "/" }            — Landing page visit
Step 2: wallet_connected                           — Wallet auth
Step 3: provider_signup_completed                  — Provider signup
Step 4: provider_secret_created                    — Signing secret set up
Step 5: service_registered                         — Service listed
Step 6: provider_first_call_received               — First revenue-generating call
```

**Key Metrics:**
| Metric | Formula | Target |
|--------|---------|--------|
| Visit → Provider Signup CVR | provider_signup_completed / unique page_viewed(/) | > 2% |
| Signup → Service Listed CVR | service_registered / provider_signup_completed | > 40% |
| Listed → First Call CVR | provider_first_call_received / service_registered | > 25% |
| Time to First Call Received | median(first_call_received.timestamp − service_registered.timestamp) | < 7 days |

---

## 7. UTM Parameter Strategy

### Standard Taxonomy

| Parameter | Convention | Examples |
|-----------|-----------|----------|
| `utm_source` | Platform name, lowercase | `producthunt`, `hackernews`, `twitter`, `github`, `newsletter`, `google` |
| `utm_medium` | Channel type | `social`, `cpc`, `email`, `referral`, `organic`, `community` |
| `utm_campaign` | Campaign slug | `launch_day_ph`, `provider_outreach_q2`, `hn_show` |
| `utm_content` | Creative variant | `hero_cta`, `sidebar_banner`, `cold_email_v2` |

### Required UTM Coverage

| Channel | Example URL |
|---------|-------------|
| Product Hunt | `?utm_source=producthunt&utm_medium=social&utm_campaign=launch_day_ph` |
| Hacker News | `?utm_source=hackernews&utm_medium=social&utm_campaign=hn_show` |
| Twitter/X | `?utm_source=twitter&utm_medium=social&utm_campaign=launch_day_ph&utm_content=thread_1` |
| Cold Email (Provider) | `?utm_source=email&utm_medium=cold_email&utm_campaign=provider_outreach_q2` |
| Docs/README | `?utm_source=github&utm_medium=referral&utm_campaign=readme_cta` |
| SDK inline | `?utm_source=sdk&utm_medium=referral&utm_campaign=sdk_dashboard_link` |

---

## 8. User Identity & Privacy

### Identity Resolution

```
Anonymous visitor → identify(wallet_address_hash)
                          ↓
              Merge with role, plan, balance tier
```

| Phase | Identifier | Notes |
|-------|-----------|-------|
| Pre-connect | Anonymous ID (cookie / device) | Auto-generated by analytics SDK |
| Post-connect | `sha256(wallet_address)` | **Never store raw wallet address in analytics.** Use one-way hash. |
| Cross-device | Wallet address hash is deterministic | Same wallet = same user across devices |

### Privacy Compliance

- **No PII in event properties.** Wallet address is always hashed.
- No tracking of on-chain balances or transaction details beyond Synapse-internal amounts.
- Respect DNT (Do Not Track) header and provide opt-out.
- Data retention: 13 months (GA4 default); raw events in Segment/PostHog: 24 months.
- GDPR: Wallet hash qualifies as pseudonymous data — document lawful basis (legitimate interest for product improvement).

---

## 9. Implementation Guide

### 9.1 Frontend (Next.js / React)

```typescript
// lib/analytics.ts — Thin wrapper for event tracking

type EventProperties = Record<string, string | number | boolean>;

export function track(eventName: string, properties?: EventProperties) {
  // Segment
  if (window.analytics) {
    window.analytics.track(eventName, {
      ...properties,
      page_path: window.location.pathname,
    });
  }
  // PostHog (if used instead)
  if (window.posthog) {
    window.posthog.capture(eventName, properties);
  }
}

export function identify(walletAddressHash: string, traits?: Record<string, unknown>) {
  window.analytics?.identify(walletAddressHash, traits);
  window.posthog?.identify(walletAddressHash, traits);
}

export function page(pageName?: string, properties?: EventProperties) {
  window.analytics?.page(pageName, properties);
  window.posthog?.capture('$pageview', properties);
}
```

### 9.2 Integration Points

| Where | How | Events |
|-------|-----|--------|
| `WalletAuthGuard` / RainbowKit callbacks | `onConnect` / `onDisconnect` hooks | S3, S4, S5 |
| Role selection UI | `onClick` handler | S6, C1, P1 |
| `useVaultDeposit` hook | Before/after tx and on error | C4, C5, C6, C7 |
| Credential creation form | `onSubmit` success/fail | C9 |
| Discovery page / search | Result render + item click | C10, C11 |
| SDK `invoke()` (Python) | Before call + response handler | C12, C13, C14 |
| Provider deploy page | Step completion + submit | P4, P5, P6, P7 |
| Gateway webhook / polling | Server-side event for first call | P9, P10 |

### 9.3 Server-Side Events (Gateway)

Some events **must** be tracked server-side for accuracy (can't rely on browser):

| Event | Source | Method |
|-------|--------|--------|
| `api_invoke_completed` / `api_invoke_failed` | Gateway settlement engine | Segment server-side SDK or direct PostHog API |
| `provider_first_call_received` | Gateway routing layer | Server-side event with provider context |
| `deposit_completed` | On-chain event listener | Blockchain event → analytics pipeline |
| `provider_settlement_claimed` | Smart contract event | Same as above |

---

## 10. Validation Checklist

Before going live, verify each event:

- [ ] **Event fires** — Check in Segment Debugger / PostHog Live Events
- [ ] **Properties populated** — No `null` or `undefined` in required fields
- [ ] **Naming matches plan** — Exact event name and property keys
- [ ] **Funnel wired** — Events appear in correct funnel order in analytics tool
- [ ] **No PII leaked** — Wallet addresses hashed; no emails/IPs in custom properties
- [ ] **UTMs captured** — `page_viewed` on landing includes all UTM params
- [ ] **Server-side events** — Gateway events reach analytics destination
- [ ] **Deduplication** — Same action doesn't fire duplicate events (e.g., React re-render)
- [ ] **Error events** — Intentionally trigger failures and verify error events fire

---

## 11. Dashboard & Alert Requirements

### Core Dashboards

| Dashboard | Key Widgets |
|-----------|-------------|
| **Funnel Overview** | Consumer 6-step funnel CVR; Provider 6-step funnel CVR; daily trend |
| **Registration** | Signups/day by role, by UTM source; wallet provider breakdown |
| **Activation** | Time-to-first-deposit distribution; time-to-first-call distribution |
| **Provider Health** | Services registered/day; avg time-to-first-call-received; active service % |
| **Revenue** | Daily invoke volume (calls); daily GMV (USDC); revenue per provider |

### Alerts (Slack / PagerDuty)

| Alert | Condition | Channel |
|-------|-----------|---------|
| Signup drop | Daily signups < 50% of 7-day avg | #growth-alerts |
| Deposit failure spike | deposit_failed rate > 20% in 1h window | #eng-alerts |
| API invoke error spike | api_invoke_failed rate > 15% in 1h window | #eng-alerts |
| Provider registration = 0 | No service_registered in 24h | #growth-alerts |
| Funnel CVR drop | Any step-to-step CVR drops > 30% vs prior week | #growth-alerts |

---

## 12. Appendix: Event → Tool Mapping

| Event Range | GA4 | Mixpanel/PostHog | Segment |
|------------|-----|------------------|---------|
| S1–S7 (Shared) | ✅ | ✅ | ✅ (source of truth) |
| C1–C8 (Consumer Reg) | ✅ (as conversions) | ✅ | ✅ |
| C9–C14 (Consumer API) | Conversion only | ✅ (detailed properties) | ✅ |
| P1–P8 (Provider Reg) | ✅ (as conversions) | ✅ | ✅ |
| P9–P12 (Provider Calls) | — | ✅ (server-side) | ✅ (server-side) |
