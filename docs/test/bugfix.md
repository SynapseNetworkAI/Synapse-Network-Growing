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
