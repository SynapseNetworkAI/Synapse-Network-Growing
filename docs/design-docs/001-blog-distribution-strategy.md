---
id: adr-001-blog-distribution
title: ADR 001 - Blog and Content Distribution Strategy
role: cross-functional
status: published
created_at: 2026-04-03
updated_at: 2026-04-03
author: CTO
---

# Architecture Decision Record (ADR) 001: Blog and Content Distribution Strategy

## 1. Context (背景问题)
The Synapse Developer Console (`user-front`) operates as a core execution and settlement terminal. We need to publish technical blogs and marketing copy to grow the platform, but we must decide where this content lives and how it is served to users.

## 2. Decision (决策)
**We will NOT build a custom CMS (Content Management System) within `user-front`.**

Instead, we will adopt a **Decoupled Git-to-Distribution** strategy:
- **SSOT (Single Source of Truth):** All articles, blogs, and GTM copy live exclusively as Markdown files inside the `Synapse-Network-Growing` repository (`roles/dev_rel/contents/` and `roles/growth_lead/`).
- **Distribution Platforms:** Content will be deployed to third-party developer-centric platforms such as:
  - **Substack** (for email subscriber growth and newsletters)
  - **Hashnode / Dev.to** (for SEO and developer community discovery)
  - **Medium / Mirror.xyz** (for Web3 specific traction)
- **User-Front Integration:** The existing Developer Console will only add a simple hardcoded "Blog" navigation link (e.g., in the top right header as shown in the platform design) that issues a `301 Redirect` or `href_<blank>` to our primary external blog host (e.g., `synapsenetwork.substack.com`).

## 3. Rationale (为什么这么做)
- **Less is More:** Building and maintaining a rich-text editor, image hosting, and SEO optimization layer inside a financial settlement dashboard introduces severe scope creep and technical debt.
- **Conversion focused:** Platforms like X, Dev.to, and Substack inherently have built-in distribution algorithms. We go to where the developers already are.
- **Isolation:** Follows the "Harness Engineering" principle. The code repository is exactly what Codex and other agents read. Storing the final product in GitHub Markdown ensures absolute version control.

## 4. Verification Check
- No PRs should be merged into `user-front` introducing new database schema models for `posts` or `articles`.
- Marketing agents (Growth Lead) will export the verified Markdown from this repo directly to external platforms.
