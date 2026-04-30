---
title: "视频脚本：MCP Server 开发工作流"
status: draft
language: zh-CN
created: 2026-04-30
---

# 视频脚本

## 开场

很多 MCP Server 演示只展示 server 本身。这个视频我想展示的是 server 周围的工作流。

我平时开发 SynapseNetwork 时，会组合使用 Claude Code、Apidog、SDK E2E、staging 和 publishing 队列。

SynapseNetwork 是一个让 agent 可以发现 API、调用 provider，并通过区块链完成小额付款的网关。

## 工作区地图

项目被拆成几个清晰的部分。

Synapse-Network 是主产品和 Gateway。Provider 是对外提供服务的 runtime。SDK 是 agent 和开发者接入层。Growing 是 ops console，用来管理需求、执行、发布和内容草稿。cliff-mind 用来存放策略、思考和内容源稿。

关键是每个 repo 的职责要清楚。

## Claude Code / Codex 循环

当我要新增或调试 provider service 时，不会直接让模型随便写代码。

我会先让它搜索现有模式：router、schemas、catalog、onboarding、tests、CI gates。

然后小步循环：

搜索、修改、测试、跑最小相关 gate，再扩大范围。

这样 AI 写代码会安全很多。

## Apidog 调接口合同

Apidog 是我看 HTTP 合同的地方。

Provider 服务不能被匿名直接调用。Agent 应该调 Gateway，Gateway 负责价格、幂等、预算、结算，然后用签名请求转发给 Provider。

所以我会用 Apidog 检查 request body、headers、status code 和 error response。

## SDK E2E

真正的产品测试不只是单元测试。

真正的测试是 agent 能不能通过 SDK 跑通：

provider register、gateway discovery、SDK search、SDK invoke、gateway-signed provider call、receipt。

这条链在 local 和 staging 都能通，系统才是真的能用。

## Local 和 Staging

Local 用来快，staging 用来验证真实环境。

Local 使用本地 URL 和本地测试凭据。Staging 使用受保护 secret 和公网 URL。

Provider runtime 不能拿 owner private key。它只应该有 HMAC 验签、rate limit、低风险 API key、数据库配置这类运行时配置。

这点很重要，因为 provider runtime 是公网数据面。

## 质量门禁

AI-native 开发需要护栏。

我会用质量门禁限制 public 返回类型、文件和函数长度、复杂度、重复代码、覆盖率、文档一致性和 secret hygiene。

这不是为了流程而流程，而是为了让 agent-assisted change 可以反复安全发生。

## Publishing 循环

最后，我会把工作流本身变成内容。

长文、脚本、截图和录屏放进 git。短社交草稿进入 publishing 队列，由人审核后发布。

这样失败会变成修复，修复会变成文档，文档会变成可复用的工作流。

## 结尾

如果你在做 MCP Server 或 agent-facing API infrastructure，不要只设计 server。

要设计 debug loop、staging proof、SDK E2E 和 publishing loop。

这些东西加起来，才让系统真正可交付。
