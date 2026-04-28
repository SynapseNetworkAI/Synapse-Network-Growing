// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlanningPage from './PlanningPage'

const apiMock = vi.hoisted(() => ({
  getPlanningMissionControl: vi.fn(),
  getPlanningMissionBoard: vi.fn(),
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
  active_goal_count: 1,
  dropped_goal_count: 0,
  achieved_goal_count: 1,
  review_summary: {},
  change_log: [],
  created_by: 'operator',
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  archived_at: null,
}

const activeGoal = {
  id: 101,
  manifest_id: 1,
  goal_key: 'synapse_growth_operating_loop',
  title: 'Build the Synapse growth operating loop',
  intent_excerpt: 'Use product, growth, and engineering lanes to move one active company goal.',
  success_metric: 'All active work is visible under one goal or unassigned.',
  domain: 'ops',
  status: 'active',
  workflow_key: 'agent_self_repair',
  project_key: 'synapse-network-growing',
  priority: 'normal',
  risk_level: 'normal',
  weight: 1,
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
  ...activeGoal,
  id: 102,
  goal_key: 'completed_lint_contracts',
  title: 'Completed lint contracts',
  status: 'achieved',
  intent_excerpt: 'Historical work already shipped.',
}

const pendingCandidate = {
  id: 10,
  manifest_id: 1,
  goal_key: activeGoal.goal_key,
  candidate_fingerprint: 'candidate-10',
  title: 'Add mission board API',
  description_markdown: 'Candidate belongs under the active goal.',
  project_id: 1,
  project_key: 'synapse-network-growing',
  workflow_key: 'agent_self_repair',
  priority: 'normal',
  risk_level: 'normal',
  confidence: 0.9,
  rationale: 'Needed to wire lanes together.',
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
      goal_key: activeGoal.goal_key,
      goal: activeGoal,
      rollup: {
        manifest_id: 1,
        goal_key: activeGoal.goal_key,
        goal: activeGoal,
        candidate_status_counts: { pending: 1 },
        requirement_status_counts: { running: 1 },
        workflow_status_counts: { running: 1 },
        release_status_counts: {},
      },
      candidates: [pendingCandidate],
    },
    {
      goal_key: achievedGoal.goal_key,
      goal: achievedGoal,
      rollup: {
        manifest_id: 1,
        goal_key: achievedGoal.goal_key,
        goal: achievedGoal,
        candidate_status_counts: {},
        requirement_status_counts: { completed: 1 },
        workflow_status_counts: { succeeded: 1 },
        release_status_counts: {},
      },
      candidates: [],
    },
  ],
  candidate_totals: { pending: 1, approved: 0, materialized: 0, rejected: 0, suppressed: 0 },
  history_preview: { items: [manifest], total: 1, page: 1, page_size: 5, total_pages: 1 },
  last_sweep: null,
}

const board = {
  active_goal: activeGoal,
  lanes: {
    product_planner: [
      {
        id: 'product_opportunity:1',
        type: 'product_opportunity',
        title: 'Track docs and staging conversion from X growth',
        status: 'proposed',
        risk_level: 'normal',
        next_action: 'Create a goal or defer this proposal.',
        deep_link: '/planning?tab=opportunities',
        evidence_label: 'docs_clicks',
        updated_at: '2026-04-19T00:00:00Z',
      },
    ],
    growth_lead: [],
    software_engineer: [
      {
        id: 'candidate:10',
        type: 'requirement_candidate',
        title: 'Add mission board API',
        status: 'pending',
        risk_level: 'normal',
        next_action: 'Review candidate and approve, defer, or reject.',
        deep_link: '/planning?tab=engineering&candidate=10',
        evidence_label: 'agent_self_repair',
        updated_at: '2026-04-19T00:00:00Z',
      },
    ],
  },
  lane_summary: {
    product_planner: { count: 1 },
    growth_lead: { count: 0 },
    software_engineer: { count: 1 },
  },
  unassigned: {
    count: 1,
    items: [
      {
        id: 'workflow:88',
        type: 'workflow',
        title: 'Workflow #88: missing lineage',
        status: 'awaiting_operator',
        risk_level: 'normal',
        next_action: 'Repair missing goal_key lineage.',
        deep_link: '/workflows/88',
        evidence_label: 'route_to_human',
        updated_at: '2026-04-19T00:00:00Z',
      },
    ],
  },
  next_actions: [],
  manifest: { id: 1, version_name: 'Mission Control Cycle', cycle_label: '2026-W17', updated_at: '2026-04-19T00:00:00Z' },
}

function renderPlanning(path = '/planning') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <PlanningPage />
    </MemoryRouter>,
  )
}

describe('PlanningPage queues', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        items: [
          {
            id: 1,
            title: 'Track docs and staging conversion from X growth',
            problem: 'Growth needs attribution.',
            suggested_goal_key: 'growth_conversion_tracking',
            recommended_lane: 'both',
            risk_level: 'normal',
            success_metric: 'docs clicks visible',
            next_action: 'Create a reviewed goal.',
            status: 'proposed',
          },
        ],
      }),
    })))
    apiMock.getPlanningMissionControl.mockResolvedValue(mission)
    apiMock.getPlanningMissionBoard.mockResolvedValue(board)
    apiMock.getPlanningManifestHistory.mockResolvedValue({ items: [manifest], total: 1, page: 1, page_size: 10, total_pages: 1 })
    apiMock.getPlanningGoal.mockResolvedValue({ ...activeGoal, intent_markdown: '# Active goal PRD' })
    apiMock.getPlanningGoalTrace.mockResolvedValue({ goal: activeGoal, nodes: [], diagnostics: [], next_actions: [], history: [] })
  })

  it('defaults to product opportunities instead of repeating the full mission board', async () => {
    renderPlanning()

    expect(await screen.findByTestId('product-opportunities-tab')).toBeInTheDocument()
    expect(screen.getByText('产品机会 / Goal Proposals')).toBeInTheDocument()
    expect(screen.queryByTestId('mission-board')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '业务目标 · 1 active' })).toBeInTheDocument()
  })

  it('shows the engineering queue from the mission board projection', async () => {
    const user = userEvent.setup()
    renderPlanning()

    await screen.findByTestId('product-opportunities-tab')
    await user.click(screen.getByRole('button', { name: /工程队列/ }))

    const queue = await screen.findByTestId('engineering-queue-tab')
    expect(within(queue).getByText('Add mission board API')).toBeInTheDocument()
    expect(within(queue).getByText('Review candidate and approve, defer, or reject.')).toBeInTheDocument()
  })

  it('opens the unassigned queue from query params', async () => {
    renderPlanning('/planning?tab=unassigned')

    const queue = await screen.findByTestId('unassigned-queue-tab')
    expect(within(queue).getByText('未归属队列')).toBeInTheDocument()
    expect(within(queue).getByText('Workflow #88: missing lineage')).toBeInTheDocument()
  })

  it('keeps goal operations in the business goals tab', async () => {
    const user = userEvent.setup()
    renderPlanning()

    await screen.findByTestId('product-opportunities-tab')
    await user.click(screen.getByRole('button', { name: /业务目标/ }))

    const goals = await screen.findByTestId('planning-goals-tab')
    expect(within(goals).getByText('Build the Synapse growth operating loop')).toBeInTheDocument()
    expect(within(goals).getByRole('button', { name: 'Edit Intent' })).toBeInTheDocument()
  })
})
