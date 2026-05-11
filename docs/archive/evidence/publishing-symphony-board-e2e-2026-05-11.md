---
id: publishing-symphony-board-e2e-2026-05-11
title: Publishing Symphony Board E2E Validation
role: dev_rel
status: ready
created_at: 2026-05-11
updated_at: 2026-05-11
author: codex
target_repo: Synapse-Network-Growing-agent-b
---

# Publishing Symphony Board E2E Validation

Local target: `http://localhost:9700/publishing?tab=tasks`

Validated content task:

`第 1 篇：我为什么要做一人公司的系统，而不是只做一个产品`

## Result

1. Creating the task generated one `source_plan` document and projected the card into `待审核`.
2. Approving the plan generated six platform tasks and six `platform_draft` documents for X, Hacker News, Reddit, V2EX, DEV, and Hashnode.
3. The card projected into `待发布` after platform documents existed.
4. Marking DEV live with `https://example.com/local-validation/solo-company-system-post` changed the task to `live`, changed the DEV document to `published`, and projected the card into `已发布`.
5. No real external platform publish was attempted.

## Bug Found And Fixed

During validation, `approve-and-generate-tasks` took about 403 seconds for six real Codex-backed platform generations. The old implementation created or updated task rows before each LLM call and committed only after all platforms completed, which held a SQLite write transaction long enough to trigger scheduler `database is locked` errors and client timeouts.

Fix: platform generation now performs the LLM call before opening the per-platform write section, commits after each platform result, and commits the approval event before serial generation starts. This keeps partial results durable and avoids holding a long write transaction while Codex is running.
