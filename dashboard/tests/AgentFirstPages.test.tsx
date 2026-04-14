import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirementPool from '../src/pages/RequirementPool'
import ExecutionsPage from '../src/pages/ExecutionsPage'
import ReleasesPage from '../src/pages/ReleasesPage'

const mockApi = {
  getRequirements: vi.fn(),
  createRequirement: vi.fn(),
  submitRequirement: vi.fn(),
  createExecution: vi.fn(),
  getExecutions: vi.fn(),
  startExecution: vi.fn(),
  getReleaseCandidates: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    createRequirement: (...args: unknown[]) => mockApi.createRequirement(...args),
    submitRequirement: (...args: unknown[]) => mockApi.submitRequirement(...args),
    createExecution: (...args: unknown[]) => mockApi.createExecution(...args),
    getExecutions: (...args: unknown[]) => mockApi.getExecutions(...args),
    startExecution: (...args: unknown[]) => mockApi.startExecution(...args),
    getReleaseCandidates: (...args: unknown[]) => mockApi.getReleaseCandidates(...args),
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
  })

  it('renders requirement surface', async () => {
    render(
      <MemoryRouter>
        <RequirementPool />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.getByText('需求面')).toBeInTheDocument()
    expect(screen.getByText('Launch FAQ')).toBeInTheDocument()
  })

  it('renders execution surface', async () => {
    render(
      <MemoryRouter>
        <ExecutionsPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getExecutions).toHaveBeenCalled())
    expect(screen.getByText('执行面')).toBeInTheDocument()
    expect(screen.getByText('Execution #11')).toBeInTheDocument()
  })

  it('renders release surface', async () => {
    render(
      <MemoryRouter>
        <ReleasesPage />
      </MemoryRouter>,
    )
    await waitFor(() => expect(mockApi.getReleaseCandidates).toHaveBeenCalled())
    expect(screen.getByText('发布面')).toBeInTheDocument()
    expect(screen.getByText(/Launch FAQ/)).toBeInTheDocument()
  })
})
