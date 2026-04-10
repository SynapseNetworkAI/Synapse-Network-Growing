---
id: landing-page-seo-audit-report
title: Landing Page SEO Audit Report & Implementation Checklist — Synapse Network
role: seo_strategist
status: draft
created_at: 2026-04-10
updated_at: 2026-04-10
author: seo-strategist-agent
---

# SEO Audit Report: Synapse Network Landing Page

## Executive Summary

Synapse Network is pre-launch. There is no public landing page deployed yet — the current repository contains an internal Ops dashboard and marketing content assets. This audit evaluates the **SEO readiness of the planned landing site** and provides a complete implementation blueprint.

### Key Findings

| Area | Status | Severity |
|------|--------|----------|
| Meta tags & title optimization | ❌ Not implemented | 🔴 Critical |
| Structured data (JSON-LD) | ❌ Not implemented | 🔴 Critical |
| robots.txt & sitemap | ❌ Not implemented | 🔴 Critical |
| Keyword targeting strategy | ❌ Not defined | 🔴 Critical |
| AI search optimization (AEO) | ❌ Not addressed | 🟡 High |
| Open Graph / Twitter Cards | ❌ Not implemented | 🟡 High |
| Canonical URL strategy | ❌ Not implemented | 🟡 High |
| Internal linking architecture | ❌ Not planned | 🟡 High |
| Content depth for target keywords | ⚠️ Partially exists in marketing docs | 🟡 High |
| Comparison/alternative pages | ❌ Not built | 🟢 Medium |
| Core Web Vitals readiness | ⏳ Depends on tech stack choice | 🟢 Medium |

### Top 3 Priorities Before Launch

1. **Implement per-page meta tags** — title, description, canonical, OG, Twitter for all 6 core pages
2. **Deploy structured data** — Organization, WebSite, SoftwareApplication, FAQPage, HowTo schemas
3. **Publish robots.txt + XML sitemap** — with explicit AI crawler allowlisting

---

## 1. Technical SEO Findings

### 1.1 Crawlability & Indexation

**Finding:** No public site exists yet. When deployed:

| Check | Recommendation | Priority |
|-------|----------------|----------|
| robots.txt | Deploy `robots.txt` at site root. Allow all standard + AI crawlers (GPTBot, PerplexityBot, ClaudeBot). Block /api/, /admin/, /dashboard/. | 🔴 P0 |
| XML sitemap | Generate and submit `sitemap.xml` to Google Search Console and Bing Webmaster Tools. Include all 6 core landing pages + docs + blog. | 🔴 P0 |
| Canonical URLs | Every page must have a self-referencing `<link rel="canonical">`. Enforce trailing-slash consistency (recommend: no trailing slash). | 🔴 P0 |
| HTTPS | Enforce HTTPS site-wide with HSTS header. Redirect all HTTP → HTTPS. | 🔴 P0 |

**Source code delivered:** `src/robots.txt`, `src/sitemap-config.ts`

### 1.2 URL Structure

**Recommended URL hierarchy:**

```
/                           → Homepage
/developers                 → Agent Developer landing
/providers                  → API Provider landing
/pricing                    → Pricing
/compare/synapse-vs-stripe  → Competitor comparison
/compare/synapse-vs-rapidapi
/docs                       → Documentation hub
/docs/quickstart
/docs/sdk/python
/docs/sdk/typescript
/docs/mcp-integration
/blog                       → Blog index
/blog/{slug}                → Individual posts
```

**Rules:**
- Lowercase, hyphen-separated
- No file extensions (.html)
- No trailing slashes
- No query parameters for content pages
- Max 3 directory levels

### 1.3 Page Speed & Core Web Vitals

**Recommendations for the landing page tech stack:**

| Metric | Target | How to Achieve |
|--------|--------|----------------|
| LCP | < 2.5s | Use SSR or SSG (Next.js, Astro). Preload hero image. Inline critical CSS. |
| INP | < 200ms | Minimize JS bundle. Lazy-load below-fold components. No heavy client-side rendering for landing pages. |
| CLS | < 0.1 | Set explicit width/height on images. Reserve space for dynamic content. Avoid layout-shifting ads or CTAs. |

**Stack recommendation:** Astro or Next.js with static export for landing pages. React SPA (current dashboard stack) is **not recommended** for SEO-critical pages — search engines struggle with client-rendered content.

### 1.4 Mobile & Security

| Check | Recommendation |
|-------|----------------|
| Responsive design | Tailwind CSS (already in dashboard stack) handles this well. Ensure tap targets ≥ 48px. |
| Viewport meta | `<meta name="viewport" content="width=device-width, initial-scale=1.0">` on all pages. |
| HTTPS | Mandatory. Use Let's Encrypt or Cloudflare for free SSL. |
| HSTS | Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` header. |

---

## 2. On-Page SEO Findings

### 2.1 Title Tags

**Current state:** Only `<title>Synapse Ops Dashboard</title>` exists (internal dashboard). No landing page titles.

**Delivered:** Complete per-page title configuration in `src/seo-config.ts`

| Page | Title (50-60 chars) | Primary Keyword |
|------|---------------------|-----------------|
| Homepage | Synapse Network — The Settlement Layer for AI Agents | AI agent payment API |
| Developers | Synapse SDK for AI Agent Developers — 3 Lines to Pay-Per-Call | AI agent SDK |
| Providers | Monetize Your API in the Agent Economy — Synapse Provider | monetize API AI agents |
| Pricing | Synapse Network Pricing — Zero-Gas Micropayments from $0.01 | AI agent API pricing |
| vs Stripe | Synapse vs Stripe — Why Stripe Fails for AI Agent Payments | Synapse vs Stripe |
| vs RapidAPI | Synapse vs RapidAPI — Agent-Native API Marketplace | Synapse vs RapidAPI |

### 2.2 Meta Descriptions

**Current state:** No meta descriptions on any page.

**Delivered:** 150-160 character descriptions per page in `src/seo-config.ts`. Each includes the primary keyword and a clear value proposition.

### 2.3 Open Graph & Twitter Cards

**Current state:** Not implemented.

**Delivered:** Full OG and Twitter Card meta tags in `src/seo-config.ts` + `src/head-injector.ts`. Requires a default OG image to be created at `/og/synapse-og-default.png` (recommended: 1200×630px).

### 2.4 Heading Structure Recommendations

Each landing page should follow this heading hierarchy:

**Homepage:**
```
H1: The Settlement Layer for AI Agents
  H2: Give Your Agent a Budget. Let It Pay for APIs.
  H2: How It Works
    H3: 1. Install the SDK
    H3: 2. Create an Agent Wallet
    H3: 3. Run Your Agent
  H2: Built for Both Sides of the Marketplace
    H3: For Agent Developers
    H3: For API Providers
  H2: Why Not Stripe? Why Not API Keys?
  H2: Frequently Asked Questions
  H2: Get Started in 3 Minutes
```

**Developer Page:**
```
H1: Build Agents That Pay for Their Own Tools
  H2: 3-Line Integration
  H2: Budget Isolation — Cryptographic Spend Limits
  H2: MCP-Native Discovery
  H2: Supported Frameworks
    H3: LangChain
    H3: CrewAI
    H3: OpenAI Agents SDK
  H2: SDK Reference
  H2: FAQ
```

---

## 3. Structured Data Assessment

**Current state:** No JSON-LD or structured data on any page.

**Delivered:** Complete schema markup templates in `src/structured-data.ts`

| Schema Type | Target Page | Rich Result Type |
|-------------|-------------|-----------------|
| Organization | All pages | Knowledge Panel |
| WebSite | All pages | Sitelinks Search Box |
| SoftwareApplication | Homepage, Developers | Software rich snippet |
| FAQPage | Homepage, Developers, Pricing | FAQ rich results |
| HowTo | Developers | How-to rich results |
| BreadcrumbList | All sub-pages | Breadcrumb trail |

**Validation:** After deployment, test all pages with [Google Rich Results Test](https://search.google.com/test/rich-results).

---

## 4. Content Optimization Recommendations

### 4.1 Homepage Content Blueprint

**Target: 800-1200 words** of visible content (not counting navigation/footer).

| Section | Content Guidance | SEO Signal |
|---------|-----------------|------------|
| Hero | "The Settlement Layer for AI Agents" + 1-sentence description + primary CTA | H1 with primary keyword |
| Problem statement | "AI agents are brilliant but broke" narrative | Matches search intent |
| How it works | 3-step visual (Install → Wallet → Run) | HowTo schema eligible |
| Two-sided value | Developer benefits + Provider benefits (tabs or columns) | Covers both ICPs |
| Comparison table | Why not Stripe / API keys / direct crypto | Links to /compare/* pages |
| Social proof | GitHub stars, demo video, framework logos | E-E-A-T trust signals |
| FAQ section | 6 questions from `structured-data.ts` | FAQ schema rich results |
| CTA | "Get Started Free" → /developers | Conversion point |

### 4.2 Developer Page Content Blueprint

**Target: 1000-1500 words**

| Section | Content Guidance |
|---------|-----------------|
| Hero | "Build Agents That Pay for Their Own Tools" + `pip install synapse-sdk` |
| Code example | Full 10-line working example with comments |
| Budget isolation explainer | Visual diagram of wallet → lock → spend → settle |
| Framework integrations | Tabs: LangChain / CrewAI / OpenAI Agents |
| SDK reference link | Quick-reference of key classes + link to full docs |
| FAQ | Framework-specific questions |

### 4.3 Provider Page Content Blueprint

**Target: 800-1000 words**

| Section | Content Guidance |
|---------|-----------------|
| Hero | "Monetize Your API in the Agent Economy" + revenue stats |
| Economics | 95% share, zero gas, instant settlement — with math |
| Use cases | 3-4 real service examples with pricing (from provider_onboarding.md) |
| Integration | 3-step quickstart (Docker → Register → Earn) |
| CTA | "Start Selling Your APIs" → Provider repo |

### 4.4 AI Search Optimization (AEO/GEO/LLMO)

To maximize appearance in AI-generated answers:

1. **Direct-answer paragraphs:** After each H2, the first 2-3 sentences should directly and concisely answer the implied question. LLMs extract these as citation blocks.

2. **Definition patterns:** Use "**Synapse Network** is..." format in the first paragraph so LLMs can attribute the definition.

3. **Structured comparisons:** Feature comparison tables are highly cited by AI search engines. Include at least one per comparison page.

4. **Specific numbers:** "$0.01 per call," "5% network fee," "$5 USDC budget" — LLMs prefer concrete data over vague claims.

5. **FAQ as training signal:** The FAQ section with structured data serves dual purpose — rich results in Google AND training/retrieval signal for AI models.

6. **robots.txt AI access:** Already configured to allow GPTBot, PerplexityBot, ClaudeBot, Google-Extended. Do NOT block these crawlers.

---

## 5. Authority & Link Building Strategy

### Internal Linking

| From | To | Anchor Text Pattern |
|------|----|---------------------|
| Homepage | /developers | "Get the SDK" / "For Agent Developers" |
| Homepage | /providers | "For API Providers" / "Start Selling" |
| Homepage | /pricing | "See Pricing" |
| Blog posts | /developers | "integrate with the Synapse SDK" |
| Comparison pages | /pricing | "see full pricing breakdown" |
| Docs | /developers | "back to developer overview" |

### External Link Opportunities

| Source | Tactic |
|--------|--------|
| GitHub READMEs | Ensure Synapse-Network, Synapse-Network-Sdk, Synapse-Network-Provider repos link back to landing page |
| Hacker News launch | Launch post links to landing page (dofollow from HN) |
| Dev.to / Hashnode | Republish tech blog with canonical back to synapse.network/blog |
| MCP ecosystem directories | Get listed in MCP tool directories |
| Framework integration docs | PR to LangChain/CrewAI docs if they maintain partner/integration lists |

---

## 6. Implementation Checklist

### Phase 1: Pre-Launch Critical (P0)

- [ ] Choose landing page tech stack (recommended: **Astro** or **Next.js static export**)
- [ ] Integrate `seo-config.ts` into page head rendering
- [ ] Integrate `structured-data.ts` JSON-LD injection on all pages
- [ ] Deploy `robots.txt` at site root
- [ ] Generate and deploy `sitemap.xml` from `sitemap-config.ts`
- [ ] Create OG image (`/og/synapse-og-default.png`, 1200×630px)
- [ ] Implement canonical URL on every page
- [ ] Enforce HTTPS with HSTS
- [ ] Submit sitemap to Google Search Console
- [ ] Submit sitemap to Bing Webmaster Tools
- [ ] Verify all pages pass [Rich Results Test](https://search.google.com/test/rich-results)

### Phase 2: Launch Week (P1)

- [ ] Publish homepage with 800+ words of optimized content
- [ ] Publish /developers page with code examples and FAQ
- [ ] Publish /providers page with economics and use cases
- [ ] Publish /pricing page with transparent pricing table
- [ ] Publish /compare/synapse-vs-stripe comparison page
- [ ] Implement BreadcrumbList schema on all sub-pages
- [ ] Verify internal linking between all tier-1 pages
- [ ] Set up Google Analytics 4 + Search Console integration
- [ ] Test all OG tags with [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/)
- [ ] Test Twitter Cards with [Card Validator](https://cards-dev.twitter.com/validator)

### Phase 3: Post-Launch Growth (P2)

- [ ] Publish /compare/synapse-vs-rapidapi comparison page
- [ ] Publish first blog post (MCP + budgeted tool use)
- [ ] Set canonical URLs on Dev.to/Hashnode cross-posts
- [ ] Monitor Google Search Console for indexation issues
- [ ] Track Core Web Vitals in Search Console
- [ ] Submit to MCP ecosystem directories
- [ ] Build backlinks from framework integration docs
- [ ] Monthly content refresh: update FAQ, add new comparison pages
- [ ] Implement hreflang tags when Chinese-language version launches

---

## 7. Files Delivered

| File | Purpose |
|------|---------|
| `src/seo-config.ts` | Per-page meta tags, OG, Twitter, canonical config |
| `src/structured-data.ts` | JSON-LD schema templates (Organization, WebSite, SoftwareApp, FAQ, HowTo, Breadcrumb) |
| `src/head-injector.ts` | SSR/SSG utility for generating SEO head elements |
| `src/sitemap-config.ts` | Sitemap URL entries + XML generator |
| `src/robots.txt` | Robots.txt with AI crawler allowlisting |
| `keyword-strategy.md` | Complete keyword map with intent, difficulty, and prioritization |
| `seo-audit-report.md` | This document — audit findings + implementation checklist |

---

## 8. Validation Criteria

This report is ready for review when:

1. ✅ All 7 source files are syntactically valid
2. ✅ Meta tags cover all 6 core landing pages
3. ✅ JSON-LD schemas pass [Schema.org Validator](https://validator.schema.org/) syntax
4. ✅ robots.txt includes AI crawler directives
5. ✅ Keyword strategy maps primary + secondary keywords per page
6. ✅ Implementation checklist is phased (P0/P1/P2)
7. ⏳ Rich Results Test validation — requires deployed site

---

*This report was generated as part of the 30-Day Blitzkrieg campaign, SEO workstream.*
