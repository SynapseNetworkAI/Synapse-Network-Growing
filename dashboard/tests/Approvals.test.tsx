import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Approvals from '../src/pages/Approvals'

const mockApi = {
  getApprovals: vi.fn(),
  getRequirements: vi.fn(),
  decideApproval: vi.fn(),
  decideRequirementApproval: vi.fn(),
  bulkDecideApprovals: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getApprovals: (...args: unknown[]) => mockApi.getApprovals(...args),
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    decideApproval: (...args: unknown[]) => mockApi.decideApproval(...args),
    decideRequirementApproval: (...args: unknown[]) => mockApi.decideRequirementApproval(...args),
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

const REQUIREMENTS = [
  {
    id: 31,
    title: 'Approval required requirement',
    description_markdown: 'Need approval before execution.',
    status: 'ready',
    priority: 'high',
    source: 'manual',
    source_ref: null,
    intake_metadata: {},
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    approval_status: 'pending_approval',
    approval_contract: {
      approval_mode: 'auto_or_human',
      required_approver_roles: ['request_owner', 'reviewer', 'tester'],
    },
    approval_requested_at: '2026-04-12T00:00:00Z',
    approved_at: null,
    current_plan_version: 1,
    blocked_by_count: 0,
    active_workflow_run_id: null,
    started_at: null,
    completed_at: null,
    created_at: '2026-04-12T00:00:00Z',
    updated_at: '2026-04-12T00:00:00Z',
    routing_context: {
      routing_mode: 'explicit',
      target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
      summary: 'Explicit target project routing.',
      automation_ready: true,
      readiness_status: 'ready',
      routed_project_keys: ['synapse-network-growing'],
      routed_display_names: ['Synapse-Network-Growing'],
      skipped_project_keys: [],
      project_scorecards: [],
    },
    score_breakdown: {
      total: 80,
      priority: 30,
      aging: 20,
      status_adjustment: 0,
      blocker_penalty: 0,
      readiness_adjustment: 10,
      automation_gap: 0,
      bug_pressure: 0,
      delivery_pressure: 0,
    },
  },
]

describe('Approvals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getApprovals.mockResolvedValue(APPROVALS)
    mockApi.getRequirements.mockResolvedValue(REQUIREMENTS)
    mockApi.decideApproval.mockResolvedValue({ ...APPROVALS[0], status: 'approved' })
    mockApi.decideRequirementApproval.mockResolvedValue({
      requirement: { ...REQUIREMENTS[0], approval_status: 'approved', approved_at: '2026-04-12T00:05:00Z' },
    })
    mockApi.bulkDecideApprovals.mockResolvedValue(APPROVALS.map((item) => ({ ...item, status: 'approved' })))
  })

  it('renders pending approvals', async () => {
    render(<MemoryRouter><Approvals /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('approval-1')).toBeDefined()
      expect(screen.getByTestId('approval-2')).toBeDefined()
      expect(screen.getByTestId('requirement-approval-31')).toBeDefined()
    })
  })

  it('bulk approves selected approvals', async () => {
    render(<MemoryRouter><Approvals /></MemoryRouter>)

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

  it('allows approving requirement execution approvals', async () => {
    render(<MemoryRouter><Approvals /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-approval-31')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('requirement-approval-comment-31'), { target: { value: 'Looks safe' } })
    fireEvent.click(screen.getByTestId('requirement-approve-31'))

    await waitFor(() => {
      expect(mockApi.decideRequirementApproval).toHaveBeenCalledWith(31, {
        action: 'approve',
        reviewer: 'cto',
        comment: 'Looks safe',
      })
    })
  })
})
