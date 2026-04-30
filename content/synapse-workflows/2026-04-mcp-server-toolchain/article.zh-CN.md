---
title: "我如何用 Claude Code、Apidog 和 SDK E2E 开发 MCP Server"
status: draft
language: zh-CN
audience: 开发者, agent builder, 基础设施团队
created: 2026-04-30
---

# 我如何用 Claude Code、Apidog 和 SDK E2E 开发 MCP Server

很多 MCP Server 演示都停在“定义一个 tool、写一个 JSON schema、本地调用一下”。这当然有用，但真正难的是后半段：当这个 Server 需要接真实 API、凭据、计费、staging 环境、多仓库协作和发布流程时，应该怎么开发、调试、部署和持续修复？

这是我平时开发 SynapseNetwork 时使用的一套工作流。

SynapseNetwork 是一个让 agent 可以发现 API、调用 provider，并通过区块链完成小额付款的网关。它不是单个服务，而是一组协同系统：Gateway、Provider runtime、SDK、质量门禁、staging 部署、文档和发布队列。要让这些东西跑起来，必须把“工作流本身”也当成产品来设计。

## 我的工具栈

日常我主要用五个界面：

1. Claude Code / Codex：读代码、改代码、重构、写测试、同步文档。
2. Apidog：检查 HTTP 合同、复现请求、调试 Gateway 和 Provider。
3. SynapseNetwork SDK：跑 agent 视角的 E2E，例如 discovery、invoke、receipt、provider onboarding。
4. Local + staging：本地追求速度，staging 验证真实部署环境。
5. SynapseNetwork Growing ops console：管理需求、执行、发布、社交草稿。

关键不是某个工具“神奇”，而是每个工具负责不同的失败模式。

Claude Code 擅长进入代码库做改动；Apidog 擅长回答“API 实际返回了什么”；SDK E2E 擅长证明用户和 agent 能不能真的跑通；staging 会暴露 DNS、权限、密钥、部署配置问题；ops console 负责留下过程记录。

## 一个典型 MCP Server 开发循环

我通常从需求开始，而不是直接打开编辑器。比如需求是：“新增一个 DeepSeek chat provider service，让 agent 可以通过 SynapseNetwork 调用。”

然后流程大概是：

1. 确认目标仓库和运行时边界。
2. 实现 provider endpoint。
3. 增加 request / response schema。
4. 把服务加入 provider catalog。
5. 增加 local onboarding 和 E2E 命令。
6. 用 SDK 跑 gateway -> provider -> receipt。
7. 用 Apidog 检查失败响应和请求合同。
8. 部署到 staging。
9. 对 staging 重新跑同一条 E2E。
10. 把踩坑过程写进 docs、examples 和发布草稿。

最后一步很重要。一个问题如果只在脑子里被解决，而没有进入文档，下次它就会以 bug 的形式回来。

## Claude Code 在哪里发挥作用

我不会把 Claude Code 当成单纯聊天框，而是当成代码库 operator。

比如做 provider service 时，我会先让它搜索现有服务模式：schemas、router、catalog、onboarding script、tests、CI gates。只有读懂现有结构之后再改代码。这样能避免 AI 最常见的问题：生成看起来合理、但和仓库真实合同不一致的代码。

我的默认节奏是：

1. 先搜索。
2. 小步修改。
3. 补测试。
4. 跑最小相关 gate。
5. 本地证据成立后再扩大范围。

这听起来不酷，但这是 agent 能稳定交付和 agent 制造混乱之间的分界线。

## Apidog 在哪里发挥作用

Apidog 是我的“线上合同显微镜”。

当 MCP Server 或 provider endpoint 失败时，我希望能清楚看到 request body、headers、status code、response shape 和示例。尤其是 gateway-signed provider 调用：没有正确签名的直接请求应该失败，而不是绕过网关。

SynapseNetwork 的调用边界是明确的：

- Agent 不直接调用付费 provider runtime。
- Agent 调 Gateway。
- Gateway 处理 discovery、价格、幂等、预算和结算。
- Gateway 用签名请求转发给 Provider。
- Provider 校验 Gateway 签名后执行服务。

Apidog 的价值就是帮我验证这条边界，而不是假装边界不存在。

## SDK E2E 才是真正的产品测试

单元测试证明代码路径能跑。SDK E2E 证明产品能用。

我最关心的是这条链：

```text
provider ensure/register
-> gateway discovery
-> SynapseClient.search()
-> SynapseClient.invoke()
-> gateway_signed provider call
-> receipt
```

如果这条链在 local 和 staging 都能跑通，说明 agent 真的可以使用这个系统。

所以 SDK 不是附属品，它就是平台对外暴露的产品形状。

## Local 和 Staging 的边界

Local 为了速度，staging 为了真相。

Local 使用本地 gateway/provider URL 和本地测试凭据。Staging 的敏感 onboarding secret 来自 Google Secret Manager 或受保护 operator shell，不能进入 Provider runtime。Provider runtime 只应该拿到运行所需的低权限配置：HMAC 验签密钥、低风险 API key、rate limit、数据库配置。

这个隔离非常重要，因为 Provider runtime 是公网数据面。它可能接第三方 API、处理下载任务、处理不可信输入。它不应该持有 owner private key。

## 质量门禁让 AI 工作流不失控

AI 写代码可以很快，但需要护栏。

SynapseNetwork 的仓库里，我持续加入这些质量门禁：

- public API 返回对象而不是 raw map；
- 文件和函数体积限制；
- 复杂度限制；
- 重复代码检测；
- 覆盖率；
- 文档一致性；
- local/staging 配置隔离；
- secret hygiene。

这些不是流程洁癖，而是为了让 agent 可以持续帮忙，同时不悄悄把代码库变差。

## 把工作流变成内容

最后一步是把工作流本身沉淀成内容。

我会把长文、视频脚本、截图、分发记录放在 git 管理的内容目录里。然后只把最终 X/Twitter 短文放进 ops console 的 publishing 队列，由人审核后发布。

这样有两条闭环：

- 产品闭环：需求 -> 实现 -> 验证 -> 交付；
- 学习闭环：失败 -> 修复 -> 文档 -> 公开工作流。

第二条闭环会让项目越来越容易被别人理解。

## 结论

如果你在做 MCP Server 或 agent-facing API infrastructure，最值得优化的不一定是 Server 本身，而是围绕 Server 的开发工作流。

我的经验是：

1. 用 Claude Code / Codex 操作代码库。
2. 用 Apidog 验证 HTTP 合同。
3. 用 SDK E2E 证明 agent 路径。
4. 用 staging 暴露部署真实问题。
5. 用 publishing 队列把调试经验变成可复用知识。

未来的 agent 经济不会只靠 demo 驱动，而是靠一套可观测、可计费、可调试、可安全运行的工作流驱动。
