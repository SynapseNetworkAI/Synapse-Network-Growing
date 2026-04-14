# Dashboard Frontend Guide

`dashboard/` 是 `Synapse-Network-Growing` 当前正式控制台前端。

当前正式方向不是“平铺卡片后台”，而是 **Agent-First Enterprise Workbench**。

## 1. Visual Thesis

1. 视觉方向固定为克制型工程工作台，接近 Linear 风格。
2. 强调结构、层级、留白和扫描效率，而不是卡片数量和装饰感。
3. Requirement / Execution / Release 三面必须各自有独立页面模板。
4. `/errors` 只能作为稳定性治理辅助页存在，不能升级成第四个主业务面。

## 2. Hard Rules

1. 默认禁止整页卡片化。
2. 卡片只能用于独立对象，不得作为每个 section 的万能容器。
3. 每个页面必须先有工作台骨架，再有组件。
4. 一个页面只能有一个主焦点。
5. 不允许用 chips / pills 代替真正的信息层级。
6. Requirement 页面不能重新混入 execution telemetry 和 release controls。
7. Release 页面不能回灌 requirement 编辑能力。
8. Error 页面只负责 fingerprint、关联对象和通知历史，不负责主业务操作。

## 3. Workbench Skeleton

每个页面优先组合这些结构，而不是自由堆叠 div：

1. `Workbench shell`
2. `Page header`
3. `Primary workspace`
4. `Secondary inspector`
5. `Activity feed`
6. `State badge`
7. `Section frame`
8. `Workbench toolbar`
9. `Overlay drawer`

当前共享骨架组件入口：

1. `src/components/workbench.tsx`

## 4. Design Tokens

当前 token 必须覆盖：

1. surface hierarchy
2. text hierarchy
3. stroke hierarchy
4. state colors
5. layout tokens
6. restrained radius / shadow tokens

token 主入口：

1. `src/index.css`

## 5. Review Checklist

所有 UI PR 默认回答下面几个问题：

1. 这个页面属于 Requirement / Execution / Release 哪一面？
2. 是否复用了 workbench 模板和 token？
3. 是否继续引入了平铺式大白卡布局？
4. 页面是否只有一个主焦点？
5. inspector 和 activity 是否承担了明确职责？
6. create / edit 是否继续被做成列表页常驻内联表单？
7. requirement create 是否只采集最小 intent，而不是把 acceptance 收集前置给用户？

如果答案是“继续堆卡片也能做”，说明方案还没收口。

## 6. List Page Pattern

列表型页面默认采用 `Toolbar + Drawer` 模式，而不是把大表单常驻铺在列表上方。

固定规则：

1. 列表页负责浏览、筛选、选择和轻操作。
2. `create / edit` 优先通过工具条触发右侧 Drawer。
3. 只有极短的单字段 quick edit 才允许 inline。
4. Requirement 列表页的主焦点是 queue 与 selection，不是 intake form。
5. `新建需求` 默认只采集标题、目标项目、描述和优先级；`验收标准` 由 agent 创建后立即生成，并在详情页可编辑。
6. 禁止使用浏览器原生 `alert / confirm`；destructive 动作使用统一确认弹窗，轻量反馈使用 toast。
