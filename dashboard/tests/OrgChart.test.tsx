import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import OrgChart from '../src/pages/OrgChart'
import { api, OrgTree, DashboardStats } from '../src/api'

// Mock the api module
vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      getOrgTree: vi.fn(),
      getAgents: vi.fn(),
      getStats: vi.fn(),
      syncAgents: vi.fn(),
    },
  }
})

const mockOrgTree: OrgTree = {
  root: {
    id: 'cto',
    display_name: 'CTO / Manager',
    type: 'cto',
    goal: 'Synapse Network 赛博 CTO',
    icon: '🧠',
    children: [
      {
        id: 'settlement',
        display_name: 'Settlement Infra',
        type: 'domain',
        goal: '链上充值担保 + 链下网关秒扣',
        icon: '💰',
        color: 'amber',
        project: 'Synapse-Network',
        children: [
          { id: 'gateway', display_name: 'Gateway', type: 'service', goal: '中心化快速路由', project: 'Synapse-Network/services/gateway', children: [] },
          { id: 'gateway_admin', display_name: 'Gateway Admin', type: 'service', goal: '后台控制面 API', project: 'Synapse-Network/services/gateway-admin', children: [] },
          { id: 'user_front', display_name: 'User Frontend', type: 'service', goal: '消费端前端', project: 'Synapse-Network/services/user-front', children: [] },
          { id: 'admin_front', display_name: 'Admin Frontend', type: 'service', goal: '运营后台前端', project: 'Synapse-Network/services/admin-front', children: [] },
        ],
      },
      {
        id: 'growth',
        display_name: 'Growth Ops',
        type: 'domain',
        goal: '最大化开发者获客',
        icon: '📈',
        color: 'green',
        project: 'Synapse-Network-Growing',
        children: [
          {
            id: 'content',
            display_name: '内容与布道',
            type: 'team',
            goal: '',
            icon: '📢',
            color: 'blue',
            children: [
              { id: 'dev_rel', display_name: 'DevRel Engineer', type: 'agent', goal: '负责 DX 和技术布道', color: 'blue', skills: ['content-strategy', 'community-marketing'], children: [] },
              { id: 'content_writer', display_name: 'Content Writer', type: 'agent', goal: '负责极简主义文案写作', color: 'blue', skills: ['copywriting', 'copy-editing'], children: [] },
            ],
          },
          {
            id: 'growth_team',
            display_name: '增长与发布',
            type: 'team',
            goal: '',
            icon: '🚀',
            color: 'green',
            children: [
              { id: 'growth_lead', display_name: 'Growth Lead', type: 'agent', goal: '负责 GTM 和增长策略', color: 'green', skills: ['marketing-ideas'], children: [] },
              { id: 'launch_strategist', display_name: 'Launch Strategist', type: 'agent', goal: '负责发布节奏', color: 'green', skills: ['launch-strategy'], children: [] },
            ],
          },
          {
            id: 'optimization',
            display_name: '优化与分析',
            type: 'team',
            goal: '',
            icon: '📊',
            color: 'purple',
            children: [
              { id: 'seo_strategist', display_name: 'SEO Strategist', type: 'agent', goal: '负责关键词优化', color: 'purple', skills: ['seo-audit', 'ai-seo'], children: [] },
              { id: 'cro_optimizer', display_name: 'CRO Optimizer', type: 'agent', goal: '负责全链路转化率优化', color: 'purple', skills: ['page-cro'], children: [] },
            ],
          },
        ],
      },
      {
        id: 'engineering',
        display_name: 'Engineering Platform',
        type: 'domain',
        goal: '工程编排与 Agent 运行时',
        icon: '🏗️',
        color: 'sky',
        children: [
          { id: 'spec2flow', display_name: 'Spec2Flow Orchestrator', type: 'service', goal: '编排控制面', project: 'Spec2Flow', children: [] },
          { id: 'agents_memory', display_name: 'Agents Memory', type: 'service', goal: 'Agent 记忆运行时', project: 'Agents-Memory', children: [] },
        ],
      },
      {
        id: 'provider',
        display_name: 'Provider Runtime',
        type: 'domain',
        goal: 'API 卖家服务端运行时',
        icon: '🔌',
        color: 'rose',
        children: [
          { id: 'provider_service', display_name: 'Provider Service', type: 'service', goal: 'Provider 自有 API runtime', project: 'Synapse-Network-Provider', children: [] },
        ],
      },
      {
        id: 'sdk',
        display_name: 'SDK & Integration',
        type: 'domain',
        goal: 'Python/TypeScript SDK',
        icon: '📦',
        color: 'indigo',
        children: [
          { id: 'sdk_python', display_name: 'Python SDK', type: 'service', goal: 'Python 端 SDK', project: 'Synapse-Network-Sdk/python', children: [] },
          { id: 'sdk_typescript', display_name: 'TypeScript SDK', type: 'service', goal: 'TypeScript SDK', project: 'Synapse-Network-Sdk/typescript', children: [] },
        ],
      },
    ],
  },
}

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

describe('OrgChart — Multi-level Global View', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Loading & error states ───────────────────────────────

  it('shows skeleton while loading', () => {
    vi.mocked(api.getOrgTree).mockReturnValue(new Promise(() => {}))
    vi.mocked(api.getStats).mockReturnValue(new Promise(() => {}))
    renderOrgChart()
    expect(screen.getByTestId('orgchart-skeleton')).toBeInTheDocument()
  })

  it('shows error when backend is unreachable', async () => {
    vi.mocked(api.getOrgTree).mockRejectedValue(new Error('Network error'))
    vi.mocked(api.getStats).mockRejectedValue(new Error('Network error'))
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-error')).toBeInTheDocument()
    })
    expect(screen.getByText(/无法连接后端/)).toBeInTheDocument()
  })

  it('shows empty state when org tree is null', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(null as unknown as OrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-empty')).toBeInTheDocument()
    })
  })

  // ── Full render ──────────────────────────────────────────

  describe('with org tree loaded', () => {
    beforeEach(() => {
      vi.mocked(api.getOrgTree).mockResolvedValue(mockOrgTree)
      vi.mocked(api.getStats).mockResolvedValue(mockStats)
    })

    it('renders page with CTO node and domain row', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
      })
      expect(screen.getByTestId('cto-node')).toBeInTheDocument()
      expect(screen.getByTestId('domain-row')).toBeInTheDocument()
    })

    // ── CTO node ───────────────────────────────────────────

    it('renders CTO node with correct name', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('cto-node')).toBeInTheDocument()
      })
      expect(screen.getByTestId('cto-node')).toHaveTextContent('CTO / Manager')
    })

    // ── Stats bar ──────────────────────────────────────────

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

    // ── 5 Domain nodes ─────────────────────────────────────

    it('renders all 5 domain nodes', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('domain-row')).toBeInTheDocument()
      })
      expect(screen.getByTestId('domain-settlement')).toBeInTheDocument()
      expect(screen.getByTestId('domain-growth')).toBeInTheDocument()
      expect(screen.getByTestId('domain-engineering')).toBeInTheDocument()
      expect(screen.getByTestId('domain-provider')).toBeInTheDocument()
      expect(screen.getByTestId('domain-sdk')).toBeInTheDocument()
    })

    it('domain nodes show child count', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('domain-settlement')).toBeInTheDocument()
      })
      expect(screen.getByTestId('domain-settlement')).toHaveTextContent('4 子节点')
      expect(screen.getByTestId('domain-growth')).toHaveTextContent('3 子节点')
      expect(screen.getByTestId('domain-engineering')).toHaveTextContent('2 子节点')
    })

    // ── Auto-expanded domains ──────────────────────────────

    it('auto-expands all domains on load', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('domain-detail-settlement')).toBeInTheDocument()
      })
      expect(screen.getByTestId('domain-detail-growth')).toBeInTheDocument()
      expect(screen.getByTestId('domain-detail-engineering')).toBeInTheDocument()
      expect(screen.getByTestId('domain-detail-provider')).toBeInTheDocument()
      expect(screen.getByTestId('domain-detail-sdk')).toBeInTheDocument()
    })

    // ── Settlement domain: service nodes ────────────────────

    it('settlement domain shows 4 service nodes', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('services-settlement')).toBeInTheDocument()
      })
      expect(screen.getByTestId('node-gateway')).toBeInTheDocument()
      expect(screen.getByTestId('node-gateway_admin')).toBeInTheDocument()
      expect(screen.getByTestId('node-user_front')).toBeInTheDocument()
      expect(screen.getByTestId('node-admin_front')).toBeInTheDocument()
    })

    // ── Growth domain: team-based layout ────────────────────

    it('growth domain shows 3 teams with agents', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('teams-growth')).toBeInTheDocument()
      })
      // Teams
      expect(screen.getByTestId('team-content')).toBeInTheDocument()
      expect(screen.getByTestId('team-growth_team')).toBeInTheDocument()
      expect(screen.getByTestId('team-optimization')).toBeInTheDocument()
      // Agent nodes within teams
      expect(screen.getByTestId('node-dev_rel')).toBeInTheDocument()
      expect(screen.getByTestId('node-content_writer')).toBeInTheDocument()
      expect(screen.getByTestId('node-growth_lead')).toBeInTheDocument()
      expect(screen.getByTestId('node-launch_strategist')).toBeInTheDocument()
      expect(screen.getByTestId('node-seo_strategist')).toBeInTheDocument()
      expect(screen.getByTestId('node-cro_optimizer')).toBeInTheDocument()
    })

    it('agent nodes show skills', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('node-dev_rel')).toBeInTheDocument()
      })
      expect(screen.getByTestId('node-dev_rel')).toHaveTextContent('content-strategy')
      expect(screen.getByTestId('node-dev_rel')).toHaveTextContent('community-marketing')
    })

    // ── Engineering domain ──────────────────────────────────

    it('engineering domain shows Spec2Flow and Agents Memory', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('services-engineering')).toBeInTheDocument()
      })
      expect(screen.getByTestId('node-spec2flow')).toBeInTheDocument()
      expect(screen.getByTestId('node-agents_memory')).toBeInTheDocument()
    })

    // ── SDK domain ──────────────────────────────────────────

    it('sdk domain shows Python and TypeScript SDKs', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('services-sdk')).toBeInTheDocument()
      })
      expect(screen.getByTestId('node-sdk_python')).toBeInTheDocument()
      expect(screen.getByTestId('node-sdk_typescript')).toBeInTheDocument()
    })

    // ── Click interactions ──────────────────────────────────

    it('clicking CTO node shows detail', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('cto-node')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('node-detail')).not.toBeInTheDocument()
      fireEvent.click(screen.getByTestId('cto-node'))
      expect(screen.getByTestId('node-detail')).toBeInTheDocument()
      expect(screen.getByTestId('detail-cto')).toHaveTextContent('CTO / Manager')
    })

    it('clicking agent node shows detail with skills', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('node-seo_strategist')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('node-seo_strategist'))
      expect(screen.getByTestId('node-detail')).toBeInTheDocument()
      expect(screen.getByTestId('detail-seo_strategist')).toHaveTextContent('SEO Strategist')
      expect(screen.getByTestId('detail-seo_strategist')).toHaveTextContent('seo-audit')
    })

    it('clicking service node shows detail with project', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('node-gateway')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('node-gateway'))
      expect(screen.getByTestId('node-detail')).toBeInTheDocument()
      expect(screen.getByTestId('detail-gateway')).toHaveTextContent('Gateway')
    })

    it('clicking domain collapses/expands its detail', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('domain-detail-provider')).toBeInTheDocument()
      })
      // Click to collapse
      fireEvent.click(screen.getByTestId('domain-provider'))
      expect(screen.queryByTestId('domain-detail-provider')).not.toBeInTheDocument()
      // Click to expand again
      fireEvent.click(screen.getByTestId('domain-provider'))
      expect(screen.getByTestId('domain-detail-provider')).toBeInTheDocument()
    })

    it('clicking same node toggles detail off', async () => {
      renderOrgChart()
      await waitFor(() => {
        expect(screen.getByTestId('node-gateway')).toBeInTheDocument()
      })
      fireEvent.click(screen.getByTestId('node-gateway'))
      expect(screen.getByTestId('node-detail')).toBeInTheDocument()
      fireEvent.click(screen.getByTestId('node-gateway'))
      expect(screen.queryByTestId('node-detail')).not.toBeInTheDocument()
    })

    // ── Sync button ─────────────────────────────────────────

    it('sync button triggers API calls', async () => {
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
})
