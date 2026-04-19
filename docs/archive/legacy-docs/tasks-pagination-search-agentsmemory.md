---
id: tasks-pagination-search-agentsmemory
title: "Tasks 分页搜索 & Agents-Memory 接入方案"
version: "1.0"
status: proposed
created_at: 2026-04-11
updated_at: 2026-04-12
author: CTO
---

# Tasks 分页搜索 & Agents-Memory 接入方案

## 一、背景与目标

### 现状问题

| 问题 | 描述 |
|------|------|
| 全量加载 | `GET /api/tasks` 一次返回所有任务，随任务增多性能下降 |
| 纯客户端过滤 | `visibleTasks` 在浏览器内做字符串匹配，数据量大时 UI 卡顿 |
| 搜索字段有限 | 当前搜索仅支持 `description`、`agent_id`、`skill_name`、`project_label`，不含 `output_content` |
| 孤立上下文 | 任务详情缺乏工程知识关联，失败原因无法与历史错误记录对比 |

### 目标

1. **任务列表分页**：每页固定 10 条，后端分页，接口支持搜索（title + content）
2. **Agents-Memory 集成**：从 Task 列表与 Task 详情能够跨系统搜索 Agents-Memory，把工程记忆带入任务上下文

---

## 二、功能一：Tasks 列表分页 + 搜索

### 2.1 后端改造（`server/routers/tasks.py`）

#### 新增响应模型

```python
# server/schemas.py 新增
class TaskPage(BaseModel):
    items: list[TaskOut]
    total: int
    page: int
    page_size: int
    total_pages: int
```

#### `GET /api/tasks` 新增查询参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | `int` | `1` | 当前页码（从 1 开始） |
| `page_size` | `int` | `10` | 每页条数，最大 100 |
| `search` | `str \| None` | `None` | 全文搜索关键词，匹配 `description` 和 `output_content` |

#### 搜索实现方式

SQLite 原生支持 `LIKE` 查询，无需额外依赖：

```python
if search:
    pattern = f"%{search}%"
    q = q.filter(
        or_(
            TaskRow.description.ilike(pattern),
            TaskRow.output_content.ilike(pattern),
        )
    )
```

> **注意**：`filter` 在 `order_by` 之前应用，保证分页结果一致性。

#### 分页实现

```python
total = q.count()
rows = (
    q.order_by(TaskRow.created_at.desc(), TaskRow.id.desc())
     .offset((page - 1) * page_size)
     .limit(page_size)
     .all()
)
total_pages = math.ceil(total / page_size) if total > 0 else 1
```

#### 兼容性

现有调用（不传 `page`/`page_size`/`search`）时，行为等价于当前逻辑（`page=1, page_size=10`），返回结构由 `list[TaskOut]` → `TaskPage`。

已有前端调用处（`api.getTasks()`）均需同步更新为解构 `.items`。

---

### 2.2 前端改造（`dashboard/src/pages/TaskBoard.tsx`）

#### 状态新增

```typescript
const [page, setPage] = useState(1)
const [totalPages, setTotalPages] = useState(1)
const [total, setTotal] = useState(0)
const [searchQuery, setSearchQuery] = useState('')        // 提交给后端的关键词
const [searchInput, setSearchInput] = useState('')        // 输入框 buffer（debounce 用）
```

#### API 调用调整

`api.getTasks()` 新增 `page`、`page_size`、`search` 参数，返回 `TaskPage`：

```typescript
getTasks: (params?: { ...; page?: number; page_size?: number; search?: string }) => {
  ...
  if (params?.page) qs.set('page', String(params.page))
  if (params?.page_size) qs.set('page_size', String(params.page_size))
  if (params?.search) qs.set('search', params.search)
  return request<TaskPage>(`/tasks${q ? '?' + q : ''}`)
}
```

#### 搜索输入

- 在现有筛选栏右侧放置搜索框
- 输入 300 ms debounce 后触发 `setSearchQuery`，同时 `setPage(1)` 重置到第一页
- 搜索命中时显示命中总数 `共 {total} 条`

#### 分页控件

```
← 上一页   第 {page} / {totalPages} 页   下一页 →
```

- 上一页：`page > 1` 时可点击
- 下一页：`page < totalPages` 时可点击
- 跳转页码输入框（可选，优先级低）

#### 保留客户端过滤

`statusFilter`、`projectFilter`、`agentGroupFilter`、`agentFilter`、`onlyAnomalies` 继续为前端过滤（参数少，后端已经支持），不需要再做 client-side `search` 过滤（search 已在后端处理）。

---

## 三、功能二：接入 Agents-Memory

### 3.1 Agents-Memory 搜索 API

Agents-Memory 运行于 `http://localhost:10000`，提供统一搜索接口：

```
GET http://localhost:10000/api/search?q=<keyword>&mode=hybrid&limit=10
```

**响应结构：**

```json
{
  "query": "oracle price manipulation",
  "mode": "hybrid",
  "results": [
    {
      "type": "error",          // "error" | "wiki"
      "id": "AME-001",
      "title": "USDT transfer 精度丢失",
      "snippet": "链上金额运算不能用 float...",
      "score": 0.92
    },
    {
      "type": "wiki",
      "id": "finance-safety",
      "title": "Finance Safety",
      "snippet": "use Decimal, never float for on-chain values.",
      "score": 0.87
    }
  ],
  "total": 2
}
```

- `type=error`：工程错误记录，点击可跳转 `http://localhost:10000/errors/{id}`
- `type=wiki`：知识图谱页面，点击可跳转 `http://localhost:10000/wiki/{id}`

---

### 3.2 集成点设计

#### A. 任务列表搜索联动（TaskBoard）

**触发时机**：用户在搜索框输入关键词时，**同时**异步获取 Agents-Memory 搜索结果，以下拉面板形式展示。

```
┌─────────────────────────────────────────────────────────┐
│  🔍  oracle price              [搜索任务]  [搜索 Memory] │
├─────────────────────────────────────────────────────────┤
│  ▸ Agents-Memory 相关记录（点击展开）                    │
│    ● [error] AME-001 — USDT 精度丢失           score 0.92│
│    ● [wiki]  finance-safety — Decimal 使用规范  score 0.87│
└─────────────────────────────────────────────────────────┘
```

- 默认折叠，有结果时显示条数徽标 `Memory (2)`
- 点击结果条目在新标签页打开对应 Agents-Memory 页面
- 搜索框清空时面板隐藏

#### B. 任务详情相关记忆（TaskDetail）

**触发时机**：进入 Task 详情页时，以任务 `description` 为关键词自动搜索 Agents-Memory（limit=5），结果展示在"文件改动"section 之后。

```
┌─ 相关工程记忆（Agents-Memory）─────────────────────────┐
│  [error] AME-001  USDT transfer 精度丢失         0.92  │
│  [wiki]  finance-safety  Decimal 使用规范         0.87  │
│  [wiki]  smart-contract-errors  常见合约错误       0.71  │
│                             [在 Agents-Memory 中搜索 →] │
└────────────────────────────────────────────────────────┘
```

- 卡片颜色：`error` 类型用红色左边框，`wiki` 类型用蓝色左边框
- "在 Agents-Memory 中搜索 →" 链接打开 `http://localhost:10000` 并携带搜索词
- 若 Agents-Memory 服务不可达，静默隐藏该 section（不展示错误）

---

### 3.3 后端代理方案（可选）

**直连方案（推荐）**：前端直接调用 `http://localhost:10000/api/search`，无需后端代理。

- 优点：实现简单，跨服务无中间层
- 前提：浏览器与 Agents-Memory 在同一机器（本地开发场景下始终成立）
- CORS：Agents-Memory 目前以 `origins=["*"]` 启动，可直连

**后端代理方案（备选）**：若未来部署到服务器，由 Synapse-Growing 后端提供 `/api/agentsmemory/search` 代理接口，转发到内网 Agents-Memory 服务，避免跨域及凭证暴露。

```
GET /api/agentsmemory/search?q=<keyword>&limit=<n>
→ 代理到 http://localhost:10000/api/search
```

---

### 3.4 前端实现（api.ts + TaskBoard + TaskDetail）

#### `api.ts` 新增

```typescript
// Agents-Memory 搜索结果类型
export interface AgentsMemoryResult {
  type: 'error' | 'wiki'
  id: string
  title: string
  snippet: string
  score: number
}

export interface AgentsMemorySearchResponse {
  query: string
  results: AgentsMemoryResult[]
  total: number
}

// 直连 Agents-Memory（不走 /api 代理前缀）
const AGENTS_MEMORY_BASE = 'http://localhost:10000'

export const agentsMemoryApi = {
  search: (q: string, limit = 10): Promise<AgentsMemorySearchResponse> =>
    fetch(`${AGENTS_MEMORY_BASE}/api/search?q=${encodeURIComponent(q)}&limit=${limit}`)
      .then(r => r.ok ? r.json() : Promise.reject(r))
}
```

#### TaskBoard 集成

```typescript
const [memoryResults, setMemoryResults] = useState<AgentsMemoryResult[]>([])
const [memoryOpen, setMemoryOpen] = useState(false)

// 伴随 searchInput debounce 触发
useEffect(() => {
  if (!searchQuery.trim()) { setMemoryResults([]); return }
  agentsMemoryApi.search(searchQuery, 5)
    .then(r => setMemoryResults(r.results))
    .catch(() => setMemoryResults([]))
}, [searchQuery])
```

#### TaskDetail 集成

```typescript
const [memoryResults, setMemoryResults] = useState<AgentsMemoryResult[]>([])

useEffect(() => {
  if (!task?.description) return
  agentsMemoryApi.search(task.description.slice(0, 100), 5)
    .then(r => setMemoryResults(r.results))
    .catch(() => {})
}, [task?.description])
```

---

## 四、实施计划

| 阶段 | 任务 | 文件 | 预估行数 |
|------|------|------|---------|
| **P1** | 后端分页：新增 `search`/`page`/`page_size` 参数 | `server/routers/tasks.py`, `server/schemas.py` | ~40 |
| **P1** | `api.ts` 更新 `getTasks` 返回类型 | `dashboard/src/api.ts` | ~15 |
| **P1** | TaskBoard：搜索框 debounce + 分页控件 | `dashboard/src/pages/TaskBoard.tsx` | ~80 |
| **P2** | `api.ts` 新增 `agentsMemoryApi` | `dashboard/src/api.ts` | ~20 |
| **P2** | TaskBoard：Memory 搜索联动面板 | `dashboard/src/pages/TaskBoard.tsx` | ~50 |
| **P2** | TaskDetail：相关工程记忆 section | `dashboard/src/pages/TaskDetail.tsx` | ~60 |
| **P3** | 后端代理接口（按需，部署到服务器时实施） | `server/routers/agentsmemory.py` | ~30 |

**实施顺序**：P1（分页+搜索）→ P2（Agents-Memory）→ P3（按需）

---

## 五、测试计划

### 后端（pytest）

| 测试用例 | 方法 |
|---------|------|
| 无参数调用返回第1页10条 | `GET /api/tasks` |
| `page=2` 返回第 11-20 条 | `GET /api/tasks?page=2` |
| `search=hello` 只返回匹配 description 或 output_content 的任务 | `GET /api/tasks?search=hello` |
| `search` + `status` 组合过滤正确 | 组合查询 |
| `total_pages` 计算正确（空结果、整除、非整除） | 边界值 |

### 前端（vitest）

| 测试用例 | 方法 |
|---------|------|
| 搜索输入 debounce 300ms 后触发 | mock timer |
| 分页按钮 disabled 状态正确 | render test |
| Memory 面板在搜索关键词清空时隐藏 | state reset |
| `agentsMemoryApi.search` 失败时静默（no error UI） | mock fetch reject |

---

## 六、风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| Agents-Memory 服务未运行 | 中 | 前端 catch 静默，不影响主流程 |
| 搜索词过长导致 Agents-Memory 慢响应 | 低 | TaskDetail 中截取前 100 字符；设置 3s timeout |
| 分页破坏现有 `requirement_id` 过滤 | 低 | `requirement_id` 过滤在 DB 层完成（`task_ids` in-query），不影响分页逻辑 |
| `total_pages` 过期（数据变化中） | 低 | 轮询时每次 reload 重新取 `total_pages` |

---

## 七、功能三：需求与任务完整信息写入 Agents-Memory

### 7.1 背景与意义

当前 Agents-Memory 的内容来自手动 `amem ingest` 或 CLI 命令。Synapse-Network-Growing 每天产生大量需求执行记录和任务输出，这些内容天然是工程决策和错误记录的最佳来源。将其自动同步到 Agents-Memory，可让知识层持续积累，后续搜索和 wiki-compile 都能沉淀为工程智慧。

2026-04-12 起，落盘模型调整为三路分流：
- 项目文档 onboarding → `wiki`
- 失败任务 → `errors`
- 完成任务 / 完成 requirement → `workflow records`

这样可以保留执行证据，同时避免把完成记录误计入错误统计。

### 7.2 写入时机

| 事件 | 触发位置 | 写入内容 |
|------|---------|---------|
| 需求全部完成（所有步骤 completed） | `_finalize_requirement()` | 需求描述 + 执行步骤摘要 + 最终产出 |
| 单个任务完成（status → completed） | `_sync_workflow_for_task_db()` 内 `task.status == "completed"` 块 | 任务描述 + 步骤上下文 + 输出内容 |
| 单个任务失败（status → failed） | `_sync_workflow_for_task_db()` 内 `task.status == "failed"` 块 | 错误信息 + 任务描述 → 自动作为 `error_record` 写入 |

### 7.3 Agents-Memory 写入接口

Agents-Memory FastAPI 运行于 `http://localhost:10100`，写入端点：

```
POST http://localhost:10100/api/ingest
Content-Type: application/json

{
  "content": "<Markdown 正文，含可选 YAML frontmatter>",
  "source_type": "requirement_completion" | "task_completion" | "error_record",
  "project": "<项目标识>",
  "dry_run": false
}
```

响应：
- `error_record` → `{"ingested": true, "id": "ERR-20260411-001", "storage_kind": "error"}`
- `task_completion` / `requirement_completion` → `{"ingested": true, "id": "TASK-42", "storage_kind": "workflow"}`

### 7.4 写入内容格式

#### A. 需求完成记录（`source_type: requirement_completion`）

```markdown
---
id: REQ-{requirement_id}
title: {requirement.title}
project: {project_name}
source_type: requirement_completion
status: completed
priority: {requirement.priority}
completed_at: {requirement.completed_at}
created_at: {requirement.created_at}
---

## 需求描述

{requirement.description_markdown}

## 执行步骤

| 步骤 | 角色 | 状态 | 执行耗时 |
|------|------|------|---------|
| {step.title} | {step.assigned_workflow_role} | {step.status} | {task.execution_time_ms}ms |
...

## 产出摘要

{最后一个 completed task 的 output_content，截取前 2000 字}

## 文件改动

{file-changes.json 列出的文件列表}
```

#### B. 任务完成记录（`source_type: task_completion`）

```markdown
---
id: TASK-{task_id}
title: {step.title}
project: {project_name}
source_type: task_completion
status: completed
agent_id: {task.agent_id}
requirement_id: {requirement_id}
execution_time_ms: {task.execution_time_ms}
completed_at: {task.completed_at}
---

## 任务描述

{task.description}

## 验收标准（done_when）

{step.done_when_markdown}

## 执行结果

{task.output_content}
```

#### C. 任务失败记录（`source_type: error_record`）

```markdown
---
id: TASK-{task_id}-FAIL
title: {task.description[:80]} — 失败
project: {project_name}
source_type: error_record
status: new
agent_id: {task.agent_id}
requirement_id: {requirement_id}
---

## 错误信息

{task.last_error_message}

## 任务描述

{task.description}

## 步骤上下文

- 步骤：{step.title}
- 角色：{step.assigned_workflow_role}
- 验收标准：{step.done_when_markdown}
```

### 7.5 后端实现

#### 新文件：`server/services/agents_memory_sync.py`

```python
"""非阻塞地将需求/任务信息推送到 Agents-Memory。"""
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

import requests  # 已在依赖中

logger = logging.getLogger("ops-dashboard.agents-memory-sync")

AGENTS_MEMORY_URL = os.environ.get("AGENTS_MEMORY_URL", "http://localhost:10100")
AGENTS_MEMORY_ENABLED = os.environ.get("AGENTS_MEMORY_SYNC_ENABLED", "true").lower() == "true"
_TIMEOUT = 5  # 秒


def _push(content: str, source_type: str, project: str) -> None:
    """在后台线程中推送内容到 Agents-Memory（失败静默）。"""
    if not AGENTS_MEMORY_ENABLED:
        return
    def _do():
        try:
            resp = requests.post(
                f"{AGENTS_MEMORY_URL}/api/ingest",
                json={"content": content, "source_type": source_type, "project": project},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info("agents-memory ingest ok: %s / %s", source_type, resp.json().get("id"))
        except Exception as exc:
            logger.debug("agents-memory ingest failed (non-critical): %s", exc)
    threading.Thread(target=_do, daemon=True).start()


def _project_name(target_project_path: str | None) -> str:
    if not target_project_path:
        return "synapse-network-growing"
    from pathlib import Path
    return Path(target_project_path).name or "synapse-network-growing"


def push_requirement_completed(requirement, steps_summary: list[dict[str, Any]], output_summary: str, changed_files: list[str]) -> None:
    project = _project_name(requirement.target_project_path)
    steps_table = "\n".join(
        f"| {s['title']} | {s['role']} | {s['status']} | {s.get('execution_time_ms', '-')}ms |"
        for s in steps_summary
    )
    files_list = "\n".join(f"- {f}" for f in changed_files) if changed_files else "（无）"
    content = f"""---
id: REQ-{requirement.id}
title: "{requirement.title}"
project: {project}
source_type: requirement_completion
status: completed
priority: {requirement.priority}
completed_at: {requirement.completed_at}
---

## 需求描述

{requirement.description_markdown}

## 执行步骤

| 步骤 | 角色 | 状态 | 执行耗时 |
|------|------|------|---------|
{steps_table}

## 产出摘要

{output_summary[:2000] if output_summary else "（无输出）"}

## 文件改动

{files_list}
"""
    _push(content, "requirement_completion", project)


def push_task_completed(task, step, requirement) -> None:
    project = _project_name(getattr(requirement, "target_project_path", None))
    content = f"""---
id: TASK-{task.id}
title: "{(step.title if step else (task.description or '')[:80])}"
project: {project}
source_type: task_completion
status: completed
agent_id: {task.agent_id}
requirement_id: {getattr(requirement, 'id', '')}
execution_time_ms: {task.execution_time_ms or 0}
---

## 任务描述

{task.description}

## 验收标准（done_when）

{step.done_when_markdown if step else ''}

## 执行结果

{(task.output_content or '')[:3000]}
"""
    _push(content, "task_completion", project)


def push_task_failed(task, step, requirement) -> None:
    project = _project_name(getattr(requirement, "target_project_path", None))
    content = f"""---
id: TASK-{task.id}-FAIL
title: "{(task.description or '')[:80]} — 失败"
project: {project}
source_type: error_record
status: new
agent_id: {task.agent_id}
requirement_id: {getattr(requirement, 'id', '')}
---

## 错误信息

{task.last_error_message or '（无错误信息）'}

## 任务描述

{task.description}

## 步骤上下文

- 步骤：{step.title if step else '（未知）'}
- 角色：{step.assigned_workflow_role if step else ''}
- 验收标准：{step.done_when_markdown if step else ''}
"""
    _push(content, "error_record", project)
```

#### 调用位置：`server/services/workflow_orchestrator.py`

在 `_sync_workflow_for_task_db()` 内已有的 `task.status == "completed"` 块后，紧接 `_snapshot_file_changes` 调用处：

```python
# task 完成时
from server.services.agents_memory_sync import push_task_completed
push_task_completed(task, step, requirement)

# task 失败时（在 task.status == "failed" 分支中）
from server.services.agents_memory_sync import push_task_failed
push_task_failed(task, step, requirement)
```

在 `_finalize_requirement()` 末尾：

```python
from server.services.agents_memory_sync import push_requirement_completed
steps_summary = [
    {"title": s.title, "role": s.assigned_workflow_role or "", "status": s.status,
     "execution_time_ms": s.compatibility_task.execution_time_ms if s.compatibility_task else None}
    for s in workflow_run.steps
]
last_task = next(
    (s.compatibility_task for s in reversed(workflow_run.steps) if s.compatibility_task and s.compatibility_task.output_content),
    None,
)
output_summary = last_task.output_content if last_task else ""
changed_files = []  # 可从各步骤的 file-changes.json 聚合
push_requirement_completed(requirement, steps_summary, output_summary, changed_files)
```

### 7.6 配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `AGENTS_MEMORY_URL` | `http://localhost:10100` | Agents-Memory FastAPI 地址 |
| `AGENTS_MEMORY_SYNC_ENABLED` | `true` | 开关，设为 `false` 完全禁用写入 |

在 `scripts/local/restart.sh` 或 `.env` 中设置即可。

### 7.7 项目标识映射

Agents-Memory 通过 `project` 字段区分项目。推导规则：

```
requirement.target_project_path → Path(...).name
  /Users/cliff/workspace/agent/Synapse-Network → "Synapse-Network"
  /Users/cliff/workspace/agent/Synapse-Network-Provider → "Synapse-Network-Provider"
  None → "synapse-network-growing"（当前系统自身）
```

发送到 Agents-Memory 前会再做 slug 归一化，统一转成小写 kebab-case：

```
Synapse-Network → "synapse-network"
Synapse-Network-Growing → "synapse-network-growing"
```

若该项目尚未在 Agents-Memory 注册，ingest 仍会成功（记录会被创建，但在项目列表中不可见，需手动 `amem bootstrap` 注册）。

### 7.8 实施计划（P2 追加）

| 任务 | 文件 | 预估行数 |
|------|------|---------|
| 新建 `agents_memory_sync.py`，实现 `_push` + 三个 push 函数 | `server/services/agents_memory_sync.py` | ~120 |
| `workflow_orchestrator.py`：task completed / failed 调用点 | `server/services/workflow_orchestrator.py` | ~10 |
| `workflow_orchestrator.py`：`_finalize_requirement` 调用点 | `server/services/workflow_orchestrator.py` | ~15 |
| 测试：mock `requests.post`，验证 content 格式和 push 触发时机 | `tests/test_agents_memory_sync.py` | ~80 |

### 7.9 写入数据流总览

```
需求完成
  _finalize_requirement()
    └─ push_requirement_completed()
         └─ POST /api/ingest (source_type=requirement_completion)
              └─ Agents-Memory memory/workflow_records/ 目录存档

任务完成
  _sync_workflow_for_task_db()  [task.status == "completed"]
    ├─ _snapshot_file_changes()   ← 已有
    └─ push_task_completed()
         └─ POST /api/ingest (source_type=task_completion)
              └─ Agents-Memory memory/workflow_records/ 目录存档

任务失败
  _sync_workflow_for_task_db()  [task.status == "failed"]
    └─ push_task_failed()
         └─ POST /api/ingest (source_type=error_record)
              └─ Agents-Memory 错误记录，可被 wiki-compile 引用
```

### 7.10 风险与缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| Agents-Memory 服务未启动 | 中 | `threading.Thread` 后台推送，5s timeout，失败 debug 级日志，主流程不受影响 |
| output_content 超大（模型输出） | 中 | 写入前截断到 3000 字符 |
| 需求 description 含敏感路径 | 低 | `target_project_path` 不写入 content 正文，仅用于派生项目名 |
| 重复写入（任务重试多次） | 低 | 每次写入生成不同 `id`（ERR-日期-序号），不去重，历史记录均保留 |
| Agents-Memory project 未注册 | 低 | ingest 仍成功，可后续补充 `amem bootstrap` 注册 |
