import { RecurringWorkflow } from '../api'

export type LaneKey = 'attention' | 'strategy' | 'execution' | 'intake' | 'health' | 'uncategorized'

export type Presentation = {
  lane: Exclude<LaneKey, 'attention'>
  label: string
  input: string
  action: string
  outputs: string[]
}

export const laneDefinitions: Array<{ key: LaneKey; title: string; description: string }> = [
  { key: 'attention', title: 'Attention Required', description: '失败、到期、锁冲突或最近运行异常会自动置顶，不被业务分组淹没。' },
  { key: 'strategy', title: 'Strategy & Planning', description: '公司目标、Planner Sweep、周度复盘这些“大脑层”自动化。' },
  { key: 'execution', title: 'Execution & Dispatch', description: '推进需求队列、审批巡检、收尾压缩这些 COO duty cycle。' },
  { key: 'intake', title: 'Intake & Support', description: '外部信号、论坛反馈、早间输入这些前台触角。' },
  { key: 'health', title: 'System Health & Reliability', description: '日志转 bug、重复需求清理和系统免疫。' },
  { key: 'uncategorized', title: 'New / Uncategorized Initiates', description: '新增任务还没有 presentation metadata，仍可运行和追踪，但需要补齐说明。' },
]

const presentationMap: Record<string, Presentation> = {
  goal_planner_sweep: {
    lane: 'strategy',
    label: '生成候选需求',
    input: 'Active goals + Operating Manifest',
    action: 'Planner Agent 拆解目标',
    outputs: ['Requirement Candidates', 'Fail-Closed Intercepts'],
  },
  weekly_operating_review: {
    lane: 'strategy',
    label: '生成周报与复盘',
    input: '上周运行、需求、事故、门禁',
    action: '刷新 company review',
    outputs: ['Operating Review', 'Next-cycle bundle'],
  },
  dispatcher_loop: {
    lane: 'execution',
    label: '推进状态机',
    input: 'Ready / blocked / paused requirements',
    action: '扫描队列并提出推进动作',
    outputs: ['Follow-up actions', 'Stuck work signals'],
  },
  approval_sweep: {
    lane: 'execution',
    label: '审批巡检',
    input: 'Pending gates + stale approvals',
    action: '刷新 human gate backlog',
    outputs: ['Approval reminders', 'Gate health'],
  },
  closeout_and_compact_sweep: {
    lane: 'execution',
    label: '上下文归档',
    input: 'Done / paused / blocked requirements',
    action: '收尾检查与上下文压缩',
    outputs: ['Acceptance candidates', 'Compaction snapshots'],
  },
  morning_intake_sweep: {
    lane: 'intake',
    label: '生成待办',
    input: 'Signals + review bundle + bug intake',
    action: '刷新输入源并创建高置信事项',
    outputs: ['Requirements', 'Operator attention items'],
  },
  forum_feedback_sweep: {
    lane: 'intake',
    label: '客服回复 / 提 Bug',
    input: 'Forum unreplied response tasks',
    action: '分类、提取、生成回复建议',
    outputs: ['Reply drafts', 'Bug candidates'],
  },
  bug_log_sweep: {
    lane: 'health',
    label: '日志转 Bug 工单',
    input: 'Runtime logs + workflow incidents',
    action: '归一化错误并尝试 materialize',
    outputs: ['Bug backlog', 'Materialized requirements'],
  },
  requirement_family_cleanup_sweep: {
    lane: 'health',
    label: '去重归档',
    input: 'Draft / ready / paused requirement families',
    action: '清理重复实验需求',
    outputs: ['Archived requirements', 'Merge recommendations'],
  },
  weekly_repo_hygiene_review: {
    lane: 'health',
    label: '周日仓库清理',
    input: 'Repo quality gates + docs metadata + Ops stale state',
    action: '生成清理计划并开低风险 PR',
    outputs: ['Cleanup PR', 'No-op evidence', 'Operator review items'],
  },
  ci_status_sweep: {
    lane: 'health',
    label: 'Final Regression 收口',
    input: 'awaiting_ci workflow runs',
    action: '读取 marker 文件并推进状态机',
    outputs: ['CI evidence', 'PR handoff', 'Needs Human reports'],
  },
}

function _record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

export function presentationFor(workflow: RecurringWorkflow): Presentation {
  const input = Object.keys(_record(workflow.input_query)).slice(0, 3).join(', ') || 'custom input query'
  const action = String(_record(workflow.output_action).kind || workflow.description || 'custom recurring action')
  const output = String(_record(workflow.validation_signal).success_metric || 'custom output')
  return presentationMap[workflow.workflow_key] || {
    lane: 'uncategorized',
    label: 'Missing Presentation Metadata',
    input,
    action,
    outputs: [output],
  }
}

export function hasPresentation(workflowKey: string): boolean {
  return Boolean(presentationMap[workflowKey])
}
