---
title: "Show HN: My workflow for building and debugging MCP servers with Claude Code and Apidog"
status: draft
platform: hacker-news
created: 2026-04-30
---

I have been building SynapseNetwork, an agent-facing API gateway where agents can discover provider APIs, invoke them, and settle usage through a blockchain-backed payment layer.

One thing I keep running into: MCP Server demos usually show the server, but not the workflow around the server.

The workflow I use combines:

- Claude Code / Codex for repo navigation and changes
- Apidog for HTTP contract debugging
- SDK E2E tests for the real agent path
- local + staging environments
- an ops console publishing queue for turning debugging notes into reusable docs

The most useful test is not just "unit tests pass." It is:

```text
provider register
-> gateway discovery
-> SDK search
-> SDK invoke
-> gateway_signed provider call
-> receipt
```

I wrote up the workflow because it has been more important than any single tool. The main lesson: if you are building agent-facing API infrastructure, design the debug loop, staging proof, SDK E2E, and docs loop as carefully as the server itself.

Feedback welcome, especially from people building MCP servers or provider-style APIs.
