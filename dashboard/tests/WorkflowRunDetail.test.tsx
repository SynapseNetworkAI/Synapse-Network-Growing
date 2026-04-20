import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import WorkflowRunDetailPage from '../src/pages/WorkflowRunDetailPage'

const workflowDetail = {
  id: 7,
  requirement_id: 4,
  requirement_title: 'Repair Ops Dashboard failure',
  workflow_key: 'agent_self_repair',
  current_state: 'awaiting_operator',
  status: 'awaiting_operator',
  resolution: 'route_to_human',
  risk_level: 'high',
  pending_human_gate_count: 1,
  outcome_label: 'Needs Human',
  is_truly_completed: false,
  completed_truthfully: false,
  needs_human: true,
  is_simulated: true,
  simulated_delivery: true,
  evidence_complete: false,
  observability_warnings: [
    'Pending human gate: this run is not truly completed.',
    'Simulated PR: delivery evidence is not a real external PR.',
  ],
  updated_at: '2026-04-18T10:00:00Z',
  started_at: '2026-04-18T09:58:00Z',
  completed_at: null,
  retry_counters: { patch_attempts: 1 },
  blackboard: {
    trigger: { ops_failure_detected: true },
    evidence: [{ kind: 'log_excerpt', summary: 'Traceback from ops-dashboard runtime' }],
    diagnosis: { action: 'patch' },
    patch_result: { changed_files_count: 1, changed_files: ['server/services/workflows/declarative.py'], planned_change_only: true },
    verification: { status: 'passed' },
    pr: { created: true, url: 'https://github.com/example/repo/pull/7', branch_name: 'ops/req-4-agent-self-repair' },
    risk_flags: ['self_modification_requires_human'],
  },
  events: [
    {
      id: 1,
      event_type: 'transition',
      from_state: 'verify',
      to_state: 'patch',
      condition: 'verification.status == "failed"',
      payload: { from_state: 'verify', to_state: 'patch' },
      created_at: '2026-04-18T09:59:00Z',
    },
    {
      id: 2,
      event_type: 'transition',
      from_state: 'open_pr',
      to_state: 'awaiting_operator',
      condition: '<default>',
      payload: { from_state: 'open_pr', to_state: 'awaiting_operator' },
      created_at: '2026-04-18T10:00:00Z',
    },
  ],
  artifacts: [
    {
      id: 31,
      artifact_type: 'workflow_agent_raw_output',
      state_key: 'diagnose',
      atom_key: 'ops_self_repair_diagnoser',
      content_summary: 'diagnose: TypeError from stale parser boundary',
      payload: { diagnosis: { action: 'patch' } },
      created_at: '2026-04-18T09:58:30Z',
    },
    {
      id: 32,
      artifact_type: 'workflow_review_pr_sync',
      state_key: 'open_pr',
      atom_key: 'open_self_repair_pr',
      content_summary: 'agent_self_repair: GitHub PR sync synced',
      payload: { status: 'synced', pr_url: 'https://github.com/example/repo/pull/7' },
      created_at: '2026-04-18T10:00:00Z',
    },
  ],
  atom_invocations: [
    {
      id: 21,
      state_key: 'diagnose',
      atom_key: 'ops_self_repair_diagnoser',
      atom_type: 'agent',
      status: 'completed',
      output_summary: 'TypeError from stale parser boundary',
      artifact_ids: [31],
      duration_ms: 42,
      error_excerpt: null,
    },
    {
      id: 22,
      state_key: 'open_pr',
      atom_key: 'open_self_repair_pr',
      atom_type: 'deterministic',
      status: 'completed',
      output_summary: 'GitHub draft PR synced',
      artifact_ids: [32],
      duration_ms: 120,
      error_excerpt: null,
    },
  ],
  timeline: [
    {
      kind: 'state_transition',
      id: 2,
      created_at: '2026-04-18T10:00:00Z',
      state_key: 'awaiting_operator',
      from_state: 'open_pr',
      to_state: 'awaiting_operator',
      condition: '<default>',
      status: 'completed',
      title: 'State transition: open_pr -> awaiting_operator',
      summary: 'Condition: <default>',
      artifact_ids: [],
    },
    {
      kind: 'atom_invocation',
      id: 21,
      created_at: '2026-04-18T09:58:30Z',
      state_key: 'diagnose',
      atom_key: 'ops_self_repair_diagnoser',
      atom_type: 'agent',
      status: 'completed',
      title: 'Atom executed: ops_self_repair_diagnoser',
      summary: 'TypeError from stale parser boundary',
      artifact_ids: [31],
      artifacts: [
        {
          id: 31,
          artifact_type: 'workflow_agent_raw_output',
          summary: 'diagnose: TypeError from stale parser boundary',
          payload: { diagnosis: { action: 'patch' } },
          raw_excerpt: '{"writes":{"diagnosis":{"action":"patch"}}}',
        },
      ],
    },
    {
      kind: 'artifact_created',
      id: 32,
      created_at: '2026-04-18T10:00:00Z',
      state_key: 'open_pr',
      atom_key: 'open_self_repair_pr',
      status: 'created',
      title: 'Artifact created: workflow_review_pr_sync #32',
      summary: 'agent_self_repair: GitHub PR sync synced',
      artifact_ids: [32],
      artifact: {
        id: 32,
        artifact_type: 'workflow_review_pr_sync',
        summary: 'agent_self_repair: GitHub PR sync synced',
        payload: { status: 'synced', pr_url: 'https://github.com/example/repo/pull/7' },
        raw_excerpt: '',
      },
    },
    {
      kind: 'human_gate',
      id: 41,
      created_at: '2026-04-18T10:00:00Z',
      state_key: 'awaiting_operator',
      status: 'pending',
      title: 'Human gate: human_gate',
      summary: 'Workflow reached a human-gated terminal state.',
      artifact_ids: [],
    },
    {
      kind: 'workflow_terminal',
      id: 7,
      created_at: '2026-04-18T10:00:00Z',
      state_key: 'awaiting_operator',
      status: 'awaiting_operator',
      title: 'Workflow terminal: awaiting_operator',
      summary: 'route_to_human',
      artifact_ids: [],
    },
  ],
  agent_outputs: [
    {
      state_key: 'diagnose',
      atom_key: 'ops_self_repair_diagnoser',
      agent_name: 'ops_self_repair_diagnoser',
      status: 'completed',
      summary: 'TypeError from stale parser boundary',
      input_summary: 'state=diagnose',
      parsed_writes: { diagnosis: { action: 'patch' } },
      raw_artifact_id: 31,
      raw_output: '{"writes":{"diagnosis":{"action":"patch"}}}',
      created_at: '2026-04-18T09:58:30Z',
    },
  ],
  changed_files_summary: {
    changed_files: ['server/services/workflows/declarative.py'],
    added_files: [],
    modified_files: ['server/services/workflows/declarative.py'],
    deleted_files: [],
    changed_files_count: 1,
    diff_summary: 'Planned observability patch',
    patch_artifact_id: null,
    planned_change_only: true,
  },
  command_results: [],
  delivery_summary: {
    pr_created: true,
    pr_url: 'https://github.com/example/repo/pull/7',
    branch_name: 'ops/req-4-agent-self-repair',
    compare_url: null,
    pr_status: 'draft',
    release_status: null,
    sync_action: 'simulated',
    simulated: true,
  },
  human_gates: [
    {
      id: 41,
      state_key: 'awaiting_operator',
      gate_type: 'human_gate',
      risk_level: 'high',
      status: 'pending',
      reason: 'Workflow reached a human-gated terminal state.',
      decision: null,
      created_at: '2026-04-18T10:00:00Z',
    },
  ],
  notifications: [
    {
      id: 51,
      channel: 'approval',
      event_type: 'human_gate_request.created',
      event_key: 'approval:human_gate_request.created:human_gate:41',
      object_type: 'human_gate',
      object_key: '41',
      service_name: 'Synapse Ops',
      status: 'skipped',
      payload: { summary: 'Workflow #7 requires operator decision.' },
      response_excerpt: 'Webhook not configured',
      delivered_at: null,
      created_at: '2026-04-18T10:00:00Z',
    },
  ],
}

const decidedWorkflowDetail = {
  ...workflowDetail,
  status: 'failed',
  resolution: 'operator_rejected',
  pending_human_gate_count: 0,
  human_gates: [
    {
      ...workflowDetail.human_gates[0],
      status: 'decided',
      decision: 'reject',
    },
  ],
}

const mockApi = {
  getWorkflowRun: vi.fn(),
  getWorkflowDefinition: vi.fn(),
  decideWorkflowHumanGate: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getWorkflowRun: (...args: unknown[]) => mockApi.getWorkflowRun(...args),
    getWorkflowDefinition: (...args: unknown[]) => mockApi.getWorkflowDefinition(...args),
    decideWorkflowHumanGate: (...args: unknown[]) => mockApi.decideWorkflowHumanGate(...args),
  },
}))

function renderPage() {
  render(
    <MemoryRouter initialEntries={['/workflows/7']}>
      <Routes>
        <Route path="/workflows/:id" element={<WorkflowRunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('WorkflowRunDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getWorkflowRun.mockResolvedValue(workflowDetail)
    mockApi.getWorkflowDefinition.mockResolvedValue({
      id: 1,
      workflow_key: 'agent_self_repair',
      version: 1,
      title: 'Agent self repair',
      status: 'active',
      description: 'Repair Agent Ops failures',
      initial_state: 'detect_ops_failure',
      states: [
        { key: 'detect_ops_failure', atom_key: 'detect_ops_failure', atom_type: 'deterministic', terminal: false, resolution: null, output_key: null, risk_level: null, transitions: [{ condition: 'ops_failure_detected', goto: 'collect_logs' }] },
        { key: 'collect_logs', atom_key: 'collect_ops_logs', atom_type: 'deterministic', terminal: false, resolution: null, output_key: null, risk_level: null, transitions: [{ condition: 'logs_collected', goto: 'diagnose' }] },
        { key: 'diagnose', atom_key: 'ops_self_repair_diagnoser', atom_type: 'agent', terminal: false, resolution: null, output_key: 'diagnosis', risk_level: null, transitions: [{ condition: 'diagnosis.action == "patch"', goto: 'patch' }] },
        { key: 'patch', atom_key: 'ops_self_repair_coder', atom_type: 'agent', terminal: false, resolution: null, output_key: 'patch_result', risk_level: null, transitions: [{ condition: 'patch_result.changed_files_count > 0', goto: 'verify' }] },
        { key: 'verify', atom_key: 'run_ops_self_repair_verification', atom_type: 'deterministic', terminal: false, resolution: null, output_key: 'verification', risk_level: null, transitions: [{ condition: 'verification.status == "failed"', goto: 'patch' }, { condition: 'verification.status == "passed"', goto: 'open_pr' }] },
        { key: 'open_pr', atom_key: 'open_self_repair_pr', atom_type: 'deterministic', terminal: false, resolution: null, output_key: 'pr', risk_level: null, transitions: [{ condition: 'pr.created', goto: 'awaiting_operator' }] },
        { key: 'awaiting_operator', atom_key: null, atom_type: 'terminal', terminal: true, resolution: 'route_to_human', output_key: null, risk_level: null, transitions: [] },
      ],
      limits: { max_patch_attempts: 2 },
      risk_policy: {},
      blackboard: {},
      spec: {},
    })
    mockApi.decideWorkflowHumanGate.mockResolvedValue(decidedWorkflowDetail)
  })

  it('renders the explainable overview instead of the old debug-first page', async () => {
    renderPage()

    await waitFor(() => expect(mockApi.getWorkflowRun).toHaveBeenCalledWith(7))
    await waitFor(() => expect(mockApi.getWorkflowDefinition).toHaveBeenCalledWith('agent_self_repair'))

    expect(screen.getByTestId('workflow-run-header')).toHaveTextContent('agent_self_repair')
    expect(screen.getByTestId('workflow-run-header')).toHaveTextContent('Needs Human')
    expect(screen.getByTestId('workflow-run-header')).toHaveTextContent('Simulated PR')
    expect(screen.getByTestId('workflow-overview-tab')).toHaveTextContent('Run #7 执行')
    expect(screen.getByTestId('workflow-correctness-panel')).toHaveTextContent('Verification passed')
    expect(screen.getByTestId('workflow-observability-warnings')).toHaveTextContent('Pending human gate')
    expect(screen.getByTestId('workflow-agent-output-panel')).toHaveTextContent('ops_self_repair_diagnoser')
    expect(screen.getByTestId('workflow-changed-files-panel')).toHaveTextContent('server/services/workflows/declarative.py')
    expect(screen.getByTestId('workflow-changed-files-panel')).toHaveTextContent('Planned change only')
    expect(screen.getByTestId('workflow-command-evidence-panel')).toHaveTextContent('No command evidence recorded')
    expect(screen.getByTestId('workflow-run-header')).toHaveTextContent('Review Human Gate')
    expect(screen.getByTestId('workflow-compact-step-rail')).toHaveTextContent('diagnose')
    expect(screen.getByTestId('workflow-compact-step-rail')).toHaveTextContent('Static progress only')
    expect(screen.queryByText('Generated Work Items')).not.toBeInTheDocument()
    expect(screen.queryByText('Raw Blackboard JSON')).not.toBeInTheDocument()
  })

  it('shows the chronological workflow timeline without a step inspector', async () => {
    renderPage()

    await waitFor(() => expect(screen.getByTestId('workflow-run-tabs')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Timeline'))

    const timeline = screen.getByTestId('workflow-timeline-panel')
    expect(timeline).toHaveTextContent('State transition: open_pr -> awaiting_operator')
    expect(timeline).toHaveTextContent('Atom executed: ops_self_repair_diagnoser')
    expect(timeline).toHaveTextContent('Artifact created: workflow_review_pr_sync #32')
    expect(timeline).toHaveTextContent('Human gate: human_gate')
    expect(timeline).toHaveTextContent('Workflow terminal: awaiting_operator')
    expect(screen.queryByTestId('workflow-step-inspector')).not.toBeInTheDocument()
    expect(screen.queryByText('Inputs')).not.toBeInTheDocument()
    expect(screen.queryByText('Outputs')).not.toBeInTheDocument()
  })

  it('groups artifacts into a human-readable evidence map and keeps raw JSON in Debug', async () => {
    renderPage()

    await waitFor(() => expect(screen.getByTestId('workflow-run-tabs')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Evidence'))

    expect(screen.getByTestId('workflow-agent-output-panel')).toHaveTextContent('ops_self_repair_diagnoser')
    expect(screen.getByTestId('workflow-changed-files-panel')).toHaveTextContent('server/services/workflows/declarative.py')
    expect(screen.getByTestId('workflow-command-evidence-panel')).toHaveTextContent('No command evidence recorded')
    expect(screen.getByTestId('workflow-evidence-map')).toHaveTextContent('GitHub PR: draft PR synced')
    expect(screen.queryByText('Raw Blackboard JSON')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Debug'))
    expect(screen.getByTestId('workflow-debug-panel')).toHaveTextContent('Download Debug Dump')
    expect(screen.getByTestId('workflow-debug-panel')).toHaveTextContent('Raw Blackboard JSON')
    expect(screen.getByTestId('workflow-debug-panel')).toHaveTextContent('Raw Artifacts')
  })

  it('submits human gate decisions from Gates & Delivery and refreshes the detail', async () => {
    renderPage()

    await waitFor(() => expect(screen.getByTestId('workflow-run-tabs')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Gates & Delivery'))
    expect(screen.getByTestId('workflow-lark-notifications')).toHaveTextContent('human_gate_request.created')
    fireEvent.click(within(screen.getByTestId('workflow-gates-delivery')).getByText('reject'))

    await waitFor(() => {
      expect(mockApi.decideWorkflowHumanGate).toHaveBeenCalledWith(7, 41, {
        decision: 'reject',
        reviewer: 'operator',
        comment: 'Operator reject from workflow detail',
      })
    })
    expect(screen.getByTestId('workflow-run-detail-page')).toHaveTextContent('operator_rejected')
  })
})
