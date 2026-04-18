import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import WorkflowRunsPage from '../src/pages/WorkflowRunsPage'

const mockApi = {
  getWorkflowRuns: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getWorkflowRuns: (...args: unknown[]) => mockApi.getWorkflowRuns(...args),
  },
}))

describe('WorkflowRunsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getWorkflowRuns.mockResolvedValue([
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
        updated_at: '2026-04-18T10:00:00Z',
        started_at: '2026-04-18T09:58:00Z',
        completed_at: null,
      },
    ])
  })

  it('renders workflow management stats, filters, and generated work summary columns', async () => {
    render(<MemoryRouter><WorkflowRunsPage /></MemoryRouter>)

    await waitFor(() => expect(mockApi.getWorkflowRuns).toHaveBeenCalledWith(expect.objectContaining({ limit: 200 })))
    expect(screen.getByTestId('workflow-run-stats')).toHaveTextContent('pending human gate')
    expect(screen.getByTestId('workflow-run-filters')).toBeInTheDocument()
    expect(screen.getAllByText('gateway_reliability_repair').length).toBeGreaterThan(0)
    expect(screen.getByText('open_gateway_repair_pr')).toBeInTheDocument()

    fireEvent.change(screen.getByDisplayValue('全部状态'), { target: { value: 'awaiting_operator' } })
    await waitFor(() => expect(mockApi.getWorkflowRuns).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'awaiting_operator' })))
  })
})
