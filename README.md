# Synapse-Growing : 30-Day Blitzkrieg 🚀

**Target:** Make Synapse Network the de-facto settlement layer for Agentic Frameworks within 30 days.
**Core Ethos:** Speed is King. Code is Law. Less is More.

## 🌟 The North Star
We are the "Stripe for AI Agents". 
- **Platform**: `Synapse-Network` (Gateway & Settlement)
- **SDK**: `Synapse-Network-Sdk` (Developer integration)
- **Provider**: `Synapse-Network-Provider` (Service onboarding)

## 🏢 Agentic Organization Structure
This repository is the brain for our Multi-Agent Marketing & Growth Engine. It is strictly partitioned by **Role** to ensure contextual isolation for autonomous agents.

- **Growth Lead (增长负责人)**: Ruthless focus on distribution, conversion, ROI, and narrative constraints.
- **DevRel (技术布道师)**: Hardcore focus on DX (Developer Experience), code snippets, API design, and system architecture.

## 🎯 The 30-Day Deliverables
1. **Hero Demo Script**: 1-minute visceral demonstration of M2M payment.
2. **`synapse-agent-demo`**: A plug-and-play codebase with a perfect README.
3. **Core Tech Blog**: *How to let AI agents discover and pay for APIs*.
4. **Launch Copy**: Hyper-optimized copy for PH / HN / X.
5. **Provider Onboarding**: Conversion-focused landing page copy for API sellers.

## Browser Automation

This repository now includes the upstream `vercel-labs/agent-browser` and `dogfood` skills for project-scoped browser automation and systematic QA.

Reusable entry points:

1. Skill source: `.agents/skills/agent-browser/`
2. Dogfood source: `.agents/skills/dogfood/`
3. Skill lock: `skills-lock.json`
4. Project defaults: `agent-browser.json`

First-time setup on a machine:

```bash
agent-browser install
```

Reusable workflow:

```bash
agent-browser open http://127.0.0.1:9700/tasks
agent-browser snapshot -i
agent-browser screenshot
```

Runtime profile, downloads, and screenshots are isolated under `.agent-browser/` and ignored from git by default.

Systematic inspection entry point:

```bash
# Read .agents/skills/dogfood/SKILL.md first, then inspect the local dashboard
agent-browser open http://127.0.0.1:9700/tasks
```

Synapse-Network-Growing/
├── README.md                 # 30天战役总纲与里程碑跟踪（已更新）
├── AGENTS.md                 # 【必须】定义各路 AI Agent 的角色系统边界、权限与交互规则 
├── roles/                    # 【核心】按公司架构切分，隔离 Agent 上下文
│   ├── growth_lead/          # 增长负责人的工作台（看重分发、转化、ROI、叙事）
│   │   ├── prompts/          # 专属于增长 Agent 的 Persona 设定
│   │   ├── go_to_market/     # ★ 需求 4: PH / HN / X 的发布文案 (3个版本)
│   │   └── landing_pages/    # ★ 需求 5: Provider Onboarding 活动页文案 (抽成/结算逻辑)
│   └── dev_rel/              # 技术布道师的工作台（看重 DX、代码优雅度、架构、MCP 接入）
│       ├── prompts/          # 专属于布道师 Agent 的 Persona 设定
│       └── contents/         # ★ 需求 3: 技术博客《How to let AI agents discover and pay...》
├── campaigns/                # 【战役执行层】存放跨角色协同的具体战役
│   └── 30_day_blitzkrieg/    # 30天冲刺战役的项目管理 (Todo, 协同结果存放处)
└── demos/                    # 【技术弹药库】开发者第一触点，由 DevRel 主导
    └── synapse-agent-demo/   # 独立的示例代码库 (可直接作为 Submodule 或开源 Repo)
        ├── README.md         # ★ 需求 2: GitHub Repo README (安装/配置/预期输出/截图)
        └── scripts/          # ★ 需求 1: 1 分钟 Hero Demo 脚本 (包含台词、终端输出、镜头切换)