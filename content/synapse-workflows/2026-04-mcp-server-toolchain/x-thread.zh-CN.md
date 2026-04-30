---
title: "X thread: MCP Server 开发工作流"
status: draft
language: zh-CN
platform: x
created: 2026-04-30
---

1/ 最近我在开发 SynapseNetwork：一个面向 agent 的 API 网关。

Agent 可以发现 API、调用 provider，并通过区块链完成小额付款。

最难的不是写一个 MCP Server。

最难的是围绕它建立一套可调试、可部署、可复用的工作流。

2/ 我的日常工具栈：

- Claude Code / Codex：读仓库、改代码、跑测试
- Apidog：调 HTTP 合同
- SynapseNetwork SDK：跑 E2E
- local + staging：验证环境真实性
- ops console：管理需求、交付、发布草稿

3/ Claude Code 最好用的方式不是“直接生成代码”。

我的规则是：

先搜索 -> 小步修改 -> 补测试 -> 跑最小 gate -> 再扩大范围。

不这样做，AI 写代码很容易变成“自动制造混乱”。

4/ Apidog 是我的 wire truth。

特别是 gateway/provider 系统里，我需要清楚看到 request body、headers、status code、response shape 和 auth error。

Provider 付费能力必须经过 Gateway 签名调用，不能被直接绕过。

5/ 真正的产品测试不是单元测试过了。

真正的测试是：

provider register
-> gateway discovery
-> SDK search
-> SDK invoke
-> gateway_signed provider call
-> receipt

这条链在 local 和 staging 都通，agent 才真的能用。

6/ Local 追求速度，staging 验证真相。

Provider runtime 不能持有 owner private key。

它只应该拿 HMAC 验签、低风险 API key、rate limit、数据库配置。

控制面 onboarding 必须隔离。

7/ AI-native 开发必须有质量门禁：

- public API 返回对象，不返回 raw map
- 文件/函数体积限制
- 复杂度检查
- 重复代码检查
- 覆盖率
- secret hygiene
- local/staging 配置隔离

8/ 最后一步是把工作流变成内容。

长文、视频脚本、截图和分发记录放进 git。

短 X 草稿进 ops console publishing 队列，人工审核后发布。

这样调试经验不会只停留在脑子里。

9/ 结论：

如果你在做 MCP Server 或 agent API infrastructure，不要只设计 server。

要设计 debug loop、staging proof、SDK E2E 和 publishing loop。

这才是 agent infrastructure 真正可交付的部分。
