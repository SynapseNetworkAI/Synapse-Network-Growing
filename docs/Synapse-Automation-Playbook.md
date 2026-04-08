---
id: synapse-automation-playbook
title: "Synapse Network: Agent 自动化协作执行方案"
version: "1.0"
status: draft
created_at: 2026-04-08
author: CTO
framework: CrewAI
---

# Synapse Network: Agent 自动化协作执行方案 (v1.0)

本方案旨在将 `AGENTS.md` 中的协议转化为一个动态的、文件驱动的**任务发动机**。通过 [CrewAI](https://github.com/crewAIInc/crewAI) 框架，实现从"手动指派"到"系统自动调度"的跨越。

**核心目标：** 从"人在系统内干活"转变为"人在系统外审计"。

---

## 目录

1. [基础设施标准化](#1-基础设施标准化)
2. [动态任务清单](#2-动态任务清单)
3. [核心引擎实现](#3-核心引擎实现)
4. [自动化审批流](#4-自动化审批流)
5. [自动化闭环](#5-自动化闭环)
6. [快速开始](#6-快速开始)
7. [后续扩展方向](#7-后续扩展方向)

---

## 1. 基础设施标准化

为了让 Agent 能够自动识别环境，项目目录需对齐以下结构：

```text
Synapse-Network-Growing/
├── .agents/
│   ├── product-marketing-context.md   # 全局上下文 (SSOT)
│   └── skills/                        # MarketingSkills 技能包
├── roles/                             # 角色定义区
│   ├── dev_rel/prompts/persona.md
│   ├── growth_lead/prompts/persona.md
│   ├── content_writer/prompts/persona.md
│   ├── seo_strategist/prompts/persona.md
│   ├── cro_optimizer/prompts/persona.md
│   └── launch_strategist/prompts/persona.md
├── campaigns/                         # 任务与产出区
│   ├── manifest.md                    # 【核心】动态任务清单
│   └── outputs/                       # 自动化产出物
├── AGENTS.md                          # 角色与协议定义
└── synapse_engine.py                  # 【核心】自动化主程序
```

> **与 AGENTS.md 的关系：** `AGENTS.md` 定义角色边界和调度协议（Persona → Skill → Task），本方案负责把这些协议变成可执行的自动化流水线。

---

## 2. 动态任务清单

`campaigns/manifest.md` 是唯一的任务输入源。以后只需在此增减任务，**无需改动 Python 代码**。

**格式规范：**

```
- [ ] [任务描述] @角色ID
```

**示例：**

```markdown
# Synapse Network 任务清单

## GTM 阶段任务
- [ ] [策划 ProductHunt 上线文案并输出为 PH_Launch.md] @growth_lead
- [ ] [针对 MCP 接入编写一篇 300 字的技术推文草稿] @dev_rel
- [ ] [编写 3 封针对 API Provider 的冷触达邮件序列] @content_writer

## 验证与发布
- [ ] [对以上所有文案进行最终 SEO 审计与品牌一致性检查] @seo_strategist
```

任务完成后引擎会自动将 `[ ]` 改为 `[x]`，无需手动更新。

---

## 3. 核心引擎实现

### 3.1 环境配置

```bash
pip install crewai langchain-openai
export OPENAI_API_KEY="sk-..."
```

### 3.2 synapse_engine.py

```python
import os
import re
from crewai import Agent, Task, Crew, Process
from langchain_openai import ChatOpenAI

# ── 配置 ──────────────────────────────────────────────────────
MODEL = "gpt-4o"
MANIFEST_PATH = "campaigns/manifest.md"
CONTEXT_PATH = ".agents/product-marketing-context.md"


class SynapseAutomation:
    """文件驱动的 Agent 自动化引擎。"""

    def __init__(self):
        self.llm = ChatOpenAI(model=MODEL)
        self.agents = self._init_agents()

    # ── 动态 Agent 加载器 ─────────────────────────────────────
    def _init_agents(self):
        """从 roles/ 目录自动读取 Persona，生成 Agent 实例。"""
        roles = {
            "dev_rel":          "负责 DX 和技术布道",
            "growth_lead":      "负责 GTM 和增长策略",
            "content_writer":   "负责极简主义文案写作",
            "seo_strategist":   "负责关键词与转化率优化",
            "cro_optimizer":    "负责全链路转化率优化",
            "launch_strategist":"负责发布节奏与飞轮编排",
        }
        agent_instances = {}
        for r_id, goal in roles.items():
            persona_path = f"roles/{r_id}/prompts/persona.md"
            if os.path.exists(persona_path):
                with open(persona_path, "r") as f:
                    backstory = f.read()
            else:
                backstory = f"你是 {r_id} 专家。"

            agent_instances[r_id] = Agent(
                role=r_id,
                goal=goal,
                backstory=backstory,
                llm=self.llm,
                allow_delegation=True,
                verbose=True,
            )
        return agent_instances

    # ── 动态任务分发器 (Dispatcher) ───────────────────────────
    def parse_tasks(self):
        """扫描 manifest.md，将 '- [ ]' 行解析为 CrewAI Task。"""
        tasks = []
        with open(MANIFEST_PATH, "r") as f:
            content = f.read()

        matches = re.findall(r"- \[ \] \[(.*?)\] @(\w+)", content)
        for desc, role_id in matches:
            if role_id in self.agents:
                tasks.append(
                    Task(
                        description=(
                            f"任务: {desc}。"
                            f"必须参考 {CONTEXT_PATH} 确保品牌一致性。"
                        ),
                        agent=self.agents[role_id],
                        expected_output="符合 YAML Frontmatter 格式的 Markdown 文档",
                        output_file=f"campaigns/outputs/{role_id}_{os.urandom(2).hex()}.md",
                    )
                )
        return tasks

    # ── 自动回写 manifest ────────────────────────────────────
    def mark_done(self, desc):
        """任务完成后自动将 manifest 中的 [ ] 改为 [x]。"""
        with open(MANIFEST_PATH, "r") as f:
            content = f.read()
        content = content.replace(f"- [ ] [{desc}]", f"- [x] [{desc}]")
        with open(MANIFEST_PATH, "w") as f:
            f.write(content)

    # ── 主执行入口 ────────────────────────────────────────────
    def run(self):
        tasks = self.parse_tasks()
        if not tasks:
            print("所有任务已完成或清单为空！")
            return

        synapse_crew = Crew(
            agents=list(self.agents.values()),
            tasks=tasks,
            process=Process.hierarchical,  # 经理 Agent 审核产出
            manager_llm=self.llm,
            memory=True,
        )

        print(f"正在启动自动化协作，共有 {len(tasks)} 个任务待处理...")
        result = synapse_crew.kickoff()
        return result


if __name__ == "__main__":
    engine = SynapseAutomation()
    engine.run()
```

### 3.3 核心组件说明

| 组件 | 职责 |
|------|------|
| `_init_agents()` | 遍历 `roles/` 加载 Persona，生成 Agent 实例 |
| `parse_tasks()` | 解析 `manifest.md` 中 `- [ ]` 行，匹配 Agent 并创建 Task |
| `mark_done()` | 任务完成后自动回写 manifest，将 `[ ]` 改为 `[x]` |
| `Crew(hierarchical)` | Manager Agent 审核所有人的产出，不合格直接打回重写 |

---

## 4. 自动化审批流

通过三层过滤，让你从繁琐的微观审核中解脱：

### 第一层：Manager Agent (虚拟 VP)

`Process.hierarchical` 模式下，经理 Agent 自动审查所有产出。字数超标、语气不对直接打回重写，你不会看到中间的烂草稿。

### 第二层：硬性格式约束 (YAML Check)

`expected_output` 强制要求包含 YAML Frontmatter。不带 `status: ready` 的产出物自动判定为不合格。

### 第三层：Human-In-The-Loop (精准干预)

对于高风险任务（如发布到社交平台），在 Task 中启用人工确认：

```python
task_publish = Task(
    description="将文案发布至 X 平台",
    agent=growth_lead,
    human_input=True,  # 程序暂停等待 Yes/No
)
```

> **原则：** 只在不可逆操作上加 `human_input=True`，其余全部自动流转。

---

## 5. 自动化闭环

Agent 完成任务后，系统自动执行以下闭环操作：

| 步骤 | 自动化逻辑 | 结果 |
|------|-----------|------|
| 产出校验 | 正则匹配 YAML 字段（ID, Title, Status），不合规直接重写 | 格式一致性 |
| 物理写入 | `output_file="campaigns/outputs/<task_id>.md"` | 文件自动生成 |
| 清单更新 | `mark_done()` 将 `[ ]` 改为 `[x]` | 进度可视化 |

---

## 6. 快速开始

### Step 1: 安装依赖

```bash
pip install crewai langchain-openai
```

### Step 2: 确认 Persona 文件

确保 `roles/` 下各角色有对应的 Persona 文件。

已有角色:
- `roles/dev_rel/prompts/persona.md`
- `roles/growth_lead/prompts/persona.md`
- `roles/content_writer/prompts/persona.md`
- `roles/seo_strategist/prompts/persona.md`
- `roles/cro_optimizer/prompts/persona.md`
- `roles/launch_strategist/prompts/persona.md`

### Step 3: 编写任务清单

编辑 `campaigns/manifest.md`，按格式添加任务：

```markdown
- [ ] [撰写关于 MCP 接入的技术教程] @dev_rel
- [ ] [策划 ProductHunt 上线文案] @growth_lead
```

### Step 4: 启动引擎

```bash
cd Synapse-Network-Growing
python synapse_engine.py
```

### 思维转变

| 过去 | 现在 |
|------|------|
| 你 → 告诉 Agent A 做任务 1 → 拿到结果 → 给 Agent B → 告诉他做任务 2 | 你 → 更新 `manifest.md` → 运行脚本 → 审核最终 Bundle |

---

## 7. 后续扩展方向

### 7.1 GitHub Action 触发

将脚本挂载在 GitHub Action 上，每当 `manifest.md` 有新 commit，Agent 团队自动开工：

```yaml
# .github/workflows/agent-dispatch.yml
on:
  push:
    paths:
      - 'campaigns/manifest.md'

jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install crewai langchain-openai
      - run: python synapse_engine.py
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

### 7.2 MCP 集成

通过 MCP 协议让 Agent 直接访问 `Synapse-Network` 代码库，实现"读代码写教程"的真自动化。

### 7.3 多模型支持

替换 `ChatOpenAI` 为其他 LLM provider（Claude、Gemini 等），或为不同角色配置不同模型以优化成本。

---

> **Synapse Network - Agentic Ops Team**
