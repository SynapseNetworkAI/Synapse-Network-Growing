# `server/services` 地图

这个目录承载 Synapse COO 控制面的服务层。后续新增服务必须优先进入对应功能分包，而不是继续把文件平铺在根目录。

## 分包一览

- `agents/`: Agent、Skill、上下文加载、执行解析与 LLM 适配。
- `runtime/`: task runtime、监控器、会话复用、运行期 guard。
- `projects/`: 项目策略、项目 onboarding、跨项目 intelligence。
- `requirements/`: requirement 语义、来源、附件、审批、family。
- `bugs/`: bug intake、bug source、日志 sweep 与外部适配。
- `signals/`: incidents、optimization signals、optimization templates。
- `reviews/`: company review、role KPI 等复盘与经营分析。
- `scheduling/`: portfolio scheduler 与 recurring workflows。
- `delivery/`: VCS、PR、deployment governance。
- `workflows/`: planner 与 orchestrator 等编排层。

## 依赖边界

- `routers/` 只能依赖各分包公开入口，不应直接依赖目录内部私有实现。
- `workflows/` 可以组合依赖其他分包。
- `requirements/` 负责 requirement 语义，不负责 portfolio 调度。
- `delivery/` 负责发布与环境能力，不回灌 requirement 执行面。

## 当前约束

- `server/services` 根目录只保留分包根说明和少量跨分包基础模块。
- 业务服务必须直接落到对应分包，不再新增平铺式 service 文件。
- `server/` 和 `tests/` 中的 Python 代码必须直接引用分包路径。
- 如果需要迁移映射，只保留在各目录 `README.md` 中，不再恢复 wrapper。
