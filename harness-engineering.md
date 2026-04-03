# Synapse-Growing: Harness Engineering 实施建议

本文档基于 OpenAI 关于 "在智能体优先的世界中利用 Codex" (Harness Engineering) 的核心理念，为 Synapse Network 的营销与技术布道（Growth & DevRel）提供落地指南。

## 🧲 核心理念 (Core Beliefs)
- **代码仓库即记录系统 (Repo as Source of Truth)**：任何不在文件系统中以 Markdown/YAML 存在的信息，对 Agent 来说就是**不存在的**。没有口头传递，没有 Slack 聊天记录。
- **环境隔离与渐进式展示**：不要给 Agent 1000 页的说明书。目录必须按角色切分，Agent 只阅读与其工作直接相关的上下文目录，并提供导航结构（AGENTS.md）而非全本说明书。
- **验证与防漂移 (Anti-Drift Guardrails)**：通过系统手段验证输出，禁止文档长毛腐烂。

---

## 📂 目录规划与隔离结构
为了实现智能体的**可读性**与**职责隔离**，我们实施了如下目录结构：

```text
Synapse-Network-Growing/
├── README.md                      # 总揽
├── AGENTS.md                      # [地图] 入口导航：定义角色、系统链接、工作法则
├── harness-engineering.md         # 本文件：工程规范与哲学
├── roles/                         # [隔离区] 角色隔离沙盒
│   ├── growth_lead/               # 仅供 Growth Lead 访问与生成的上下文
│   │   ├── prompts/               # 角色记忆与提示工程
│   │   ├── go_to_market/          # 各种 GTM 文案产出位置
│   │   └── landing_pages/         # 网站副本产出位置
│   └── dev_rel/                   # 仅供 DevRel 访问与生成的上下文
│       ├── prompts/               # 角色记忆与提示工程
│       └── contents/              # 硬核技术博客与内容
├── campaigns/                     # [战役指挥室] 计划与状态追踪中心
│   ├── active/                    # 正在进行的战役 (例如 30_day_blitzkrieg)
│   └── archived/                  # 归档的完结战役 
└── demos/                         # [代码产出] 技术输出区
    └── synapse-agent-demo/        # 真实代码示例库
├── docs/                          # [决策与文档记录系统]
│   └── design-docs/               # ADR (架构执行记录) 与顶层战略存放点
```

### 1. 如何把增长负责人和技术布道师隔离？
- **目录级权限约束**：当调用 Growth Agent 时，其工作目录锚定在 `roles/growth_lead/`；DevRel 则被锚定在 `roles/dev_rel/`。
- **独立的 Persona 文件**：互不干涉在各自 `prompts/` 文件夹下。Growth 不需要去理解底层的代码执行逻辑细节，DevRel 不用去学习获客转化率的推文文法。

---

## 📅 计划与任务管理 (Campaigns as Code)

### 1. 工作计划放在哪里？
- 工作计划被实例化为**执行计划文档 (Execution Plans)**。
- 位置：`campaigns/active/<campaign_name>/manifest.md` (例如 `campaigns/active/30_day_blitzkrieg/manifest.md`)。
- 当战役完结后，将其整个文件夹移至 `campaigns/archived/` 下进行归档。

### 2. 产出结果放在哪里？
- **绝不**与计划放在一起。
- 技术代码、Demo 脚本产出到 `demos/`。
- 技术博客产出到 `roles/dev_rel/contents/`。
- 营销推文和转化网页产出到 `roles/growth_lead/` 中的对应子目录。

### 3. 如何做计划和任务拆分？
- 采用 **Markdown Task Lists**，每一个子任务都**必须提供显式连接 (Hard Links)** 指向文件系统。
- 示例：`- [ ] 编写推文 -> `[文件连接](../roles/growth_lead/go_to_market/ph_copy.md)`。

### 4. 如何保持计划和工作产出状态保持一致 (SSOT)？
- **状态注入 (Frontmatter)**：所有产出文档开头必须有强制 YAML 头。
  ```yaml
  ---
  status: draft / review / ready / published
  created_at: 2026-04-03
  author: [Agent Name]
  ---
  ```
- **唯一真理源 (Single Source of Truth)**：只有当产出文档的 Frontmatter status 变为 `ready`，才可以回到 manifest 文件中将 `[ ]` 改为 `[x]`。

---

## 🛠 验证与自动化

### 1. 如何验证技术布道师的工作结果？
- **可执行性验证**：DevRel 的内容最终对应的是 `Synapse-Network-Sdk` 和 `Synapse-Network-Provider`。
- 我们要求 DevRel 输出的代码示例必须存放在独立的 `demos/...` 文件夹下，必须包含能够真正运行的 `start.sh` 或 Python 脚本。
- **验证手段**：未来可接入一个专门的 Agent/脚本执行 `cd demos/xx && sh run.sh`，Exit 0 即成功。

### 2. 如何验证增长负责人的工作结果？
- **平台合规验证**：Growth 的文案将被特定的结构检查器（Linting）扫描。例如，HN 的文案不允许有奇怪的表情符号，X 的推文需要包含 Thread 的结构换行规则。
