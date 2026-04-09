---
id: taskboard-bugfix-log
title: "TaskBoard / Approvals Bug 记录"
created_at: 2026-04-08
updated_at: 2026-04-09
---

# TaskBoard / Approvals Bug 记录

| # | 时间 | 模块 | 描述 | 状态 |
|---|------|------|------|------|
| 1 | 2026-04-08 | tests/conftest.py | SQLite in-memory DB 每个连接独立，导致 create_all 建的表在另一个连接查不到。改用 `StaticPool` 使所有连接共享同一个内存 DB | ✅ fixed |
| 2 | 2026-04-08 | server/database.py, tests/conftest.py | SQLAlchemy PRAGMA foreign_keys 需要通过 `cursor.execute()` 而非直接在 dbapi_conn 上调用 | ✅ fixed |
| 3 | 2026-04-09 | scripts/local/*.sh, scripts/prod/*.sh | `cd "$(dirname "$0")/.."` 解析到 `scripts/` 而非项目根目录，导致 `uvicorn server.main:app` 找不到模块。改为 `SCRIPT_DIR/../..` | ✅ fixed |
| 4 | 2026-04-09 | scripts/local/*.sh, scripts/prod/*.sh | 脚本使用系统 Python 3.9 而非 venv Python 3.14，缺少依赖。增加 venv 自动激活 | ✅ fixed |
| 5 | 2026-04-09 | server/database.py | 新增 `group` 列后，`create_all` 不会 ALTER 已存在的表，导致 `no such column: agents.group`。在 `init_db` 中增加轻量迁移：用 `inspect()` 检测缺失列并执行 `ALTER TABLE` | ✅ fixed |
| 6 | 2026-04-09 | tests/test_tasks_api.py, tests/test_approvals_api.py | `run_task()` 从同步→异步后，旧测试期望立即 `status=completed`，实际返回 `status=running`。改为 mock `dispatch` + 手动调用 `_run_task_sync` 验证完整流程 | ✅ fixed |
| 7 | 2026-04-09 | tests/conftest.py | `task_runner._run_task_sync()` 内部 `SessionLocal()` 连接到生产 DB，而非测试 in-memory DB。在 conftest 的 `setup_db` 中 patch `server.services.task_runner.SessionLocal` 为 `TestSession` | ✅ fixed |
| 8 | 2026-04-09 | dashboard/tests/TaskBoard.test.tsx | 展开任务卡片测试 click 了外层 div (`task-3`)，但 `onClick` 在内层 header div 上。改为 click 内部文本 `#3` | ✅ fixed |
| 9 | 2026-04-09 | dashboard/tests/TaskBoard.test.tsx | Polling 测试使用 `vi.useFakeTimers()` 与 React async 渲染冲突导致超时。改为 real timers + `waitFor` 等真实 3s 轮询周期 | ✅ fixed |
| 10 | 2026-04-09 | server/services/llm_adapter.py, tests/test_crew_integration.py | Provider 构造器把显式空字符串也当成“回退到 config”，导致 `.env` 中的 Copilot token 污染无 key 测试，并触发真实外网请求。改为仅在参数为 `None` 时才回退配置；测试继续用显式空字符串验证无 key 分支 | ✅ fixed |
| 11 | 2026-04-09 | tests/test_tasks_api.py, dashboard/src/pages/TaskBoard.tsx | 新增重试与详情重构后出现两处回归：重试测试误把 `running` 任务当失败任务，详情区缺失 `skill-badge-*` 导致前端测试失败。前者改为先构造真实 failed 源任务再 retry，后者恢复详情 skill badge 标识 | ✅ fixed |
| 12 | 2026-04-09 | tests/test_tasks_api.py, tests/conftest.py | Phase 2 持久化快照测试直接 `import tests.conftest.TestSession`，触发 pytest `conftest` 被按不同模块名加载，落到另一套 in-memory SQLite，查询时报 `no such table: agents`。改为通过 pytest fixture 注入共享 `db_session` | ✅ fixed |
| 13 | 2026-04-09 | dashboard/tests/Approvals.test.tsx, dashboard/src/pages/Approvals.tsx | 第三阶段新增批量审批测试时，文件结尾缺少 `)` 导致 Vitest 报 `Expected ')' but found 'EOF'`；同时状态样式判断使用嵌套三元表达式，可读性差。修复测试闭合语法，并提取 `statusClassName()` 简化样式分支 | ✅ fixed |
| 14 | 2026-04-09 | tests/test_tasks_api.py, tests/test_approvals_api.py, tests/test_crew_integration.py, dashboard/tests/TaskBoard.test.tsx | 新增 runtime 抽象后，旧测试仍 patch `server.services.task_runner._engine`，而 `_run_task_sync()` 已改为走 `get_task_runtime()`；同时 TaskBoard 抽屉开始自动请求日志，旧测试未提供 `getTaskLogs` mock。统一切换测试到 fake runtime，并补默认日志 mock 和运行时事件断言 | ✅ fixed |
| 15 | 2026-04-09 | copilot-sdk-runner/package.json | 初版把 `@github/copilot-sdk` 写成了不存在的 `^0.17.0`，`npm install` 直接失败。改为 npm 上实际存在的稳定版本 `^0.2.1`，随后完成依赖安装与 import smoke check | ✅ fixed |
| 16 | 2026-04-09 | server/services/task_runtime.py, copilot-sdk-runner/run_session.mjs | live smoke 中 `copilot_sdk` runtime 会在 60 秒后报 `Timeout after 60000ms waiting for session.idle`。根因是 Python 层外部 timeout 已放宽到配置值，但 Node runner 内部 `session.sendAndWait()` 仍使用 SDK 默认 60s。改为从后端显式传入 `timeoutMs`，让 runner 与 `COPILOT_SDK_TIMEOUT` 保持一致 | ✅ fixed |
| 17 | 2026-04-09 | dashboard/vitest.config.ts | 引入 Playwright 后，Vitest 默认文件发现把 `tests/e2e` 和 `node_modules` 中的包自测一起扫进来，导致单测运行出现大量无关失败。改为显式 `include` 本仓库 `tests/**/*.test.ts(x)`，并排除 `tests/e2e/**` | ✅ fixed |
| 18 | 2026-04-09 | tests/test_copilot_auth_api.py | Copilot auth 文件回退测试在本机已登录环境下会优先命中真实 `COPILOT_OAUTH_TOKEN` / `GITHUB_TOKEN`，导致临时目录 fixture 失效并出现不稳定失败。测试中显式 patch 配置 token 为空，确保只验证 `apps.json` / `oauth.json` 解析逻辑 | ✅ fixed |
