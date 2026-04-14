import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RequirementDetail from '../src/pages/RequirementDetail'

const mockApi = {
  getRequirement: vi.fn(),
  updateRequirement: vi.fn(),
  submitRequirement: vi.fn(),
  approveRequirement: vi.fn(),
  rejectRequirement: vi.fn(),
  startExecution: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    updateRequirement: (...args: unknown[]) => mockApi.updateRequirement(...args),
    submitRequirement: (...args: unknown[]) => mockApi.submitRequirement(...args),
    approveRequirement: (...args: unknown[]) => mockApi.approveRequirement(...args),
    rejectRequirement: (...args: unknown[]) => mockApi.rejectRequirement(...args),
    startExecution: (...args: unknown[]) => mockApi.startExecution(...args),
  },
}))

const baseDetail = {
  requirement: {
    id: 3,
    title: 'Bug Fix: Runtime traceback detected',
    description_markdown: 'Fix the runtime traceback surfaced by the intake pipeline.',
    acceptance_criteria_markdown: '- Traceback no longer appears\n- Targeted regression check passes',
    status: 'ready',
    priority: 'high',
    source: 'bug_intake',
    source_ref: 'error-fingerprint:runtime_log_error:abc123',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    target_projects: ['/Users/cliff/workspace/agent/Synapse-Network-Growing'],
    approval_required: false,
    approval_status: 'waived',
    created_at: '2026-04-14T00:00:00Z',
    updated_at: '2026-04-14T00:00:00Z',
    active_execution_run_id: null,
    latest_execution_run_id: null,
    latest_release_status: null,
  },
  approval: {
    approval_decision: 'waived',
    approval_status: 'waived',
    approval_reason: null,
    approval_source: 'policy_waived',
    required_approver_roles: [],
    risk_flags: [],
    pending_execution_start: false,
    auto_started: false,
    execution_run_id: null,
  },
  latest_execution_id: null,
  latest_release_id: null,
  policy_summary_markdown: '',
}

describe('RequirementDetail SaaS editing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi.getRequirement.mockResolvedValue(baseDetail)
    mockApi.updateRequirement.mockResolvedValue(baseDetail)
  })

  it('allows editing only before execution has started', async () => {
    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.getByTestId('toggle-edit-requirement-btn')).toBeInTheDocument()
    expect(screen.queryByText('修订需求')).not.toBeInTheDocument()
    expect(screen.queryByText('执行许可')).not.toBeInTheDocument()
    expect(screen.queryByText('策略摘要')).not.toBeInTheDocument()
    expect(screen.queryByText('执行 / 发布跳转')).not.toBeInTheDocument()
    expect(screen.queryByTestId('requirement-approval-notice')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-edit-requirement-btn'))
    fireEvent.change(screen.getByTestId('edit-requirement-title'), { target: { value: 'Bug Fix: Traceback removed' } })
    fireEvent.change(screen.getByTestId('edit-requirement-target-project-path'), { target: { value: '/tmp/project-a' } })
    fireEvent.change(screen.getByTestId('edit-requirement-priority'), { target: { value: 'normal' } })
    fireEvent.change(screen.getByTestId('edit-requirement-description'), { target: { value: 'Updated description' } })
    fireEvent.change(screen.getByTestId('edit-requirement-acceptance'), { target: { value: '- Updated acceptance' } })
    fireEvent.click(screen.getByTestId('save-requirement-btn'))

    await waitFor(() =>
      expect(mockApi.updateRequirement).toHaveBeenCalledWith(
        3,
        expect.objectContaining({
          title: 'Bug Fix: Traceback removed',
          description_markdown: 'Updated description',
          acceptance_criteria_markdown: '- Updated acceptance',
          priority: 'normal',
          target_project_path: '/tmp/project-a',
        }),
      ),
    )
  })

  it('hides the edit button after execution has started', async () => {
    mockApi.getRequirement.mockResolvedValueOnce({
      ...baseDetail,
      requirement: {
        ...baseDetail.requirement,
        status: 'running',
        latest_execution_run_id: 12,
      },
      latest_execution_id: 12,
    })

    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.queryByTestId('toggle-edit-requirement-btn')).not.toBeInTheDocument()
  })

  it('shows a compact approval notice only when manual approval is pending', async () => {
    mockApi.getRequirement.mockResolvedValueOnce({
      ...baseDetail,
      requirement: {
        ...baseDetail.requirement,
        status: 'blocked',
      },
      approval: {
        ...baseDetail.approval,
        approval_decision: 'pending_manual_approval',
        approval_status: 'pending_approval',
        approval_reason: 'High risk requirement needs operator review.',
        required_approver_roles: ['operator'],
      },
    })

    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.getByTestId('requirement-approval-notice')).toBeInTheDocument()
    expect(screen.getByText('High risk requirement needs operator review.')).toBeInTheDocument()
    expect(screen.queryByText('执行许可')).not.toBeInTheDocument()
  })
})
