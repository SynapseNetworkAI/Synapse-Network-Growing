# `runtime/` 地图

负责 task runtime、后台 monitor、会话复用、告警与运行期 guard。

## 公开入口

- `task_runtime.py`
- `task_runner.py`
- `runtime_guards.py`
- `task_metadata.py`
- `alerting.py`
- `codex_cli*.py`
- `copilot_*.py`
- `openai_responses_monitor.py`

## 依赖边界

- 可以依赖 `agents/` 与 `delivery/`。
- 不应承担 requirement CRUD 或 portfolio 调度。

## 禁止依赖

- 不得直接承担 requirement CRUD、release governance 或 portfolio scheduling。
- 不得让 monitor/router 直接依赖 runtime 私有 helper。

## 常见改动

- runtime 选择与 prompt packet：`task_runtime.py`
- monitor 与 session 问题：对应 `*_monitor.py`、`codex_session_registry.py`
- 运行期告警：`alerting.py`

## 迁移映射

- `server.services.alerting` -> `server.services.runtime.alerting`
- `server.services.runtime_guards` -> `server.services.runtime.runtime_guards`
- 其余 runtime 平铺模块同名迁移到本目录
