---
id: growing-project-architecture
title: Growing 项目架构图
role: software_engineer
status: ready
created_at: 2026-04-16
updated_at: 2026-04-16
author: codex
target_repo: Synapse-Network-Growing
doc_status: active
---

# Growing 项目架构图

## 概览

本文给出 `Synapse-Network-Growing` 的当前项目架构视图，覆盖后端、前端、测试、文档/脚本等核心边界，并直接引用仓库内保留的架构图产物。

![Growing 项目架构图](./assets/growing-project-architecture.svg)

- Canonical graph artifact: [`/.code-review-graph/graph.svg`](../.code-review-graph/graph.svg)
- Graph summary: [`/.code-review-graph/architecture-overview.json`](../.code-review-graph/architecture-overview.json)
- Regenerate command: `python3 scripts/generate_architecture_graph.py`

## 主要子系统

### 1. Product Surface

- `dashboard/src/`
  React 19 + Vite 的运维工作台，承载 Requirement、Execution、Release、Project、Error 等页面。
- `server/main.py` + `server/routers/`
  FastAPI 应用入口，负责生命周期、监控器启动、HTTP middleware、路由注册与 `/api/*` 暴露。

### 2. Execution Core

- `server/services/workflows/` + `server/services/requirements/`
  需求计划、任务编排、验证代理、交付前后状态推进，是执行主链的核心。
- `server/services/runtime/` + `server/services/agents/`
  负责 Codex/Copilot/OpenAI runtime 适配、监控、agent loader、session state 和 task runtime。
- `server/services/projects/`
  管理 project center、policy、onboarding、组织映射，是多项目治理入口。
- `server/services/bugs/` + `server/services/signals/` + `server/services/scheduling/`
  处理错误发现、优化信号、定时/周期工作流与调度相关能力。
- `server/services/delivery/`
  负责 VCS 交付、PR 同步、部署治理，接在 verification 之后。
- `server/database.py` + `server/config.py` + `server/logging_utils.py`
  提供数据库、配置与结构化日志底座，被 API 和服务层共同依赖。

### 3. Verification and Support

- `tests/`
  后端 pytest 套件，覆盖 API、workflow、delivery、runtime、project policy 等核心路径。
- `dashboard/tests/`
  前端 Vitest 与 Playwright 套件，覆盖页面交互和真实 requirement workflow。
- `docs/` + `roles/` + `demos/`
  架构文档、persona、评审产出和 demo 资产，为人和 agent 提供执行上下文。
- `scripts/`
  本地启动、重置、发布和校验入口，用于驱动开发和运维流程。

## 关键调用与依赖关系

### 前端到后端

- `dashboard/src/api.ts` 将 workbench 页面操作映射到 FastAPI `/api/*` 路由。
- `dashboard/tests/` 主要验证 `dashboard/src/`，并在 E2E 场景中联通真实后端。

### 后端主链

- `server/main.py` 在启动时初始化数据库、恢复 runtime 状态，并注册所有 routers。
- `server/routers/` 作为 HTTP surface，把请求分发到 `services/workflows`、`services/projects`、`services/bugs`、`services/delivery` 等分包。
- `services/workflows` 聚合 `requirements`、`runtime`、`projects`、`delivery`、`bugs/signals`，因此是后端依赖最集中的核心层。
- `services/runtime` 承载 agent 执行与监控，向下依赖数据库/配置，向上被 workflow engine 调用。
- `services/projects` 为 requirement、execution、release 提供目标项目、策略和 onboarding 约束。
- `services/bugs` / `signals` / `scheduling` 形成错误发现与优化闭环，并回流到 workflow engine。
- `services/delivery` 接收 verification 之后的交付动作，处理分支、PR、deployment governance。

### 数据与验证

- `server/database.py`、`server/config.py`、`server/logging_utils.py` 是共享底座，几乎所有后端分包都回落到这里。
- `tests/conftest.py` 直接挂接 `server.main.app`、替换 `get_db` 和 runtime patch，因此后端测试是 API + orchestration 的集成验证层，不只是单元测试层。

## 目录边界建议

- `server/routers/` 保持 HTTP entrypoint 职责，不继续下沉业务逻辑。
- `server/services/*/` 继续按分包组织；跨域流程统一在 `workflows/` 编排，而不是回退到平铺 service 文件。
- `dashboard/src/` 只承载前端工作台和 API client，不接入后端内部实现。
- `tests/` 和 `dashboard/tests/` 分别保持后端、前端验证边界。
- `docs/`、`roles/`、`demos/` 继续视为上下文与证据层，不混入运行逻辑。

## 生成说明

这份图的 canonical 产物保存在 `.code-review-graph/` 下，输出路径与 `code-review-graph visualize --format svg` 对齐：

- `.code-review-graph/graph.svg`
- `.code-review-graph/architecture-overview.json`

当前仓库执行环境无法直接联网安装上游 `code-review-graph` 包，因此这里采用离线静态扫描生成兼容产物布局：

- attempted command: `python3 -m pip download code-review-graph --no-deps -d /tmp/code-review-graph-download`
- result: failed in the sandbox because outbound package index access is unavailable

1. 扫描仓库内 Python 和 TypeScript 导入关系。
2. 将文件聚合到固定的子系统边界。
3. 补充 docs/prompt/API 这类导入关系之外的上下文依赖。
4. 输出 SVG 架构图和 JSON 摘要，供后续团队与 agent 复用。
