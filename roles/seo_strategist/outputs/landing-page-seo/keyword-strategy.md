---
id: landing-page-keyword-strategy
title: Landing Page Keyword Strategy — Synapse Network
role: seo_strategist
status: draft
created_at: 2026-04-10
updated_at: 2026-04-10
author: seo-strategist-agent
---

# Keyword Strategy: Synapse Network Landing Pages

## Strategy Principle

Target **high-intent, solution-seeking queries** where developers are actively looking for ways to:
1. Let AI agents pay for APIs
2. Manage agent spending / budgets
3. Monetize APIs to machine clients
4. Compare payment infrastructure options

Avoid: generic informational queries ("what is an AI agent") that attract tire-kickers with zero buying intent.

---

## Keyword Map by Page

### 1. Homepage (`/`)

| Type | Keyword | Search Intent | Est. Difficulty |
|------|---------|---------------|-----------------|
| **Primary** | AI agent payment API | Transactional | Medium |
| Secondary | Stripe for AI agents | Navigational/Comparison | Low |
| Secondary | AI agent micropayments | Informational-Commercial | Medium |
| Secondary | machine-to-machine payment API | Commercial | Medium |
| Long-tail | how to let AI agents pay for APIs | Informational-Commercial | Low |
| Long-tail | agent budget isolation cryptocurrency | Commercial | Low |
| Long-tail | MCP agent tool payment | Commercial | Low |

**Content signal:** The homepage must clearly answer "What does Synapse do?" within the first viewport. Use the primary keyword in the H1 and the first 100 words.

---

### 2. Developer Page (`/developers`)

| Type | Keyword | Search Intent | Est. Difficulty |
|------|---------|---------------|-----------------|
| **Primary** | AI agent SDK | Commercial | Medium |
| Secondary | LangChain payment integration | Commercial | Low |
| Secondary | CrewAI tool payments | Commercial | Low |
| Secondary | OpenAI agents SDK payment | Commercial | Low |
| Secondary | agent wallet Python SDK | Commercial | Low |
| Long-tail | give AI agent spending budget | Informational-Commercial | Low |
| Long-tail | MCP tool discovery for agents | Informational | Low |
| Long-tail | prevent AI agent overspending | Problem-solving | Low |

**Content signal:** Lead with a code snippet (`pip install synapse-sdk`, 3-line integration). Developers search for practical solutions, not pitch decks.

---

### 3. Provider Page (`/providers`)

| Type | Keyword | Search Intent | Est. Difficulty |
|------|---------|---------------|-----------------|
| **Primary** | monetize API AI agents | Commercial | Low |
| Secondary | sell API to AI agents | Commercial | Low |
| Secondary | API marketplace AI | Commercial | Medium |
| Secondary | API monetization platform | Commercial | High |
| Long-tail | earn USDC from API calls | Commercial | Low |
| Long-tail | list API for machine clients | Commercial | Low |
| Long-tail | AI agent API provider revenue | Informational-Commercial | Low |

**Content signal:** Lead with economics (95% revenue share, instant settlement). Include a "What agents are buying" section to prove demand.

---

### 4. Pricing Page (`/pricing`)

| Type | Keyword | Search Intent | Est. Difficulty |
|------|---------|---------------|-----------------|
| **Primary** | AI agent API pricing | Commercial | Low |
| Secondary | micropayment API pricing | Commercial | Low |
| Secondary | zero gas fee payments | Commercial | Medium |
| Long-tail | how much does AI agent API cost | Informational | Low |
| Long-tail | M2M transaction pricing model | Informational-Commercial | Low |

**Content signal:** Transparent pricing table. Show the math: "$0.01 call × 5% fee = $0.0005 network cost." Comparison with Stripe's $0.30 minimum.

---

### 5. Comparison: Synapse vs Stripe (`/compare/synapse-vs-stripe`)

| Type | Keyword | Search Intent | Est. Difficulty |
|------|---------|---------------|-----------------|
| **Primary** | Synapse vs Stripe | Comparison | Low |
| Secondary | Stripe alternative AI agents | Comparison | Low |
| Secondary | micropayment alternative to Stripe | Comparison | Medium |
| Long-tail | Stripe minimum fee micropayments | Problem-solving | Low |
| Long-tail | why Stripe doesn't work for AI agents | Problem-solving | Low |

**Content signal:** Feature-by-feature comparison table. Acknowledge Stripe's strengths for H2M; position Synapse as the M2M solution.

---

### 6. Comparison: Synapse vs RapidAPI (`/compare/synapse-vs-rapidapi`)

| Type | Keyword | Search Intent | Est. Difficulty |
|------|---------|---------------|-----------------|
| **Primary** | Synapse vs RapidAPI | Comparison | Low |
| Secondary | RapidAPI alternative for agents | Comparison | Low |
| Secondary | AI-native API marketplace | Commercial | Low |
| Long-tail | RapidAPI not designed for AI agents | Problem-solving | Low |

**Content signal:** Emphasize autonomous discovery (MCP vs browsing a catalog), per-call billing vs subscription plans.

---

## Topic Cluster Architecture

```
                    [Homepage: AI Agent Payment API]
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
    [/developers]       [/providers]         [/pricing]
     Agent SDK           API Monetize        Micropayment Costs
            │                  │                  │
     ┌──────┴──────┐   ┌──────┴──────┐          │
  [/docs/sdk]   [/blog]  [Use Cases]     [/compare/*]
  Quickstart    Tutorials  By vertical   vs Stripe / RapidAPI
```

**Internal linking rules:**
1. Homepage links to all tier-1 pages (developers, providers, pricing)
2. Every tier-1 page links back to homepage and to its siblings
3. Comparison pages link to the relevant tier-1 page (vs Stripe → pricing)
4. Blog posts link to the most relevant tier-1 page as CTA
5. Documentation pages link to `/developers` as the entry point

---

## AI Search (AEO/GEO/LLMO) Keyword Targets

These are not traditional SEO keywords — they are **queries that developers ask AI assistants**:

| Query Pattern | Target Page | Structural Signal |
|---------------|-------------|-------------------|
| "How do I let my AI agent pay for APIs?" | Homepage / Developers | FAQ schema, clear H2 answer |
| "What's the best payment API for AI agents?" | Homepage | List schema, feature comparison |
| "Stripe alternative for micropayments" | vs-Stripe | Comparison table, direct answer |
| "How to monetize my API to AI agents" | Providers | HowTo schema, step-by-step |
| "MCP tool payment integration" | Developers | Code block, tutorial structure |
| "prevent AI agent from overspending" | Developers | FAQ schema, problem-solution |

**Optimization rules for AI citation:**
1. Answer the query in the first 2 sentences after the H2
2. Use structured data (FAQ, HowTo) so LLMs can extract clean answers
3. Include specific numbers ($0.01, 5%, $5 budget)
4. Cite your own product name clearly in the answer paragraph
5. Use definition-style formatting: "**Synapse Network** is a decentralized..."

---

## Keyword Prioritization Matrix

| Page | Impact | Effort | Priority |
|------|--------|--------|----------|
| Homepage | 🔴 Critical | Medium | **P0** |
| /developers | 🔴 Critical | Medium | **P0** |
| /providers | 🟡 High | Low | **P1** |
| /compare/synapse-vs-stripe | 🟡 High | Low | **P1** |
| /pricing | 🟡 High | Low | **P1** |
| /compare/synapse-vs-rapidapi | 🟢 Medium | Low | **P2** |
| /blog (ongoing) | 🟢 Medium | Ongoing | **P2** |
