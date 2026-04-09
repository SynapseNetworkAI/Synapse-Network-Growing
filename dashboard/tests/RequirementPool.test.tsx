import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import RequirementPool from '../src/pages/RequirementPool'

const mockApi = {
  getRequirements: vi.fn(),
  getRequirement: vi.fn(),
  createRequirement: vi.fn(),
  planRequirement: vi.fn(),
  startRequirement: vi.fn(),
  reviseRequirement: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    createRequirement: (...args: unknown[]) => mockApi.createRequirement(...args),
    planRequirement: (...args: unknown[]) => mockApi.planRequirement(...args),
    startRequirement: (...args: unknown[]) => mockApi.startRequirement(...args),
    reviseRequirement: (...args: unknown[]) => mockApi.reviseRequirement(...args),
  },
}))

const BLOCKER = {
  id: 2,
  title: 'Shared data contract',
  description_markdown: 'Finish the upstream shared contract first.',
  status: 'done',
  priority: 'normal',
  source: 'manual',
  source_ref: null,
  current_plan_version: 1,
  blocked_by_count: 0,
  active_workflow_run_id: 5,
  started_at: '2026-04-10T00:00:00Z',
  completed_at: '2026-04-10T00:05:00Z',
  created_at: '2026-04-10T00:00:00Z',
  updated_at: '2026-04-10T00:05:00Z',
}

const REQUIREMENT = {
  id: 1,
  title: 'Launch FAQ quality gate',
  description_markdown: 'Validate the launch FAQ output until checks pass.',
  status: 'in_progress',
  priority: 'high',
  source: 'manual',
  source_ref: null,
  current_plan_version: 1,
  blocked_by_count: 0,
  active_workflow_run_id: 7,
  started_at: '2026-04-10T00:00:00Z',
  completed_at: null,
  created_at: '2026-04-10T00:00:00Z',
  updated_at: '2026-04-10T00:00:10Z',
}

const DETAIL = {
  requirement: REQUIREMENT,
  workflow_run: {
    id: 7,
    requirement_id: 1,
    plan_version: 1,
    status: 'running',
    triggered_by: 'user',
    planner_artifact_id: 9,
    started_at: '2026-04-10T00:00:00Z',
    completed_at: null,
    created_at: '2026-04-10T00:00:00Z',
    updated_at: '2026-04-10T00:00:10Z',
    steps: [
      {
        id: 11,
        workflow_run_id: 7,
        requirement_id: 1,
        step_key: 'implementation',
        step_type: 'implementation',
        title: 'Implement requirement',
        status: 'completed',
        sequence_no: 10,
        assigned_agent_id: 'content_writer',
        assigned_workflow_role: 'implementer',
        branch_from_step_id: null,
        compatibility_task_id: 21,
        retry_count: 0,
        handoff_summary_markdown: null,
        done_when_markdown: 'Output is ready for review.',
        started_at: '2026-04-10T00:00:00Z',
        completed_at: '2026-04-10T00:00:05Z',
      },
      {
        id: 12,
        workflow_run_id: 7,
        requirement_id: 1,
        step_key: 'test',
        step_type: 'test',
        title: 'Validate output',
        status: 'failed',
        sequence_no: 30,
        assigned_agent_id: 'seo_strategist',
        assigned_workflow_role: 'tester',
        branch_from_step_id: null,
        compatibility_task_id: 22,
        retry_count: 0,
        handoff_summary_markdown: null,
        done_when_markdown: 'Validation passes.',
        started_at: '2026-04-10T00:00:06Z',
        completed_at: '2026-04-10T00:00:08Z',
      },
      {
        id: 13,
        workflow_run_id: 7,
        requirement_id: 1,
        step_key: 'bugfix-12',
        step_type: 'bugfix',
        title: 'Bugfix after test failure',
        status: 'running',
        sequence_no: 50,
        assigned_agent_id: 'content_writer',
        assigned_workflow_role: 'bugfixer',
        branch_from_step_id: 12,
        compatibility_task_id: 23,
        retry_count: 0,
        handoff_summary_markdown: null,
        done_when_markdown: 'Fix is ready for re-review.',
        started_at: '2026-04-10T00:00:09Z',
        completed_at: null,
      },
    ],
  },
  dependencies: [
    {
      id: 1,
      requirement_id: 1,
      depends_on_requirement_id: 2,
      depends_on_title: 'Shared data contract',
      depends_on_status: 'done',
      dependency_type: 'hard_block',
    },
  ],
  acceptance_checks: [
    {
      id: 1,
      requirement_id: 1,
      check_key: 'review_passed',
      description: 'Review passes',
      check_type: 'manual_review',
      owner_role: 'reviewer',
      status: 'passed',
      success_criteria_markdown: null,
      verified_by_step_id: 11,
      evidence_artifact_id: 30,
      created_at: '2026-04-10T00:00:00Z',
      updated_at: '2026-04-10T00:00:05Z',
    },
    {
      id: 2,
      requirement_id: 1,
      check_key: 'validation_passed',
      description: 'Validation passes',
      check_type: 'content_assertion',
      owner_role: 'tester',
      status: 'failed',
      success_criteria_markdown: null,
      verified_by_step_id: 12,
      evidence_artifact_id: 31,
      created_at: '2026-04-10T00:00:00Z',
      updated_at: '2026-04-10T00:00:08Z',
    },
  ],
  artifacts: [
    {
      id: 31,
      requirement_id: 1,
      workflow_run_id: 7,
      step_id: 12,
      producer_step_id: 12,
      artifact_type: 'bug_report',
      path: null,
      content_summary: 'Validation failed in the FAQ flow.',
      human_readable_body: 'Validation failed in the FAQ flow.',
      machine_readable_payload: '{}',
      created_at: '2026-04-10T00:00:08Z',
    },
  ],
}

describe('RequirementPool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getRequirements.mockResolvedValue([REQUIREMENT, BLOCKER])
    mockApi.getRequirement.mockResolvedValue(DETAIL)
    mockApi.createRequirement.mockResolvedValue(DETAIL)
    mockApi.planRequirement.mockResolvedValue(DETAIL)
    mockApi.startRequirement.mockResolvedValue(DETAIL)
    mockApi.reviseRequirement.mockResolvedValue(DETAIL)
  })

  it('renders requirement list and detail panels', async () => {
    render(<RequirementPool />)

    await waitFor(() => {
      expect(screen.getByTestId('requirements-page')).toBeDefined()
      expect(screen.getByTestId('requirement-card-1')).toBeDefined()
    })

    await waitFor(() => {
      expect(screen.getByTestId('workflow-steps-panel')).toBeDefined()
      expect(screen.getByTestId('workflow-step-13')).toHaveTextContent('Bugfix after test failure')
    })
    expect(screen.getByTestId('dependencies-panel')).toHaveTextContent('Shared data contract')
  })

  it('creates a new requirement', async () => {
    render(<RequirementPool />)

    // Wait for requirements to load so dependency candidates are available
    await waitFor(() => {
      expect(screen.getByTestId('requirement-card-1')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('create-requirement-btn'))
    fireEvent.change(screen.getByTestId('requirement-title'), { target: { value: 'New requirement' } })
    fireEvent.change(screen.getByTestId('requirement-description'), { target: { value: '## Goal\n\nShip it.' } })
    fireEvent.change(screen.getByTestId('requirement-priority'), { target: { value: 'high' } })
    fireEvent.click(screen.getByTestId('create-dependency-2'))
    fireEvent.click(screen.getByTestId('submit-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.createRequirement).toHaveBeenCalledWith({
        title: 'New requirement',
        description_markdown: '## Goal\n\nShip it.',
        priority: 'high',
        depends_on_requirement_ids: [2],
        auto_start: true,
      })
    })
  })

  it('plans and starts a requirement', async () => {
    // Use a draft requirement so the plan button is not disabled
    const draftReq = { ...REQUIREMENT, status: 'draft' }
    const draftDetail = { ...DETAIL, requirement: draftReq }
    mockApi.getRequirements.mockResolvedValue([draftReq, BLOCKER])
    mockApi.getRequirement.mockResolvedValue(draftDetail)
    mockApi.planRequirement.mockResolvedValue(draftDetail)
    mockApi.startRequirement.mockResolvedValue(draftDetail)

    render(<RequirementPool />)

    await waitFor(() => {
      expect(screen.getByTestId('plan-requirement-btn')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('plan-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.planRequirement).toHaveBeenCalledWith(1)
    })

    fireEvent.click(screen.getByTestId('start-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.startRequirement).toHaveBeenCalledWith(1)
    })
  })

  it('submits a requirement revision', async () => {
    render(<RequirementPool />)

    await waitFor(() => {
      expect(screen.getByTestId('toggle-revise-btn')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('toggle-revise-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('revise-description')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('revise-description'), { target: { value: '## Revised\n\nClarify acceptance criteria.' } })
    fireEvent.change(screen.getByTestId('revise-note'), { target: { value: 'Reviewer flagged ambiguous acceptance criteria.' } })
    fireEvent.click(screen.getByTestId('submit-revision-btn'))

    await waitFor(() => {
      expect(mockApi.reviseRequirement).toHaveBeenCalledWith(1, {
        title: 'Launch FAQ quality gate',
        description_markdown: '## Revised\n\nClarify acceptance criteria.',
        revision_note: 'Reviewer flagged ambiguous acceptance criteria.',
        source_ref: null,
        depends_on_requirement_ids: [2],
      })
    })
  })
})