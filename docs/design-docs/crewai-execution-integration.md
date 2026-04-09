---
id: crewai-execution-integration
title: "CrewAI 真实执行集成方案"
version: "1.0"
status: implemented
created_at: 2026-04-11
author: CTO
---

# CrewAI 真实执行集成方案

## 1. 现状分析 (Current State)

### 1.1 模拟执行逻辑

当前 `server/routers/tasks.py` 中的 `run_task()` 是 **100% 模拟** 的：

```python
# 当前代码 (server/routers/tasks.py:73-93)
row.status = "running"
row.started_at = utcnow()
# ... 立即写入 "[模拟产出] {description}" → status = completed
```

**问题：**
- 没有真实的 LLM 调用或 Agent 逻辑
- 同步阻塞 — 无法处理耗时任务
- `output_path` 字段从未使用，无文件产出能力
- 没有 CrewAI 依赖 — 项目中 `crewai` 搜索结果为 0

### 1.2 已有资产

| 资产 | 路径 | 状态 |
|------|------|------|
| 6 个 Agent Persona | `roles/*/prompts/persona.md` | ✅ YAML 前置 + 系统提示词完整 |
| 35+ Skill SKILL.md | `.agents/skills/*/SKILL.md` | ✅ 详细执行指令 |
| 产品上下文 | `.agents/product-marketing-context.md` | ✅ 统一上下文 |
| 调度协议 | `AGENTS.md` | ✅ Persona → Skill → Task 三步法 |
| Agent 自动发现 | `server/services/agent_loader.py` | ✅ 从 persona.md 加载元数据 |
| 技能匹配 | `server/services/agent_matcher.py` | ✅ 置信度评分 |
| 任务状态机 | `server/database.py` TaskRow | ✅ pending → running → completed/failed |

### 1.3 调度协议 (来自 AGENTS.md)

```
Step 1: 加载 Persona → roles/<agent>/prompts/persona.md
Step 2: 加载 Skill  → .agents/skills/<skill-name>/SKILL.md (自动读取 product-marketing-context.md)
Step 3: 下达任务    → 明确产出物路径、格式要求、KPI 标准
```

---

## 2. 目标架构 (Target Architecture)

### 2.1 核心目标

1. **真实执行** — Agent 通过 CrewAI 调用 LLM，按 Persona + Skill 指令完成任务
2. **文件读写** — Agent 能读取项目文件作为上下文，生成文件产出（Markdown/代码/配置）
3. **异步非阻塞** — 长耗时任务后台执行，不阻塞 API 响应
4. **跨项目扩展** — 为后续 Spec2Flow/MCP 跨项目写入预留接口

### 2.2 新增目录结构

```text
server/
├── services/
│   ├── agent_loader.py         # 已有 — Agent 元数据加载
│   ├── agent_matcher.py        # 已有 — 技能匹配
│   ├── crew_engine.py          # 🆕 CrewAI 引擎封装
│   ├── skill_loader.py         # 🆕 Skill SKILL.md 加载器
│   ├── context_loader.py       # 🆕 项目上下文加载 (product-marketing-context.md + 任意文件)
│   └── task_runner.py          # 🆕 异步任务调度器
```

### 2.3 执行流程

```
POST /api/tasks/{id}/run
        │
        ▼
  ┌─────────────┐
  │ task_runner  │  设置 status=running, 启动后台线程
  │  .dispatch() │
  └──────┬──────┘
         │ (background thread / asyncio.to_thread)
         ▼
  ┌─────────────┐
  │ crew_engine  │  1. 加载 Persona (系统提示词)
  │  .execute()  │  2. 加载 Skill SKILL.md (任务指令)
  │              │  3. 加载 Context (product-marketing-context.md + 相关文件)
  │              │  4. 构建 CrewAI Agent + Task + Crew
  │              │  5. crew.kickoff()
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐
  │ 结果处理     │  1. output_content = crew 输出文本
  │              │  2. output_path = 写入文件路径 (可选)
  │              │  3. status → completed / pending_approval / failed
  │              │  4. 写入 task_logs
  └─────────────┘
```

---

## 3. 详细设计

### 3.1 `crew_engine.py` — CrewAI 引擎封装

**核心职责：** 将 Persona + Skill + Task Description 组装成 CrewAI Crew 并执行。

```python
# server/services/crew_engine.py
from crewai import Agent, Task, Crew, Process
from server.services.skill_loader import load_skill
from server.services.context_loader import load_context

class CrewEngine:
    def __init__(self, project_root: Path):
        self.project_root = project_root

    def execute(self, persona: dict, skill_name: str, task_description: str,
                output_dir: Path | None = None) -> CrewResult:
        """
        执行单个 Agent-Task 组合。

        Args:
            persona: 从 persona.md 解析的完整数据 (frontmatter + body)
            skill_name: 技能名 (如 "seo-audit", "copywriting")
            task_description: 用户下达的任务描述
            output_dir: 产出文件写入目录，None 则只返回文本

        Returns:
            CrewResult(text=str, files=list[Path], error=str|None)
        """
        # 1. 构建 Agent
        agent = Agent(
            role=persona["display_name"],
            goal=persona["goal"],
            backstory=persona["body"],  # persona.md 正文作为背景故事
            verbose=True,
            allow_delegation=False,
        )

        # 2. 构建 Task
        skill_instructions = load_skill(skill_name)
        context = load_context(self.project_root)
        full_description = f"""{context}

## Skill Instructions
{skill_instructions}

## Task
{task_description}
"""
        task = Task(
            description=full_description,
            agent=agent,
            expected_output="Markdown formatted output",
            output_file=str(output_dir / "output.md") if output_dir else None,
        )

        # 3. 执行 Crew
        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )
        result = crew.kickoff()

        return CrewResult(
            text=str(result),
            files=[output_dir / "output.md"] if output_dir else [],
            error=None,
        )
```

### 3.2 `skill_loader.py` — Skill 加载器

```python
# server/services/skill_loader.py
from pathlib import Path
from server.config import PROJECT_ROOT

SKILLS_DIR = PROJECT_ROOT / ".agents" / "skills"

def load_skill(skill_name: str) -> str:
    """加载 .agents/skills/{skill_name}/SKILL.md 全文。"""
    path = SKILLS_DIR / skill_name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_name}")
    return path.read_text(encoding="utf-8")

def list_skills() -> list[str]:
    """列出所有可用技能名。"""
    return [d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
```

### 3.3 `context_loader.py` — 上下文加载器

```python
# server/services/context_loader.py
from pathlib import Path

def load_context(project_root: Path, extra_files: list[str] | None = None) -> str:
    """加载 product-marketing-context.md + 额外上下文文件。"""
    parts = []

    # 必读上下文
    ctx_path = project_root / ".agents" / "product-marketing-context.md"
    if ctx_path.exists():
        parts.append(f"# Product Marketing Context\n{ctx_path.read_text(encoding='utf-8')}")

    # 额外文件 (用户在任务中附加的参考文件)
    for rel_path in (extra_files or []):
        full = project_root / rel_path
        if full.exists() and full.is_file():
            parts.append(f"# Reference: {rel_path}\n{full.read_text(encoding='utf-8')}")

    return "\n\n---\n\n".join(parts)
```

### 3.4 `task_runner.py` — 异步任务调度

```python
# server/services/task_runner.py
import asyncio
import logging
from pathlib import Path
from server.database import SessionLocal, TaskRow, TaskLogRow, ApprovalRow, utcnow
from server.services.crew_engine import CrewEngine
from server.config import PROJECT_ROOT

logger = logging.getLogger("ops-dashboard.task_runner")

engine = CrewEngine(PROJECT_ROOT)

def dispatch(task_id: int, agent_persona: dict, skill_name: str):
    """在后台线程中执行 CrewAI 任务。"""
    import threading
    thread = threading.Thread(
        target=_run_task_sync,
        args=(task_id, agent_persona, skill_name),
        daemon=True,
    )
    thread.start()
    return thread

def _run_task_sync(task_id: int, agent_persona: dict, skill_name: str):
    """同步执行，运行在独立线程中。"""
    db = SessionLocal()
    try:
        task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
        if not task:
            return

        # 产出目录
        output_dir = PROJECT_ROOT / "roles" / agent_persona["role"] / "outputs" / f"task-{task_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        _log(db, task_id, "crew_started", f"skill={skill_name}")

        result = engine.execute(
            persona=agent_persona,
            skill_name=skill_name,
            task_description=task.description,
            output_dir=output_dir,
        )

        # 写入结果
        task.output_content = result.text
        if result.files:
            task.output_path = str(result.files[0])

        if task.requires_approval:
            task.status = "pending_approval"
            db.add(ApprovalRow(task_id=task.id))
            _log(db, task_id, "approval_requested")
        else:
            task.status = "completed"
            task.completed_at = utcnow()
            _log(db, task_id, "completed")

        _log(db, task_id, "output", result.text[:500])
        db.commit()
        logger.info("Task #%d completed: output=%d chars, files=%s",
                     task_id, len(result.text), result.files)

    except Exception as e:
        logger.exception("Task #%d failed", task_id)
        task = db.query(TaskRow).filter(TaskRow.id == task_id).first()
        if task:
            task.status = "failed"
            task.output_content = f"[ERROR] {e}"
            task.completed_at = utcnow()
            _log(db, task_id, "failed", str(e))
            db.commit()
    finally:
        db.close()

def _log(db, task_id, event_type, detail=None):
    db.add(TaskLogRow(task_id=task_id, event_type=event_type, detail=detail))
    db.flush()
```

### 3.5 `run_task()` 路由改造

```python
# server/routers/tasks.py — 改造后
@router.post("/{task_id}/run", response_model=TaskOut)
def run_task(
    task_id: int,
    skill: str = Query(..., description="要执行的技能名，如 seo-audit"),
    db: Session = Depends(get_db),
):
    row = db.query(TaskRow).filter(TaskRow.id == task_id).first()
    if not row:
        raise HTTPException(404, "Task not found")
    if row.status != "pending":
        raise HTTPException(400, f"Cannot run task in '{row.status}' status")

    # 加载 Agent Persona
    agent = db.query(AgentRow).filter(AgentRow.id == row.agent_id).first()
    persona = _load_full_persona(agent.id)  # 返回 frontmatter + body

    # 转为 running
    row.status = "running"
    row.started_at = utcnow()
    _add_log(db, row.id, "started", f"skill={skill}")
    db.commit()
    db.refresh(row)

    # 后台执行
    from server.services.task_runner import dispatch
    dispatch(task_id=row.id, agent_persona=persona, skill_name=skill)

    return row  # 立即返回 status=running
```

**关键变化：**
- 新增 `skill` 查询参数 — 指定执行哪个 Skill
- 立即返回 `status=running`，真实执行在后台线程
- 前端通过轮询 `GET /api/tasks/{id}` 获取最终状态

### 3.6 数据模型扩展

```sql
-- TaskRow 新增字段
ALTER TABLE tasks ADD COLUMN skill_name TEXT;           -- 执行使用的 Skill
ALTER TABLE tasks ADD COLUMN context_files TEXT;         -- JSON: 额外上下文文件路径列表
ALTER TABLE tasks ADD COLUMN execution_time_ms INTEGER;  -- 执行耗时 (毫秒)
```

### 3.7 前端变更

**TaskBoard.tsx 改造：**

1. 创建任务时新增 Skill 选择器（下拉，从 agent 的 skills 字段填充）
2. "运行" 按钮携带选中的 skill 参数
3. 任务卡片显示实时状态：running 时显示 spinner + 轮询
4. 运行完成后展示 output_content (Markdown 渲染) + 可下载 output_path 文件

**新增 API 调用：**
```typescript
// dashboard/src/api.ts
export function runTask(taskId: number, skill: string) {
  return fetch(`${BASE}/api/tasks/${taskId}/run?skill=${encodeURIComponent(skill)}`, {
    method: "POST",
  }).then(handleResponse);
}

export function getSkills(): Promise<string[]> {
  return fetch(`${BASE}/api/skills`).then(handleResponse);
}
```

---

## 4. 文件读写能力 (File I/O)

### 4.1 读取：Agent 上下文注入

Agent 在执行时可以读取：
- `.agents/product-marketing-context.md` — 自动注入
- 任务附带的 `context_files` 列表中的文件 — 相对于项目根目录
- `roles/{agent}/outputs/` 中的历史产出 — 作为参考

**安全边界：**
- 只允许读取 `PROJECT_ROOT` 下的文件
- 路径归一化，阻止 `../` 目录遍历
- 文件大小限制 (单文件 ≤ 100KB，总上下文 ≤ 500KB)

### 4.2 写入：Agent 产出物

```
roles/{agent_id}/outputs/task-{task_id}/
├── output.md          # 主要产出 (CrewAI output_file)
├── attachments/       # 附加产出 (可选)
└── metadata.json      # 执行元数据: 耗时、模型、token 用量
```

产出路径写入 `TaskRow.output_path`，前端可以：
- 内联渲染 Markdown 产出 (`output_content`)
- 提供下载链接 (`output_path`)

### 4.3 跨项目读写 (Phase 3 预留)

```python
# 未来通过 workspace_root 参数支持跨项目
class CrewEngine:
    def execute(self, ..., workspace_root: Path | None = None):
        root = workspace_root or self.project_root
        # 所有文件操作相对于 root
```

---

## 5. LLM 配置

### 5.1 环境变量

```env
# .env (不提交到 git)
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o           # CrewAI 默认使用
# 或者使用其他 Provider:
# ANTHROPIC_API_KEY=...
# CREWAI_LLM=anthropic/claude-sonnet-4-20250514
```

CrewAI 原生支持 OpenAI、Anthropic、Ollama 等，通过环境变量配置即可，无需额外代码。

### 5.2 配置文件扩展

```python
# server/config.py 新增
LLM_MODEL = os.environ.get("CREWAI_LLM", "gpt-4o")
LLM_TEMPERATURE = float(os.environ.get("CREWAI_TEMPERATURE", "0.7"))
MAX_CONTEXT_SIZE = int(os.environ.get("MAX_CONTEXT_SIZE", "500000"))  # 500KB
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "100000"))        # 100KB
```

---

## 6. 三阶段演进计划

### Phase 1: CrewAI 真实执行 (本次)

**目标:** 替换 `run_task()` 模拟逻辑，Agent 真正通过 LLM 执行任务。

| # | 任务 | 文件 | 预期产出 |
|---|------|------|---------|
| 1.1 | 安装 CrewAI 依赖 | `requirements.txt` (新建) | crewai, crewai-tools |
| 1.2 | 实现 `skill_loader.py` | `server/services/skill_loader.py` | 加载 .agents/skills/ |
| 1.3 | 实现 `context_loader.py` | `server/services/context_loader.py` | 加载上下文 + 安全边界 |
| 1.4 | 实现 `crew_engine.py` | `server/services/crew_engine.py` | CrewAI 引擎封装 |
| 1.5 | 实现 `task_runner.py` | `server/services/task_runner.py` | 后台线程调度 |
| 1.6 | 改造 `run_task()` 路由 | `server/routers/tasks.py` | 异步执行 + skill 参数 |
| 1.7 | 数据库迁移 | `server/database.py` | 新增 skill_name / context_files / execution_time_ms |
| 1.8 | 前端 Skill 选择器 | `dashboard/src/pages/TaskBoard.tsx` | 下拉选择 + 运行状态轮询 |
| 1.9 | 新增 Skills API | `server/routers/skills.py` | `GET /api/skills` 列表 |
| 1.10 | 测试 | `tests/` | crew_engine / task_runner / skill_loader 单测 |
| 1.11 | 端到端验证 | 手动 | 提交一个 SEO Audit 任务，验证真实产出 |

### Phase 2: Agent 文件操作 + Git (未来)

**目标:** Agent 可以 clone 仓库、修改文件、提交 PR。

| # | 能力 | 实现方式 |
|---|------|---------|
| 2.1 | Git clone & checkout | CrewAI Tool: `GitTool` |
| 2.2 | 文件读写 Tool | CrewAI Tool: `FileReadWriteTool` |
| 2.3 | PR 创建 | GitHub API / MCP GitHub Tool |
| 2.4 | Spec2Flow 适配 | 将任务 Spec 转化为 Agent 执行流 |

### Phase 3: 跨项目编排 (未来)

**目标:** Growing 中的 Agent 可以向 Synapse-Network、Synapse-Network-Provider 等项目写入。

| # | 能力 | 实现方式 |
|---|------|---------|
| 3.1 | 多项目 Registry | 注册各项目的 workspace_root、可写路径、Agent Card |
| 3.2 | 权限控制 | 每项目定义 `allowed_paths` 白名单 |
| 3.3 | Spec2Flow 编排 | 跨项目任务拆解 → 子任务分发 → 结果聚合 |
| 3.4 | MCP 集成 | 通过 MCP Server 提供跨项目文件访问 |

---

## 7. 安全考量

1. **路径遍历防护** — 所有文件路径必须 `resolve()` 后检查是否在 `PROJECT_ROOT` 内
2. **文件大小限制** — 防止 OOM：单文件 100KB，总上下文 500KB
3. **LLM API Key 安全** — 仅通过环境变量注入，禁止硬编码、禁止日志输出
4. **输出沙盒** — Agent 只能写入 `roles/{agent}/outputs/` 或指定的 output_dir
5. **超时控制** — 单任务执行超时 5 分钟 → 自动 fail
6. **审批门控** — `requires_approval=true` 的任务，产出在审批通过前不对外暴露

---

## 8. 依赖清单

```txt
# requirements.txt (新建)
fastapi>=0.115
uvicorn>=0.34
sqlalchemy>=2.0
pydantic>=2.0
crewai>=0.108
crewai-tools>=0.36
python-dotenv>=1.0
```

---

## 9. 验收标准

- [ ] `POST /api/tasks/{id}/run?skill=copywriting` → 返回 `status: running`
- [ ] 30 秒内 `GET /api/tasks/{id}` → `status: completed` + 真实 LLM 产出
- [ ] `output_content` 包含有意义的 Markdown 文本，非模拟内容
- [ ] `roles/{agent}/outputs/task-{id}/output.md` 文件存在
- [ ] `requires_approval=true` 的任务 → `status: pending_approval` + 审批后才完成
- [ ] 任务失败时 → `status: failed` + 错误信息
- [ ] 前端 Skill 下拉选择正常，运行后显示 spinner + 最终产出
- [ ] 所有旧测试通过 + 新增 ≥ 15 个测试
