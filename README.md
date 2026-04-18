# Synapse-Network-Growing

Synapse-Network-Growing 的目标，不只是做增长内容仓库，而是逐步演进成一个 **AI 时代的公司操作系统**:

1. 让任务先进入统一需求池，而不是散落在聊天、文档、会议和人为转述里。
2. 让 Agent 成为默认执行者，自动完成需求分析、实现、测试、修复、复盘和协作交付。
3. 让系统持续优化的不只是单个任务，还包括项目质量、交付速度、跨团队协作流程和组织运行方式。
4. 让人从“中间传话与重复执行”中退出，回到目标定义、边界设定、风险审批和异常决策。

这套方向对应 [AI 时代的公司架构设计](../cliff-mind/agnet/ai时代公司架构设计.md) 里的核心判断：

## Branch Delivery Note

- `ops/req-23-live-validate-branch-delivery-minimal-ch` — requirement #23 live validates a minimal branch delivery path; README is the only touched artifact in this repo for clarity and traceability.

- 组织要从“职能分工”升级成“能力编排 + 治理边界”。
- 流程要从给人看的 SOP，升级成“人和 Agent 都能执行的 machine-readable workflow”。
- 人应该主要站在流程两端：定义目标、设定边界、处理例外，而不是承担大量中间搬运。

## 🌟 项目定位

这个仓库是整个 Synapse 体系里的 **运营与编排中枢**，负责把“AI 时代公司架构”落成真实可运行的系统。

- **主产品**: `Synapse-Network`
  核心业务系统，负责 Gateway、结算、风控、运营后台与产品主链路。
- **服务提供者运行时**: `Synapse-Network-Provider`
  面向 API / Service Provider 的运行时与接入侧能力。
- **用户接入层**: `Synapse-Network-Sdk`
  面向开发者和 Agent 框架的 Python / TypeScript SDK。
- **记忆与约束层**: `Agents-Memory`
  提供长期记忆、文档规范、标准约束和项目上下文沉淀。
- **编排与优化层**: `Synapse-Network-Growing`
  负责需求池、Agent 组织、执行编排、跨项目协同、优化闭环与可视化控制面。

## 🧭 系统设计原则

后续设计与实现必须遵守 [系统设计原则](docs/design-docs/system-design-principles.md)。

当前最重要的硬约束是：

1. 把模型当不稳定部件，不当同事。
2. 错误路径按主路径设计，不能依赖无限重试。
3. verification 必须独立于 implementation。
4. 多代理的重点是隔离不确定性，不是堆 worker 数量。
5. runtime / subagent 必须有生命周期、cleanup、abort 传播与可追踪 transcript。
6. 复杂执行流的新唯一真相是 Declarative Workflow Factory：State Machine YAML + Blackboard + Atom Registry + Risk/Human Gate，不再为 fixed `workflow_steps` 主链做新兼容。

## 🏢 AI 时代公司架构映射

围绕 AI-native company 的五层模型，这个仓库当前承担的是下面几层能力：

1. **目标层**: 把任务、需求、角色和项目统一进一个可调度的控制面。
2. **流程层**: 把需求拆成 machine-readable 的 workflow step，而不是停留在口头协作。
3. **能力层**: 复用角色、技能、运行时、浏览器自动化、记忆系统，而不是每个项目各做一套。
4. **治理层**: 通过审批、状态机、日志、测试和异常分支控制高风险动作。
5. **评估层**: 为后续的自动优化预留任务结果、工件、变更快照、执行日志和项目维度的数据基础。

## ✅ 当前已经具备的能力

从现有实现和设计文档看，Synapse-Network-Growing 已经不只是“营销 Agent 仓库”，而是具备了多项目自动执行的第一代骨架：

1. **需求池 + 工作流编排**
   需求已经是顶层对象，不再只是单条 task；系统支持规划、执行、测试、同 session 自修复、revision 和关闭闭环。
2. **多 Agent 角色协作**
   业务角色来自 `roles/*`，执行时再映射到 workflow role 和 runtime agent，已经具备串行协作基础。
3. **正式项目中心**
   系统已经引入一等 `Project` 对象，用来统一管理 root path、GitHub repo、默认分支、部署策略和环境标签；Requirement 与 Release 都挂到 Project 上运行。
4. **多项目组织视图**
   `server/org-structure.yaml` 已经把 `Synapse-Network`、`Synapse-Network-Provider`、`Synapse-Network-Sdk`、`Agents-Memory`、`Spec2Flow` 纳入统一组织图。
5. **长任务与后台恢复**
   当前 runtime 已支持长任务执行、监控、恢复、日志持久化和状态同步。
6. **记忆回流**
   项目文档可进入 `Agents-Memory` wiki，失败任务进入错误记录，完成任务 / 需求进入 workflow records，为后续优化提供可复用经验。

## ⚠️ 为了实现 AI 时代公司架构，还缺的关键能力

如果目标是“任务全部交给 Agent 执行，并且能自主优化多个项目和协作流程”，当前设计方向是对的，但还没有完全闭环。接下来最关键的缺口有：

1. **项目级治理与授权边界**
   现在已经有正式 Project 主数据和 project policy，但还需要继续补齐更细粒度的目录授权、动作审批和跨项目资源边界。
2. **项目级目标与指标系统**
   现在更偏执行编排，缺少 outcome-based evaluation，例如质量分、转化指标、交付时长、缺陷率、回滚率、协作摩擦成本。
3. **自动优化引擎**
   系统能执行需求，但还缺“发现问题 → 生成优化需求 → 排序 → 自动验证收益”的持续优化回路。
4. **跨项目调度与资源仲裁**
   现在支持多项目目标，但还缺 portfolio scheduler，去决定哪个项目优先、哪些 Agent 资源分配给哪个项目、冲突时如何仲裁。
5. **标准化 SOP / Policy 包**
   现在有角色、提示词和技能，但每个项目的 machine-readable SOP、审批规则、Definition of Done 还不够完整。
6. **安全的交付闭环**
   还需要更完整的 worktree / branch / PR / review / rollout / rollback 自动化，才能安全地大规模改多个真实项目。

## 🧭 现在的设计是否支持自动化优化多个项目

**短答案：可以支持，但目前属于“方向已经正确，底座已经成型，离 fully autonomous multi-project optimizer 还差几层治理和评估能力”。**

更具体地说：

1. **支持的部分**
   现在已经有多项目组织图、正式 Project 中心、跨项目写代码、任务日志、变更快照、记忆沉淀和需求池工作流，这些都是必须的基础设施。
2. **还不够的部分**
   目前更像“多项目执行编排器”，还不是“多项目自我优化系统”；它能帮你做事，但还不够稳地判断“做什么最值得、做完是否真的变好、是否应该继续扩大自动化权限”。
3. **结论**
   用现在这套设计去驱动多个外部项目做自动化执行，已经是可行的；要升级成真正的 AI 公司操作系统，还需要补齐策略、评估、治理和交付安全这四个层面。

## 当前正式功能清单

当前系统已实现的正式能力清单维护在：

- `docs/design-docs/current-feature-inventory.md`

后续新增、删除或重构正式功能时，应与代码一起同步更新这份清单。

Workflow 详情页当前是新的正式可观测性视图：

1. 当前 `workflow_key`、`current_state`、`status`、`resolution`。
2. State timeline 与 transition events。
3. Blackboard 摘要、retry counters 与风险状态。
4. Atom invocations、artifacts、command evidence。
5. pending / decided human gates。
6. requirement / release / error fingerprint 的反向跳转。

Requirement 与 Workflow 当前正式约束：

1. requirement 创建必须挂到正式 `Project`，不再只靠裸路径推断。
2. requirement submit 后创建 declarative workflow run；新主链不再创建 `/api/executions` fixed-step run。
3. 复杂执行流唯一真相是 State Machine YAML + Blackboard + Atom Registry + Risk/Human Gate。
4. Agent atom 只产出结构化结果，不能直接改变 workflow state；state transition 由 deterministic runner 判定。
5. 所有 loop 必须有 retry budget；超过预算进入 `awaiting_operator` 或失败终态。
6. 资金、结算、合约、auth、生产部署、自修改系统、外部付费动作必须进入 human gate。
7. `/api/errors/intake` 仍进入 discovery pipeline，但 materialize 后挂到 declarative workflow run，而不是旧 execution run。
8. 前端主入口是 `/workflows` 与 `/workflows/:id`；旧 `/executions` API 和页面已从新业务主链移除。

## Browser Automation

This repository now includes the upstream `vercel-labs/agent-browser` and `dogfood` skills for project-scoped browser automation and systematic QA.

Reusable entry points:

1. Skill source: `.agents/skills/agent-browser/`
2. Dogfood source: `.agents/skills/dogfood/`
3. Skill lock: `skills-lock.json`
4. Project defaults: `agent-browser.json`

First-time setup on a machine:

```bash
agent-browser install
```

Reusable workflow:

```bash
agent-browser open http://127.0.0.1:9700/requirements
agent-browser snapshot -i
agent-browser screenshot
```

Runtime profile, downloads, and screenshots are isolated under `.agent-browser/` and ignored from git by default.

## Testing

Frontend and backend validation commands:

```bash
/Users/cliff/workspace/agent/.venv/bin/python -m pytest -q
cd dashboard && npm test
cd dashboard && npm run build
cd dashboard && npm run test:e2e
```

`npm run test:e2e` now boots an isolated real FastAPI backend plus Vite frontend, keeps the existing mocked smoke coverage, and adds a real requirement-workflow end-to-end verification with screenshot evidence under `dashboard/test-results/`.

Systematic inspection entry point:

```bash
# Read .agents/skills/dogfood/SKILL.md first, then inspect the local dashboard
agent-browser open http://127.0.0.1:9700/requirements
```

## Runtime Config

If you are using OpenAI instead of Copilot, keep the runtime configuration aligned around these four keys:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_EXECUTION_MODE=session
ORCHESTRATION_BACKEND=openai_responses
```

You also need a valid `OPENAI_API_KEY`. If `ORCHESTRATION_BACKEND` is left at `copilot_sdk`, the backend will keep dispatching Copilot workers even if the provider text says `openai`.

If you want the system to use your locally authenticated Codex CLI instead of API billing, use the `codex_cli` backend. Do not paste ChatGPT session tokens into `.env`; keep the login inside the Codex CLI itself and point the backend at that local runtime:

```env
ORCHESTRATION_BACKEND=codex_cli
LLM_PROVIDER=codex
LLM_MODEL=gpt-5-codex
CODEX_CLI_MODEL=gpt-5-codex
CODEX_CLI_FULL_AUTO=true
```

Notes:

1. Execution tasks use the local `codex exec` runtime.
2. Plan agent calls can be selected independently with `PLANNER_BACKEND`; leave it empty to infer from `ORCHESTRATION_BACKEND`.
3. `CODEX_CLI_MODEL` is optional; if omitted, the system falls back to `LLM_MODEL`.
4. `CODEX_CLI_FULL_AUTO=false` switches to explicit sandbox mode using `CODEX_CLI_SANDBOX`.
5. This path uses your existing Codex / ChatGPT login state, not `OPENAI_API_KEY`.

Recommended planner adapter config:

```env
PLANNER_BACKEND=codex_sdk
PLANNER_MODEL=gpt-5.4
PLANNER_TIMEOUT=300
```

Supported planner adapters are `openai`, `claude`, `copilot`, `codex_cli`, and `codex_sdk`. See [Planner Adapter Architecture](docs/design-docs/planner-adapter-architecture.md).

Recommended Codex Python SDK direction:

For long-running OPS automation, prefer a future `codex_sdk` backend over direct `codex exec` subprocess management. The Python SDK gives the backend thread/resume/stream/interrupt/structured-output APIs while still requiring `codex app-server` / `codex-cli-bin`, so `codex_cli` should remain the production fallback during rollout. See [Codex Python SDK Runtime Architecture](docs/design-docs/codex-python-sdk-runtime-architecture.md).

Runtime auth guard alerting:

```env
OPS_RUNTIME_AUTH_ALERTS_ENABLED=true
OPS_LARK_BOT_WEBHOOK_URL=...
OPS_LARK_BOT_KEYWORD=告警
```

When Copilot SDK returns an explicit enterprise-policy / authorization error, the system now sends a Lark alert and pauses the task + parent requirement instead of continuing into a misleading failure loop.

## Python Runtime Standard

`Synapse-Network-Growing` backend requires Python 3.14+ locally and in production. The shared local virtualenv is expected at:

```bash
/Users/cliff/workspace/agent/.venv
```

Recommended local setup:

```bash
/opt/homebrew/bin/python3.14 -m venv /Users/cliff/workspace/agent/.venv
/Users/cliff/workspace/agent/.venv/bin/python -m pip install -U pip setuptools wheel
/Users/cliff/workspace/agent/.venv/bin/pip install -r requirements.txt
```

The local and prod startup scripts call `scripts/python_runtime_guard.sh` before importing the app. This prevents the Pydantic v2 / PEP 604 typing path from accidentally running under macOS Python 3.9.

## Python Logging Standard

`Synapse-Network-Growing` 当前把 Python 日志视为正式运行时契约，而不是辅助文本输出。

固定标准：

1. Python 服务默认使用 `structlog + logging`
2. 主输出是 `stdout` JSON
3. 本地文件只做 `JSONL` 备份，并按天切分
4. 默认优先绑定链路字段：
   - `request_id`
   - `task_id`
   - `requirement_id`
   - `execution_id`
   - `release_id`
   - `fingerprint_key`
5. 每条日志至少应包含：
   - `ts`
   - `level`
   - `event`
   - `service`
   - `env`
   - `logger`
   - `message`

安装新增 Python 依赖时，先执行：

```bash
/Users/cliff/workspace/agent/.venv/bin/pip install -r requirements.txt
```

开发者约束：

1. 新增 Python 服务日志时，不继续扩展自由文本日志为主输出。
2. traceback 可以保留，但不要把 token、secret、authorization header、webhook url 等敏感信息写入日志。
3. 当前阶段先在各服务内按同一规范实现，不把日志能力塞进 SDK 文档或假设已有共享 logging 包。
4. requirement、execution、release、error loop 的自动化治理、告警和通知，应优先依赖结构化字段而不是非结构化 message 解析。

## Key Docs

1. `docs/phase2-plan.md` - Phase 2 dashboard implementation baseline
2. `docs/ops-console-usage.md` - 控制台页面用途、后端接口映射与 `/requirements` 空白排查
3. `docs/plans/ai-company-ops-roadmap/README.md` - AI 时代公司操作系统路线图与下一阶段需求池
4. `docs/design-docs/company-ops-latest-architecture.md` - 最新模块交互、signal 来源、日志与数据库策略
5. `docs/design-docs/system-design-principles.md` - 当前正式硬约束，包括三面分治与最小执行流
6. `docs/design-docs/planner-adapter-architecture.md` - Plan Agent provider adapter、配置优先级与扩展边界
7. `docs/design-docs/codex-python-sdk-runtime-architecture.md` - Codex Python SDK runtime 与 CLI fallback 方案
8. `docs/design-docs/plan-agent-project-scoped-session-reuse.md` - Plan Agent 按项目复用 Codex session 的 scope 与 registry
9. `docs/design-docs/declarative-agent-workflow-factory.md` - 声明式 Agent 工作流工厂、Blackboard、State Machine 与场景推演
10. `docs/design-docs/workflow-factory-frontend-control-plane.md` - Workflow Factory 前端控制台、模块划分、历史数据清理与 operator UX 方案
11. `docs/design-docs/legacy-execution-retirement-inventory.md` - 旧 execution 主链退役清单、已删除入口和剩余数据库边界
12. `docs/design-docs/current-feature-inventory.md` - 当前正式功能清单
13. `docs/plans/coo-operating-workflows/README.md` - 把系统升级成 AI 公司 COO operating system 的自动工作流方案与实施计划
14. `docs/plans/bug-intake-and-auto-remediation/README.md` - 把系统 bug 接入需求池、自动修复与验证闭环的方案与实施计划

Synapse-Network-Growing/
├── README.md                 # 项目定位、系统目标、能力边界与演进方向
├── AGENTS.md                 # 【必须】定义各路 AI Agent 的角色系统边界、权限与交互规则
├── roles/                    # 【核心】按公司能力与角色切分，隔离 Agent 上下文
│   ├── growth_lead/          # 增长负责人的工作台（看重分发、转化、ROI、叙事）
│   │   ├── prompts/          # 专属于增长 Agent 的 Persona 设定
│   │   ├── go_to_market/     # ★ 需求 4: PH / HN / X 的发布文案 (3个版本)
│   │   └── landing_pages/    # ★ 需求 5: Provider Onboarding 活动页文案 (抽成/结算逻辑)
│   └── dev_rel/              # 技术布道师的工作台（看重 DX、代码优雅度、架构、MCP 接入）
│       ├── prompts/          # 专属于布道师 Agent 的 Persona 设定
│       └── contents/         # ★ 需求 3: 技术博客《How to let AI agents discover and pay...》
├── campaigns/                # 【战役执行层】存放跨角色协同的具体战役
│   └── 30_day_blitzkrieg/    # 30天冲刺战役的项目管理 (Todo, 协同结果存放处)
└── demos/                    # 【技术弹药库】开发者第一触点，由 DevRel 主导
    └── synapse-agent-demo/   # 独立的示例代码库 (可直接作为 Submodule 或开源 Repo)
        ├── README.md         # ★ 需求 2: GitHub Repo README (安装/配置/预期输出/截图)
        └── scripts/          # ★ 需求 1: 1 分钟 Hero Demo 脚本 (包含台词、终端输出、镜头切换)
