# `delivery/` 地图

负责 branch/PR/deploy 等交付与发布治理能力。

## 公开入口

- `vcs.py`
- `pull_request.py`
- `deployment_governance.py`

## 依赖边界

- 负责发布与环境能力，不负责 requirement 执行面。
- `workflows/` 可以调用本目录完成 closeout 或发布治理。

## 禁止依赖

- 不得回灌 requirement 执行控制面。
- 不得承担 requirement 详情页上的 workflow/context/runtime 决策。

## 迁移映射

- `server.services.delivery_vcs` -> `server.services.delivery.vcs`
- `server.services.delivery_pr` -> `server.services.delivery.pull_request`
- `server.services.deployment_governance` -> `server.services.delivery.deployment_governance`
