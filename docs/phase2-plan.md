---
id: phase2-ops-dashboard
title: "Phase 2: Agentic Ops Dashboard 技术方案"
version: "1.0"
status: completed
created_at: 2026-04-08
author: CTO
---

# Phase 2: Agentic Ops Dashboard 技术方案

## 概述

为 Synapse-Network-Growing 构建一个轻量 Web 管理面板，可视化 Agent 组织架构、任务看板、执行历史，并支持 Web 端任务提交与审批。

## 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| Backend | FastAPI + SQLite | 轻量、零外部依赖、与 CrewAI 同为 Python |
| Frontend | React + Vite + TailwindCSS | 快速原型、与 Synapse-Network 前端技术栈一致 |
| ORM | SQLAlchemy (async) | FastAPI 生态标配 |
| 测试 | pytest + httpx (后端) / vitest (前端) | 项目已有 pytest 惯例 |

## 目录结构

```text
Synapse-Network-Growing/
├── server/                          # FastAPI 后端
│   ├── main.py                      # 启动入口
│   ├── database.py                  # SQLite 连接 & 表定义
│   ├── models.py                    # SQLAlchemy 模型
│   ├── schemas.py                   # Pydantic 请求/响应模型
│   ├── routers/
│   │   ├── agents.py                # /api/agents
│   │   ├── tasks.py                 # /api/tasks
│   │   └── approvals.py            # /api/approvals
│   └── services/
│       ├── agent_loader.py          # 从 roles/ 加载 Agent 元数据
│       └── engine.py                # CrewAI 引擎封装
├── dashboard/                       # React 前端
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── OrgChart.tsx         # 组织架构
│   │   │   ├── TaskBoard.tsx        # 任务看板
│   │   │   └── Approvals.tsx        # 审批中心
│   │   └── components/
│   └── index.html
├── tests/
│   ├── test_agents_api.py
│   ├── test_tasks_api.py
│   └── test_approvals_api.py
└── docs/
    ├── phase2-plan.md               # 本文件
    └── bugfix.md                    # Bug 记录
```

## 数据模型

```sql
CREATE TABLE agents (
    id          TEXT PRIMARY KEY,       -- role_id: dev_rel, growth_lead...
    display_name TEXT NOT NULL,
    goal        TEXT NOT NULL,
    persona_path TEXT,
    skills      TEXT,                   -- JSON array
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    description     TEXT NOT NULL,
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    status          TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | pending_approval | approved | rejected | completed | failed
    requires_approval BOOLEAN DEFAULT 0,
    priority        TEXT DEFAULT 'normal',  -- low | normal | high
    output_path     TEXT,
    output_content  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    started_at      TEXT,
    completed_at    TEXT
);

CREATE TABLE approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    reviewer    TEXT,
    comment     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    decided_at  TEXT
);

CREATE TABLE task_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id),
    event_type  TEXT NOT NULL,  -- created | started | output | approval_requested | approved | rejected | completed | failed
    detail      TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
```

## API 设计

### Agents

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/agents` | 全部 Agent 列表 |
| GET | `/api/agents/{id}` | Agent 详情 + 任务统计 |
| POST | `/api/agents/sync` | 从 `roles/` 目录同步 Agent 到 DB |

### Tasks

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 任务列表，支持 `?status=` `?agent_id=` 筛选 |
| POST | `/api/tasks` | 创建新任务 |
| POST | `/api/tasks/{id}/run` | 触发执行（调用 CrewAI） |
| GET | `/api/tasks/{id}/logs` | 任务执行日志 |

### Approvals

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/approvals?status=pending` | 待审批列表 |
| POST | `/api/approvals/{id}/decide` | 批准或拒绝 `{action: "approve"|"reject", comment: ""}` |

### Dashboard

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/dashboard/stats` | 全局统计：Agent 数、任务分布、完成率 |

## 实施计划

| # | 任务 | 状态 |
|---|------|------|
| 1 | 创建 `server/` 骨架：database + models + schemas | ✅ completed |
| 2 | 实现 agents API + agent_loader service | ✅ completed |
| 3 | 实现 tasks API（CRUD + 状态流转） | ✅ completed |
| 4 | 实现 approvals API | ✅ completed |
| 5 | 实现 dashboard stats API | ✅ completed |
| 6 | 编写 pytest 测试覆盖所有 API | ✅ completed (27 tests) |
| 7 | 创建 `dashboard/` React 骨架 | ✅ completed |
| 8 | 实现 OrgChart / TaskBoard / Approvals 页面 | ✅ completed |
| 9 | 端到端验证 & Bug 修复 | ✅ completed (2 bugs fixed) |
| 10 | 更新文档状态 | ✅ completed |
