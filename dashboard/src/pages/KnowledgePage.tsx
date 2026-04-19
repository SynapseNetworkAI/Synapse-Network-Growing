import { Link } from 'react-router-dom'
import { AgentReasoningCard, CockpitPanel, EmptyCockpitState, MetricTile } from '../components/controlPlane'

export default function KnowledgePage() {
  return (
    <div className="space-y-6">
      <CockpitPanel
        eyebrow="Knowledge"
        title="资产与 SOP"
        description="Knowledge 是 Agent-First 系统的长期记忆层。v1 先把概念入口建立起来，后续接 workflow artifacts、SOP Ledger 和 executable checklist。"
      >
        <div className="grid gap-4 md:grid-cols-3">
          <MetricTile label="Artifacts" value="Workflow" detail="workflow_artifacts 是当前证据真相" tone="info" />
          <MetricTile label="SOP Ledger" value="Planned" detail="修复经验沉淀为 checklist / lint rule" tone="warning" />
          <MetricTile label="Debug Payload" value="Hidden" detail="raw JSON 不进入主操作面" tone="muted" />
        </div>
      </CockpitPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <AgentReasoningCard
          title="Artifacts live with workflow runs"
          summary="当前产出物、Agent raw output、command logs、diff summary 都从 Workflow Detail 的 Evidence / Debug 中查看。Knowledge 页面后续会做跨 workflow 的索引。"
          metadata={<Link className="text-cyan-200 hover:text-cyan-100" to="/workflows">Open Workflow Operations Center</Link>}
        />
        <AgentReasoningCard
          title="SOP must be executable"
          tone="warning"
          summary="SOP 不应该只是心得体会。它应沉淀为 checklist、schema rule、verification command 或 lint rule，让下一轮 Agent 能真实复用。"
        />
      </div>

      <EmptyCockpitState
        title="Knowledge index is not wired yet"
        description="这个页面是新控制平面的占位入口。实施 SOP Ledger 时，必须从 workflow_artifacts 和成功修复结果提炼可执行规则。"
      />
    </div>
  )
}
