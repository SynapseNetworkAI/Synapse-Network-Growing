// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CommandCenterPage from './CommandCenterPage'

const apiMock = vi.hoisted(() => ({
  getStats: vi.fn(),
  getWorkflowRunsSummary: vi.fn(),
  getPlanningMissionBoard: vi.fn(),
  getPlanningTaskBoard: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

const board = {
  active_goal: {
    id: 1,
    goal_key: 'synapse_growth_operating_loop',
    title: 'Build the Synapse growth operating loop',
    intent_excerpt: 'One active company goal with product, growth, and engineering lanes.',
    success_metric: 'All active work has a lane.',
    domain: 'ops',
    risk_level: 'normal',
  },
  active_goals: [
    {
      id: 1,
      goal_key: 'synapse_growth_operating_loop',
      title: 'Build the Synapse growth operating loop',
      intent_excerpt: 'One active company goal with product, growth, and engineering lanes.',
      success_metric: 'All active work has a lane.',
      domain: 'company',
      status: 'active',
      risk_level: 'normal',
    },
    {
      id: 2,
      goal_key: 'sdk_developer_quickstart',
      title: 'SDK & Developer Experience quickstart',
      intent_excerpt: 'Turn the SDK quickstart into an evidence-bound engineering lane.',
      success_metric: 'Quickstart demo completes with receipt evidence.',
      domain: 'product',
      status: 'active',
      risk_level: 'normal',
    },
  ],
  lanes: {
    product_planner: [
      {
        id: 'product_opportunity:1',
        type: 'product_opportunity',
        title: 'Add conversion tracking for staging visits',
        status: 'proposed',
        risk_level: 'normal',
        next_action: 'Open Planning and review this opportunity.',
        deep_link: '/planning?tab=opportunities',
        evidence_label: 'docs clicks',
        updated_at: '2026-04-28T00:00:00Z',
      },
    ],
    growth_lead: [
      {
        id: 'social_draft:8',
        type: 'publishing_draft',
        title: 'X launch proof draft',
        status: 'needs_review',
        risk_level: 'normal',
        next_action: 'Review the X draft before publishing.',
        deep_link: '/publishing',
        evidence_label: '900 chars',
        updated_at: '2026-04-28T00:00:00Z',
      },
    ],
    software_engineer: [
      {
        id: 'workflow:13',
        type: 'workflow',
        title: 'Workflow #13: agent_self_repair',
        status: 'awaiting_operator',
        risk_level: 'normal',
        next_action: 'Review the human gate decision summary.',
        deep_link: '/workflows/13',
        evidence_label: 'route_to_human',
        updated_at: '2026-04-28T00:00:00Z',
      },
    ],
  },
  lane_summary: {
    product_planner: { count: 1 },
    growth_lead: { count: 1 },
    software_engineer: { count: 1 },
  },
  unassigned: {
    count: 1,
    items: [],
  },
  traction_proof: {
    status: 'incomplete',
    items: [
      {
        key: 'docs_staging_visits',
        label: 'Docs / staging visits',
        status: 'missing',
        evidence_label: 'analytics_unavailable',
        next_action: 'Connect analytics before claiming traffic proof.',
        deep_link: '/planning?tab=opportunities',
      },
      {
        key: 'ops_lane_health',
        label: 'Ops lane health',
        status: 'blocked',
        evidence_label: '1 unassigned item(s)',
        next_action: 'Repair unassigned lineage.',
        deep_link: '/planning?tab=unassigned',
      },
    ],
  },
  next_actions: [],
  manifest: {
    id: 1,
    version_name: 'Goal Mission Cycle',
    cycle_label: '2026-W18',
    updated_at: '2026-04-28T00:00:00Z',
  },
}

const taskBoard = {
  columns: [
    { key: 'backlog', title: 'Backlog', description: '', hidden: false, count: 2, cards: [] },
    { key: 'todo', title: 'Todo', description: '', hidden: false, count: 1, cards: [] },
    { key: 'in_progress', title: 'In Progress', description: '', hidden: false, count: 3, cards: [] },
    { key: 'human_review', title: 'Human Review', description: '', hidden: false, count: 1, cards: [] },
    { key: 'rework', title: 'Rework', description: '', hidden: false, count: 1, cards: [] },
    { key: 'delivery', title: 'Delivery', description: '', hidden: false, count: 0, cards: [] },
    { key: 'done', title: 'Done', description: '', hidden: false, count: 4, cards: [] },
    { key: 'canceled', title: 'Canceled', description: '', hidden: true, count: 1, cards: [] },
  ],
  summary: { total: 13, visible_total: 12, include_done_days: 7 },
  generated_at: '2026-04-28T00:00:00Z',
}

function renderCommandCenter() {
  return render(
    <MemoryRouter>
      <CommandCenterPage />
    </MemoryRouter>,
  )
}

describe('CommandCenterPage mission dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getStats.mockResolvedValue({
      requirement_active: 3,
      workflow_running: 1,
      human_gate_pending: 2,
      workflow_failed: 0,
    })
    apiMock.getWorkflowRunsSummary.mockResolvedValue({
      running: 1,
      needs_human: 2,
      pending_gate_count: 2,
      failed_count: 0,
      failed: 0,
    })
    apiMock.getPlanningMissionBoard.mockResolvedValue(board)
    apiMock.getPlanningTaskBoard.mockResolvedValue(taskBoard)
  })

  it('renders a read-only nested mission board with unassigned red light', async () => {
    renderCommandCenter()

    await waitFor(() => expect(screen.getByTestId('mission-board')).toBeInTheDocument())
    expect(screen.getAllByText('Build the Synapse growth operating loop').length).toBeGreaterThan(0)
    expect(screen.getByTestId('mission-lane-product_planner')).toHaveTextContent('Add conversion tracking for staging visits')
    expect(screen.getByTestId('mission-lane-growth_lead')).toHaveTextContent('X launch proof draft')
    expect(screen.getByTestId('mission-lane-software_engineer')).toHaveTextContent('Workflow #13: agent_self_repair')
    expect(screen.getByTestId('mission-traction-proof')).toHaveTextContent('Evidence, not vibes')
    expect(screen.getByTestId('active-business-goals')).toHaveTextContent('SDK & Developer Experience quickstart')
    expect(screen.getByTestId('mission-traction-proof')).toHaveTextContent('Docs / staging visits')
    expect(screen.getByRole('link', { name: 'Unassigned 1' })).toHaveAttribute('href', '/planning?tab=unassigned')
    expect(screen.getByRole('link', { name: /Rework/i })).toHaveAttribute('href', '/planning?tab=board&column=rework')
  })

  it('does not expose product opportunity processing actions on Command Center', async () => {
    renderCommandCenter()

    await waitFor(() => expect(screen.getByTestId('mission-board')).toBeInTheDocument())
    const boardRegion = screen.getByTestId('mission-board')
    expect(within(boardRegion).queryByRole('button', { name: /Create Goal/i })).not.toBeInTheDocument()
    expect(within(boardRegion).queryByRole('button', { name: /Reject/i })).not.toBeInTheDocument()
    expect(within(boardRegion).queryByRole('button', { name: /Defer/i })).not.toBeInTheDocument()
  })
})
