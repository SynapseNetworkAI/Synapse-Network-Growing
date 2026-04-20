// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlanningPage from './PlanningPage'

const apiMock = vi.hoisted(() => ({
  getPlanningMissionControl: vi.fn(),
  getPlanningManifestHistory: vi.fn(),
  saveActivePlanningManifest: vi.fn(),
  runPlannerSweep: vi.fn(),
  archiveAndStartPlanningCycle: vi.fn(),
  dropPlanningGoal: vi.fn(),
  approveRequirementCandidate: vi.fn(),
  approveAndRunRequirementCandidate: vi.fn(),
  rejectRequirementCandidate: vi.fn(),
  materializeRequirementCandidate: vi.fn(),
  getPlanningGoal: vi.fn(),
  getPlanningGoalTrace: vi.fn(),
  createPlanningGoal: vi.fn(),
  updatePlanningGoal: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

const manifest = {
  id: 1,
  manifest_key: 'manifest-test',
  version_name: 'Mission Control Cycle',
  cycle_label: '2026-W17',
  status: 'active',
  revision: 2,
  payload: {
    focus_weights: { reliability: 0.6, growth: 0.25, support: 0.15 },
    global_budget: { daily_usd_limit: 25, max_concurrent_workers: 2 },
    global_constraints: ['No production deploy without human approval.'],
  },
  goal_count: 2,
  active_goal_count: 2,
  dropped_goal_count: 0,
  achieved_goal_count: 0,
  review_summary: {},
  change_log: [],
  created_by: 'operator',
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  archived_at: null,
}

const reliabilityGoal = {
  id: 101,
  manifest_id: 1,
  goal_key: 'gateway_reliability',
  title: 'Gateway reliability',
  intent_excerpt: 'Keep gateway healthy.',
  success_metric: '5xx < 1%',
  domain: 'reliability',
  status: 'active',
  workflow_key: 'gateway_reliability_repair',
  project_key: 'synapse',
  priority: 'normal',
  risk_level: 'normal',
  weight: 0.6,
  acceptance_kind: 'business',
  execution_acceptance_steps: [],
  metadata: {},
  closed_at: null,
  review_note: null,
  drop_decision: {},
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
}

const growthGoal = {
  id: 102,
  manifest_id: 1,
  goal_key: 'operator_growth',
  title: 'Operator growth',
  intent_excerpt: 'Find growth work.',
  success_metric: 'approved candidate throughput',
  domain: 'growth',
  status: 'active',
  workflow_key: 'agent_self_repair',
  project_key: 'synapse',
  priority: 'normal',
  risk_level: 'normal',
  weight: 0.25,
  acceptance_kind: 'business',
  execution_acceptance_steps: [],
  metadata: {},
  closed_at: null,
  review_note: null,
  drop_decision: {},
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
}

const achievedGoal = {
  ...growthGoal,
  id: 103,
  goal_key: 'completed_lint_contracts',
  title: 'Completed lint contracts',
  intent_excerpt: 'Historical contract work already shipped.',
  success_metric: 'contract checks shipped',
  domain: 'ops',
  status: 'achieved',
  weight: 0.1,
}

const droppedGoal = {
  ...growthGoal,
  id: 104,
  goal_key: 'retired_gateway_idea',
  title: 'Retired gateway idea',
  intent_excerpt: 'Dropped historical gateway work.',
  success_metric: 'not pursued',
  domain: 'reliability',
  status: 'dropped',
  weight: 0.05,
}

const reliabilityCandidate = {
  id: 10,
  manifest_id: 1,
  goal_key: 'gateway_reliability',
  candidate_fingerprint: 'fp-10',
  title: 'Add gateway precision guardrail',
  description_markdown: 'Guardrail belongs under reliability.',
  project_id: 1,
  project_key: 'synapse',
  workflow_key: 'gateway_reliability_repair',
  priority: 'normal',
  risk_level: 'normal',
  confidence: 0.82,
  rationale: 'Reliability goal has capacity.',
  expected_evidence: [],
  status: 'pending',
  suppression_reason: null,
  reject_reason: null,
  reject_comment: null,
  approved_by: null,
  materialized_requirement_id: null,
  metadata: {},
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  approved_at: null,
  rejected_at: null,
}

const materializedCandidate = {
  ...reliabilityCandidate,
  id: 11,
  candidate_fingerprint: 'fp-11',
  title: 'Weaponize self-repair lint and architecture contract gates',
  description_markdown: 'This long materialized markdown should not be visible in the mission lane.',
  status: 'materialized',
  materialized_requirement_id: 6,
  confidence: 0.89,
  metadata: {
    generated_by: 'planner_agent_v1',
    auto_run_status: 'workflow_completed',
  },
  updated_at: '2026-04-19T01:00:00Z',
}

const validationFailedCandidate = {
  ...reliabilityCandidate,
  id: 12,
  candidate_fingerprint: 'fp-12',
  title: 'Unsafe planner output draft',
  description_markdown: 'Raw planner output with verbose markdown should stay behind details.',
  status: 'validation_failed',
  materialized_requirement_id: null,
  suppression_reason: 'acceptance_validation_failed',
  confidence: 0.66,
  metadata: {
    generated_by: 'planner_agent_v1',
    acceptance_validation_error: "required command 'python -m ruff check' is not in the safe command allowlist.",
  },
  updated_at: '2026-04-19T02:00:00Z',
}

const duplicateValidationFailedCandidate = {
  ...validationFailedCandidate,
  id: 13,
  candidate_fingerprint: 'fp-13',
  title: 'Unsafe planner output retry',
  updated_at: '2026-04-19T03:00:00Z',
}

const mission = {
  manifest,
  global_steering: {
    focus_weights: { reliability: 0.6, growth: 0.25, support: 0.15 },
    global_budget: { daily_usd_limit: 25, max_concurrent_workers: 2 },
    global_constraints: ['No production deploy without human approval.'],
  },
  goal_lanes: [
    {
      goal_key: 'gateway_reliability',
      goal: reliabilityGoal,
      rollup: {
        manifest_id: 1,
        goal_key: 'gateway_reliability',
        goal: reliabilityGoal,
        candidate_status_counts: { pending: 1, materialized: 1, validation_failed: 1 },
        requirement_status_counts: {},
        workflow_status_counts: {},
        release_status_counts: {},
      },
      candidates: [reliabilityCandidate, materializedCandidate, validationFailedCandidate, duplicateValidationFailedCandidate],
    },
    {
      goal_key: 'operator_growth',
      goal: growthGoal,
      rollup: {
        manifest_id: 1,
        goal_key: 'operator_growth',
        goal: growthGoal,
        candidate_status_counts: {},
        requirement_status_counts: {},
        workflow_status_counts: {},
        release_status_counts: {},
      },
      candidates: [],
    },
    {
      goal_key: 'completed_lint_contracts',
      goal: achievedGoal,
      rollup: {
        manifest_id: 1,
        goal_key: 'completed_lint_contracts',
        goal: achievedGoal,
        candidate_status_counts: { materialized: 1 },
        requirement_status_counts: { completed: 1 },
        workflow_status_counts: { succeeded: 1 },
        release_status_counts: { pr_opened: 1 },
      },
      candidates: [],
    },
    {
      goal_key: 'retired_gateway_idea',
      goal: droppedGoal,
      rollup: {
        manifest_id: 1,
        goal_key: 'retired_gateway_idea',
        goal: droppedGoal,
        candidate_status_counts: { validation_failed: 1 },
        requirement_status_counts: {},
        workflow_status_counts: {},
        release_status_counts: {},
      },
      candidates: [],
    },
  ],
  candidate_totals: { pending: 1, approved: 0, materialized: 0, rejected: 0, suppressed: 0 },
  history_preview: { items: [manifest], total: 1, page: 1, page_size: 5, total_pages: 1 },
  last_sweep: null,
}

describe('PlanningPage Mission Control', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getPlanningMissionControl.mockResolvedValue(mission)
    apiMock.getPlanningManifestHistory.mockResolvedValue({ items: [manifest], total: 1, page: 1, page_size: 10, total_pages: 1 })
    apiMock.approveRequirementCandidate.mockResolvedValue({ ...reliabilityCandidate, status: 'approved' })
    apiMock.approveAndRunRequirementCandidate.mockResolvedValue({
      candidate: { ...reliabilityCandidate, status: 'materialized', materialized_requirement_id: 99 },
      requirement_id: 99,
      workflow_run_id: 7,
      workflow_status: 'succeeded',
      workflow_current_state: 'done',
      auto_run_status: 'workflow_completed',
      next_action: 'view_completion_evidence',
    })
    apiMock.getPlanningGoal.mockResolvedValue({
      ...reliabilityGoal,
      intent_markdown: '# Reliability PRD\n\nKeep gateway healthy with concrete checks.',
    })
    apiMock.getPlanningGoalTrace.mockResolvedValue({
      goal: { id: 101, goal_key: 'gateway_reliability', title: 'Gateway reliability', intent_present: true },
      nodes: [
        { kind: 'goal', status: 'ok', title: 'Goal PRD saved', summary: 'PRD exists', object_id: 101, deep_link: '/planning?goal=gateway_reliability', diagnostic: null, metadata: {} },
        { kind: 'candidate', status: 'ok', title: 'Candidate #10', summary: 'materialized', object_id: 10, deep_link: '/planning?candidate=10', diagnostic: null, metadata: { generated_by: 'planner_agent_v1' } },
      ],
      diagnostics: [],
      next_actions: [],
      history: [],
    })
    apiMock.updatePlanningGoal.mockResolvedValue({
      ...reliabilityGoal,
      intent_markdown: '# Updated PRD',
    })
    apiMock.createPlanningGoal.mockResolvedValue({
      ...growthGoal,
      id: 103,
      goal_key: 'new_goal',
      title: 'New goal',
      intent_markdown: '# New goal',
    })
  })

  it('defaults to mission control and groups candidates under their goal lane', async () => {
    render(<PlanningPage />)

    expect(await screen.findByTestId('mission-control-tab')).toBeTruthy()
    expect(screen.queryByTestId('raw-manifest-drawer')).toBeNull()

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    expect(lanes).toHaveLength(2)
    expect(within(lanes[0]).getByText('gateway_reliability')).toBeTruthy()
    expect(within(lanes[0]).getByText('Add gateway precision guardrail')).toBeTruthy()
    expect(within(lanes[0]).getByText('Candidates (1 Pending, 1 Materialized, 2 Failed)')).toBeTruthy()
    expect(within(lanes[1]).queryByText('Add gateway precision guardrail')).toBeNull()
  })

  it('renders materialized work and deduped fail-closed drafts as progressive disclosure', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    const reliabilityLane = lanes[0]

    expect(within(reliabilityLane).getByTestId('candidate-materialized')).toBeTruthy()
    expect(within(reliabilityLane).getByText('Materialized: Weaponize self-repair lint and architecture contract gates')).toBeTruthy()
    expect(within(reliabilityLane).getByRole('link', { name: 'Requirement #6' })).toBeTruthy()
    expect(within(reliabilityLane).getByTestId('planner-intercepts')).toBeTruthy()

    await user.click(within(reliabilityLane).getByText('展开查看 1 类 Planner 拦截记录 (2 failed attempts)'))

    expect(within(reliabilityLane).getByText('2x Failed')).toBeTruthy()
    expect(within(reliabilityLane).getByText(/Fail Closed: required command 'python -m ruff check'/)).toBeTruthy()
    expect(within(reliabilityLane).getByRole('button', { name: 'Edit Goal PRD' })).toBeTruthy()
    expect(within(reliabilityLane).getByRole('button', { name: 'Run Sweep Now' })).toBeTruthy()
    expect(within(reliabilityLane).getAllByRole('button', { name: 'Trace Path' }).length).toBeGreaterThan(1)
    const failedRow = within(reliabilityLane).getByTestId('validation-failed-candidate-row')
    expect(within(failedRow).queryByRole('button', { name: 'Approve & Run' })).toBeNull()
    expect(within(failedRow).queryByRole('button', { name: 'Materialize & Run' })).toBeNull()
    await user.click(within(reliabilityLane).getByText('Show attempts (2)'))
    expect(within(reliabilityLane).getAllByText('View Agent Raw Output')).toHaveLength(2)
  })

  it('groups active goals above collapsed historical goals with local search', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    expect(await screen.findByTestId('active-goals-section')).toBeTruthy()
    const activeSection = screen.getByTestId('active-goals-section')
    expect(within(activeSection).getByText('Gateway reliability')).toBeTruthy()
    expect(within(activeSection).queryByText('Completed lint contracts')).toBeNull()

    expect(screen.getByText('Achieved (1)')).toBeTruthy()
    expect(screen.getByText('Dropped (1)')).toBeTruthy()
    expect(screen.queryByPlaceholderText('Filter achieved goals...')).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Achieved (1)' }))
    const achievedSection = screen.getByTestId('achieved-goals-section')
    await waitFor(() => {
      expect(within(achievedSection).getByPlaceholderText('Filter achieved goals...')).toBeTruthy()
    })
    expect(within(achievedSection).getByText('Completed lint contracts')).toBeTruthy()

    await user.type(within(achievedSection).getByPlaceholderText('Filter achieved goals...'), 'missing')
    expect(within(achievedSection).queryByText('Completed lint contracts')).toBeNull()
    expect(within(achievedSection).getByText('No achieved goals match this filter.')).toBeTruthy()
  })

  it('virtualizes large historical goal groups instead of rendering every row', async () => {
    const user = userEvent.setup()
    const achievedLanes = Array.from({ length: 25 }, (_, index) => {
      const goal = {
        ...achievedGoal,
        id: 300 + index,
        goal_key: `achieved_${index}`,
        title: `Achieved goal ${index}`,
      }
      return {
        goal_key: goal.goal_key,
        goal,
        rollup: {
          manifest_id: 1,
          goal_key: goal.goal_key,
          goal,
          candidate_status_counts: { materialized: 1 },
          requirement_status_counts: { completed: 1 },
          workflow_status_counts: { succeeded: 1 },
          release_status_counts: {},
        },
        candidates: [],
      }
    })
    apiMock.getPlanningMissionControl.mockResolvedValueOnce({
      ...mission,
      goal_lanes: [mission.goal_lanes[0], mission.goal_lanes[1], ...achievedLanes],
    })

    render(<PlanningPage />)
    await screen.findByTestId('active-goals-section')
    await user.click(screen.getByRole('button', { name: 'Achieved (25)' }))

    await waitFor(() => {
      expect(screen.getByTestId('virtualized-achieved-goals')).toBeTruthy()
    })
    expect(screen.getAllByTestId('historical-goal-row').length).toBeLessThan(25)
  })

  it('renders planner intercept timestamps as local time with UTC source in the time element', async () => {
    const user = userEvent.setup()
    const { container } = render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getByText('展开查看 1 类 Planner 拦截记录 (2 failed attempts)'))

    const time = container.querySelector('time[datetime="2026-04-19T03:00:00.000Z"]')
    expect(time).toBeTruthy()
    expect(time?.getAttribute('title')).toBe('2026-04-19T03:00:00.000Z')
    expect(time?.textContent).toMatch(/GMT[+-]\d{2}:\d{2}/)
  })

  it('approves and runs a candidate from inside its goal lane', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getByRole('button', { name: 'Approve & Run' }))

    await waitFor(() => {
      expect(apiMock.approveAndRunRequirementCandidate).toHaveBeenCalledWith(10, { operator: 'operator' })
    })
  })

  it('still supports approve-only when an operator wants to stage a candidate', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getByRole('button', { name: 'Approve only' }))

    await waitFor(() => {
      expect(apiMock.approveRequirementCandidate).toHaveBeenCalledWith(10, { operator: 'operator' })
    })
  })

  it('blocks steering save when focus weights do not total 100 percent', async () => {
    render(<PlanningPage />)

    await screen.findByTestId('focus-weight-sliders')
    fireEvent.change(screen.getByLabelText('Weight reliability'), { target: { value: '80' } })

    expect(screen.getByTestId('weight-total-warning')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Save Steering Revision' })).toBeDisabled()
  })

  it('keeps raw manifest JSON goal-free and edits full markdown through the goal API', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    await screen.findByTestId('mission-control-tab')
    await user.click(screen.getByText('Steering Details'))
    await user.click(screen.getByRole('button', { name: '</> Edit raw JSON' }))

    const rawDrawer = await screen.findByTestId('raw-manifest-drawer')
    expect(within(rawDrawer).queryByText('gateway_reliability')).toBeNull()
    expect(within(rawDrawer).getByDisplayValue(/focus_weights/)).toBeTruthy()

    await user.click(within(rawDrawer).getByRole('button', { name: 'Close' }))
    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getByRole('button', { name: 'Edit Intent' }))

    await waitFor(() => {
      expect(apiMock.getPlanningGoal).toHaveBeenCalledWith(101)
    })
    const drawer = await screen.findByTestId('goal-intent-drawer')
    expect(within(drawer).getByDisplayValue(/Reliability PRD/)).toBeTruthy()

    fireEvent.change(within(drawer).getByPlaceholderText(/Write the full PRD/), { target: { value: '# Updated PRD\n\n- Check gateway.' } })
    await user.click(within(drawer).getByRole('button', { name: 'Save Intent' }))

    await waitFor(() => {
      expect(apiMock.updatePlanningGoal).toHaveBeenCalledWith(101, {
        intent_markdown: '# Updated PRD\n\n- Check gateway.',
        operator: 'operator',
      })
    })
  })

  it('opens a single-goal trace panel from the goal lane', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getAllByRole('button', { name: 'Trace Path' })[0])

    await waitFor(() => {
      expect(apiMock.getPlanningGoalTrace).toHaveBeenCalledWith(101)
    })
    const drawer = await screen.findByTestId('goal-trace-drawer')
    expect(within(drawer).getByText('Goal PRD saved')).toBeTruthy()
    expect(within(drawer).getByText('Candidate #10')).toBeTruthy()
  })

  it('marks blocked trace candidates as planner intercepts instead of human gates', async () => {
    const user = userEvent.setup()
    apiMock.getPlanningGoalTrace.mockResolvedValueOnce({
      goal: { id: 101, goal_key: 'gateway_reliability', title: 'Gateway reliability', intent_present: true },
      nodes: [
        {
          kind: 'candidate',
          status: 'blocked',
          title: 'Candidate #9',
          summary: 'validation_failed',
          object_id: 9,
          deep_link: '/planning?candidate=9',
          diagnostic: {
            reason: 'required command is unsafe',
            source: 'requirement_candidate',
            timestamp: '2026-04-20T06:36:09Z',
          },
          metadata: { generated_by: 'planner_agent_v1' },
        },
      ],
      diagnostics: [],
      next_actions: [],
      history: [],
    })
    render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getAllByRole('button', { name: 'Trace Path' })[0])

    const drawer = await screen.findByTestId('goal-trace-drawer')
    expect(within(drawer).getByText(/Planner Intercept · not a Human Gate/)).toBeTruthy()
  })

  it('closes planning drawers with Escape', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    await screen.findByTestId('mission-control-tab')
    await user.click(screen.getByText('Steering Details'))
    await user.click(screen.getByRole('button', { name: '</> Edit raw JSON' }))
    expect(await screen.findByTestId('raw-manifest-drawer')).toBeTruthy()

    await user.keyboard('{Escape}')

    await waitFor(() => {
      expect(screen.queryByTestId('raw-manifest-drawer')).toBeNull()
    })
  })

  it('runs dirty intent Escape through the existing close confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    render(<PlanningPage />)

    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getByRole('button', { name: 'Edit Intent' }))
    const drawer = await screen.findByTestId('goal-intent-drawer')
    fireEvent.change(within(drawer).getByPlaceholderText(/Write the full PRD/), { target: { value: '# Dirty PRD' } })

    await user.keyboard('{Escape}')

    expect(confirmSpy).toHaveBeenCalled()
    expect(screen.getByTestId('goal-intent-drawer')).toBeTruthy()

    confirmSpy.mockReturnValue(true)
    await user.keyboard('{Escape}')

    await waitFor(() => {
      expect(screen.queryByTestId('goal-intent-drawer')).toBeNull()
    })
    confirmSpy.mockRestore()
  })

  it('creates a goal from core intent and markdown without acceptance JSON', async () => {
    const user = userEvent.setup()
    render(<PlanningPage />)

    await screen.findByTestId('mission-control-tab')
    await user.click(screen.getByRole('button', { name: 'New Goal' }))

    const drawer = await screen.findByTestId('goal-settings-drawer')
    await user.type(within(drawer).getByLabelText('Title'), 'Optimize Payment Gateway')
    fireEvent.blur(within(drawer).getByLabelText('Title'))

    expect(within(drawer).getByLabelText('Goal key')).toHaveValue('optimize_payment_gateway')

    await user.type(within(drawer).getByLabelText('Success metric'), 'p95 checkout latency < 500ms')
    fireEvent.change(within(drawer).getByPlaceholderText(/Write the full PRD/), {
      target: { value: '# Payment Gateway PRD\n\n- Reduce contention\n\n```bash\nnpm test\n```' },
    })
    await user.click(within(drawer).getByRole('button', { name: 'preview' }))
    expect(within(drawer).getByText('Payment Gateway PRD')).toBeTruthy()

    await user.click(within(drawer).getByText('Advanced Settings'))
    expect(within(drawer).getByText(/Acceptance steps are generated at Candidate level/)).toBeTruthy()

    await user.click(within(drawer).getByRole('button', { name: 'Create Goal' }))

    await waitFor(() => {
      expect(apiMock.createPlanningGoal).toHaveBeenCalledWith(expect.objectContaining({
        goal_key: 'optimize_payment_gateway',
        title: 'Optimize Payment Gateway',
        intent_markdown: '# Payment Gateway PRD\n\n- Reduce contention\n\n```bash\nnpm test\n```',
        success_metric: 'p95 checkout latency < 500ms',
      }))
    })
    expect(apiMock.createPlanningGoal.mock.calls[0][0]).not.toHaveProperty('execution_acceptance_steps')
    expect(apiMock.saveActivePlanningManifest).not.toHaveBeenCalled()
  })

  it('warns before closing a dirty goal creation drawer', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    render(<PlanningPage />)

    await screen.findByTestId('mission-control-tab')
    await user.click(screen.getByRole('button', { name: 'New Goal' }))
    const drawer = await screen.findByTestId('goal-settings-drawer')
    await user.type(within(drawer).getByLabelText('Title'), 'Do not lose this')
    await user.click(within(drawer).getByRole('button', { name: 'Close' }))

    expect(confirmSpy).toHaveBeenCalled()
    expect(screen.getByTestId('goal-settings-drawer')).toBeTruthy()
    confirmSpy.mockRestore()
  })
})
