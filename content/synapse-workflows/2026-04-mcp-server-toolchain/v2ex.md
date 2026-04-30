---
title: "分享我开发 SynapseNetwork MCP Server 的工具流"
status: draft
platform: v2ex
language: zh-CN
created: 2026-04-30
---

# 分享我开发 SynapseNetwork MCP Server 的工具流：Claude Code、Apidog、SDK E2E 和 staging

最近在做 SynapseNetwork，一个面向 agent 的 API 网关：agent 可以发现 API、调用 provider，并通过区块链完成小额付款。

做下来最大的体会是：MCP Server 或 agent API infrastructure 的难点不只是 server 本身，而是围绕它的开发、调试、部署和验证工作流。

我现在比较稳定的一套工具流：

1. Claude Code / Codex：读代码、改代码、补测试、同步文档。
2. Apidog：调 HTTP 合同，确认 request/response/header/auth error。
3. SDK E2E：站在 agent/consumer 视角跑完整链路。
4. local + staging：本地跑得快，staging 验证真实部署问题。
5. ops console publishing：把踩坑经验整理成草稿，人审后发布。

我最关心的 E2E 不是“某个单测过了”，而是：

```text
provider register
-> gateway discovery
-> SDK search
-> SDK invoke
-> gateway_signed provider call
-> receipt
```

这条链在 local 和 staging 都通，说明 agent 真的能用。

几个踩坑后的规则：

- Provider runtime 不能持有 owner private key。
- local E2E 不能读 staging Secret Manager。
- Agent 不能绕过 Gateway 直接调付费 provider。
- public API 返回要对象化，不要到处返回 raw dict/map。
- AI 写代码必须先搜索现有模式，再小步改，再跑最小 gate。

后面我准备把这套 workflow 整理成文章和录屏。录屏会用 staging/testnet、mock key、单独浏览器 profile，避免泄露密钥和本地敏感信息。

也想听听大家做 MCP Server 或多服务 API gateway 时，怎么组织 local/staging、SDK E2E 和接口调试。
