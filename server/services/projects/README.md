# `projects/` 地图

负责项目策略、项目 onboarding、跨项目 intelligence 与路由支撑。

## 公开入口

- `policy.py`
- `onboarding.py`
- `intelligence.py`

## 依赖边界

- 可以依赖 requirement、signal 等只读数据。
- 不负责 workflow orchestration。

## 常见改动

- 默认项目策略与 capability matrix：`policy.py`
- onboarding manifest：`onboarding.py`
- 路由评分与 requirement 序列化：`intelligence.py`

## 迁移映射

- `server.services.project_policy` -> `server.services.projects.policy`
- `server.services.project_onboarding` -> `server.services.projects.onboarding`
- `server.services.project_intelligence` -> `server.services.projects.intelligence`
