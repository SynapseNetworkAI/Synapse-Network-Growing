---
id: orgchart-ui-design
title: 组织架构页面设计方案
status: approved
created_at: 2026-04-09
author: CTO
---

# 组织架构页面设计方案

## 现状问题

当前 OrgChart 页面是纯平铺的卡片网格（3 列），无法体现：
1. 角色之间的**分组关系**（内容组 vs 增长组 vs 优化组）
2. 角色之间的**协作流向**（Launch Strategist 协调 Content Writer 和 Growth Lead）
3. 技能的**交叉引用**（多个角色共享同一技能包）

## 方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| 树菜单 (Tree) | 实现简单，折叠展开 | 过于朴素，无法体现协作关系 | 深层级 (>3 层) |
| 思维导图 (Mind Map) | 发散展示好看 | 节点多时混乱，依赖重型库 | 头脑风暴/知识图谱 |
| 传统组织架构图 (Org Chart) | 直觉清晰，上下级一目了然 | 扁平结构时显得空洞 | 大型层级组织 |
| **分组看板 + 中心辐射图 (推荐)** | 兼顾分组、协作、详情 | 需少量自定义布局 | 小型扁平团队 (5-15人) |

## 推荐方案：分组看板 + 中心辐射布局

### 设计理念

你的 Agent 团队是 **1 个 Manager (CTO/虚拟 VP) + 6 个专家**，按职能域分为 3 组。不是深度树，而是**星型拓扑**。

### 页面布局 (从上到下)

```
┌──────────────────────────────────────────────────────────────┐
│  📊 Dashboard Stats Bar (Agent数 | 任务数 | 完成数 | 待审批)  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                    ┌──────────────┐                          │
│                    │  🧠 Manager  │  ← 虚拟 VP / CTO       │
│                    │  (CrewAI)    │                          │
│                    └──────┬───────┘                          │
│              ┌────────────┼────────────┐                     │
│              ▼            ▼            ▼                     │
│   ┌─────────────┐ ┌────────────┐ ┌──────────────┐          │
│   │ 📢 内容与布道 │ │ 🚀 增长与发布│ │ 📈 优化与分析  │          │
│   │  Content    │ │  Growth    │ │  Analytics   │          │
│   ├─────────────┤ ├────────────┤ ├──────────────┤          │
│   │ DevRel      │ │ Growth Lead│ │ SEO Strateg. │          │
│   │ Content Wr. │ │ Launch Str.│ │ CRO Optimizer│          │
│   └─────────────┘ └────────────┘ └──────────────┘          │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  🔍 Agent 详情卡片（点击上方节点展开）                           │
│  ┌────────────────────────────────────┐                      │
│  │ DevRel Engineer          dev_rel   │                      │
│  │ 负责 DX 和技术布道                    │                      │
│  │ Skills: content-strategy, ...      │                      │
│  │ 任务: 5  完成: 3  进行中: 1          │                      │
│  │ [查看任务] [分配任务]                 │                      │
│  └────────────────────────────────────┘                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 分组定义

| 组名 | 英文 | 包含角色 | 颜色 |
|------|------|---------|------|
| 内容与布道 | Content & Advocacy | `dev_rel`, `content_writer` | 蓝色 |
| 增长与发布 | Growth & Launch | `growth_lead`, `launch_strategist` | 绿色 |
| 优化与分析 | Optimization & Analytics | `seo_strategist`, `cro_optimizer` | 紫色 |

### 数据模型扩展

在 persona frontmatter 中新增 `group` 字段，支持分组渲染：

```yaml
---
role: dev_rel
display_name: DevRel Engineer
goal: 负责 DX 和技术布道
group: content        # ← 新增：content | growth | optimization
skills:
  - content-strategy
  - community-marketing
---
```

API 响应新增 `group` 字段：

```json
{
  "id": "dev_rel",
  "display_name": "DevRel Engineer",
  "group": "content",
  ...
}
```

### 交互设计

#### 1. 中心辐射图区域 (上半部分)

- **Manager 节点**居中，三个分组节点围绕排列
- 每个分组节点下方展示包含的 Agent（小头像/图标）
- 节点之间用**虚线**连接表示协作流
- 点击任意 Agent 节点 → 下方展开详情卡片
- 选中的 Agent 高亮，其关联技能和任务计数实时显示

#### 2. Agent 详情卡片 (下半部分)

- 默认展示所有 Agent 的卡片网格（保持现有设计）
- 点击辐射图中的分组 → 只显示该组的卡片
- 每张卡片增加快捷操作按钮：
  - **查看任务** → 跳转到任务看板并自动过滤该 Agent
  - **分配任务** → 弹出创建任务表单，Agent 已预填

#### 3. 空状态 & 错误处理

- 后端未启动 → 显示"无法连接后端，请启动 `sh scripts/local/start.sh`"
- 无 Agent → 显示自动加载说明和重试入口
- 加载中 → 骨架屏 (Skeleton) 代替纯文字

### 实现方案

#### 纯 CSS 实现（推荐，MVP 阶段）

不引入 D3 或 React-Flow 等重型库。用 CSS Grid + Flexbox + CSS 连线实现辐射图。

```
优点：零依赖、打包体积不变、足够 6-15 个节点
缺点：节点超过 20 个需改为库方案
```

#### 技术要点

```
中心节点:        absolute + 50% 居中
分组节点:        CSS Grid 3 列
连线:            CSS border + ::before/::after 伪元素
动画:            transition + scale 做选中态
响应式:          md 以下堆叠为列表视图
```

### 配色方案

```
Manager (CTO):       bg-gray-800 text-white
Content 组:          bg-blue-50 border-blue-300
Growth 组:           bg-green-50 border-green-300
Optimization 组:     bg-purple-50 border-purple-300
选中态:              ring-2 ring-blue-500 scale-105
悬停态:              shadow-md translate-y-[-2px]
技能 Tag:            bg-{group-color}-100 text-{group-color}-700
```

### 后续演进

| 阶段 | 增强 |
|------|------|
| MVP (现在) | 纯 CSS 辐射图 + 分组 + 详情卡片 |
| V2 | 接入 React-Flow，支持拖拽编辑组织架构 |
| V3 | 实时任务状态流动动画（running 任务在连线上流动） |
| V4 | Agent 间协作关系图（基于任务 delegation 数据） |
