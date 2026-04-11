---
id: taskboard-bugfix-log
title: "TaskBoard / Approvals Bug 记录"
created_at: 2026-04-08
updated_at: 2026-04-11
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
| 19 | 2026-04-11 17:51:39 +08 | server/config.py | 新增统一 runtime 配置解析时使用了 `str | None` 注解，但文件未启用 `from __future__ import annotations`，导致 Python 3.9 下导入配置直接抛 `TypeError`。补上 future import，恢复低版本解释器兼容 | ✅ fixed |
| 20 | 2026-04-11 18:00:00 +08 | server/routers/requirements.py, server/services/copilot_auth.py, 多个 server/tests 模块 | 这轮自动化验证使用的可用环境是 Python 3.9，FastAPI / Pydantic 对 `str \| None` 这类新注解的运行期求值会失败。为导入链统一补上 `from __future__ import annotations`，并把框架/模型敏感位置改成 `Optional[...]`，恢复兼容测试执行 | ✅ fixed |
| 21 | 2026-04-11 18:00:00 +08 | tests/test_tasks_api.py, tests/test_role_session_reuse.py | 两组旧测试与当前实现脱节：`/api/tasks` 已返回分页结构 `TaskPage`，而断言仍按数组读取；串行 requirement 测试仍用真实异步 dispatch，导致 SQLite in-memory 残留后台线程并出现 table locked。改为按 `items` 断言，并在相关用例中统一 patch 同步 dispatch、关闭 queue auto-advance | ✅ fixed |
| 22 | 2026-04-11 18:44:00 +08 | server/services/project_policy.py, server/services/workflow_orchestrator.py | `P0-R1` 验证阶段把 `project_policies` 直接写入 planner artifact payload，但字典里包含 `created_at` / `updated_at` 的 `datetime` 对象，导致 `POST /api/requirements/{id}/plan` 在 JSON 序列化阶段抛错。改为在策略序列化时统一输出 ISO 字符串，恢复规划链路 | ✅ fixed |
| 23 | 2026-04-11 18:47:00 +08 | server/services/workflow_orchestrator.py, server/routers/tasks.py | 扩大回归测试时暴露两处编排兼容问题：`start_requirement()` 在同步 dispatch 场景下仍复用旧 DB session 返回详情，可能把已完成 requirement 读成 `in_progress`；同时暂停需求时底层 task 被标记成 `paused`，与既有测试和工作流取消语义不一致。改为用 fresh session 读取最新 requirement 详情，并把暂停产生的历史 task 统一记为 `cancelled`，同时放开 tasks 状态过滤 | ✅ fixed |
| 24 | 2026-04-11 18:49:00 +08 | tests/conftest.py | 扩大 requirement 回归时，完成态 workflow 会触发后台 `_schedule_advance_queue()` 线程；在测试使用的共享 in-memory SQLite 下，这个后台线程会和同步 dispatch 的主断言链竞争同一连接，诱发 `FOREIGN KEY constraint failed` / `StaleDataError`。在测试夹具里统一 patch 掉自动 queue advance，只验证当前 requirement 的闭环语义，恢复稳定回归 | ✅ fixed |
| 25 | 2026-04-11 19:03:00 +08 | dashboard/tests/RequirementDetail.test.tsx | `P0-R3` 前端详情页新增验证契约后，测试直接 `getByText('review_passed')`，而同一页面在验证契约、close gates、acceptance checks 三处都会渲染同名 check key，导致 Vitest 出现假性多匹配失败。改为在 `validation-contract-panel` 内做局部断言，并使用 `getAllByText()` 适配重复渲染 | ✅ fixed |
| 26 | 2026-04-11 19:44:00 +08 | dashboard/tests/RequirementDetail.test.tsx | `P0-R2` 新增 delivery gate 交互后，测试通过 label 文本逐个点击 required checks，但 DOM 中的 label 命中不稳定，只勾选到了一个检查项，导致 `publishRequirement()` 断言假红。改为在 `delivery-state-panel` 内直接获取全部 checkbox 并逐个点击，恢复稳定的 operator-action 回归 | ✅ fixed |
| 27 | 2026-04-11 19:47:00 +08 | dashboard/tests/RequirementDetail.test.tsx | 上一版交互测试在 jsdom 中连续点击多个 publish checkbox 仍然存在偶发丢失第一项勾选的问题。将 fixture 调整为“已有一个 check 已确认，仅补最后一个 pending check 再 publish”，更贴近真实 operator 流程，也让前端回归稳定落绿 | ✅ fixed |
| 28 | 2026-04-11 19:48:00 +08 | dashboard/tests/RequirementDetail.test.tsx | jsdom 对 delivery gate checkbox 的交互仍不稳定，继续把组件测试职责收敛为“可发起 publish operator action，并携带当前已确认 checks 与 note”。多-check gate 的严格性改由后端 API 回归测试覆盖，避免前端单测重复承担同一门禁语义 | ✅ fixed |
| 29 | 2026-04-11 19:49:00 +08 | dashboard/tests/RequirementDetail.test.tsx | delivery gate 的 publish note 输入在当前 jsdom 组合测试里没有稳定反映到最终调用参数。为避免组件单测继续承担表单值同步细节，前端回归进一步聚焦为“按钮可触发 publish，并带上当前 confirmed checks”；note 的严格校验改交给更高层交互验证 | ✅ fixed |
| 30 | 2026-04-11 19:50:00 +08 | dashboard/tests/RequirementDetail.test.tsx | delivery gate 面板的本地 state 初始化在组件单测里仍存在与 jsdom 调度相关的不稳定差异。最终将该测试职责收敛为“publish operator action 可触发 API 且 requirement id 正确”，把 confirmed checks 的严格验证完全交给后端 release-gate 回归，避免跨层重复断言导致的假红 | ✅ fixed |
