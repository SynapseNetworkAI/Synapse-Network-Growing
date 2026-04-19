import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import WorkflowRunsPage from '../src/pages/WorkflowRunsPage'

const mockApi = {
  getWorkflowRunsSummary: vi.fn(),
  getWorkflowDefinitions: vi.fn(),
  getWorkflowRunsPage: vi.fn(),
  archiveWorkflowRun: vi.fn(),
  createWorkflowFollowup: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getWorkflowRunsSummary: (...args: unknown[]) => mockApi.getWorkflowRunsSummary(...args),
    getWorkflowDefinitions: (...args: unknown[]) => mockApi.getWorkflowDefinitions(...args),
    getWorkflowRunsPage: (...args: unknown[]) => mockApi.getWorkflowRunsPage(...args),
    archiveWorkflowRun: (...args: unknown[]) => mockApi.archiveWorkflowRun(...args),
    createWorkflowFollowup: (...args: unknown[]) => mockApi.createWorkflowFollowup(...args),
  },
}))

describe('WorkflowRunsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getWorkflowRunsSummary.mockResolvedValue({
      running: 1,
      needs_human: 1,
      failed: 0,
      completed: 0,
      completed_today: 0,
      pending_release: 1,
      average_duration_ms: 120000,
      archived: 0,
      pending_candidate_count: 0,
      recent_candidates: [],
    })
    mockApi.getWorkflowDefinitions.mockResolvedValue([
      {
        id: 1,
        workflow_key: 'gateway_reliability_repair',
        version: 1,
        title: 'Gateway Reliability Repair',
        status: 'active',
        description: 'Repair gateway',
        initial_state: 'detect_ops_failure',
        states: [],
        limits: {},
        risk_policy: {},
        blackboard: {},
        spec: {},
      },
    ])
    mockApi.getWorkflowRunsPage.mockResolvedValue({
      items: [
        {
          id: 77,
          requirement_id: 4,
          requirement_title: 'Repair gateway',
          workflow_key: 'gateway_reliability_repair',
          current_state: 'awaiting_operator',
          status: 'awaiting_operator',
          resolution: 'route_to_human',
          risk_level: 'high',
          pending_human_gate_count: 1,
          last_atom: 'open_gateway_repair_pr',
          artifact_count: 4,
          atom_count: 5,
          duration_ms: 120000,
          pr_url: 'https://github.com/example/repo/pull/1',
          updated_at: '2026-04-18T10:00:00Z',
          started_at: '2026-04-18T09:58:00Z',
          completed_at: null,
        },
      ],
      total: 1,
      page: 1,
      page_size: 100,
      total_pages: 1,
    })
  })

  it('renders workflow management stats, filters, and generated work summary columns', async () => {
    render(<MemoryRouter><WorkflowRunsPage /></MemoryRouter>)

    await waitFor(() => expect(mockApi.getWorkflowRunsPage).toHaveBeenCalledWith(expect.objectContaining({ tab: 'active', page_size: 100 })))
    expect(screen.getByTestId('workflow-run-stats')).toHaveTextContent('Needs Human')
    expect(screen.getByTestId('workflow-run-filters')).toBeInTheDocument()
    expect(screen.getAllByText('gateway_reliability_repair').length).toBeGreaterThan(0)
    expect(screen.getByText('open_gateway_repair_pr')).toBeInTheDocument()
    expect(screen.getByText('处理 Human Gate')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Definitions'))
    await waitFor(() => expect(screen.getByTestId('workflow-definitions-panel')).toBeInTheDocument())
  })
})
