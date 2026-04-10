---
id: landing-page-seo-review
title: "Review: Landing Page SEO 优化方案"
role: dev_rel
status: review
created_at: 2026-04-10
updated_at: 2026-04-10
author: dev-rel-agent
reviewed_deliverable: roles/seo_strategist/outputs/landing-page-seo
---

# DevRel Review: Landing Page SEO 优化方案

## Review Summary

| Criterion | Verdict |
|-----------|---------|
| **Completeness** | ✅ PASS — All 7 deliverables present |
| **Product Alignment** | ✅ PASS — Consistent with product marketing context |
| **Technical Accuracy** | ⚠️ CONDITIONAL PASS — 3 issues require fixes |
| **Code Quality** | ⚠️ CONDITIONAL PASS — 2 issues require fixes |
| **SEO Correctness** | ✅ PASS — Schemas, meta tags, keyword strategy are sound |
| **DX Usability** | ⚠️ CONDITIONAL PASS — 1 issue requires fix |

### Overall Verdict: **CONDITIONAL PASS** — Fix 4 blocking issues, then approved.

---

## Blocking Issues (Must Fix)

### B1. `head-injector.tsx` — SEOHead component renders into `<body>`, not `<head>`

**Severity:** 🔴 Critical
**File:** `src/head-injector.tsx:98-108`

The `SEOHead` React component renders all meta tags, canonical links, and JSON-LD inside a hidden `<div>` in the body:

```tsx
return React.createElement('div', {
  id: 'seo-head',
  style: { display: 'none' },
  dangerouslySetInnerHTML: { __html: html },
});
```

**Problem:** Search engines expect `<meta>`, `<title>`, `<link rel="canonical">`, and JSON-LD `<script>` tags in the `<head>` element. While Google *may* tolerate some body-placed meta tags, this is unreliable and explicitly defeats the purpose of an SEO component. This is a **DX trap** — a developer copying this component would silently break their SEO.

**Fix:** Either:
1. Replace with a `react-helmet-async` implementation (as the comment claims but doesn't deliver)
2. Use `ReactDOM.createPortal(...)` targeting `document.head`
3. Rename/reframe the component as a pure string generator for SSR/SSG only, and remove the misleading React component wrapper

**Recommendation:** Option 3 is simplest and most honest. Keep `generateHeadHTML()` (it's well-written), remove `SEOHead` component, and add a clear usage example for Next.js/Astro.

---

### B2. Sitemap/SEO config mismatch — phantom page `synapse-vs-direct-crypto`

**Severity:** 🟡 High
**File:** `src/sitemap-config.ts:27`

The sitemap includes a URL that has **no corresponding SEO config**:

```ts
{ loc: `${BASE}/compare/synapse-vs-direct-crypto`, changefreq: 'monthly', priority: 0.7 },
```

But `seo-config.ts` only defines `vs-stripe` and `vs-rapidapi`. There's no keyword strategy, meta tags, or content blueprint for this page.

**Fix:** Either remove this entry from the sitemap, or add the corresponding page definition in `seo-config.ts` and `keyword-strategy.md`.

---

### B3. `sitemap-config.ts` duplicates `BASE` constant instead of importing `SITE_BASE`

**Severity:** 🟡 High
**File:** `src/sitemap-config.ts:16`

```ts
const BASE = 'https://synapse.network';  // local duplicate
```

Meanwhile `seo-config.ts` already exports:

```ts
export const SITE_BASE = 'https://synapse.network';
```

**Problem:** When the domain changes (it's currently TBD per product context), someone will update one but not the other. This violates the DRY baseline.

**Fix:** `import { SITE_BASE } from './seo-config';` and delete the local `BASE` const.

---

### B4. `head-injector.tsx` `Object.entries` destructuring lacks type annotation

**Severity:** 🟡 High
**File:** `src/head-injector.tsx:63-64`

Under `--strict`, this line fails:

```ts
const attrs = Object.entries(l)
  .map(([k, v]) => `${k}="${escapeAttr(String(v))}"`)
```

`k` and `v` are implicitly `any`. TypeScript strict mode rejects this.

**Fix:** Add explicit type:

```ts
.map(([k, v]: [string, unknown]) => ...)
```

---

## Non-Blocking Issues (Should Fix)

### N1. `robots.txt` includes `/_next/static/` disallow — framework assumption

**File:** `src/robots.txt:9`

The audit report's **top recommendation** is Astro or Next.js SSG. But the robots.txt hardcodes a Next.js-specific path. If the team picks Astro, this rule is dead weight and confusing.

**Recommendation:** Add a comment: `# Uncomment if using Next.js:` and keep the line commented-out by default, or move it to a framework-specific section.

### N2. Placeholder URLs and emails should be clearly flagged

**Files:** `src/structured-data.ts:22-23, 33`

- `https://twitter.com/SynapseNetwork` — may not exist
- `https://github.com/Synapse-Network` — may not exist
- `support@synapse.network` — placeholder

These are fine as templates, but should have `// TODO: verify before launch` comments so they don't slip through.

### N3. `downloadUrl` points to non-existent PyPI package

**File:** `src/structured-data.ts:78`

```ts
downloadUrl: 'https://pypi.org/project/synapse-sdk/',
```

The SDK isn't published on PyPI yet. Per DevRel rules, we should only reference existing artifacts. Add a `// TODO: update when package is published` comment.

### N4. Document frontmatter has `status: draft` — should be `status: ready`

**Files:** `keyword-strategy.md:5`, `seo-audit-report.md:5`

Per the campaign tracking protocol, when deliverables are complete, their status should be `ready` so the campaign checklist can be updated.

### N5. `softwareVersion: '0.1.0'` is hardcoded

**File:** `src/structured-data.ts:79`

This will drift immediately. Either pull from `package.json` at build time or add a TODO comment.

---

## What's Good

1. **Keyword strategy is sharp.** Intent-based targeting with clear difficulty/priority ranking. Avoids vanity keywords. The AI search (AEO/LLMO) section is forward-thinking and well-structured.

2. **Structured data is comprehensive.** 6 schema types covering Organization, WebSite, SoftwareApp, FAQ, HowTo, Breadcrumb. The FAQ content is accurate to the product spec.

3. **`seo-config.ts` is well-architected.** Clean types, single source of truth for all meta tags, sensible defaults. The `getHeadMeta()` helper is immediately usable.

4. **Phased implementation checklist is practical.** P0/P1/P2 breakdown with realistic scoping. Pre-launch vs launch-week vs post-launch gives the team a clear runway.

5. **Content blueprints per page are actionable.** Word counts, section hierarchy, heading structures — a content writer can execute from these specs directly.

6. **AI crawler allowlisting in robots.txt** is the right call for a product that wants AI search visibility.

---

## Compilation Verification

| File | Compiles? | Notes |
|------|-----------|-------|
| `seo-config.ts` | ✅ Yes | Clean under `--strict --target es2020` |
| `structured-data.ts` | ✅ Yes | Clean (imports from seo-config work) |
| `sitemap-config.ts` | ✅ Yes | Clean (standalone, no imports) |
| `head-injector.tsx` | ❌ No | Requires React types in scope; strict-mode type error on `Object.entries` destructuring |
| `robots.txt` | N/A | Static file, valid syntax |

Note: The implementation step claimed "All TypeScript compiles cleanly ✅" — this is inaccurate for `head-injector.tsx` in strict mode.

---

## Review Acceptance Checklist

| # | Check | Status |
|---|-------|--------|
| 1 | All 7 files delivered | ✅ |
| 2 | Meta tags cover 6 core pages | ✅ |
| 3 | JSON-LD schemas syntactically valid | ✅ |
| 4 | robots.txt includes AI crawlers | ✅ |
| 5 | Keyword strategy maps primary + secondary per page | ✅ |
| 6 | Implementation checklist is phased | ✅ |
| 7 | All TS files compile cleanly | ❌ B4 |
| 8 | No config inconsistencies across files | ❌ B2, B3 |
| 9 | React component is production-viable | ❌ B1 |
| 10 | Product accuracy (no phantom references) | ⚠️ N2, N3 |

**Result:** 6/10 pass, 4 require fixes → **CONDITIONAL PASS**

---

## Required Actions Before Approval

1. Fix B1: Remove `SEOHead` React component; keep `generateHeadHTML` as SSR utility + add framework-specific usage docs
2. Fix B2: Remove or define `synapse-vs-direct-crypto` sitemap entry
3. Fix B3: Import `SITE_BASE` instead of duplicating in `sitemap-config.ts`
4. Fix B4: Add explicit types to `Object.entries` destructuring

After these 4 fixes, this deliverable moves to `status: ready`.
