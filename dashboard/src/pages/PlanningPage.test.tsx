// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlanningPage from './PlanningPage'

const apiMock = vi.hoisted(() => ({
  getPlanningMissionControl: vi.fn(),
  getPlanningMissionBoard: vi.fn(),
  getPlanningMissionWorkbench: vi.fn(),
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
  active_goals: [
    activeGoal,
    {
      ...activeGoal,
      id: 103,
      goal_key: 'sdk_developer_quickstart',
      title: 'SDK & Developer Experience quickstart',
      domain: 'product',
      success_metric: 'Quickstart demo completes with receipt evidence.',
    },
  ],
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

const workbench = {
  root: {
    id: 'goal:synapse_growth_operating_loop',
    parent_id: null,
    level: 0,
    type: 'company_goal',
    title: 'Build the Synapse growth operating loop',
    status: 'active',
    lane: null,
    goal_key: activeGoal.goal_key,
    stage_statuses: {
      opportunity: 'waiting',
      candidate: 'waiting',
      requirement: 'missing',
      workflow: 'missing',
      pr: 'missing',
      release: 'missing',
      online_record: 'missing',
    },
    next_action: 'All active work is visible under one goal or unassigned.',
    deep_link: '/planning?tab=goals',
    detail_api: '/api/planning/goals/101',
    updated_at: '2026-04-19T00:00:00Z',
    evidence_label: '',
    children: [
      {
        id: 'goal:sdk_developer_quickstart',
        parent_id: 'goal:synapse_growth_operating_loop',
        level: 1,
        type: 'business_goal',
        title: 'SDK & Developer Experience quickstart',
        status: 'active',
        lane: null,
        goal_key: 'sdk_developer_quickstart',
        stage_statuses: {
          opportunity: 'missing',
          candidate: 'waiting',
          requirement: 'missing',
          workflow: 'missing',
          pr: 'missing',
          release: 'missing',
          online_record: 'missing',
        },
        next_action: 'Quickstart demo completes with receipt evidence.',
        deep_link: '/planning?tab=goals',
        detail_api: '/api/planning/goals/103',
        updated_at: '2026-04-19T00:00:00Z',
        evidence_label: '',
        children: [
          {
            id: 'lane:software_engineer:sdk_developer_quickstart',
            parent_id: 'goal:sdk_developer_quickstart',
            level: 2,
            type: 'mission_lane',
            title: 'Software Engineer',
            status: 'waiting',
            lane: 'software_engineer',
            goal_key: 'sdk_developer_quickstart',
            stage_statuses: {
              opportunity: 'missing',
              candidate: 'waiting',
              requirement: 'missing',
              workflow: 'missing',
              pr: 'missing',
              release: 'missing',
              online_record: 'missing',
            },
            next_action: 'Review candidate and approve, defer, or reject.',
            deep_link: '/planning?tab=engineering',
            detail_api: null,
            updated_at: null,
            evidence_label: '',
            children: [
              {
                id: 'candidate:10',
                parent_id: 'lane:software_engineer:sdk_developer_quickstart',
                level: 3,
                type: 'requirement_candidate',
                title: 'Add mission board API',
                status: 'pending',
                lane: 'software_engineer',
                goal_key: 'sdk_developer_quickstart',
                stage_statuses: {
                  opportunity: 'missing',
                  candidate: 'waiting',
                  requirement: 'missing',
                  workflow: 'missing',
                  pr: 'missing',
                  release: 'missing',
                  online_record: 'missing',
                },
                next_action: 'Review candidate and approve, defer, or reject.',
                deep_link: '/planning?tab=engineering&candidate=10',
                detail_api: '/api/planning/candidates?candidate_id=10',
                updated_at: '2026-04-19T00:00:00Z',
                evidence_label: 'agent_self_repair',
                children: [],
              },
            ],
          },
        ],
      },
    ],
  },
  unassigned: { count: 1, items: board.unassigned.items },
  summary: { active_goal_count: 2, work_item_count: 3 },
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
    apiMock.getPlanningMissionWorkbench.mockResolvedValue(workbench)
    apiMock.getPlanningManifestHistory.mockResolvedValue({ items: [manifest], total: 1, page: 1, page_size: 10, total_pages: 1 })
    apiMock.getPlanningGoal.mockResolvedValue({ ...activeGoal, intent_markdown: '# Active goal PRD' })
    apiMock.getPlanningGoalTrace.mockResolvedValue({ goal: activeGoal, nodes: [], diagnostics: [], next_actions: [], history: [] })
  })

  it('defaults to Mission Workbench with a tree hierarchy and stage rail', async () => {
    renderPlanning()

    await screen.findByText('目标 → 战线 → 任务 → 证据')
    await screen.findByTestId('mission-workbench-row-candidate:10')
    const tab = screen.getByTestId('mission-workbench-tab')
    expect(within(tab).getByText('目标 → 战线 → 任务 → 证据')).toBeInTheDocument()
    expect(within(tab).getByText('SDK & Developer Experience quickstart')).toBeInTheDocument()
    expect(within(tab).getByText('Add mission board API')).toBeInTheDocument()
    expect(within(tab).getAllByText('Candidate').length).toBeGreaterThan(0)
    expect(screen.queryByTestId('mission-board')).not.toBeInTheDocument()
  })

  it('opens centered Mission Workbench detail modal', async () => {
    const user = userEvent.setup()
    renderPlanning()

    await screen.findByText('目标 → 战线 → 任务 → 证据')
    const row = await screen.findByTestId('mission-workbench-row-candidate:10')
    await user.click(within(row).getByRole('button', { name: '详情' }))

    const dialog = screen.getByRole('dialog', { name: /Mission item detail Add mission board API/ })
    expect(dialog).toBeInTheDocument()
    expect(within(dialog).getByText('Review candidate and approve, defer, or reject.')).toBeInTheDocument()
    expect(within(dialog).queryByText(/Drawer/i)).not.toBeInTheDocument()
  })

  it('still exposes product opportunities as a focused queue tab', async () => {
    const user = userEvent.setup()
    renderPlanning()

    await screen.findByTestId('mission-workbench-tab')
    await user.click(screen.getByRole('button', { name: '产品机会' }))
    expect(await screen.findByTestId('product-opportunities-tab')).toBeInTheDocument()
    expect(screen.getByText('产品机会 / Goal Proposals')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '业务目标 · 1 active' })).toBeInTheDocument()
  })

  it('opens product opportunities directly from a deep link and highlights the item', async () => {
    renderPlanning('/planning?tab=opportunities&opportunity=1')

    const tab = await screen.findByTestId('product-opportunities-tab')
    const row = await screen.findByTestId('product-opportunity-1')
    expect(tab).toBeInTheDocument()
    expect(row.className).toContain('border-cyan-300')
  })

  it('shows the engineering queue from the mission board projection', async () => {
    const user = userEvent.setup()
    renderPlanning()

    await screen.findByText('目标 → 战线 → 任务 → 证据')
    await user.click(screen.getByRole('button', { name: /工程队列/ }))

    const queue = await screen.findByTestId('engineering-queue-tab')
    expect(within(queue).getByText('Add mission board API')).toBeInTheDocument()
    expect(within(queue).getByText('Review candidate and approve, defer, or reject.')).toBeInTheDocument()
  })

  it('shows the planner sweep action when engineering queue has no active work', async () => {
    const user = userEvent.setup()
    apiMock.getPlanningMissionBoard.mockResolvedValueOnce({
      ...board,
      lanes: { ...board.lanes, software_engineer: [] },
      lane_summary: { ...board.lane_summary, software_engineer: { count: 0 } },
    })
    apiMock.runPlannerSweep.mockResolvedValue({ created_candidate_ids: [] })
    renderPlanning()

    await screen.findByText('目标 → 战线 → 任务 → 证据')
    await user.click(screen.getByRole('button', { name: /工程队列/ }))
    const queue = await screen.findByTestId('engineering-queue-tab')
    expect(within(queue).getByText('工程线还没有 active 任务')).toBeInTheDocument()
    await user.click(within(queue).getByRole('button', { name: 'Run Planner Sweep' }))

    expect(apiMock.runPlannerSweep).toHaveBeenCalledWith({ dry_run: false, triggered_by: 'operator' })
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

    await screen.findByText('目标 → 战线 → 任务 → 证据')
    await user.click(screen.getByRole('button', { name: /业务目标/ }))

    const goals = await screen.findByTestId('planning-goals-tab')
    expect(within(goals).getByText('Build the Synapse growth operating loop')).toBeInTheDocument()
    expect(within(goals).getByRole('button', { name: 'Edit Intent' })).toBeInTheDocument()
  })
})
