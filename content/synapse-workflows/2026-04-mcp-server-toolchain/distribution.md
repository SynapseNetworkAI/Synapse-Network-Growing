---
title: "Distribution tracker"
status: draft
created: 2026-04-30
---

# Distribution Tracker

Canonical content source:
`/Users/cliff/workspace/agent/Synapse-Network-Growing/content/synapse-workflows/2026-04-mcp-server-toolchain`

Publishing queue:
`http://localhost:9700/publishing`

Rule:
Long-form articles, video scripts, screenshots, and raw recordings stay in git. Only final short social drafts are copied into `/publishing` for human review.

## Publishing Checklist

- [ ] Run text secret scan on markdown and subtitle files.
- [ ] Review screenshots and recordings for secrets, private paths, credentials, notifications, and personal accounts.
- [ ] Copy final X thread into `/publishing`.
- [ ] Manually review X draft in `/publishing`.
- [ ] Publish or schedule X thread.
- [ ] Publish long-form English article to blog first.
- [ ] Submit HN manually.
- [ ] Post Reddit variants manually, one community at a time.
- [ ] Post V2EX manually.
- [ ] Upload final video only from `assets/final/`.
- [ ] Backfill URLs below.

## Platform Status

| Platform | Source File | Status | URL | Notes |
| --- | --- | --- | --- | --- |
| X English thread | `x-thread.en.md` | draft | - | Import into `/publishing` after final review. |
| X Chinese thread | `x-thread.zh-CN.md` | draft | - | Optional if Chinese X audience is active. |
| Hacker News | `hn.md` | draft | - | Keep neutral, non-marketing. |
| Reddit r/LocalLLaMA | `reddit-local-llama.md` | draft | - | Ask workflow question, avoid promotional tone. |
| Reddit r/OpenAI | `reddit-openai.md` | draft | - | Focus on AI coding workflow. |
| Reddit r/java | `reddit-java.md` | draft | - | Only post if Java SDK discussion is desired. |
| V2EX | `v2ex.md` | draft | - | Chinese workflow discussion. |
| Long-form English | `article.en.md` | draft | - | Publish to blog/docs when ready. |
| Long-form Chinese | `article.zh-CN.md` | draft | - | Publish after English source stabilizes. |
| Video | `video/script.en.md` | draft | - | Record only after checklist passes; publish `assets/final/synapse-workflow-demo.mp4`. |

## Secret Scan Command

```bash
cd /Users/cliff/workspace/agent/Synapse-Network-Growing/content/synapse-workflows/2026-04-mcp-server-toolchain
rg -i "private key|bearer|jwt|secret|token|api_key|password|mnemonic|gcloud secrets versions access|BEGIN .* KEY" .
```

Expected result:
Only intentional safety checklist mentions should appear. No real credentials or secret values are allowed.
