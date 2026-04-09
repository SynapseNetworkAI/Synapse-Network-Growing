---
id: copilot-sdk-runtime-automation-test-plan
title: Copilot SDK Runtime 自动化测试方案
status: verified
created_at: 2026-04-09
updated_at: 2026-04-09
author: github-copilot
target_repo: Synapse-Network-Growing
---

# Copilot SDK Runtime 自动化测试方案

## 1. 目标

本方案用于验证当前已落地的 Copilot SDK 长任务运行时实现，重点覆盖以下能力：

1. 后端任务执行可以在 `legacy` 与 `copilot_sdk` 运行时之间切换
2. 任务接口会返回运行时元数据：`runtime_backend`、`runtime_session_id`、`runtime_selected_agent`
3. Copilot SDK 任务会以 detached worker 方式执行，并通过 monitor 持续同步状态、事件和最终产出
4. TaskBoard 右侧抽屉只展示人类可读的 `assistant_output`，而不是原始 runtime 事件噪音
5. 执行时长会在任务运行中动态更新，并在完成后回落到最终落库的 `execution_time_ms`
6. 前端页面在新增运行时信息后仍能稳定渲染、测试、打包
7. 浏览器级验证可以稳定覆盖组织架构、任务抽屉运行时元数据、创建任务、失败后重试、单条审批与批量审批主链路

## 2. 覆盖范围

### 后端

直接覆盖文件：

1. `server/routers/tasks.py`
2. `server/services/task_runner.py`
3. `server/services/task_runtime.py`
4. `server/services/copilot_sdk_bridge.py`
5. `server/services/copilot_sdk_state.py`
6. `server/services/copilot_sdk_monitor.py`
7. `server/database.py`
8. `server/main.py`

对应测试：

1. `tests/test_tasks_api.py`
2. `tests/test_crew_integration.py`
3. `tests/test_copilot_sdk_bridge.py`

重点验证内容：

1. `run` / `retry` / `bulk-retry` 路径仍然可用
2. `_run_task_sync()` 不再依赖旧的 `_engine` 单例，而是通过 `get_task_runtime()` 执行
3. `copilot_sdk` 运行时以 `deferred=True` 返回，任务保持 `running`
4. monitor 会增量消费 runtime 事件并写入 `task_logs`
5. `runtime_event_cursor` 可以保证重复轮询时幂等
6. stale heartbeat 会触发 `resumeSession()` 恢复

### 前端

直接覆盖文件：

1. `dashboard/src/pages/TaskBoard.tsx`
2. `dashboard/src/api.ts`

对应测试：

1. `dashboard/tests/TaskBoard.test.tsx`
2. `dashboard/tests/Approvals.test.tsx`
3. `dashboard/tests/OrgChart.test.tsx`
4. `dashboard/tests/e2e/smoke.spec.ts`

重点验证内容：

1. 任务抽屉展示 `runtime_backend`
2. 任务抽屉展示 `runtime_selected_agent`
3. 任务抽屉展示 `runtime_session_id`
4. 任务抽屉主视图只展示 `assistant_output`
5. 原始 `runtime_started`、`tool_execution_complete` 等机器事件不再作为主展示内容
6. 任务卡片与详情抽屉中的执行时长会随运行中任务动态刷新
7. 新增运行时字段后既有 TaskBoard 交互不回归
8. 浏览器级路由切换、任务详情抽屉、创建任务、失败后重试、单条审批、批量审批在真实 DOM 中可执行

## 3. 自动化执行命令

后端：

```bash
/Users/cliff/workspace/agent/.venv/bin/python -m pytest tests -q
```

前端单测：

```bash
cd dashboard
npx vitest run
```

前端构建：

```bash
cd dashboard
npm run build
```

前端浏览器 E2E：

```bash
cd dashboard
npm run test:e2e
```

Node runner 依赖 smoke check：

```bash
cd copilot-sdk-runner
npm install --registry=https://registry.npmjs.org
node -e "import('@github/copilot-sdk').then((m) => console.log(typeof m.CopilotClient))"
```

## 4. 通过标准

本次改造通过需要同时满足：

1. 后端 pytest 全通过
2. 前端 Vitest 全通过
3. 前端 build 成功
4. TaskBoard 对 `assistant_output` 主展示和动态执行时长存在自动化断言覆盖
5. 浏览器级 Playwright smoke 覆盖通过
6. Node runner 可以成功导入 `@github/copilot-sdk`

## 5. 本次验证结果

验证时间：2026-04-09

后端：

```bash
/Users/cliff/workspace/agent/.venv/bin/python -m pytest tests -q
```

结果：`108 passed`

前端：

```bash
cd dashboard
npx vitest run
```

结果：`48 passed`

TaskBoard 定向 UI 验证：

```bash
cd dashboard
npx vitest run tests/TaskBoard.test.tsx
```

结果：`26 passed`

其中新增覆盖：

1. 抽屉只展示 `assistant_output`
2. 运行中任务的执行时长在列表和抽屉内动态更新

浏览器级 E2E：

```bash
cd dashboard
npm run test:e2e
```

结果：`6 passed`

其中覆盖：

1. 组织架构首页加载
2. 任务抽屉运行时元数据、assistant transcript 与执行时长展示
3. 创建任务
4. 失败任务重试
5. 单条审批
6. 批量审批

前端构建：

```bash
cd dashboard
npm run build
```

结果：打包成功

Node runner：

```bash
cd copilot-sdk-runner
node -e "import('@github/copilot-sdk').then((m) => console.log(typeof m.CopilotClient))"
```

结果：输出 `function`

真实登录态 live smoke：

1. 本机会话已在 `ORCHESTRATION_BACKEND=copilot_sdk` 下成功执行任务 `#17` 与 `#18`
2. 最终任务 `#18` 返回 `runtime_backend=copilot_sdk`，且 UI 可展示 `runtime_session_id`、`assistant_output` 与执行时长

## 6. 当前限制

以下内容仍然不适合作为确定性的 CI 自动化断言：

1. 真实 GitHub Copilot 登录态下的 `run_session.mjs` 远程会话执行

原因：

1. 真实 Copilot SDK 会话依赖本机有效登录态和外部网络，不适合作为稳定自动化断言
2. 当前新增的 Playwright 用例使用 `/api/*` mock 来保证浏览器回归稳定，不直接依赖本机后端与远端 Copilot 状态

结论：

1. 本次代码改动已通过后端、前端单测、浏览器级 Playwright、构建与 runner 依赖层面的验证
2. 真实登录态 live smoke 也已在本机完成，但它仍应保留为发布前人工验证项