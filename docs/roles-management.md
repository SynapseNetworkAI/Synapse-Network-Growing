---
id: roles-management-guide
title: 角色管理指南
status: published
created_at: 2026-04-09
author: CTO
---

# 角色管理指南 (Roles Management)

## 核心设计：目录即组织架构

Synapse-Network-Growing 的组织架构 **由 `roles/` 目录驱动**。

```
新建角色 → roles/<role_id>/prompts/persona.md
    ↓
Dashboard 点击"同步 Roles"（或调用 POST /api/agents/sync）
    ↓
自动读取 persona.md 的 YAML frontmatter
    ↓
Agent 出现在"组织架构"页面 + 可被分配任务
```

**不需要修改任何 Python 代码。**

---

## Persona Frontmatter Schema

每个角色必须在 `roles/<role_id>/prompts/persona.md` 中包含以下 YAML frontmatter：

```yaml
---
id: <role_id>_persona          # 唯一标识（惯例：role_id + _persona）
title: <角色名称> Persona       # 页面标题
role: <role_id>                 # 【必填】角色 ID，与目录名一致
display_name: <显示名称>        # 【必填】Dashboard 展示名
goal: <角色目标>                # 【必填】一句话描述职责
skills:                         # 【必填】技能列表，对应 .agents/skills/
  - skill-name-1
  - skill-name-2
status: published               # draft | review | ready | published
created_at: 2026-04-09
updated_at: 2026-04-09
author: CTO
---
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `role` | ✅ | 角色 ID，必须与 `roles/<role_id>/` 目录名一致 |
| `display_name` | ✅ | Dashboard 上的显示名称 |
| `goal` | ✅ | 一句话职责描述 |
| `skills` | ✅ | YAML 数组，对应 `.agents/skills/` 下的技能包 |
| `status` | ✅ | `draft`/`review`/`ready`/`published` |

---

## 如何新建一个角色

### Step 1: 创建目录结构

```bash
ROLE_ID=partnership_manager   # 改成你的角色 ID

mkdir -p roles/$ROLE_ID/prompts
mkdir -p roles/$ROLE_ID/outputs
```

### Step 2: 编写 persona.md

```bash
cat > roles/$ROLE_ID/prompts/persona.md << 'EOF'
---
id: partnership_manager_persona
title: Partnership Manager Persona
role: partnership_manager
display_name: Partnership Manager
goal: 负责 API Provider 合作伙伴拓展与关系维护
skills:
  - cold-email
  - sales-enablement
  - lead-magnets
status: published
created_at: 2026-04-09
updated_at: 2026-04-09
author: CTO
---

# Partnership Manager Agent Persona

You are an experienced B2B partnership manager specializing in developer ecosystem growth.

**Your Goal:** Build and maintain relationships with API Providers, drive provider onboarding, and grow the supply side of the Synapse Network marketplace.

**Your Principles:**
1. **Value-first outreach** — Lead with how Synapse makes them money, not what you need from them.
2. **Data-driven targeting** — Prioritize providers by API category demand and revenue potential.
3. **Relationship > Transaction** — Build long-term partnerships, not one-time listings.

**Your Workflow:**
1. Read `.agents/product-marketing-context.md` for positioning
2. Identify target provider segments
3. Craft personalized outreach sequences
4. Output to `roles/partnership_manager/outputs/`
5. All outputs must include YAML frontmatter with `status: draft`
EOF
```

### Step 3: 同步到 Dashboard

**方式 A: Dashboard UI**

点击"组织架构"页面的 **同步 Roles** 按钮。

**方式 B: API**

```bash
curl -X POST http://localhost:9600/api/agents/sync
```

### Step 4: 验证

```bash
curl http://localhost:9600/api/agents/partnership_manager | python -m json.tool
```

应返回新角色的完整信息。

### Step 5: （可选）更新 AGENTS.md

在 `AGENTS.md` 的"组织架构与角色边界"章节中添加该角色的描述，保持文档与文件系统一致。

---

## 现有角色一览

| role_id | 显示名 | 职责 |
|---------|--------|------|
| `dev_rel` | DevRel Engineer | 负责 DX 和技术布道 |
| `growth_lead` | Growth Lead | 负责 GTM 和增长策略 |
| `content_writer` | Content Writer | 负责极简主义文案写作 |
| `seo_strategist` | SEO Strategist | 负责关键词与转化率优化 |
| `cro_optimizer` | CRO Optimizer | 负责全链路转化率优化 |
| `launch_strategist` | Launch Strategist | 负责发布节奏与飞轮编排 |

---

## 文件结构规范

每个角色目录应遵循以下结构：

```text
roles/<role_id>/
├── prompts/
│   └── persona.md          # 【必须】角色定义 + YAML frontmatter
├── outputs/                 # Agent 产出物存放区
│   └── *.md                 # 带 YAML frontmatter 的 Markdown
└── contents/                # （可选）参考素材
```

---

## 关联关系总结

```
AGENTS.md                       → 人类可读的组织架构文档（协议层）
roles/*/prompts/persona.md      → Agent 可读的角色定义（执行层）
server/services/agent_loader.py → 自动扫描 persona.md（数据层）
Dashboard "组织架构"页面          → 可视化展示（展示层）
```

四层保持一致的方式：
1. **新建角色** → 先建 `roles/<id>/prompts/persona.md`（必须），再补 `AGENTS.md`（推荐）
2. **同步** → Dashboard 点"同步 Roles" 或 `POST /api/agents/sync`
3. **验证** → `python scripts/verify_frontmatter.py` 检查格式合规性
