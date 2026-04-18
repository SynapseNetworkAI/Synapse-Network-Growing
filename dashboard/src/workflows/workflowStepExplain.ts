import {
  DeclarativeAtomInvocation,
  DeclarativeWorkflowArtifact,
  DeclarativeWorkflowDefinition,
  DeclarativeWorkflowDefinitionState,
  DeclarativeWorkflowEvent,
  DeclarativeWorkflowRunDetail,
} from '../api'

export type StepContract = {
  stateKey: string
  purpose: string
  actorLabel: string
  reads: string[]
  writes: string[]
  successSignals: string[]
  failureSignals: string[]
  evidenceHints: string[]
}

export type StepViewModel = {
  stateKey: string
  atomKey: string | null
  atomType: string
  status: string
  purpose: string
  actorLabel: string
  reads: string[]
  writes: string[]
  successSignals: string[]
  failureSignals: string[]
  evidenceHints: string[]
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
  matchedTransition: string | null
  nextState: string | null
  evidenceArtifacts: DeclarativeWorkflowArtifact[]
  invocation: DeclarativeAtomInvocation | null
  definitionState: DeclarativeWorkflowDefinitionState | null
}

export type CorrectnessItem = {
  key: string
  label: string
  passed: boolean
  detail: string
}

export type NextAction = {
  label: string
  tone: 'ready' | 'blocked' | 'running' | 'muted'
  detail: string
  href?: string
  tab?: 'overview' | 'steps' | 'evidence' | 'gates' | 'debug'
}

const GATEWAY_RELIABILITY_STEPS: Record<string, StepContract> = {
  detect_ops_failure: {
    stateKey: 'detect_ops_failure',
    purpose: '判断是否存在 gateway drift 或错误信号，避免没有真实信号时启动修复链路。',
    actorLabel: 'Deterministic Atom',
    reads: ['trigger'],
    writes: ['gateway_drift_detected', 'no_gateway_drift'],
    successSignals: ['gateway_drift_detected == true -> collect_logs', 'no_gateway_drift == true -> done'],
    failureSignals: ['signal missing or invalid -> done / awaiting_operator'],
    evidenceHints: ['transition event', 'trigger payload'],
  },
  collect_logs: {
    stateKey: 'collect_logs',
    purpose: '收集诊断所需日志和上下文，为 Agent 判断错误原因准备证据。',
    actorLabel: 'Deterministic Atom',
    reads: ['trigger'],
    writes: ['logs_collected', 'logs_missing', 'evidence'],
    successSignals: ['logs_collected == true -> diagnose'],
    failureSignals: ['logs_missing == true -> awaiting_operator'],
    evidenceHints: ['log artifact', 'evidence payload'],
  },
  diagnose: {
    stateKey: 'diagnose',
    purpose: 'Agent 解释错误原因，并决定是否需要进入 patch。',
    actorLabel: 'Agent Atom',
    reads: ['trigger', 'evidence'],
    writes: ['diagnosis'],
    successSignals: ['diagnosis.action == "patch" -> patch'],
    failureSignals: ['diagnosis.action == "needs_operator" -> awaiting_operator'],
    evidenceHints: ['workflow_agent_raw_output'],
  },
  patch: {
    stateKey: 'patch',
    purpose: 'Agent 生成修复方案或实际补丁，使代码/配置朝验收目标推进。',
    actorLabel: 'Agent Atom',
    reads: ['diagnosis', 'verification'],
    writes: ['patch_result'],
    successSignals: ['patch_result.changed_files_count > 0 -> verify'],
    failureSignals: ['no changed files or retry budget exhausted -> awaiting_operator'],
    evidenceHints: ['workflow_agent_raw_output', 'changed files summary'],
  },
  verify: {
    stateKey: 'verify',
    purpose: '验证修复是否通过必要检查；失败时允许回到 patch 自修复。',
    actorLabel: 'Deterministic Atom',
    reads: ['patch_result'],
    writes: ['verification'],
    successSignals: ['verification.status == "passed" -> risk_gate'],
    failureSignals: ['verification.status == "failed" -> patch / awaiting_operator'],
    evidenceHints: ['verification payload', 'command evidence'],
  },
  risk_gate: {
    stateKey: 'risk_gate',
    purpose: '判断当前风险和证据是否足够自动流转，避免高风险动作绕过人工门禁。',
    actorLabel: 'Gate Atom',
    reads: ['verification', 'risk_flags'],
    writes: ['gate'],
    successSignals: ['gate.decision == "auto_flow" -> open_pr'],
    failureSignals: ['gate.decision == "human_required" -> awaiting_operator'],
    evidenceHints: ['risk flags', 'gate payload'],
  },
  open_pr: {
    stateKey: 'open_pr',
    purpose: '提交、推送分支并创建 GitHub draft PR，把修复交付到可审阅状态。',
    actorLabel: 'Delivery Atom',
    reads: ['patch_result', 'verification', 'gate'],
    writes: ['pr'],
    successSignals: ['pr.created == true -> observing'],
    failureSignals: ['pr.failed == true -> awaiting_operator'],
    evidenceHints: ['workflow_vcs_delivery', 'workflow_review_pr_sync'],
  },
  observing: {
    stateKey: 'observing',
    purpose: '观察业务指标是否恢复，区分“测试通过”和“线上状态恢复”。',
    actorLabel: 'Deterministic Atom',
    reads: ['pr'],
    writes: ['observation'],
    successSignals: ['observation.restored == true -> done'],
    failureSignals: ['observation.not_restored == true -> patch / awaiting_operator'],
    evidenceHints: ['observation payload', 'monitoring signal'],
  },
  awaiting_operator: {
    stateKey: 'awaiting_operator',
    purpose: '自动化不能安全继续，等待 operator 审查、批准、拒绝或继续重试。',
    actorLabel: 'Human Gate',
    reads: ['pr', 'verification', 'risk_flags', 'human_gate_decisions'],
    writes: ['human_gate_decisions'],
    successSignals: ['operator approve / reject / continue_retry'],
    failureSignals: ['pending gate remains unresolved'],
    evidenceHints: ['human gate request'],
  },
  done: {
    stateKey: 'done',
    purpose: '工作流完成，后续只需要追踪 PR / release 或归档证据。',
    actorLabel: 'Terminal State',
    reads: ['verification', 'gate', 'pr', 'observation'],
    writes: [],
    successSignals: ['resolution == "completed"'],
    failureSignals: [],
    evidenceHints: ['final blackboard'],
  },
}

const AGENT_SELF_REPAIR_STEPS: Record<string, StepContract> = {
  ...GATEWAY_RELIABILITY_STEPS,
  detect_ops_failure: {
    stateKey: 'detect_ops_failure',
    purpose: '判断 Agent Ops 自身是否真的故障，避免系统在无故障时自我修改。',
    actorLabel: 'Deterministic Atom',
    reads: ['trigger'],
    writes: ['ops_failure_detected', 'no_ops_failure'],
    successSignals: ['ops_failure_detected == true -> collect_logs'],
    failureSignals: ['no_ops_failure == true -> done'],
    evidenceHints: ['ops runtime signal'],
  },
  collect_logs: {
    stateKey: 'collect_logs',
    purpose: '读取 Ops runtime 日志，让 Agent 基于真实 traceback 诊断自身问题。',
    actorLabel: 'Deterministic Atom',
    reads: ['trigger'],
    writes: ['logs_collected', 'logs_missing', 'evidence'],
    successSignals: ['logs_collected == true -> diagnose'],
    failureSignals: ['logs_missing == true -> awaiting_operator'],
    evidenceHints: ['server/logs/ops-dashboard.jsonl'],
  },
  diagnose: {
    stateKey: 'diagnose',
    purpose: 'Agent 定位自身故障模块，并判断是否需要 patch。',
    actorLabel: 'Agent Atom',
    reads: ['evidence', 'trigger'],
    writes: ['diagnosis'],
    successSignals: ['diagnosis.action == "patch" -> patch'],
    failureSignals: ['needs_operator -> awaiting_operator'],
    evidenceHints: ['workflow_agent_raw_output'],
  },
  open_pr: {
    stateKey: 'open_pr',
    purpose: '只创建自修复 PR，不自动部署自己，防止系统自毁。',
    actorLabel: 'Delivery Atom',
    reads: ['patch_result', 'verification'],
    writes: ['pr'],
    successSignals: ['pr.created == true -> awaiting_operator'],
    failureSignals: ['pr.failed == true -> awaiting_operator'],
    evidenceHints: ['workflow_vcs_delivery', 'workflow_review_pr_sync'],
  },
  awaiting_operator: {
    stateKey: 'awaiting_operator',
    purpose: '自修改代码必须等待人工审查，operator 决定 merge、reject 或继续 retry。',
    actorLabel: 'Human Gate',
    reads: ['pr', 'risk_flags', 'verification'],
    writes: ['human_gate_decisions'],
    successSignals: ['operator decision recorded'],
    failureSignals: ['pending human gate'],
    evidenceHints: ['human gate request', 'PR URL'],
  },
}

const CONTRACTS: Record<string, Record<string, StepContract>> = {
  gateway_reliability_repair: GATEWAY_RELIABILITY_STEPS,
  agent_self_repair: AGENT_SELF_REPAIR_STEPS,
}

function fallbackContract(state: DeclarativeWorkflowDefinitionState | null, stateKey: string): StepContract {
  const atomType = state?.atom_type || 'unknown'
  return {
    stateKey,
    purpose: state?.terminal ? '终态：工作流在这里收口。' : '执行该状态绑定的 atom，并根据 transition 条件进入下一状态。',
    actorLabel: state?.terminal ? 'Terminal State' : `${atomType} atom`,
    reads: [],
    writes: state?.output_key ? [state.output_key] : [],
    successSignals: state?.transitions.map((item) => `${item.condition} -> ${item.goto}`) || [],
    failureSignals: [],
    evidenceHints: ['state event', 'atom invocation'],
  }
}

function valueAtPath(source: Record<string, unknown>, path: string): unknown {
  return path.split('.').filter(Boolean).reduce<unknown>((current, segment) => {
    if (current && typeof current === 'object' && segment in current) {
      return (current as Record<string, unknown>)[segment]
    }
    return undefined
  }, source)
}

function pickPaths(source: Record<string, unknown>, paths: string[]) {
  return paths.reduce<Record<string, unknown>>((result, path) => {
    result[path] = valueAtPath(source, path)
    return result
  }, {})
}

function eventForState(events: DeclarativeWorkflowEvent[], stateKey: string) {
  return events.find((event) => event.from_state === stateKey) || null
}

function artifactsForStep(
  artifacts: DeclarativeWorkflowArtifact[],
  stateKey: string,
  atomKey: string | null,
  invocation: DeclarativeAtomInvocation | null,
) {
  const ids = new Set(invocation?.artifact_ids || [])
  return artifacts.filter((artifact) => {
    if (ids.has(artifact.id)) return true
    if (artifact.state_key === stateKey) return true
    if (atomKey && artifact.atom_key === atomKey) return true
    return false
  })
}

function statusForStep(
  detail: DeclarativeWorkflowRunDetail,
  state: DeclarativeWorkflowDefinitionState | null,
  stateKey: string,
  invocation: DeclarativeAtomInvocation | null,
  transition: DeclarativeWorkflowEvent | null,
) {
  if (invocation?.status) return invocation.status
  if (detail.current_state === stateKey) return detail.status
  if (state?.terminal && detail.current_state === stateKey) return detail.status
  if (transition) return 'completed'
  return 'not_started'
}

export function buildStepViewModels(
  detail: DeclarativeWorkflowRunDetail,
  definition: DeclarativeWorkflowDefinition | null,
): StepViewModel[] {
  const states = definition?.states?.length
    ? definition.states
    : Array.from(
      new Set([
        ...detail.events.flatMap((event) => [event.from_state || '', event.to_state]),
        ...detail.atom_invocations.map((item) => item.state_key),
        detail.current_state,
      ].filter(Boolean)),
    ).map((key) => ({
      key,
      atom_key: null,
      atom_type: 'unknown',
      terminal: false,
      resolution: null,
      output_key: null,
      risk_level: null,
      transitions: [],
    }))

  const dictionary = CONTRACTS[detail.workflow_key] || {}
  return states.map((state) => {
    const contract = dictionary[state.key] || fallbackContract(state, state.key)
    const invocation = detail.atom_invocations.find((item) => item.state_key === state.key) || null
    const transition = eventForState(detail.events, state.key)
    const atomKey = state.atom_key || invocation?.atom_key || null
    const evidenceArtifacts = artifactsForStep(detail.artifacts, state.key, atomKey, invocation)
    return {
      stateKey: state.key,
      atomKey,
      atomType: state.atom_type || invocation?.atom_type || 'unknown',
      status: statusForStep(detail, state, state.key, invocation, transition),
      purpose: contract.purpose,
      actorLabel: contract.actorLabel,
      reads: contract.reads,
      writes: contract.writes,
      successSignals: contract.successSignals,
      failureSignals: contract.failureSignals,
      evidenceHints: contract.evidenceHints,
      inputs: pickPaths(detail.blackboard, contract.reads),
      outputs: pickPaths(detail.blackboard, contract.writes),
      matchedTransition: transition?.condition || null,
      nextState: transition?.to_state || null,
      evidenceArtifacts,
      invocation,
      definitionState: state,
    }
  })
}

export function artifactDisplayTitle(artifact: DeclarativeWorkflowArtifact) {
  const payload = artifact.payload || {}
  if (artifact.artifact_type === 'workflow_transition_event') {
    const from = String(payload.from_state || artifact.state_key || 'start')
    const to = String(payload.to_state || '')
    return `Transition: ${from} -> ${to || 'unknown'}`
  }
  if (artifact.artifact_type === 'workflow_agent_raw_output') {
    return `Agent Output: ${artifact.state_key || artifact.atom_key || artifact.id}`
  }
  if (artifact.artifact_type === 'workflow_vcs_delivery') {
    return 'Git Delivery: commit and push branch'
  }
  if (artifact.artifact_type === 'workflow_review_pr_sync') {
    return 'GitHub PR: draft PR synced'
  }
  return `${artifact.artifact_type} #${artifact.id}`
}

export function buildCorrectnessItems(detail: DeclarativeWorkflowRunDetail): CorrectnessItem[] {
  const blackboard = detail.blackboard
  const verification = (blackboard.verification || {}) as Record<string, unknown>
  const gate = (blackboard.gate || {}) as Record<string, unknown>
  const pr = (blackboard.pr || {}) as Record<string, unknown>
  const observation = (blackboard.observation || {}) as Record<string, unknown>
  const failedInvocation = detail.atom_invocations.find((item) => item.status === 'failed')
  const pendingGate = detail.human_gates.some((gateItem) => gateItem.status === 'pending')
  return [
    {
      key: 'diagnosis',
      label: 'Diagnosis produced',
      passed: Boolean(blackboard.diagnosis),
      detail: blackboard.diagnosis ? 'Agent produced diagnosis payload.' : 'No diagnosis payload found.',
    },
    {
      key: 'patch',
      label: 'Patch result produced',
      passed: Boolean(blackboard.patch_result),
      detail: blackboard.patch_result ? 'Patch output exists on blackboard.' : 'No patch output found.',
    },
    {
      key: 'verification',
      label: 'Verification passed',
      passed: verification.status === 'passed',
      detail: verification.status ? `verification.status = ${String(verification.status)}` : 'No verification status found.',
    },
    {
      key: 'risk_gate',
      label: 'Risk gate safe',
      passed: !blackboard.gate || gate.decision === 'auto_flow',
      detail: gate.decision ? `gate.decision = ${String(gate.decision)}` : 'No risk gate required for this workflow.',
    },
    {
      key: 'pr',
      label: 'PR created',
      passed: pr.created === true && Boolean(pr.url),
      detail: pr.url ? String(pr.url) : pr.created ? 'PR marked created without URL.' : 'No PR created.',
    },
    {
      key: 'observation',
      label: 'Observation restored',
      passed: !blackboard.observation || observation.restored === true,
      detail: observation.restored === true ? 'Observation reports restored.' : blackboard.observation ? 'Observation did not report restored.' : 'No observation required.',
    },
    {
      key: 'human_gate',
      label: 'No pending human gate',
      passed: !pendingGate,
      detail: pendingGate ? 'Operator review is required.' : 'No pending human gate.',
    },
    {
      key: 'failed_atom',
      label: 'No failed atom',
      passed: !failedInvocation,
      detail: failedInvocation ? `Failed at ${failedInvocation.state_key}` : 'All recorded atom invocations completed.',
    },
  ]
}

export function buildNextAction(detail: DeclarativeWorkflowRunDetail): NextAction {
  const failedInvocation = detail.atom_invocations.find((item) => item.status === 'failed')
  const verification = (detail.blackboard.verification || {}) as Record<string, unknown>
  const observation = (detail.blackboard.observation || {}) as Record<string, unknown>
  const pr = (detail.blackboard.pr || {}) as Record<string, unknown>
  const maxPatchAttempts = Number(((detail.blackboard.limits || {}) as Record<string, unknown>).max_patch_attempts || 2)
  const patchAttempts = Number(detail.retry_counters.patch_attempts || 0)
  if (detail.pending_human_gate_count > 0) {
    return { label: 'Review Human Gate', tone: 'blocked', detail: 'Workflow is waiting for operator decision.', tab: 'gates' }
  }
  if (failedInvocation) {
    return { label: 'Inspect Failure', tone: 'blocked', detail: `Atom failed at ${failedInvocation.state_key}.`, tab: 'steps' }
  }
  if (verification.status === 'failed' && patchAttempts < maxPatchAttempts) {
    return { label: 'Continue Retry', tone: 'running', detail: 'Verification failed but retry budget remains.', tab: 'gates' }
  }
  if (verification.status === 'failed') {
    return { label: 'Route to Human', tone: 'blocked', detail: 'Verification failed and retry budget is exhausted.', tab: 'gates' }
  }
  if (observation.not_restored === true) {
    return { label: 'Reopen / Retry', tone: 'blocked', detail: 'Observation did not confirm recovery.', tab: 'steps' }
  }
  if (pr.created === true && pr.url) {
    return { label: 'Open PR', tone: 'ready', detail: 'Draft PR is available for review.', href: String(pr.url), tab: 'gates' }
  }
  if (detail.status === 'succeeded' || detail.resolution === 'completed') {
    return { label: 'No action needed', tone: 'muted', detail: 'Workflow has completed without a pending operator action.' }
  }
  return { label: 'Inspect Current State', tone: 'running', detail: `Current state is ${detail.current_state}.`, tab: 'steps' }
}

export function hasSimulatedEvidence(detail: DeclarativeWorkflowRunDetail) {
  const text = JSON.stringify({
    blackboard: detail.blackboard,
    artifacts: detail.artifacts.map((artifact) => artifact.payload),
  }).toLowerCase()
  return text.includes('simulated') || text.includes('test mode')
}
