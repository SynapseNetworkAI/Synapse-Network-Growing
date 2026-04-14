# `scheduling/` 地图

负责跨项目调度和 recurring workflow。

## 公开入口

- `portfolio_scheduler.py`
- `recurring_workflows.py`

## 依赖边界

- 可以依赖 requirement、signal、project policy 数据。
- 不直接承载 requirement CRUD。

## 迁移映射

- `server.services.portfolio_scheduler` -> `server.services.scheduling.portfolio_scheduler`
- `server.services.recurring_workflows` -> `server.services.scheduling.recurring_workflows`
