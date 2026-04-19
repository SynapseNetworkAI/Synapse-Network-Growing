import { Link } from 'react-router-dom'
import { ActionButton, AgentReasoningCard, CockpitPanel, MetricTile } from '../components/controlPlane'

export default function IntakePage() {
  return (
    <div className="space-y-6">
      <CockpitPanel
        eyebrow="Intake"
        title="需求发现入口"
        description="Intake 是 Watcher、Forum、Error、Planner Signal 的汇流区。它不直接修复问题，只负责把信号变成候选或正式需求。"
        actions={<ActionButton href="/errors">查看 Error Signals</ActionButton>}
      >
        <div className="grid gap-4 md:grid-cols-4">
          <MetricTile label="Error Signals" value="Active" detail="错误指纹、去重、需求 gate" tone="danger" />
          <MetricTile label="Planner Signals" value="Planning" detail="Goal -> Candidate" tone="info" />
          <MetricTile label="Forum Feedback" value="Planned" detail="用户帖子 -> 回复建议 / bug candidate" tone="warning" />
          <MetricTile label="Watcher Events" value="System" detail="定时扫描与 drift 检测" tone="success" />
        </div>
      </CockpitPanel>

      <div className="grid gap-4 lg:grid-cols-2">
        <AgentReasoningCard
          title="Error Signals"
          tone="danger"
          summary="运行时错误、日志扫描和 intake fingerprint gate 汇聚到这里。重复错误不会不断污染需求池。"
          metadata={<Link className="text-cyan-200 hover:text-cyan-100" to="/errors">Open /errors</Link>}
        />
        <AgentReasoningCard
          title="Planner Candidates"
          tone="info"
          summary="自上而下的需求发现仍在 Planning Console 中完成。Planner 只生成 RequirementCandidate，不直接污染正式 Requirement。"
          metadata={<Link className="text-cyan-200 hover:text-cyan-100" to="/planning">Open /planning</Link>}
        />
        <AgentReasoningCard
          title="Forum Feedback"
          tone="warning"
          summary="用户帖子应该由 Synapse-Network/gateway-admin 保存回复状态，Growing 只生成 triage、candidate 和 reply draft。"
          metadata="v1: product design documented, admin-front integration remains external."
        />
        <AgentReasoningCard
          title="Watcher Events"
          tone="info"
          summary="后台定时任务和 watcher drift 不应隐藏在日志中。可通过 System Ops / Scheduled Jobs 观察。"
          metadata={<Link className="text-cyan-200 hover:text-cyan-100" to="/schedules">Open /schedules</Link>}
        />
      </div>
    </div>
  )
}
