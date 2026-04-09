---
id: phase2-bugfix
title: "Phase 2 Bug 记录"
created_at: 2026-04-08
---

# Phase 2: Bug 记录

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
