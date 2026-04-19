# `reviews/` 地图

负责经营复盘、公司 review 与角色 KPI。

## 公开入口

- `company_review.py`
- `role_kpis.py`

## 依赖边界

- 可以聚合 portfolio、signals、requirements、workflow runs 与 release 数据。
- 不直接控制 workflow dispatch。

## 迁移映射

- `server.services.company_review` -> `server.services.reviews.company_review`
- `server.services.role_kpis` -> `server.services.reviews.role_kpis`
