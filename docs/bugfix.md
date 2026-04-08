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
