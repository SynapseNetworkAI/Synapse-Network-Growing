import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import OrgChart from '../src/pages/OrgChart'
import { api, OrgTree, DashboardStats, CompanyOperatingReview } from '../src/api'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      getOrgTree: vi.fn(),
      getStats: vi.fn(),
      getCompanyOperatingReview: vi.fn(),
      refreshCompanyOperatingReview: vi.fn(),
      syncAgents: vi.fn(),
    },
  }
})

const mockOrgTree: OrgTree = {
  root: {
    id: 'roles',
    display_name: '真实 Agent 角色',
    type: 'org',
    goal: 'Only roles discovered from roles/* are rendered here.',
    children: [
      {
        id: 'group-content',
        display_name: 'content',
        type: 'group',
        goal: '2 discovered roles',
        color: 'blue',
        children: [
          {
            id: 'content_writer',
            display_name: 'Content Writer',
            type: 'agent',
            goal: 'Write concise launch copy.',
            skills: ['copywriting', 'copy-editing'],
            children: [],
          },
          {
            id: 'dev_rel',
            display_name: 'DevRel Engineer',
            type: 'agent',
            goal: 'Own developer education and GTM technical enablement.',
            skills: ['content-strategy', 'community-marketing'],
            children: [],
          },
        ],
      },
      {
        id: 'group-optimization',
        display_name: 'optimization',
        type: 'group',
        goal: '1 discovered roles',
        color: 'green',
        children: [
          {
            id: 'seo_strategist',
            display_name: 'SEO Strategist',
            type: 'agent',
            goal: 'Own SEO execution.',
            skills: ['seo-audit'],
            children: [],
          },
        ],
      },
    ],
  },
}

const mockStats: DashboardStats = {
  agent_count: 3,
  task_total: 15,
  task_pending: 3,
  task_running: 2,
  task_completed: 7,
  task_failed: 1,
  approval_pending: 2,
}

const mockReview: CompanyOperatingReview = {
  id: 1,
  cycle_label: '2026-W15',
  title: 'Company Operating Review',
  summary_markdown: 'Cycle focus: release blockers.\n\nRecommended next move: SDK critical release blocker.',
  portfolio_summary: {
    active_requirements: 2,
    open_signals: 3,
    approval_required_decisions: 1,
    rebalance_opportunities: 1,
    projects_over_budget: 0,
    blocked_publish_projects: 1,
  },
  project_highlights: [
    {
      project_key: 'synapse-network-sdk',
      display_name: 'Synapse-Network-Sdk',
      readiness_status: 'ready',
      readiness_score: 100,
      active_count: 0,
      queued_count: 2,
      bug_report_count: 1,
      blocked_publish_count: 1,
      scheduler_weight: 1.1,
      autonomy_mode: 'execute_autonomously',
      budget_used: 24,
      budget_remaining: 71,
    },
  ],
  bottlenecks: [
    {
      item_key: 'blocked-publish:synapse-network-sdk',
      title: 'Synapse-Network-Sdk publish gate is blocked',
      severity: 'high',
      summary: 'One publish blocker remains open.',
      project_key: 'synapse-network-sdk',
      recommendation: 'Prioritize release blocker cleanup.',
    },
  ],
  incidents: [
    {
      item_key: 'signal:7',
      title: 'SDK critical release blocker',
      severity: 'high',
      summary: 'The SDK release is blocked by failing checks.',
      project_key: 'synapse-network-sdk',
      recommendation: 'Convert to a release bottleneck requirement.',
    },
  ],
  next_cycle_recommendations: [
    {
      candidate_type: 'signal',
      title: 'SDK critical release blocker',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      action: 'intake',
      score: 88,
      budget_cost: 26,
      source_ref: 'signal:7',
      rationale: 'Top-ranked release bottleneck across the portfolio.',
    },
  ],
  source_snapshot: {
    scheduler_generated_at: '2026-04-11T13:00:00Z',
  },
  created_at: '2026-04-11T13:00:00Z',
  updated_at: '2026-04-11T13:05:00Z',
}

function renderOrgChart() {
  return render(
    <BrowserRouter>
      <OrgChart />
    </BrowserRouter>
  )
}

describe('OrgChart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getCompanyOperatingReview).mockResolvedValue(mockReview)
    vi.mocked(api.refreshCompanyOperatingReview).mockResolvedValue(mockReview)
  })

  it('shows skeleton while loading', () => {
    vi.mocked(api.getOrgTree).mockReturnValue(new Promise(() => {}))
    vi.mocked(api.getStats).mockReturnValue(new Promise(() => {}))
    vi.mocked(api.getCompanyOperatingReview).mockReturnValue(new Promise(() => {}))
    renderOrgChart()
    expect(screen.getByTestId('orgchart-skeleton')).toBeInTheDocument()
  })

  it('shows error state when api calls fail', async () => {
    vi.mocked(api.getOrgTree).mockRejectedValue(new Error('network'))
    vi.mocked(api.getStats).mockRejectedValue(new Error('network'))
    vi.mocked(api.getCompanyOperatingReview).mockRejectedValue(new Error('network'))
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-error')).toBeInTheDocument()
    })
  })

  it('shows empty state when root is missing', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(null as unknown as OrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getCompanyOperatingReview).mockResolvedValue(mockReview)
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-empty')).toBeInTheDocument()
    })
  })

  it('renders dynamic groups and agents', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(mockOrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
    })

    expect(screen.getByTestId('org-root')).toHaveTextContent('真实 Agent 角色')
    expect(screen.getByTestId('group-group-content')).toHaveTextContent('content')
    expect(screen.getByTestId('group-group-optimization')).toHaveTextContent('optimization')
    expect(screen.getByTestId('node-content_writer')).toHaveTextContent('Content Writer')
    expect(screen.getByTestId('node-dev_rel')).toHaveTextContent('community-marketing')
    expect(screen.getByTestId('company-review-panel')).toHaveTextContent('Company Operating Review')
    expect(screen.getAllByText('SDK critical release blocker').length).toBeGreaterThan(0)
  })

  it('shows selected node detail', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(mockOrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('node-seo_strategist')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('node-seo_strategist'))
    expect(screen.getByTestId('node-detail')).toBeInTheDocument()
    expect(screen.getByTestId('detail-seo_strategist')).toHaveTextContent('SEO Strategist')
  })

  it('sync button reloads roles', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(mockOrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.syncAgents).mockResolvedValue([])
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('同步 Roles'))
    await waitFor(() => {
      expect(api.syncAgents).toHaveBeenCalled()
    })
  })

  it('refreshes the operating review', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(mockOrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.refreshCompanyOperatingReview).mockResolvedValue({
      ...mockReview,
      id: 2,
      summary_markdown: 'Cycle focus: budget pressure.',
    })
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('company-review-panel')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('refresh-company-review'))
    await waitFor(() => {
      expect(api.refreshCompanyOperatingReview).toHaveBeenCalled()
      expect(screen.getByText(/Cycle focus: budget pressure/)).toBeInTheDocument()
    })
  })
})
