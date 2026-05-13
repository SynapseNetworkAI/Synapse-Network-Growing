# Synapse Company Ops 系统设计原则

这份文档是 `Synapse-Network-Growing` 的短入口。它只保留常驻上下文必须知道的硬原则；细则按主题放在 `docs/design-docs/principles/`，由 `docs/design-docs/context-loading-map.md` 按需加载。

不要用 Markdown import 或自动拼接把所有主题文档重新塞回上下文。拆分的目标是减少常驻上下文，而不是换一个文件名。

## 常驻硬原则

1. 模型是不稳定部件，不是可靠同事；可靠性必须来自状态机、权限、验证、恢复、日志和预算。
2. 错误路径是主路径的一部分；每条核心执行链都必须有失败分支、恢复分支、熔断条件和 operator 接管点。
3. Execute 不能自证正确；Validate 必须独立于 Execute，Deliver 只能发生在验证成功之后。
4. 默认 workflow 保持最小：`intake -> execute -> validate -> deliver`。复杂任务才展开 execution graph。
5. Agent 主导执行内容，程序只做需求治理、运行时治理、稳定性治理、自动化编排和发布治理。
6. Planner 只做 shape decision，不生成固定 research/plan/closeout 仪式。
7. 复杂 workflow 必须由 deterministic runner 基于 schema、evidence、policy、budget 和 guard 推进；Agent Atom 不直接改 workflow state。
8. 新执行链的唯一真相是 declarative workflow run；不得恢复旧 fixed-step execution 兼容路径。
9. Acceptance 必须 fail closed：缺少可执行验收、未知 evidence、危险命令、无 diff 的 code_delivery 或 verification inconclusive 都不能放行。
10. Push / PR quality gates 是合并前 hard gate；上下文规则只做实现前预防，不能替代 CI。
11. 后台任务、recurring workflow、runtime、release、publish、rollback 都必须可观测，有 run history、证据和 operator drill-down。
12. Ops Console 是 Human-Agent Control Plane，默认展示状态、原因和下一步动作；raw JSON 只能在 debug/details 中出现。
13. Requirement / Execution / Release 必须分面治理；Project 是正式主对象，Release / Deployment 以 Project 为边界。
14. 前端必须是 Enterprise Workbench，不得回到平铺卡片后台、长期内联表单、Drawer/Side Panel 或浏览器原生 confirm。
15. 上下文是预算，不是垃圾桶；长期规则、项目 policy、会话上下文和临时证据必须分层治理。
16. 治理优先于更强自主性；policy、validation、delivery、incident、observability 未收口前，不升级更复杂的 agent 自主决策。

## 按需加载入口

1. 任务开始时先读本短入口和 `docs/design-docs/context-loading-map.md`。
2. 根据任务触发词只加载相关主题文档；不要无脑读取整个 `docs/design-docs/principles/` 目录。
3. 高风险任务可以做 full principles sweep，但必须说明原因，例如 production deploy、auth、funds、settlement、rollback、workflow runner 或 cross-surface refactor。

## 主题文档

1. Planning / workflow / acceptance: `docs/design-docs/principles/planning-lifecycle.md`
2. CI / PR / code quality: `docs/design-docs/principles/quality-gates.md`
3. Ops Console / decision surfaces: `docs/design-docs/principles/ops-console.md`
4. Runtime / recurring workflows / observability: `docs/design-docs/principles/runtime-observability.md`
5. Release / deploy / rollback: `docs/design-docs/principles/release-governance.md`
6. Social publishing / X operations: `docs/design-docs/principles/social-publishing.md`
7. Frontend workbench / UI anti-regression: `docs/design-docs/principles/frontend-workbench.md`
