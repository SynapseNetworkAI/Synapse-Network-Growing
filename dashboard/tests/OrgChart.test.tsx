import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import OrgChart from '../src/pages/OrgChart'
import { api, OrgTree, DashboardStats } from '../src/api'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      getOrgTree: vi.fn(),
      getStats: vi.fn(),
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
  })

  it('shows skeleton while loading', () => {
    vi.mocked(api.getOrgTree).mockReturnValue(new Promise(() => {}))
    vi.mocked(api.getStats).mockReturnValue(new Promise(() => {}))
    renderOrgChart()
    expect(screen.getByTestId('orgchart-skeleton')).toBeInTheDocument()
  })

  it('shows error state when api calls fail', async () => {
    vi.mocked(api.getOrgTree).mockRejectedValue(new Error('network'))
    vi.mocked(api.getStats).mockRejectedValue(new Error('network'))
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-error')).toBeInTheDocument()
    })
  })

  it('shows empty state when root is missing', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(null as unknown as OrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
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
})
