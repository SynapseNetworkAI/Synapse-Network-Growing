# `bugs/` 地图

负责 bug intake、bug source、日志 sweep 与外部日志适配。

## 公开入口

- `intake.py`
- `sources.py`
- `external_adapter.py`
- `log_sweep.py`
- `log_scheduler.py`
- `error_loop.py`

## 依赖边界

- 可以产出 requirement 输入，但不直接承担 requirement 调度。
- `error_loop.py` 允许触发 requirement submit，但不接管 execution / release 主面。

## 迁移映射

- `server.services.bug_intake` -> `server.services.bugs.intake`
- `server.services.bug_sources` -> `server.services.bugs.sources`
- `server.services.external_bug_adapter` -> `server.services.bugs.external_adapter`
- `server.services.bug_log_sweep` -> `server.services.bugs.log_sweep`
- `server.services.bug_log_scheduler` -> `server.services.bugs.log_scheduler`
