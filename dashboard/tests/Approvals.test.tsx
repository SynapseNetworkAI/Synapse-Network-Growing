import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import Approvals from '../src/pages/Approvals'

const mockApi = {
  getApprovals: vi.fn(),
  decideApproval: vi.fn(),
  bulkDecideApprovals: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getApprovals: (...args: unknown[]) => mockApi.getApprovals(...args),
    decideApproval: (...args: unknown[]) => mockApi.decideApproval(...args),
    bulkDecideApprovals: (...args: unknown[]) => mockApi.bulkDecideApprovals(...args),
  },
}))

const APPROVALS = [
  {
    id: 1,
    task_id: 11,
    status: 'pending',
    reviewer: null,
    comment: null,
    created_at: '2026-04-10T00:00:00Z',
    decided_at: null,
    task: {
      id: 11,
      description: 'Approve launch copy',
      agent_id: 'growth_lead',
      status: 'pending_approval',
      requires_approval: true,
      priority: 'high',
      project_id: 'Synapse-Network-Growing',
      project_label: 'Synapse-Network-Growing',
      agent_group: 'growth',
      skill_name: 'social-content',
      context_files: null,
      retry_of_task_id: null,
      attempt_no: 1,
      last_error_message: null,
      output_path: null,
      output_content: 'Draft ready',
      execution_time_ms: 1000,
      created_at: '2026-04-10T00:00:00Z',
      started_at: '2026-04-10T00:01:00Z',
      completed_at: '2026-04-10T00:02:00Z',
    },
  },
  {
    id: 2,
    task_id: 12,
    status: 'pending',
    reviewer: null,
    comment: null,
    created_at: '2026-04-10T00:05:00Z',
    decided_at: null,
    task: {
      id: 12,
      description: 'Approve homepage hero copy',
      agent_id: 'content_writer',
      status: 'pending_approval',
      requires_approval: true,
      priority: 'normal',
      project_id: 'Synapse-Network-Growing',
      project_label: 'Synapse-Network-Growing',
      agent_group: 'content',
      skill_name: 'copywriting',
      context_files: null,
      retry_of_task_id: null,
      attempt_no: 1,
      last_error_message: null,
      output_path: null,
      output_content: 'Hero draft',
      execution_time_ms: 1200,
      created_at: '2026-04-10T00:05:00Z',
      started_at: '2026-04-10T00:06:00Z',
      completed_at: '2026-04-10T00:07:00Z',
    },
  },
]

describe('Approvals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getApprovals.mockResolvedValue(APPROVALS)
    mockApi.decideApproval.mockResolvedValue({ ...APPROVALS[0], status: 'approved' })
    mockApi.bulkDecideApprovals.mockResolvedValue(APPROVALS.map((item) => ({ ...item, status: 'approved' })))
  })

  it('renders pending approvals', async () => {
    render(<Approvals />)

    await waitFor(() => {
      expect(screen.getByTestId('approval-1')).toBeDefined()
      expect(screen.getByTestId('approval-2')).toBeDefined()
    })
  })

  it('bulk approves selected approvals', async () => {
    render(<Approvals />)

    await waitFor(() => {
      expect(screen.getByTestId('select-approval-1')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('select-approval-1'))
    fireEvent.click(screen.getByTestId('select-approval-2'))
    fireEvent.change(screen.getByTestId('bulk-approval-comment'), { target: { value: 'Batch approved' } })
    fireEvent.click(screen.getByTestId('bulk-approve'))

    await waitFor(() => {
      expect(mockApi.bulkDecideApprovals).toHaveBeenCalledWith({
        approval_ids: [1, 2],
        action: 'approve',
        comment: 'Batch approved',
        reviewer: 'cto',
      })
    })
  })
})