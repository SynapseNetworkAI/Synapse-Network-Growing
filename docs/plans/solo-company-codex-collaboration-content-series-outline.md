---
id: solo-company-codex-collaboration-series-outline
title: Solo Company + Codex + Growing 内容系列大纲
role: growth_lead
status: draft
created_at: 2026-05-11
updated_at: 2026-05-11
author: codex
target_repo: Synapse-Network-Growing
---

# Solo Company + Codex + Growing 内容系列大纲

## 1. 这份大纲放在哪里最合适

建议放在：

`/Users/cliff/workspace/agent/Synapse-Network-Growing/docs/plans/solo-company-codex-collaboration-content-series-outline.md`

原因：

1. 这不是正式架构真相文档，而是一个面向内容生产和后续分发的策划包。
2. `docs/plans/` 在当前仓库里明确就是“新计划 / 新计划包的暂存区”。
3. 后面如果系列已经稳定并沉淀成产品能力说明，可以再把结果收敛到 `docs/design-docs/` 或 `docs/ops/`；如果只是阶段性内容策划，保留在 `docs/plans/` 最合适。

## 2. 系列定位

这个系列不是泛泛讲“AI 编程很厉害”，而是讲一条真实、可复制、可验证的路径：

**一个人如何把公司、研发、门禁、发布、上线、内容分发都放进自己的系统里，并让 Codex 成为执行引擎，而不是聊天机器人。**

这套系列的差异化，不在“我用了 AI”，而在：

1. 我把 AI 放进了带约束的系统里。
2. 我不是让 AI 直接替我发版、发帖、改生产，而是让它在 fail-closed rails 上工作。
3. 我做的不是单个 demo，而是从需求、执行、验证、发布到社交分发的一体化个人公司操作系统。

## 3. 目标受众

1. 想做一人公司的工程师 / 独立开发者。
2. 想把 Codex 真正接进研发流程，而不是只拿来写几个函数的人。
3. 想做“AI + 工程系统 + 自动化运营”的创始人。
4. 对 agent workflow、human gate、CI、部署系统、内容分发系统感兴趣的人。

## 4. 系列总主线

主线建议统一为：

**从“一个人 + 一个 AI 助手”到“一个人拥有自己的公司级操作系统”。**

可以拆成 10 篇，前 7 篇适合先发 X，后 3 篇适合做长文、官网、知乎、公众号、V2EX 和 Hacker News 衍生版本。

## 5. 系列结构

## 第 1 篇：我为什么要做一人公司的系统，而不是只做一个产品

### 核心问题

1. 一人公司最大的瓶颈不是写代码，而是上下文切换、流程断裂和质量失控。
2. 没有系统时，一个人会同时扮演 PM、工程师、QA、发布经理、运营。
3. 只靠记忆和手工流程，复杂度一上来就会崩。

### 要讲的内容

1. 为什么我没有把 Codex 当“写代码工具”，而是当“执行引擎”。
2. 为什么需要一个控制平面，而不是多个零散脚本。
3. 为什么 Synapse-Network-Growing 是公司运营系统，而不是普通后台。

### 适合的标题方向

1. 一人公司最大的问题，不是没人，是没有系统
2. 我没有先做产品，我先做了自己的公司操作系统

## 第 2 篇：我如何用 Codex 开发项目，而不是和 AI 聊天

### 核心问题

1. 大多数人把 Codex 用成“问答工具”。
2. 真正高价值的用法，是让它进入仓库、读取真实文档、遵守真实约束、直接改真实代码。

### 要讲的内容

1. 进入仓库前先读 `llms.txt`、`AGENTS.md`、架构约束文档。
2. Codex 不是凭空写代码，而是先读项目入口、设计文档、测试入口、发布约束。
3. 真正有效的协作方式：让 Codex 在真实 repo 里执行，而不是在抽象 prompt 里空想。
4. 多仓库分工：`Growing` 做控制平面，`Synapse-Network` 做主产品，`Provider` 做服务集成，`Sdk` 做开发者入口。

### 要点金句

1. 不是“给 AI 一个需求”，而是“把 AI 放进一套真实工程环境里”。
2. 不是“让 AI 帮我想”，而是“让 AI 在约束下替我推进”。

## 第 3 篇：我怎么和 Codex 协作，才不会把项目写崩

### 核心问题

1. AI 一旦没有 rails，就会变成高输出、低可靠性的风险源。
2. 一人公司最怕的不是写得慢，而是写得快、错得大、回滚难。

### 要讲的内容

1. 我把模型当不稳定部件，不把它当同事。
2. 让 agent 负责推理，让 deterministic runner 负责状态推进。
3. execute 不能自证正确，verification 必须独立。
4. 高风险动作必须 Human Gate：生产、资金、auth、部署、外部发布。
5. fail closed 比“自动修复一切”更重要。

### 可突出系统事实

1. `Growing` 当前核心链路是：
   `Operating Manifest -> RequirementCandidate -> Requirement -> Declarative Workflow Run -> Evidence -> Human Gate / Release / Done`
2. 社交发布同样受约束，Agent 可以写稿，但不能绕过人类直接代表官方账号发声。

## 第 4 篇：我给项目加了哪些硬约束，为什么这比“AI 很聪明”更重要

### 核心问题

1. 真正能让一人公司跑起来的，不是模型能力，而是约束设计。

### 要讲的内容

1. `llms.txt` 作为工作区路由入口。
2. `AGENTS.md` 作为 repo 级协作协议。
3. 架构约束：不造 God Agent，不让 Python `if/else` 偷偷接管复杂流程。
4. workflow 必须可观测：状态、artifact、run history、logs、evidence 都要有。
5. public social publishing 是 representational communication，必须人审。

### 重点表达

1. 我不是追求“全自动”。
2. 我追求的是“有边界的自动化”。

## 第 5 篇：一人公司也需要 CI、门禁和质量检测，不然 AI 只会放大事故

### 核心问题

1. 没有质量门禁，AI 只会把交付速度放大成事故速度。

### 要讲的内容

1. verification 独立于 execute。
2. acceptance matrix 是可执行契约，不是装饰文档。
3. `Push Quality Gates v2` 的思路：repo guardrails、代码质量、测试、diff coverage、dashboard tests/build、安全扫描、依赖审计、空白字符检查。
4. 长耗时 CI 不阻塞 workflow worker，而是进入 `awaiting_ci`，由 `ci_status_sweep` 异步收口。
5. 新代码文件、函数复杂度、重复、lint、typecheck、安全都要 fail closed。

### 适合的标题方向

1. 为什么我一个人做项目，反而比很多团队更依赖门禁
2. AI 时代最重要的不是生成代码，而是生成之后谁来拦它

## 第 6 篇：我如何通过自己研发的发布系统上线，而不是手工 SSH

### 核心问题

1. 一人公司最容易卡死在“开发完成”和“真正上线”之间。

### 要讲的内容

1. `Growing` 的 `/releases` 不是一个按钮，而是一条可追踪的发布治理链。
2. Release Task 记录发布意图，Deployment Record 记录物理部署事实。
3. staging 和 production 必须分开治理。
4. staging 可以基于 `main` 或 PR checks 通过的分支做显式 operator 发布。
5. production deploy / rollback 必须 Human Gate。
6. 成功上线要进入 Online Record，而不是只看 GitHub Actions 绿了没。
7. 你的系统差异化：不是 GitHub Action 本身，而是把 PR、部署、健康检查、回滚和上线账本连成了一个 operator-facing control plane。

### 标题方向

1. 我没有把部署交给运气，我给它做了一个控制平面
2. 真正的“上线”，不是 CI 通过，而是系统承认它已经在线

## 第 7 篇：我如何把产品更新变成内容，再通过 Growing 发布到 X

### 核心问题

1. 一人公司如果开发和分发断裂，增长就会永远落后于研发。

### 要讲的内容

1. `/publishing` 是 Social Ops Center，不只是发帖页面。
2. 内容来源不是拍脑袋，而是产品更新、release、completed requirements、趋势、watchlist、metrics。
3. X 的内容生成走专用 `SOCIAL_CONTENT_LLM_PROVIDER` / `SOCIAL_CONTENT_LLM_MODEL`。
4. 生成内容必须经过 brand refinement、risk gate、human review。
5. 系统支持内容资产、分发任务、分发账号、趋势、metrics，不只是 X。
6. X 需要显式 operator 点击确认；非 X 平台可以做人审后的手工 live/removed 记录与分发跟踪。

### 要强调的关键事实

1. Agent 能写草稿，不能擅自代表你发声。
2. 我做的不是“自动发帖器”，而是“内容控制平面”。

## 第 8 篇：我如何把一篇 X 帖子扩展成多平台分发系统

### 核心问题

1. 同一份核心观点，不应该每个平台重写一次。

### 要讲的内容

1. 先有 canonical content asset，再生成 platform-specific distribution tasks。
2. X、Hacker News、Reddit、V2EX、DEV、Hashnode 可以有不同包装，但来源是同一篇核心资产。
3. 每个平台的标题、正文、CTA、链接方式、讨论风格都要变，但观点主轴不变。
4. Distribution 任务不等于自动发；外部动作依然要保留人类确认。

### 平台拆法建议

1. X：观点密度最高，hook 最强。
2. LinkedIn：创始人/系统建设叙事。
3. 公众号/知乎：长文方法论。
4. V2EX / Hacker News / Reddit：偏工程事实、架构权衡、踩坑和证据。

## 第 9 篇：为什么我先做系统，再做规模

### 核心问题

1. 很多人想先靠人堆规模，再补系统。
2. 一人公司没有这个奢侈。

### 要讲的内容

1. 一个人最稀缺的是注意力，不是执行欲望。
2. 系统的作用，是让你把注意力从重复劳动切到高价值判断。
3. Human Gate 不是拖慢速度，而是把人的时间留给真正高风险决策。

## 第 10 篇：一人公司的终局，不是更会用 AI，而是拥有自己的操作系统

### 核心问题

1. 未来一人公司真正的护城河，不只是代码能力，而是组织能力被系统化。

### 要讲的内容

1. 你的系统把需求、执行、验证、发布、上线、分发都接进了一条链。
2. Codex 是引擎，但 rails、gate、evidence、release、publishing 才是壁垒。
3. 最终卖点不是“AI 替我工作”，而是“我把公司运行方式产品化了”。

## 6. 建议先发顺序

建议第一轮先发这 6 篇：

1. 第 1 篇：为什么先做系统，不先做产品
2. 第 2 篇：我如何用 Codex 开发，而不是和 AI 聊天
3. 第 3 篇：我如何和 Codex 协作，才不会把项目写崩
4. 第 5 篇：为什么一人公司更需要 CI、门禁和质量检测
5. 第 6 篇：我如何通过自己的发布系统上线
6. 第 7 篇：我如何通过 Growing 把产品更新发布到 X

原因：

1. 这 6 篇最能体现你的差异化。
2. 它们天然能形成从理念到工程到发布再到增长的连续叙事。
3. 它们既能发 X，也能扩成长文和其他平台版本。

## 7. 每篇统一模板

建议每篇都按同一个骨架写：

1. 反常识开头
2. 我遇到的真实问题
3. 我为什么不用常见做法
4. 我如何在系统里设计这件事
5. 一个关键约束 / 门禁 / 失败案例
6. 最终形成的能力
7. 一句可传播的结论

## 8. 平台改写策略

### X

1. 强 hook。
2. 1 个核心观点。
3. 1 条主线。
4. 少量术语，多用判断句。

### LinkedIn

1. 增加创业者视角和组织设计视角。
2. 用“我是怎么做的”叙事。

### 公众号 / 知乎

1. 展开系统细节。
2. 增加架构图、流程图、门禁设计、CI 事实。

### V2EX / Hacker News / Reddit

1. 少一些品牌话术。
2. 多一些工程事实、约束、权衡、踩坑、验证和证据。

## 9. 这个系列最值得打出去的几个关键词

1. 一人公司
2. Codex 协作
3. agent-first workflow
4. human gate
5. fail closed
6. verification 独立
7. 发布控制平面
8. 社交分发控制平面
9. Growing
10. 公司级操作系统

## 10. 下一步建议

下一步最合理的执行顺序是：

1. 先把第 1 篇到第 7 篇各自压成一版 `X` 主帖大纲。
2. 再为每篇生成：
   - 1 个 X 版本
   - 1 个长文版本
   - 1 个 V2EX / HN / Reddit 技术版
3. 最后把它们接到 `Growing` 的 `/publishing` 资产与分发任务里，形成可追踪的内容生产和发布队列。

## 11. 推荐的后续文档拆分

如果你准备长期做这个系列，建议基于这份总大纲继续拆 3 份子文档：

1. `solo-company-codex-collaboration-x-series.md`
   - 每篇 X 帖子的 hook、正文、结尾 CTA
2. `solo-company-codex-collaboration-longform-series.md`
   - 每篇长文结构、配图、案例、证据
3. `solo-company-codex-collaboration-distribution-plan.md`
   - 平台映射、发布时间、账号策略、手工发布步骤、metrics 观察口径
