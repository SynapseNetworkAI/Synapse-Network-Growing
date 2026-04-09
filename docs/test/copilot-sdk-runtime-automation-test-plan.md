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

本方案用于验证本次 Copilot SDK 多 Agent 运行时改造后的四类能力：

1. 后端任务执行可以在 `legacy` 与 `copilot_sdk` 运行时之间切换
2. 任务接口会返回运行时元数据：`runtime_backend`、`runtime_session_id`、`runtime_selected_agent`
3. 运行时事件会被写入 `task_logs` 并在 TaskBoard 右侧抽屉中展示
4. 前端页面在新增运行时信息后仍能稳定渲染、测试、打包
5. 浏览器级验证可以稳定覆盖组织架构、任务抽屉运行时元数据、审批流

## 2. 覆盖范围

### 后端

直接覆盖文件：

1. `server/routers/tasks.py`
2. `server/services/task_runner.py`
3. `server/services/task_runtime.py`
4. `server/services/copilot_sdk_bridge.py`
5. `server/database.py`

对应测试：

1. `tests/test_tasks_api.py`
2. `tests/test_approvals_api.py`
3. `tests/test_crew_integration.py`
4. `tests/test_copilot_auth_api.py`

重点验证内容：

1. `run` / `retry` / `bulk-retry` 路径仍然可用
2. `_run_task_sync()` 不再依赖旧的 `_engine` 单例，而是通过 `get_task_runtime()` 执行
3. `copilot_sdk` 运行时结果会落库并写入 runtime/subagent 事件
4. 审批流在新运行时抽象下保持兼容

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
4. 任务抽屉展示运行时事件流
5. 新增运行时字段后既有 TaskBoard 交互不回归
6. 浏览器级路由切换、任务详情抽屉、审批操作在真实 DOM 中可执行

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
4. Node runner 可以成功导入 `@github/copilot-sdk`
5. TaskBoard 新增运行时信息存在自动化断言覆盖
6. 浏览器级 Playwright smoke 覆盖通过

## 5. 本次验证结果

验证时间：2026-04-09

后端：

```bash
/Users/cliff/workspace/agent/.venv/bin/python -m pytest tests/test_tasks_api.py tests/test_approvals_api.py tests/test_crew_integration.py tests/test_copilot_auth_api.py
```

结果：`80 passed`

前端：

```bash
cd dashboard
npx vitest run
```

结果：`47 passed`

TaskBoard 定向 UI 验证：

```bash
cd dashboard
npx vitest run tests/TaskBoard.test.tsx
```

结果：`25 passed`

浏览器级 E2E：

```bash
cd dashboard
npm run test:e2e
```

结果：`3 passed`

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
2. 最终任务 `#18` 返回 `runtime_backend=copilot_sdk`，且 UI 可展示 `runtime_session_id` 与运行时事件

## 6. 当前限制

以下内容仍然不适合作为确定性的 CI 自动化断言：

1. 真实 GitHub Copilot 登录态下的 `run_session.mjs` 远程会话执行

原因：

1. 真实 Copilot SDK 会话依赖本机有效登录态和外部网络，不适合作为稳定自动化断言
2. 当前新增的 Playwright 用例使用 `/api/*` mock 来保证浏览器回归稳定，不直接依赖本机后端与远端 Copilot 状态

结论：

1. 本次代码改动已通过后端、前端单测、浏览器级 Playwright、构建与 runner 依赖层面的验证
2. 真实登录态 live smoke 也已在本机完成，但它仍应保留为发布前人工验证项