import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirementPool from '../src/pages/RequirementPool'
import ExecutionsPage from '../src/pages/ExecutionsPage'
import ReleasesPage from '../src/pages/ReleasesPage'
import ErrorsPage from '../src/pages/ErrorsPage'

const mockApi = {
  getRequirements: vi.fn(),
  createRequirement: vi.fn(),
  deleteRequirement: vi.fn(),
  updateRequirement: vi.fn(),
  submitRequirement: vi.fn(),
  createExecution: vi.fn(),
  getExecutions: vi.fn(),
  startExecution: vi.fn(),
  getReleaseCandidates: vi.fn(),
  getErrors: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    createRequirement: (...args: unknown[]) => mockApi.createRequirement(...args),
    deleteRequirement: (...args: unknown[]) => mockApi.deleteRequirement(...args),
    updateRequirement: (...args: unknown[]) => mockApi.updateRequirement(...args),
    submitRequirement: (...args: unknown[]) => mockApi.submitRequirement(...args),
    createExecution: (...args: unknown[]) => mockApi.createExecution(...args),
    getExecutions: (...args: unknown[]) => mockApi.getExecutions(...args),
    startExecution: (...args: unknown[]) => mockApi.startExecution(...args),
    getReleaseCandidates: (...args: unknown[]) => mockApi.getReleaseCandidates(...args),
    getErrors: (...args: unknown[]) => mockApi.getErrors(...args),
  },
}))

describe('agent-first pages smoke', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi.getRequirements.mockResolvedValue([
      {
        id: 1,
        title: 'Launch FAQ',
        description_markdown: 'Validate FAQ launch path.',
        status: 'ready',
        priority: 'high',
        source: 'manual',
        source_ref: null,
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: 'Checks pass.',
        approval_required: false,
        approval_status: 'waived',
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    mockApi.getExecutions.mockResolvedValue([
      {
        id: 11,
        requirement_id: 1,
        status: 'queued',
        execution_mode: 'direct',
        complexity: 'simple',
        planner_summary: 'Direct execute.',
        validation_profile: 'minimal',
        delivery_intent: 'pr_required',
        approval_required: false,
        target_projects: ['Synapse-Network'],
        latest_task_id: null,
        started_at: null,
        completed_at: null,
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    mockApi.getReleaseCandidates.mockResolvedValue([
      {
        requirement: {
          id: 1,
          title: 'Launch FAQ',
          status: 'done',
          target_projects: ['Synapse-Network'],
          latest_execution_run_id: 11,
        },
        validation: {
          status: 'passed',
          summary_markdown: 'All checks green.',
          updated_at: '2026-04-14T00:00:00Z',
        },
        release: {
          status: 'ready',
          branch_name: 'ops/req-1-launch-faq',
          commit_sha: 'abc1234',
          pr_number: 17,
          updated_at: '2026-04-14T00:00:00Z',
        },
      },
    ])
    mockApi.getErrors.mockResolvedValue([
      {
        fingerprint_key: 'runtime_log_error:abc123',
        source_kind: 'runtime_log_error',
        service_name: 'Synapse Gateway',
        project_key: 'synapse-network',
        project_root_path: '/Users/cliff/workspace/agent/Synapse-Network',
        incident_code: 'gateway_timeout',
        severity: 'high',
        summary: 'Gateway timeout while opening FAQ route',
        evidence_excerpt: 'TimeoutError: gateway request exceeded budget',
        status: 'open',
        occurrence_count: 3,
        first_seen_at: '2026-04-14T00:00:00Z',
        latest_seen_at: '2026-04-14T01:00:00Z',
        latest_error_event_id: 9,
        linked_requirement_id: 1,
        latest_execution_run_id: 11,
      },
    ])
  })

  it('renders requirement surface', async () => {
    render(
      <MemoryRouter>
        <RequirementPool />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.getByText('需求列表')).toBeInTheDocument()
    expect(screen.getByText('Launch FAQ')).toBeInTheDocument()
  })

  it('opens create and edit requirement drawers from the toolbar', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockApi.createRequirement.mockResolvedValue({
      requirement: {
        id: 2,
        title: 'Improve Queue Copy',
        description_markdown: 'Tighten the requirement queue copy.',
        status: 'draft',
        priority: 'normal',
        source: 'manual',
        source_ref: null,
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        target_projects: ['Synapse-Network-Growing'],
        acceptance_criteria_markdown: 'Copy updated.',
        approval_required: false,
        approval_status: 'waived',
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    })
    mockApi.updateRequirement.mockResolvedValue({
      requirement: {
        id: 1,
        title: 'Launch FAQ Updated',
        description_markdown: 'Validate FAQ launch path.',
        status: 'ready',
        priority: 'high',
        source: 'manual',
        source_ref: null,
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: 'Checks pass.',
        approval_required: false,
        approval_status: 'waived',
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    })

    render(
      <MemoryRouter>
        <RequirementPool />
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.queryByRole('heading', { name: '新建需求' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '新建需求' }))
    expect(screen.getByRole('heading', { name: '新建需求' })).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('输入需求标题'), {
      target: { value: 'Improve Queue Copy' },
    })
    fireEvent.change(screen.getByPlaceholderText('输入需求描述'), {
      target: { value: 'Tighten the requirement queue copy.' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(mockApi.createRequirement).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('heading', { name: '新建需求' })).not.toBeInTheDocument())

    const editButton = screen.getAllByRole('button', { name: '编辑' })[0]
    expect(editButton).toBeEnabled()
    fireEvent.click(editButton)
    expect(screen.getByRole('heading', { name: '编辑需求' })).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('Launch FAQ'), {
      target: { value: 'Launch FAQ Updated' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(mockApi.updateRequirement).toHaveBeenCalledWith(1, expect.objectContaining({ title: 'Launch FAQ Updated' })))

    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    await waitFor(() => expect(mockApi.deleteRequirement).toHaveBeenCalledWith(1))
  })

  it('renders execution surface', async () => {
    render(
      <MemoryRouter>
        <ExecutionsPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getExecutions).toHaveBeenCalled())
    expect(screen.getByText('执行列表')).toBeInTheDocument()
    expect(screen.getByText('Execution #11')).toBeInTheDocument()
  })

  it('renders release surface', async () => {
    render(
      <MemoryRouter>
        <ReleasesPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getReleaseCandidates).toHaveBeenCalled())
    expect(screen.getByText('发布列表')).toBeInTheDocument()
    expect(screen.getByText(/Launch FAQ/)).toBeInTheDocument()
  })

  it('renders error surface', async () => {
    render(
      <MemoryRouter>
        <ErrorsPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getErrors).toHaveBeenCalled())
    expect(screen.getByText('错误列表')).toBeInTheDocument()
    expect(screen.getByText('Synapse Gateway')).toBeInTheDocument()
  })
})
