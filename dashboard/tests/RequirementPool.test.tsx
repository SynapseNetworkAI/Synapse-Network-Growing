import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirementPool from '../src/pages/RequirementPool'

const mockApi = {
  getRequirements: vi.fn(),
  getRequirementScheduler: vi.fn(),
  getProjectPolicies: vi.fn(),
  rebalanceRequirementScheduler: vi.fn(),
  getRequirement: vi.fn(),
  createRequirement: vi.fn(),
  planRequirement: vi.fn(),
  startRequirement: vi.fn(),
  pauseRequirement: vi.fn(),
  deleteRequirement: vi.fn(),
  advanceQueue: vi.fn(),
  reviseRequirement: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    getRequirementScheduler: (...args: unknown[]) => mockApi.getRequirementScheduler(...args),
    getProjectPolicies: (...args: unknown[]) => mockApi.getProjectPolicies(...args),
    rebalanceRequirementScheduler: (...args: unknown[]) => mockApi.rebalanceRequirementScheduler(...args),
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    createRequirement: (...args: unknown[]) => mockApi.createRequirement(...args),
    planRequirement: (...args: unknown[]) => mockApi.planRequirement(...args),
    startRequirement: (...args: unknown[]) => mockApi.startRequirement(...args),
    pauseRequirement: (...args: unknown[]) => mockApi.pauseRequirement(...args),
    deleteRequirement: (...args: unknown[]) => mockApi.deleteRequirement(...args),
    advanceQueue: (...args: unknown[]) => mockApi.advanceQueue(...args),
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
  intake_metadata: {},
  target_project_path: null,
  acceptance_contract: {},
  approval_status: 'approved',
  approval_contract: {},
  approval_requested_at: null,
  approved_at: '2026-04-10T00:00:00Z',
  current_plan_version: 1,
  blocked_by_count: 0,
  active_workflow_run_id: 5,
  started_at: '2026-04-10T00:00:00Z',
  completed_at: '2026-04-10T00:05:00Z',
  created_at: '2026-04-10T00:00:00Z',
  updated_at: '2026-04-10T00:05:00Z',
  routing_context: {
    routing_mode: 'unrouted',
    target_project_path: null,
    summary: 'Requirement is not routed to a managed project yet.',
    automation_ready: false,
    readiness_status: 'unrouted',
    routed_project_keys: [],
    routed_display_names: [],
    skipped_project_keys: [],
    project_scorecards: [],
  },
  score_breakdown: {
    total: 18,
    priority: 10,
    aging: 8,
    status_adjustment: -100,
    blocker_penalty: 0,
    readiness_adjustment: 0,
    bug_pressure: 0,
    delivery_pressure: 0,
    automation_gap: 0,
  },
}

const REQUIREMENT = {
  id: 1,
  title: 'Launch FAQ quality gate',
  description_markdown: 'Validate the launch FAQ output until checks pass.',
  status: 'in_progress',
  priority: 'high',
  source: 'manual',
  source_ref: null,
  intake_metadata: {},
  target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing\n/Users/cliff/workspace/agent/Synapse-Network',
  acceptance_contract: {},
  approval_status: 'approved',
  approval_contract: {},
  approval_requested_at: null,
  approved_at: '2026-04-10T00:00:00Z',
  current_plan_version: 1,
  blocked_by_count: 0,
  active_workflow_run_id: 7,
  started_at: '2026-04-10T00:00:00Z',
  completed_at: null,
  created_at: '2026-04-10T00:00:00Z',
  updated_at: '2026-04-10T00:00:10Z',
  routing_context: {
    routing_mode: 'explicit',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing\n/Users/cliff/workspace/agent/Synapse-Network',
    summary: 'Explicit target project routing. Projects: Synapse-Network-Growing, Synapse-Network.',
    automation_ready: true,
    readiness_status: 'ready',
    routed_project_keys: ['synapse-network-growing', 'synapse-network'],
    routed_display_names: ['Synapse-Network-Growing', 'Synapse-Network'],
    skipped_project_keys: [],
    project_scorecards: [
      {
        project_key: 'synapse-network-growing',
        display_name: 'Synapse-Network-Growing',
        root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        policy_status: 'active',
        release_mode: 'manual',
        requires_manual_approval: true,
        readiness_status: 'ready',
        readiness_score: 100,
        automation_ready: true,
        onboarding_present: true,
        active_requirement_count: 1,
        completed_requirement_count: 2,
        total_requirement_count: 3,
        bug_report_count: 1,
        blocked_publish_count: 0,
        validation_pass_rate: 0.67,
        automation_coverage: 0.67,
        notes: 'Control plane repo.',
        agents_memory_namespace: 'synapse-network-growing',
      },
    ],
  },
  score_breakdown: {
    total: 72,
    priority: 30,
    aging: 30,
    status_adjustment: 0,
    blocker_penalty: 0,
    readiness_adjustment: 10,
    bug_pressure: 6,
    delivery_pressure: 0,
    automation_gap: -4,
  },
}

const PAUSED_REQUIREMENT = {
  ...REQUIREMENT,
  status: 'paused',
  updated_at: '2026-04-10T00:00:12Z',
}

const DELETED_REQUIREMENT = {
  ...REQUIREMENT,
  id: 4,
  title: 'Archived launch QA',
  status: 'deleted',
  updated_at: '2026-04-10T00:00:15Z',
}

const READY_REQUIREMENT = {
  ...BLOCKER,
  id: 3,
  title: 'Queue next launch review',
  status: 'ready',
  current_plan_version: 1,
  active_workflow_run_id: null,
  completed_at: null,
  created_at: '2026-04-10T00:06:00Z',
  updated_at: '2026-04-10T00:06:00Z',
  routing_context: {
    routing_mode: 'auto',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Sdk',
    summary: 'Auto-routed requirement to matching managed projects. Projects: Synapse-Network-Sdk.',
    automation_ready: true,
    readiness_status: 'policy_only',
    routed_project_keys: ['synapse-network-sdk'],
    routed_display_names: ['Synapse-Network-Sdk'],
    skipped_project_keys: [],
    project_scorecards: [],
  },
  score_breakdown: {
    total: 54,
    priority: 10,
    aging: 30,
    status_adjustment: 0,
    blocker_penalty: 0,
    readiness_adjustment: 6,
    bug_pressure: 0,
    delivery_pressure: 0,
    automation_gap: 8,
  },
}

const UNPLANNED_REQUIREMENT = {
  ...READY_REQUIREMENT,
  id: 5,
  title: 'Incident recovery follow-up',
  current_plan_version: 0,
  active_workflow_run_id: null,
}

const PENDING_APPROVAL_REQUIREMENT = {
  ...READY_REQUIREMENT,
  id: 6,
  title: 'Pending approval rollout',
  approval_status: 'pending_approval',
  approval_contract: {
    approval_mode: 'auto_or_human',
  },
  approval_requested_at: '2026-04-10T00:06:00Z',
  approved_at: null,
}

function makeRequirement(id: number, title: string) {
  return {
    ...BLOCKER,
    id,
    title,
    created_at: `2026-04-10T00:${String(id).padStart(2, '0')}:00Z`,
    updated_at: `2026-04-10T00:${String(id).padStart(2, '0')}:30Z`,
  }
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
  delivery_state: null,
}

const SCHEDULER_PLAN = {
  global_capacity: 3,
  active_count: 1,
  available_slots: 2,
  generated_at: '2026-04-10T00:00:10Z',
  project_states: [
    {
      project_key: 'synapse-network-growing',
      display_name: 'Synapse-Network-Growing',
      root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
      active_count: 1,
      queued_count: 0,
      max_parallel_requirements: 1,
      autonomy_mode: 'execute_autonomously',
      allow_rebalance: true,
      allow_preemption: true,
      scheduler_weight: 1.2,
      portfolio_budget_points: 140,
      budget_used: 26,
      budget_remaining: 114,
      readiness_status: 'ready',
      readiness_score: 100,
    },
    {
      project_key: 'synapse-network-sdk',
      display_name: 'Synapse-Network-Sdk',
      root_path: '/Users/cliff/workspace/agent/Synapse-Network-Sdk',
      active_count: 0,
      queued_count: 1,
      max_parallel_requirements: 1,
      autonomy_mode: 'execute_autonomously',
      allow_rebalance: true,
      allow_preemption: true,
      scheduler_weight: 1.1,
      portfolio_budget_points: 95,
      budget_used: 0,
      budget_remaining: 95,
      readiness_status: 'policy_only',
      readiness_score: 70,
    },
  ],
  decisions: [
    {
      candidate_type: 'requirement',
      action: 'running',
      requirement_id: 1,
      signal_id: null,
      title: 'Launch FAQ quality gate',
      project_key: 'synapse-network-growing',
      project_display_name: 'Synapse-Network-Growing',
      score: 74,
      base_score: 72,
      scheduler_weight: 1.2,
      autonomy_mode: 'execute_autonomously',
      budget_cost: 26,
      project_slot_available: false,
      reason: 'currently running',
      reasons: ['currently running'],
      template_key: null,
      source: 'manual',
      preempt_requirement_id: null,
      approval_required: false,
    },
    {
      candidate_type: 'requirement',
      action: 'start',
      requirement_id: 3,
      signal_id: null,
      title: 'Queue next launch review',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      score: 63,
      base_score: 54,
      scheduler_weight: 1.1,
      autonomy_mode: 'execute_autonomously',
      budget_cost: 22,
      project_slot_available: true,
      reason: 'scheduled in current capacity window',
      reasons: ['base score 54', 'project weight 1.1', 'scheduled in current capacity window'],
      template_key: null,
      source: 'manual',
      preempt_requirement_id: null,
      approval_required: false,
    },
  ],
  started_ids: [],
  created_requirement_ids: [],
  preempted_ids: [],
  rebalanced_ids: [],
  skipped: [],
}

const PROJECT_POLICIES = [
  {
    id: 1,
    project_key: 'synapse-network-growing',
    display_name: 'Synapse-Network-Growing',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    status: 'active',
    allowed_write_globs: ['**'],
    forbidden_globs: ['.git/**'],
    required_checks: ['pytest -q'],
    release_mode: 'manual',
    requires_manual_approval: true,
    autonomy_mode: 'execute_autonomously',
    allow_rebalance: true,
    allow_preemption: true,
    capability_matrix: {
      shell_access: true,
      git_read: true,
      git_write: true,
      git_push: false,
      network_access: true,
      publish: false,
    },
    interrupt_policy: {
      operator_confirmation_actions: ['git_push', 'publish'],
      auto_pause_on_events: ['capability_denied'],
      auto_abort_on_events: ['forbidden_write'],
    },
    scheduler_weight: 1.2,
    max_parallel_requirements: 1,
    portfolio_budget_points: 140,
    notes: 'Control plane repo.',
    created_at: '2026-04-10T00:00:00Z',
    updated_at: '2026-04-10T00:00:00Z',
  },
  {
    id: 2,
    project_key: 'synapse-network',
    display_name: 'Synapse-Network',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network',
    status: 'active',
    allowed_write_globs: ['**'],
    forbidden_globs: ['.git/**'],
    required_checks: ['pytest -q'],
    release_mode: 'manual',
    requires_manual_approval: true,
    autonomy_mode: 'execute_with_approval',
    allow_rebalance: true,
    allow_preemption: false,
    capability_matrix: {
      shell_access: true,
      git_read: true,
      git_write: true,
      git_push: false,
      network_access: false,
      publish: false,
    },
    interrupt_policy: {
      operator_confirmation_actions: ['git_push', 'publish'],
      auto_pause_on_events: ['capability_denied'],
      auto_abort_on_events: ['forbidden_write'],
    },
    scheduler_weight: 1.4,
    max_parallel_requirements: 1,
    portfolio_budget_points: 130,
    notes: 'Primary product repo.',
    created_at: '2026-04-10T00:00:00Z',
    updated_at: '2026-04-10T00:00:00Z',
  },
]

describe('RequirementPool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getRequirements.mockResolvedValue([REQUIREMENT, BLOCKER])
    mockApi.getRequirementScheduler.mockResolvedValue(SCHEDULER_PLAN)
    mockApi.getProjectPolicies.mockResolvedValue(PROJECT_POLICIES)
    mockApi.rebalanceRequirementScheduler.mockResolvedValue(SCHEDULER_PLAN)
    mockApi.getRequirement.mockResolvedValue(DETAIL)
    mockApi.createRequirement.mockResolvedValue(DETAIL)
    mockApi.planRequirement.mockResolvedValue(DETAIL)
    mockApi.startRequirement.mockResolvedValue(DETAIL)
    mockApi.pauseRequirement.mockResolvedValue({ ...DETAIL, requirement: PAUSED_REQUIREMENT })
    mockApi.deleteRequirement.mockResolvedValue({ ...DETAIL, requirement: DELETED_REQUIREMENT })
    mockApi.advanceQueue.mockResolvedValue({ skipped: 'no ready requirements' })
    mockApi.reviseRequirement.mockResolvedValue(DETAIL)
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('renders requirement list', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirements-page')).toBeDefined()
      expect(screen.getByTestId('requirement-card-1')).toBeDefined()
      expect(screen.getByText('目标项目:')).toBeDefined()
      expect(screen.getByTestId('scheduler-panel')).toBeDefined()
    })

    expect(screen.getByText(/路由: explicit \/ readiness: ready/)).toBeDefined()
    expect(screen.getByText('Score: 72')).toBeDefined()
    expect(screen.getByText(/Multi-Project Scheduler/)).toBeDefined()
    expect(screen.getByText(/全局槽位 1\/3/)).toBeDefined()
    expect(screen.getAllByText(/autonomy: execute_autonomously/).length).toBeGreaterThan(0)
    expect(screen.getByText(/budget: 26\/140/)).toBeDefined()
  })

  it('creates a new requirement', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    // Wait for requirements to load so dependency candidates are available
    await waitFor(() => {
      expect(screen.getByTestId('requirement-card-1')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('create-requirement-btn'))
    fireEvent.change(screen.getByTestId('requirement-title'), { target: { value: 'New requirement' } })
    fireEvent.change(screen.getByTestId('requirement-description'), { target: { value: '## Goal\n\nShip it.' } })
    fireEvent.change(screen.getByTestId('requirement-priority'), { target: { value: 'high' } })
    fireEvent.focus(screen.getByTestId('create-dependency-search'))
    fireEvent.mouseDown(screen.getByTestId('create-dependency-2'))
    fireEvent.click(screen.getByTestId('submit-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.createRequirement).toHaveBeenCalledWith({
        title: 'New requirement',
        description_markdown: '## Goal\n\nShip it.',
        priority: 'high',
        target_project_path: undefined,
        depends_on_requirement_ids: [2],
        auto_start: true,
      })
    })
  })

  it('shows approval badge and blocks start for pending requirement approvals', async () => {
    mockApi.getRequirements.mockResolvedValue([PENDING_APPROVAL_REQUIREMENT])

    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-card-6')).toBeDefined()
    })

    expect(screen.getByTestId('requirement-approval-badge-6')).toHaveTextContent('待审批')
    expect(screen.getByTestId('requirement-toggle-6')).toBeDisabled()
  })

  it('creates a requirement from selected managed project policies', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-card-1')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('create-requirement-btn'))
    fireEvent.change(screen.getByTestId('requirement-title'), { target: { value: 'Managed requirement' } })
    fireEvent.change(screen.getByTestId('requirement-description'), { target: { value: 'Use managed projects.' } })
    fireEvent.click(screen.getByTestId('requirement-target-policy-1'))
    fireEvent.click(screen.getByTestId('requirement-target-policy-2'))
    fireEvent.click(screen.getByTestId('submit-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.createRequirement).toHaveBeenCalledWith(expect.objectContaining({
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing\n/Users/cliff/workspace/agent/Synapse-Network',
      }))
    })
  })

  it('toggles running requirement from pause to start', async () => {
    mockApi.getRequirements
      .mockResolvedValueOnce([REQUIREMENT, BLOCKER])
      .mockResolvedValueOnce([REQUIREMENT, BLOCKER])
      .mockResolvedValueOnce([PAUSED_REQUIREMENT, BLOCKER])

    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-toggle-1').textContent).toBe('暂停')
    })

    fireEvent.click(screen.getByTestId('requirement-toggle-1'))

    await waitFor(() => {
      expect(mockApi.pauseRequirement).toHaveBeenCalledWith(1)
      expect(screen.getByTestId('requirement-toggle-1').textContent).toBe('启动')
    })
  })

  it('includes deleted status filter and renders both target projects', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByRole('option', { name: '已暂停' })).toBeDefined()
      expect(screen.getByRole('option', { name: '已删除' })).toBeDefined()
      expect(screen.getByText('/Users/cliff/workspace/agent/Synapse-Network-Growing')).toBeDefined()
      expect(screen.getByText('/Users/cliff/workspace/agent/Synapse-Network')).toBeDefined()
    })
  })

  it('soft deletes a requirement from the pool', async () => {
    mockApi.getRequirements
      .mockResolvedValueOnce([REQUIREMENT, BLOCKER])
      .mockResolvedValueOnce([REQUIREMENT, BLOCKER])
      .mockResolvedValueOnce([DELETED_REQUIREMENT, BLOCKER])

    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-delete-1')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('requirement-delete-1'))

    await waitFor(() => {
      expect(mockApi.deleteRequirement).toHaveBeenCalledWith(1)
      expect(screen.getByText('已删除')).toBeDefined()
    })
  })

  it('sorts running requirements first and deleted requirements last', async () => {
    mockApi.getRequirements.mockResolvedValue([DELETED_REQUIREMENT, READY_REQUIREMENT, REQUIREMENT, BLOCKER])

    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-card-1')).toBeDefined()
      expect(screen.getByTestId('requirement-card-3')).toBeDefined()
    })

    const cardIds = Array.from(document.querySelectorAll('[data-testid^="requirement-card-"]'))
      .map((element) => element.getAttribute('data-testid'))

    expect(cardIds).toEqual([
      'requirement-card-1',
      'requirement-card-3',
      'requirement-card-2',
      'requirement-card-4',
    ])
  })

  it('uses score sort mode when loading requirements', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(mockApi.getRequirements).toHaveBeenCalledWith(undefined, 'score', undefined)
    })

    fireEvent.change(screen.getByTestId('requirement-sort-mode'), { target: { value: 'updated' } })

    await waitFor(() => {
      expect(mockApi.getRequirements).toHaveBeenCalledWith(undefined, undefined, undefined)
    })
  })

  it('sends requirement search query to backend', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-search')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('requirement-search'), { target: { value: 'session not found' } })

    await waitFor(() => {
      expect(mockApi.getRequirements).toHaveBeenCalledWith(undefined, 'score', 'session not found')
    })
  })

  it('shows pending-planning requirements as 待规划 and allows direct start', async () => {
    mockApi.getRequirements.mockResolvedValue([UNPLANNED_REQUIREMENT])

    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirement-card-5')).toBeDefined()
    })

    expect(screen.getByText('待规划')).toBeDefined()
    expect(screen.getByText('待生成 workflow plan')).toBeDefined()

    fireEvent.click(screen.getByTestId('requirement-toggle-5'))

    await waitFor(() => {
      expect(mockApi.startRequirement).toHaveBeenCalledWith(5)
    })
  })

  it('keeps the current pagination page after reloading pool data', async () => {
    const pagedRequirements = Array.from({ length: 11 }, (_, index) =>
      makeRequirement(index + 10, `Requirement ${index + 1}`),
    )
    mockApi.getRequirements.mockResolvedValue(pagedRequirements)

    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('requirements-pagination')).toBeDefined()
    })

    const pagination = screen.getByTestId('requirements-pagination')
    fireEvent.click(within(pagination).getByRole('button', { name: '2' }))

    await waitFor(() => {
      expect(screen.getByText('11–11 / 11 条需求')).toBeDefined()
      expect(screen.getByTestId('requirement-card-10')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('scheduler-advance-btn'))

    await waitFor(() => {
      expect(mockApi.advanceQueue).toHaveBeenCalled()
      expect(screen.getByText('11–11 / 11 条需求')).toBeDefined()
      expect(screen.getByTestId('requirement-card-10')).toBeDefined()
    })
  })


})
