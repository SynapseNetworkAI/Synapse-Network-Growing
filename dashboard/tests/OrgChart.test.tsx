import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import OrgChart from '../src/pages/OrgChart'
import { api, Agent, DashboardStats } from '../src/api'

// Mock the api module
vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      getAgents: vi.fn(),
      getStats: vi.fn(),
      syncAgents: vi.fn(),
    },
  }
})

const mockAgents: Agent[] = [
  { id: 'dev_rel', display_name: 'DevRel Engineer', goal: '负责 DX 和技术布道', group: 'content', persona_path: null, skills: '["content-strategy","community-marketing"]', task_count: 5, completed_count: 3 },
  { id: 'content_writer', display_name: 'Content Writer', goal: '负责极简主义文案写作', group: 'content', persona_path: null, skills: '["copywriting","copy-editing"]', task_count: 3, completed_count: 1 },
  { id: 'growth_lead', display_name: 'Growth Lead', goal: '负责 GTM 和增长策略', group: 'growth', persona_path: null, skills: '["marketing-ideas","launch-strategy"]', task_count: 4, completed_count: 2 },
  { id: 'launch_strategist', display_name: 'Launch Strategist', goal: '负责发布节奏与飞轮编排', group: 'growth', persona_path: null, skills: '["launch-strategy","pricing-strategy"]', task_count: 2, completed_count: 0 },
  { id: 'seo_strategist', display_name: 'SEO Strategist', goal: '负责关键词与转化率优化', group: 'optimization', persona_path: null, skills: '["seo-audit","ai-seo"]', task_count: 1, completed_count: 1 },
  { id: 'cro_optimizer', display_name: 'CRO Optimizer', goal: '负责全链路转化率优化', group: 'optimization', persona_path: null, skills: '["page-cro","ab-test-setup"]', task_count: 0, completed_count: 0 },
]

const mockStats: DashboardStats = {
  agent_count: 6,
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

  // ── Loading state ────────────────────────────────────────

  it('shows skeleton while loading', () => {
    // Never resolve to keep loading state
    vi.mocked(api.getAgents).mockReturnValue(new Promise(() => {}))
    vi.mocked(api.getStats).mockReturnValue(new Promise(() => {}))
    renderOrgChart()
    expect(screen.getByTestId('orgchart-skeleton')).toBeInTheDocument()
  })

  // ── Error state ──────────────────────────────────────────

  it('shows error when backend is unreachable', async () => {
    vi.mocked(api.getAgents).mockRejectedValue(new Error('Network error'))
    vi.mocked(api.getStats).mockRejectedValue(new Error('Network error'))
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-error')).toBeInTheDocument()
    })
    expect(screen.getByText(/无法连接后端/)).toBeInTheDocument()
  })

  // ── Empty state with auto-sync ───────────────────────────

  it('shows empty state when no agents after sync', async () => {
    vi.mocked(api.getAgents).mockResolvedValue([])
    vi.mocked(api.getStats).mockResolvedValue({ ...mockStats, agent_count: 0 })
    vi.mocked(api.syncAgents).mockResolvedValue([])
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-empty')).toBeInTheDocument()
    })
    expect(screen.getByText('同步 Roles')).toBeInTheDocument()
  })

  // ── Full render ──────────────────────────────────────────

  describe('with agents loaded', () => {
    beforeEach(() => {
      vi.mocked(api.getAgents).mockResolvedValue(mockAgents)
      vi.mocked(api.getStats).mockResolvedValue(mockStats)
    })

    it('renders the page with all sections', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
      })
      // Stats bar
      expect(screen.getByTestId('stats-bar')).toBeInTheDocument()
      // Manager node
      expect(screen.getByTestId('manager-node')).toBeInTheDocument()
      // Three group columns
      expect(screen.getByTestId('group-columns')).toBeInTheDocument()
      expect(screen.getByTestId('group-content')).toBeInTheDocument()
      expect(screen.getByTestId('group-growth')).toBeInTheDocument()
      expect(screen.getByTestId('group-optimization')).toBeInTheDocument()
    })

    // ── Stats display ────────────────────────────────────────

    it('displays correct stat values', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('stats-bar')).toBeInTheDocument()
      })
      expect(screen.getByTestId('stat-Agent 总数')).toHaveTextContent('6')
      expect(screen.getByTestId('stat-任务总数')).toHaveTextContent('15')
      expect(screen.getByTestId('stat-已完成')).toHaveTextContent('7')
      expect(screen.getByTestId('stat-待审批')).toHaveTextContent('2')
    })

    // ── Group structure ──────────────────────────────────────

    it('groups agents correctly into 3 columns', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('group-content')).toBeInTheDocument()
      })

      // Content group: dev_rel, content_writer
      const contentGroup = screen.getByTestId('group-content')
      expect(contentGroup).toHaveTextContent('内容与布道')
      expect(screen.getByTestId('agent-node-dev_rel')).toBeInTheDocument()
      expect(screen.getByTestId('agent-node-content_writer')).toBeInTheDocument()

      // Growth group: growth_lead, launch_strategist
      const growthGroup = screen.getByTestId('group-growth')
      expect(growthGroup).toHaveTextContent('增长与发布')
      expect(screen.getByTestId('agent-node-growth_lead')).toBeInTheDocument()
      expect(screen.getByTestId('agent-node-launch_strategist')).toBeInTheDocument()

      // Optimization group: seo_strategist, cro_optimizer
      const optGroup = screen.getByTestId('group-optimization')
      expect(optGroup).toHaveTextContent('优化与分析')
      expect(screen.getByTestId('agent-node-seo_strategist')).toBeInTheDocument()
      expect(screen.getByTestId('agent-node-cro_optimizer')).toBeInTheDocument()
    })

    // ── Manager node ─────────────────────────────────────────

    it('renders the manager/CTO node at center', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('manager-node')).toBeInTheDocument()
      })
      expect(screen.getByTestId('manager-node')).toHaveTextContent('CTO / Manager')
    })

    // ── All agent cards displayed ────────────────────────────

    it('displays all 6 agent cards in the card grid', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-cards')).toBeInTheDocument()
      })
      for (const agent of mockAgents) {
        expect(screen.getByTestId(`agent-card-${agent.id}`)).toBeInTheDocument()
      }
    })

    // ── Agent card content ───────────────────────────────────

    it('renders agent card with correct details', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-card-dev_rel')).toBeInTheDocument()
      })
      const card = screen.getByTestId('agent-card-dev_rel')
      expect(card).toHaveTextContent('DevRel Engineer')
      expect(card).toHaveTextContent('负责 DX 和技术布道')
      expect(card).toHaveTextContent('content-strategy')
      expect(card).toHaveTextContent('community-marketing')
      expect(card).toHaveTextContent('任务: 5')
      expect(card).toHaveTextContent('完成: 3')
      expect(card).toHaveTextContent('内容与布道')  // group tag
    })

    // ── Agent node brings up task counts ─────────────────────

    it('agent nodes show task count and completed count', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-node-dev_rel')).toBeInTheDocument()
      })
      const node = screen.getByTestId('agent-node-dev_rel')
      expect(node).toHaveTextContent('任务: 5')
      expect(node).toHaveTextContent('完成: 3')
    })

    // ── Click agent node shows detail ────────────────────────

    it('clicking agent node shows detail card', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-node-growth_lead')).toBeInTheDocument()
      })

      // No detail section initially
      expect(screen.queryByTestId('agent-detail')).not.toBeInTheDocument()

      // Click on growth_lead node
      fireEvent.click(screen.getByTestId('agent-node-growth_lead'))

      // Detail section appears
      expect(screen.getByTestId('agent-detail')).toBeInTheDocument()
      expect(screen.getByTestId('agent-detail')).toHaveTextContent('Growth Lead')
      expect(screen.getByTestId('agent-detail')).toHaveTextContent('负责 GTM 和增长策略')
    })

    // ── Click agent node again deselects ─────────────────────

    it('clicking same agent node toggles off detail', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-node-growth_lead')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('agent-node-growth_lead'))
      expect(screen.getByTestId('agent-detail')).toBeInTheDocument()

      fireEvent.click(screen.getByTestId('agent-node-growth_lead'))
      expect(screen.queryByTestId('agent-detail')).not.toBeInTheDocument()
    })

    // ── Click group filters cards ────────────────────────────

    it('clicking group column filters agent cards to that group', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('group-content')).toBeInTheDocument()
      })

      // Initially all 6 cards visible
      expect(screen.getByTestId('agent-cards')).toHaveTextContent('全部 Agent')
      for (const a of mockAgents) {
        expect(screen.getByTestId(`agent-card-${a.id}`)).toBeInTheDocument()
      }

      // Click content group
      fireEvent.click(screen.getByTestId('group-content'))

      // Only content agents visible
      expect(screen.getByTestId('agent-cards')).toHaveTextContent('内容与布道 成员')
      expect(screen.getByTestId('agent-card-dev_rel')).toBeInTheDocument()
      expect(screen.getByTestId('agent-card-content_writer')).toBeInTheDocument()
      expect(screen.queryByTestId('agent-card-growth_lead')).not.toBeInTheDocument()
      expect(screen.queryByTestId('agent-card-seo_strategist')).not.toBeInTheDocument()
    })

    // ── Click group again deselects filter ───────────────────

    it('clicking same group column toggles off filter', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('group-content')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('group-content'))
      expect(screen.queryByTestId('agent-card-growth_lead')).not.toBeInTheDocument()

      fireEvent.click(screen.getByTestId('group-content'))
      expect(screen.getByTestId('agent-card-growth_lead')).toBeInTheDocument()
      expect(screen.getByTestId('agent-cards')).toHaveTextContent('全部 Agent')
    })

    // ── Sync button triggers API ─────────────────────────────

    it('sync button calls syncAgents and reloads', async () => {
      vi.mocked(api.syncAgents).mockResolvedValue(mockAgents)
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
      })

      const syncBtn = screen.getAllByText('同步 Roles')[0]
      fireEvent.click(syncBtn)

      await waitFor(() => {
        expect(api.syncAgents).toHaveBeenCalled()
      })
    })

    // ── Group colors / group tag rendering ───────────────────

    it('agent cards show group color tags', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-card-seo_strategist')).toBeInTheDocument()
      })
      const card = screen.getByTestId('agent-card-seo_strategist')
      expect(card).toHaveTextContent('优化与分析')
    })

    // ── Skills rendering ─────────────────────────────────────

    it('renders skill tags for each agent', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('agent-card-cro_optimizer')).toBeInTheDocument()
      })
      const card = screen.getByTestId('agent-card-cro_optimizer')
      expect(card).toHaveTextContent('page-cro')
      expect(card).toHaveTextContent('ab-test-setup')
    })

    // ── Manager node click resets selection ───────────────────

    it('clicking manager node resets group and agent selection', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('group-growth')).toBeInTheDocument()
      })

      // Select a group first
      fireEvent.click(screen.getByTestId('group-growth'))
      expect(screen.queryByTestId('agent-card-dev_rel')).not.toBeInTheDocument()

      // Click manager to reset
      fireEvent.click(screen.getByTestId('manager-node'))
      expect(screen.getByTestId('agent-card-dev_rel')).toBeInTheDocument()
      expect(screen.getByTestId('agent-cards')).toHaveTextContent('全部 Agent')
    })
  })

  // ── Auto-sync on empty initial load ────────────────────────

  it('auto-syncs when initial agent list is empty', async () => {
    vi.mocked(api.getAgents)
      .mockResolvedValueOnce([])         // first call: empty
      .mockResolvedValueOnce(mockAgents) // after sync: has agents
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.syncAgents).mockResolvedValue(mockAgents)

    renderOrgChart()
    await waitFor(() => {
      expect(api.syncAgents).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
    })
  })
})
