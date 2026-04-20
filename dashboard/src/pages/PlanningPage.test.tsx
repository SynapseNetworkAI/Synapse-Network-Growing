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
        candidate_status_counts: { pending: 1 },
        requirement_status_counts: {},
        workflow_status_counts: {},
        release_status_counts: {},
      },
      candidates: [reliabilityCandidate],
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
    apiMock.updatePlanningGoal.mockResolvedValue({
      ...reliabilityGoal,
      intent_markdown: '# Updated PRD',
    })
    apiMock.createPlanningGoal.mockResolvedValue({
      ...growthGoal,
      id: 103,
      goal_key: 'new_goal',
      title: 'New goal',
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
    expect(within(lanes[1]).queryByText('Add gateway precision guardrail')).toBeNull()
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
    await user.click(screen.getByRole('button', { name: '</> Edit raw JSON' }))

    const rawDrawer = await screen.findByTestId('raw-manifest-drawer')
    expect(within(rawDrawer).queryByText('gateway_reliability')).toBeNull()
    expect(within(rawDrawer).getByDisplayValue(/focus_weights/)).toBeTruthy()

    await user.click(within(rawDrawer).getByRole('button', { name: 'Close' }))
    const lanes = await screen.findAllByTestId('goal-mission-lane')
    await user.click(within(lanes[0]).getByRole('button', { name: 'Edit Intent & PRD' }))

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
})
