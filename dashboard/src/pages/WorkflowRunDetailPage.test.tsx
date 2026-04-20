// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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

function renderWorkflow() {
  render(
    <MemoryRouter initialEntries={['/workflows/42?tab=evidence']}>
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
})
