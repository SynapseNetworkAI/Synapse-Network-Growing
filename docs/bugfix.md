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
