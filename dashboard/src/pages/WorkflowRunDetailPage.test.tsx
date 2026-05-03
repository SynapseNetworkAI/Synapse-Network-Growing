// @vitest-environment jsdom

import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WorkflowRunDetailPage from './WorkflowRunDetailPage'

const apiMock = vi.hoisted(() => ({
  getWorkflowRun: vi.fn(),
  getWorkflowDefinition: vi.fn(),
  confirmWorkflowBusinessOutcome: vi.fn(),
  rejectWorkflowBusinessOutcome: vi.fn(),
  requestWorkflowBusinessFollowup: vi.fn(),
  archiveWorkflowRun: vi.fn(),
  createWorkflowFollowup: vi.fn(),
  decideWorkflowHumanGate: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

vi.mock('../components/workbench', async () => {
  const actual = await vi.importActual<typeof import('../components/workbench')>('../components/workbench')
  return {
    ...actual,
    useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
  }
})

const baseDetail = {
  id: 42,
  requirement_id: 7,
  requirement_title: 'Manual copy tweak',
  workflow_key: 'gateway_reliability_repair',
  current_state: 'done',
  status: 'succeeded',
  resolution: 'completed',
  risk_level: 'normal',
  goal_key: null,
  operating_manifest_id: null,
  pending_human_gate_count: 0,
  last_human_gate_decision: null,
  last_atom: 'open_gateway_pr',
  artifact_count: 1,
  atom_count: 1,
  duration_ms: 1000,
  pr_url: null,
  release_status: null,
  updated_at: '2026-04-20T00:00:00Z',
  started_at: '2026-04-20T00:00:00Z',
  completed_at: '2026-04-20T00:00:01Z',
  archived_at: null,
  archived_by: null,
  archive_reason: null,
  outcome_label: 'Awaiting Business Confirmation',
  is_truly_completed: false,
  completed_truthfully: false,
  needs_human: true,
  is_simulated: false,
  simulated_delivery: false,
  evidence_complete: true,
  acceptance_override: true,
  manual_review_prompt: '帮我看看网页改对了没',
  business_outcome_status: null,
  business_outcome_confirmed_by: null,
  business_outcome_confirmed_at: null,
  business_outcome_note: null,
  awaiting_business_confirmation: true,
  blackboard: {
    acceptance: {
      acceptance_override: true,
      manual_review_prompt: '帮我看看网页改对了没',
      override_by: 'operator',
      override_reason: 'small manual task',
    },
    verification: { status: 'passed' },
    pr: {},
  },
  retry_counters: {},
  events: [],
  artifacts: [
    { id: 1, artifact_type: 'workflow_command_result', state_key: 'verify', atom_key: 'verify', content_summary: 'npm test passed', payload: {}, created_at: '2026-04-20T00:00:01Z' },
  ],
  atom_invocations: [],
  human_gates: [],
  timeline: [],
  notifications: [],
  observability_warnings: [],
  agent_outputs: [],
  changed_files_summary: { changed_files: ['dashboard/src/App.tsx'], added_files: [], modified_files: ['dashboard/src/App.tsx'], deleted_files: [], changed_files_count: 1, diff_summary: 'copy tweak', planned_change_only: false },
  command_results: [{ command: 'npm test', exit_code: 0, duration_ms: 1000, stdout_excerpt: 'pass', stderr_excerpt: '', simulated: false }],
  delivery_summary: { pr_created: false, pr_url: null, branch_name: null, compare_url: null, pr_status: null, release_status: null, sync_action: null, simulated: false },
}

const blockedGateDetail = {
  ...baseDetail,
  current_state: 'awaiting_operator',
  status: 'awaiting_operator',
  resolution: 'route_to_human',
  pending_human_gate_count: 1,
  human_gates: [
    {
      id: 5,
      state_key: 'awaiting_operator',
      gate_type: 'human_gate',
      risk_level: 'normal',
      status: 'pending',
      reason: 'Workflow reached a human-gated terminal state.',
      decision: null,
      created_at: '2026-04-20T00:00:02Z',
    },
  ],
  operator_decision_summary: {
    headline: 'Agent 正在处理：Repair acceptance checks',
    status_label: '已暂停等待指示',
    status_tone: 'blocked',
    what_happened: '验收矩阵未通过，系统不能证明任务已完成。',
    root_cause_kind: 'acceptance_matrix_failed',
    root_cause: 'npm --prefix dashboard run test:e2e timed out after 600s',
    error_excerpt: 'Timeout of 60000ms exceeded.\nPage crashed during login sequence.',
    recommended_next_action: '优先让 Agent 基于失败摘要继续修复；不要把未通过验收当作完成。',
    can_continue_retry: true,
    can_reject: true,
    can_supersede_retry: false,
    can_terminate: false,
  },
  notifications: [
    {
      id: 9,
      channel: 'approval',
      event_type: 'human_gate_request.created',
      event_key: 'gate-5',
      object_type: 'human_gate',
      object_key: '5',
      service_name: 'Synapse',
      status: 'delivered',
      payload: { summary: 'gate created' },
      event_id: null,
      fingerprint_key: 'fingerprint-debug-only',
      fingerprint: { occurrence_count: 1, suppressed_count: 0 },
      response_excerpt: null,
      delivered_at: '2026-04-20T00:00:03Z',
      created_at: '2026-04-20T00:00:03Z',
    },
  ],
}

function renderWorkflow(initialPath = '/workflows/42?tab=evidence') {
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/workflows/:id" element={<WorkflowRunDetailPage />} />
        <Route path="/requirements/:id" element={<div>Requirement Detail</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('WorkflowRunDetailPage Human Override evidence', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getWorkflowRun.mockResolvedValue(baseDetail)
    apiMock.getWorkflowDefinition.mockResolvedValue({ workflow_key: 'gateway_reliability_repair', states: [], spec: {}, initial_state: 'detect_ops_failure', title: '', status: 'active', id: 1, version: 1, description: '', limits: {}, risk_policy: {}, blackboard: {} })
    apiMock.confirmWorkflowBusinessOutcome.mockResolvedValue({
      ...baseDetail,
      outcome_label: 'Completed',
      is_truly_completed: true,
      completed_truthfully: true,
      needs_human: false,
      awaiting_business_confirmation: false,
      business_outcome_status: 'confirmed',
      business_outcome_confirmed_by: 'operator',
      business_outcome_confirmed_at: '2026-04-20T00:05:00Z',
      business_outcome_note: 'Business outcome confirmed from workflow Evidence tab.',
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders Manual Review Panel instead of fake step matrix for Human Override runs', async () => {
    renderWorkflow()

    const panel = await screen.findByTestId('workflow-manual-review-panel')
    expect(within(panel).getByText('帮我看看网页改对了没')).toBeTruthy()
    expect(screen.queryByTestId('workflow-step-verification-matrix')).toBeNull()
    expect(within(panel).getByRole('button', { name: 'Confirm Business Outcome' })).toBeTruthy()
  })

  it('confirms business outcome from the manual review panel', async () => {
    const user = userEvent.setup()
    renderWorkflow()

    const panel = await screen.findByTestId('workflow-manual-review-panel')
    await user.click(within(panel).getByRole('button', { name: 'Confirm Business Outcome' }))

    await waitFor(() => {
      expect(apiMock.confirmWorkflowBusinessOutcome).toHaveBeenCalledWith(42, {
        operator: 'operator',
        note: 'Business outcome confirmed from workflow Evidence tab.',
      })
    })
    const updatedPanel = await screen.findByTestId('workflow-manual-review-panel')
    expect(within(updatedPanel).getByText(/Confirmed by operator/)).toBeTruthy()
  })

  it('surfaces smart PR sync status in the delivery panel', async () => {
    apiMock.getWorkflowRun.mockResolvedValue({
      ...baseDetail,
      delivery_summary: {
        pr_created: true,
        pr_url: 'https://github.com/openai/synapse-network-growing/pull/26',
        branch_name: 'ops/req-7-agent-self-repair',
        compare_url: 'https://github.com/openai/synapse-network-growing/compare/main...ops/req-7-agent-self-repair',
        pr_status: 'draft',
        release_status: null,
        sync_action: 'updated',
        simulated: false,
        human_commits_detected: true,
        rebase_attempted: true,
        rebase_status: 'succeeded',
      },
      blackboard: {
        ...baseDetail.blackboard,
        pr: {
          pr_status: 'draft',
          branch_name: 'ops/req-7-agent-self-repair',
          base_branch: 'main',
          sync: { sync_action: 'updated', human_commits_detected: true },
          vcs: { status: 'delivered', rebase_status: 'succeeded', human_commits_detected: true },
        },
      },
    })

    renderWorkflow('/workflows/42?tab=gates')

    const panel = await screen.findByTestId('workflow-pr-delivery')
    expect(within(panel).getByText('Human commits detected and rebased')).toBeTruthy()
    expect(within(panel).getByText('Open GitHub PR')).toBeTruthy()
  })

  it('renders delivery-blocked summaries from trusted top-level delivery fields', async () => {
    apiMock.getWorkflowRun.mockResolvedValue({
      ...baseDetail,
      delivery_summary: undefined,
      delivery_status: 'delivery_blocked',
      release_status: 'delivery_blocked',
      delivery_branch: 'ops/req-12-agent-self-repair',
      delivery_base_branch: 'main',
      changed_files_count: 1,
      command_evidence_count: 7,
    })

    renderWorkflow('/workflows/42?tab=gates')

    const panel = await screen.findByTestId('workflow-pr-delivery')
    expect(within(panel).getByText('Delivery blocked before PR handoff')).toBeTruthy()
    expect(within(panel).getByText('ops/req-12-agent-self-repair')).toBeTruthy()
    expect(within(panel).getByText('7')).toBeTruthy()
  })

  it('hides stale delivery branches when delivery status is not trustworthy', async () => {
    apiMock.getWorkflowRun.mockResolvedValue({
      ...baseDetail,
      delivery_summary: undefined,
      delivery_status: null,
      release_status: null,
      delivery_branch: 'ops/stale-branch',
      delivery_base_branch: 'main',
    })

    renderWorkflow('/workflows/42?tab=gates')

    await screen.findByTestId('workflow-gates-delivery')
    expect(screen.queryByTestId('workflow-pr-delivery')).toBeNull()
    expect(screen.queryByText('ops/stale-branch')).toBeNull()
  })

  it('renders a decision-first gate view and moves Lark details to Debug', async () => {
    apiMock.getWorkflowRun.mockResolvedValue(blockedGateDetail)

    renderWorkflow('/workflows/42?tab=gates')

    const summary = await screen.findByTestId('workflow-operator-decision-summary')
    expect(within(summary).getByText('已暂停等待指示')).toBeTruthy()
    expect(within(summary).getByText('验收矩阵未通过，系统不能证明任务已完成。')).toBeTruthy()
    expect(within(summary).getByText('npm --prefix dashboard run test:e2e timed out after 600s')).toBeTruthy()
    const actionPanel = await screen.findByTestId('workflow-human-action-panel')
    expect(within(actionPanel).getByRole('button', { name: '继续让 Agent 修复' })).toBeTruthy()
    expect(within(actionPanel).getByRole('button', { name: '确认并放行' })).toBeTruthy()
    expect(screen.queryByText('fingerprint-debug-only')).toBeNull()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Debug' }))
    const debugNotifications = await screen.findByTestId('workflow-lark-notifications-debug')
    expect(within(debugNotifications).getByText(/fingerprint-debug-only/)).toBeTruthy()
  })

  it('debounces human gate decisions while the runner is resuming', async () => {
    const user = userEvent.setup()
    apiMock.getWorkflowRun.mockResolvedValue(blockedGateDetail)
    let resolveDecision: (value: unknown) => void = () => {}
    const decisionPromise = new Promise((resolve) => {
      resolveDecision = resolve
    })
    apiMock.decideWorkflowHumanGate.mockReturnValue(decisionPromise)

    renderWorkflow('/workflows/42?tab=gates')

    const actionPanel = await screen.findByTestId('workflow-human-action-panel')
    const retryButton = within(actionPanel).getByRole('button', { name: '继续让 Agent 修复' })
    await user.dblClick(retryButton)

    expect(apiMock.decideWorkflowHumanGate).toHaveBeenCalledTimes(1)
    expect(within(actionPanel).getByRole('button', { name: '处理中...' })).toBeDisabled()
    expect(within(actionPanel).getByRole('button', { name: '确认并放行' })).toBeDisabled()

    resolveDecision({ ...blockedGateDetail, resume_attempted: true, resume_status: 'resumed' })
    await waitFor(() => expect(apiMock.decideWorkflowHumanGate).toHaveBeenCalledTimes(1))
  })

  it('requires confirmation before retrying a killed dirty workspace', async () => {
    const user = userEvent.setup()
    apiMock.getWorkflowRun.mockResolvedValue({
      ...blockedGateDetail,
      workspace_recovery: {
        workspace_trust_state: 'dirty_after_kill',
        requires_workspace_recovery: true,
        recovery_status: 'human_review',
        root_cause: 'dirty_after_kill',
        latest_session_id: 11,
        killed_at: '2026-04-20T00:00:04Z',
        kill_signal: 'SIGKILL',
        repo_root: '/tmp/project/.runtime/worktrees/workflow-1',
        branch: 'ops/req-1',
        expected_branch: 'ops/req-1',
        logs: ['Run workspace recovery before retrying agent.'],
      },
    })
    apiMock.decideWorkflowHumanGate.mockResolvedValue({
      ...blockedGateDetail,
      resume_attempted: true,
      resume_status: 'resumed',
    })

    renderWorkflow('/workflows/42?tab=gates')

    const actionPanel = await screen.findByTestId('workflow-human-action-panel')
    await screen.findByTestId('workflow-workspace-recovery')
    const retryButton = within(actionPanel).getByRole('button', { name: 'Recover Workspace & Retry' })
    await user.click(retryButton)

    expect(apiMock.decideWorkflowHumanGate).not.toHaveBeenCalled()
    const dialogTitle = await screen.findByRole('heading', { name: 'Recover Workspace & Retry' })
    const dialog = dialogTitle.closest('section')
    expect(dialog).toBeTruthy()
    await user.click(within(dialog as HTMLElement).getByRole('button', { name: 'Recover Workspace & Retry' }))

    await waitFor(() => expect(apiMock.decideWorkflowHumanGate).toHaveBeenCalledWith(42, 5, expect.objectContaining({ decision: 'continue_retry' })))
  })

  it('short polls after a gate decision and warns when the workflow blocks again', async () => {
    apiMock.getWorkflowRun
      .mockResolvedValueOnce(blockedGateDetail)
      .mockResolvedValueOnce({
        ...blockedGateDetail,
        human_gates: [{ ...blockedGateDetail.human_gates[0], id: 6 }],
        operator_decision_summary: {
          ...blockedGateDetail.operator_decision_summary,
          root_cause: 'Acceptance matrix failed again after retry.',
          error_excerpt: 'FAILED tests/test_ops_console.py::test_gate_resume',
        },
      })
    apiMock.decideWorkflowHumanGate.mockResolvedValue({
      ...blockedGateDetail,
      current_state: 'running',
      status: 'running',
      pending_human_gate_count: 0,
      human_gates: [{ ...blockedGateDetail.human_gates[0], status: 'decided', decision: 'continue_retry' }],
      resume_attempted: true,
      resume_status: 'running',
    })

    renderWorkflow('/workflows/42?tab=gates')
    const actionPanel = await screen.findByTestId('workflow-human-action-panel')

    vi.useFakeTimers()
    fireEvent.click(within(actionPanel).getByRole('button', { name: '继续让 Agent 修复' }))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByTestId('workflow-gate-decision-feedback')).toHaveTextContent('决策已记录，等待 Runner 推进或再次阻断。')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(apiMock.getWorkflowRun).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('workflow-gate-decision-feedback')).toHaveTextContent('Agent 已继续尝试，但工作流仍停在人工门禁')
    expect(screen.getByText('Acceptance matrix failed again after retry.')).toBeTruthy()
  })

  it('shows acceptance matrix liveness and timeout evidence', async () => {
    apiMock.getWorkflowRun.mockResolvedValue({
      ...baseDetail,
      blackboard: {
        ...baseDetail.blackboard,
        acceptance_matrix: {
          status: 'running',
          current_step_key: 'frontend_validation',
          current_command: 'npm --prefix dashboard run build',
          current_command_started_at: new Date().toISOString(),
          verify_phase_started_at: '2026-04-20T00:00:00Z',
        },
      },
      command_results: [
        {
          command: 'npm --prefix dashboard run build',
          exit_code: 124,
          duration_ms: 600000,
          stdout_excerpt: '',
          stderr_excerpt: 'command timed out after 600s',
          timeout: true,
          timeout_seconds: 600,
          killed: true,
          step_key: 'frontend_validation',
          simulated: false,
        },
      ],
    })

    renderWorkflow()

    const runtimePanel = await screen.findByTestId('workflow-acceptance-matrix-runtime')
    expect(within(runtimePanel).getByText(/Running acceptance command for/)).toBeTruthy()
    expect(within(runtimePanel).getByText('frontend_validation')).toBeTruthy()
    expect(within(runtimePanel).queryByText(/passing workflow evidence/)).toBeNull()
    const commandPanel = await screen.findByTestId('workflow-command-evidence-panel')
    expect(within(commandPanel).getByText('Timed out after 600s')).toBeTruthy()
    expect(within(commandPanel).getByText('process group killed')).toBeTruthy()
  })
})
