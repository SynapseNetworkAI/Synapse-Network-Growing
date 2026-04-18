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
  updated_at: '2026-04-18T10:00:00Z',
  started_at: '2026-04-18T09:58:00Z',
  completed_at: null,
  retry_counters: { patch_attempts: 1 },
  blackboard: {
    diagnosis: { action: 'patch' },
    verification: { status: 'passed' },
    pr: { created: true },
  },
  events: [
    {
      id: 1,
      event_type: 'transition',
      from_state: 'verify',
      to_state: 'patch',
      condition: 'verification.status == "failed"',
      payload: {},
      created_at: '2026-04-18T09:59:00Z',
    },
    {
      id: 2,
      event_type: 'transition',
      from_state: 'open_pr',
      to_state: 'awaiting_operator',
      condition: '<default>',
      payload: {},
      created_at: '2026-04-18T10:00:00Z',
    },
  ],
  artifacts: [
    {
      id: 11,
      artifact_type: 'workflow_transition_event',
      state_key: 'open_pr',
      atom_key: null,
      content_summary: 'open_pr -> awaiting_operator',
      payload: { from_state: 'open_pr', to_state: 'awaiting_operator' },
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
  ],
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
  decideWorkflowHumanGate: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getWorkflowRun: (...args: unknown[]) => mockApi.getWorkflowRun(...args),
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
    mockApi.decideWorkflowHumanGate.mockResolvedValue(decidedWorkflowDetail)
  })

  it('renders state machine timeline, blackboard, atoms, artifacts, and human gates', async () => {
    renderPage()

    await waitFor(() => expect(mockApi.getWorkflowRun).toHaveBeenCalledWith(7))
    expect(screen.getByText('agent_self_repair')).toBeInTheDocument()
    expect(screen.getByText('state: awaiting_operator')).toBeInTheDocument()
    expect(screen.getByTestId('workflow-state-timeline')).toHaveTextContent('verify → patch')
    expect(screen.getByTestId('workflow-blackboard')).toHaveTextContent('"verification"')
    expect(screen.getByTestId('workflow-atom-invocations')).toHaveTextContent('ops_self_repair_diagnoser')
    expect(screen.getByTestId('workflow-artifacts')).toHaveTextContent('workflow_transition_event')
    expect(screen.getByTestId('workflow-human-gates')).toHaveTextContent('Workflow reached a human-gated terminal state.')
  })

  it('submits human gate decisions and refreshes the detail', async () => {
    renderPage()

    await waitFor(() => expect(screen.getByTestId('workflow-human-gates')).toBeInTheDocument())
    fireEvent.click(within(screen.getByTestId('workflow-human-gates')).getByText('reject'))

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
