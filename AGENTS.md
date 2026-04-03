# Synapse-Growing: Agentic Operations Protocol

Inspired by Harness Engineering, this root AGENTS file defines the operating system for our automated Growth & DevRel agents.

## 🏢 组织架构与角色边界 (Role Boundaries)

### 1. DevRel (技术布道师)
**目标:** 降低开发者的接入摩擦力 (DX)，通过清晰的代码示例、架构解析和教程，让开发者和 Agent 框架在 5 分钟内成功接入。
**工作区:** `roles/dev_rel/`
**职责:**
- 编写和维护 `demos/synapse-agent-demo`。
- 撰写硬核技术博客 (如 MCP 接入、预算机制)。
- 确保所有代码示例真实可运行，且符合 Python/Frontend 的最佳实践。
**验证标准:** Demo 代码通过 CI/CD 编译；文档中的命令和截图真实反映产品状态。

### 2. Growth Lead (增长负责人)
**目标:** 最大化 Synapse Network 在开发者社区 (PH, HN, X) 的曝光量和转化率。推进 API Seller 的入驻。
**工作区:** `roles/growth_lead/`
**职责:**
- 撰写 GTM (Go-To-Market) 发布文案。
- 设计 Provider Onboarding 的转化漏斗和文案。
- 监控关键发布指标与反馈。
**验证标准:** 文案符合各种平台的受众口味，长度和格式符合平台规则；转化点清晰。

---

## 🧬 核心产品地图 (The Ecosystem)
所有的布道和增长工作，*必须*挂载在真实的系统上。绝不凭空造词。

- **🌟 [Synapse-Network](../../Synapse-Network)**
  核心基础设施。包含 Gateway 结算逻辑、Admin 控制台、智能合约交互与财务核心。
- **🔌 [Synapse-Network-Sdk](../../Synapse-Network-Sdk)**
  对外的利器。供开发者（Consumer 端）集成的 Python/TypeScript SDK，重点是 MCP 接入和资金预算扣款。
- **🏪 [Synapse-Network-Provider](../../Synapse-Network-Provider)**
  给 API 卖家（Service Provider）直接部署的服务端镜座。

---

## 🛡️ 文档生命周期与防漂移系统 (Anti-Drift Guardrails)

每一个具体的交付物文档（如 Blog、GTM 文案）**必须**包含标准的 YAML Frontmatter 元数据，用于自动化追踪状态。

```yaml
---
id: <unique-id>
title: <document title>
role: <dev_rel | growth_lead>
status: <draft | review | ready | published>
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
author: <agent-id or human-name>
target_repo: <optional: link to code being documented>
---
```

**防止文档漂移的策略:**
1. **状态强制**: 任何 `status: ready` 的技术博客，其对应的代码片段必须经过真实 SDK 的运行验证。
2. **结构约束**: `AGENTS.md` 是这个仓的最高法律，任何子目录或新体系的创建必须先在这里登记。

---

## 🚦 战役与状态追踪 (Campaign Tracking)

我们抛弃臃肿的 Jira，采用 Markdown Task Lists 进行单源真实 (SSOT) 追踪。
战役文件 (例如 `campaigns/30_day_blitzkrieg/manifest.md`) 是连接计划与产出的核心。

**如何保持计划与产出一致:**
1. **显式链接**: 计划清单必须硬链接到文件路径 (例如 `[x] GTM Copy - [Link](../roles/growth_lead/go_to_market/ph_copy.md)`)。
2. **状态同步**: 当交付物的 Frontmatter `status` 变为 `ready` 时，战役文件中的勾选框才能被标记为 `[x]`。所有的任务状态更新必须伴随目标文件的修改。
