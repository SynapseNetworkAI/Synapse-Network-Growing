---
title: "SynapseNetwork MCP Server Workflow Content Pack"
status: draft
created: 2026-04-30
---

# SynapseNetwork MCP Server Workflow Content Pack

This folder is the canonical source for a workflow article and video package about building SynapseNetwork MCP/provider services with Claude Code, Apidog, SDK E2E, staging, and the ops publishing queue.

Canonical path:
`/Users/cliff/workspace/agent/Synapse-Network-Growing/content/synapse-workflows/2026-04-mcp-server-toolchain`

## Source Files

| File | Purpose |
| --- | --- |
| `article.en.md` | English long-form source article. |
| `article.zh-CN.md` | Chinese long-form adaptation. |
| `x-thread.en.md` | English X/Twitter thread draft. |
| `x-thread.zh-CN.md` | Chinese X/Twitter thread draft. |
| `hn.md` | Hacker News submission text. |
| `reddit-local-llama.md` | Reddit r/LocalLLaMA version. |
| `reddit-openai.md` | Reddit r/OpenAI version. |
| `reddit-java.md` | Reddit r/java discussion version. |
| `v2ex.md` | V2EX Chinese discussion version. |
| `distribution.md` | Publishing checklist and URL tracker. |
| `video/shot-list.md` | Shot-by-shot recording plan. |
| `video/script.en.md` | English video narration script. |
| `video/script.zh-CN.md` | Chinese video narration script. |
| `video/recording-checklist.md` | Local recording safety checklist. |
| `video/post-production.md` | Local ffmpeg/whisper processing runbook. |

## Storage Rule

Keep long-form articles, scripts, screenshots, raw recordings, edited videos, and distribution records in this git-backed folder.

Use `http://localhost:9700/publishing` only for final short social drafts that need human review before posting.

## Publishing Use

- Publish `article.en.md` to the company/personal blog first, then optionally cross-post to Dev.to and Hashnode.
- Use `article.zh-CN.md` for V2EX or Chinese developer communities.
- Copy `x-thread.en.md` and optional `x-thread.zh-CN.md` into `/publishing` only after final review.
- Submit `hn.md`, Reddit variants, and `v2ex.md` manually; do not automate cross-posting.
- Backfill all final URLs in `distribution.md`.

## Recording Rule

Record locally only after `video/shot-list.md` and `video/recording-checklist.md` are reviewed. Raw videos go to `assets/recordings/raw/`; publishable edits go to `assets/recordings/edited/`; final video, subtitles, and covers go to `assets/final/`.

Expected final files:

- `assets/final/synapse-workflow-demo.mp4`
- `assets/final/synapse-workflow.en.srt`
- optional `assets/final/synapse-workflow.zh-CN.srt`
- optional `assets/final/synapse-workflow-demo-subtitled.mp4`
