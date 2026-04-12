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
      materializeCompanyReviewBundle: vi.fn(),
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
    completed_requirements: 5,
    completion_rate: 62.5,
    open_signals: 3,
    approval_required_decisions: 1,
    rebalance_opportunities: 1,
    projects_over_budget: 0,
    blocked_publish_projects: 1,
    budget_spent_points: 144,
    tokens_used: 188000,
    prompt_cache_saved_chars: 9200,
    deduped_bindings: 7,
    escalations: 2,
    downgrades: 3,
    human_gate_hotspots: 2,
    tier_mix: {
      mini: 4,
      standard: 9,
      max: 2,
    },
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
      completed_requirements: 3,
      budget_spent_points: 88,
      prompt_cache_saved_chars: 4200,
      escalations: 1,
      downgrades: 2,
      tier_mix: {
        mini: 1,
        standard: 4,
        max: 1,
      },
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
      item_key: 'bug_report:7',
      title: 'SDK critical release blocker',
      severity: 'high',
      summary: 'The SDK release is blocked by failing checks.',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      recommendation: 'Convert to a release bottleneck requirement.',
      incident_family: 'verification',
      incident_code: 'automated_validation_failure',
      recovery_status: 'bugfix_loop_active',
      requirement_id: 40,
      source_ref: 'incident:bug_report:7',
    },
  ],
  human_gate_hotspots: [
    {
      gate_key: 'step_operator_confirmation::max_tier::implementation::synapse-network-sdk',
      title: 'Synapse-Network-Sdk max-tier',
      approval_type: 'step_operator_confirmation',
      approval_scope: 'max_tier',
      step_type: 'implementation',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      occurrence_count: 2,
      pending_count: 1,
      latest_status: 'pending',
      summary: 'Synapse-Network-Sdk triggered step_operator_confirmation on implementation with scope max_tier.',
      recommendation: 'Split or reroute work earlier so fewer branches escalate into max-tier human-gated execution.',
    },
    {
      gate_key: 'publish_manual_gate::publish::synapse-network-sdk',
      title: 'Synapse-Network-Sdk publish gate',
      approval_type: 'publish_manual_gate',
      approval_scope: 'publish',
      step_type: 'publish',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      occurrence_count: 1,
      pending_count: 1,
      latest_status: 'pending',
      summary: 'Synapse-Network-Sdk has review-ready work waiting on manual publish approval.',
      recommendation: 'Stabilize delivery checks so more review-ready work can auto-promote without operator intervention.',
    },
  ],
  automation_candidates: [
    {
      candidate_key: 'automation:step_operator_confirmation::max_tier::implementation::synapse-network-sdk',
      title: 'Automate gate: Synapse-Network-Sdk max-tier',
      gate_key: 'step_operator_confirmation::max_tier::implementation::synapse-network-sdk',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      automation_type: 'max_tier_branch_reduction',
      priority: 'normal',
      rationale: 'Split or reroute work earlier so fewer branches escalate into max-tier human-gated execution.',
      occurrence_count: 2,
    },
    {
      candidate_key: 'automation:publish_manual_gate::publish::synapse-network-sdk',
      title: 'Automate gate: Synapse-Network-Sdk publish gate',
      gate_key: 'publish_manual_gate::publish::synapse-network-sdk',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      automation_type: 'publish_automation',
      priority: 'high',
      rationale: 'Stabilize delivery checks so more review-ready work can auto-promote without operator intervention.',
      occurrence_count: 1,
    },
  ],
  next_cycle_recommendations: [
    {
      candidate_type: 'incident',
      title: 'SDK critical release blocker',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      action: 'approval_required',
      score: 92,
      budget_cost: 24,
      source_ref: 'incident:bug_report:7',
      rationale: 'Resolve the active incident before expanding automation scope.',
      approval_required: true,
      requirement_id: 40,
      incident_family: 'verification',
      incident_code: 'automated_validation_failure',
      recovery_status: 'operator_review_required',
    },
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
  next_cycle_requirement_bundle: [
    {
      bundle_item_key: 'signal:7',
      title: 'Release Bottleneck: Synapse-Network-Sdk - SDK critical release blocker',
      candidate_type: 'signal',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      action: 'intake',
      materialization_mode: 'create_requirement',
      priority: 'high',
      score: 88,
      budget_cost: 26,
      source_ref: 'signal:7',
      target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Sdk',
      requirement_id: null,
      template_key: 'release_bottleneck',
      rationale: 'Top-ranked release bottleneck across the portfolio.',
      description_markdown: '## Optimization Template',
      acceptance_checks: [
        { check_key: 'release_blocker_removed' },
        { check_key: 'rollback_path_documented' },
      ],
      approval_required: true,
    },
  ],
  operator_review_package: {
    title: 'Operator Review Package',
    summary_markdown: 'Cycle `2026-W15` operator package.\n\n- Bundle candidates: 1',
    checklist: [
      'Confirm the next-cycle bundle matches the current company goal and operator bandwidth.',
    ],
    decisions: [
      {
        decision_key: 'bundle-approval:signal:7',
        title: 'Approve next-cycle bundle item: Release Bottleneck: Synapse-Network-Sdk - SDK critical release blocker',
        decision_type: 'bundle_approval',
        severity: 'high',
        summary: 'Synapse-Network-Sdk / intake / score 88',
        owner_hint: 'operator',
        related_bundle_item_key: 'signal:7',
      },
    ],
    recommended_bundle_item_keys: ['signal:7'],
  },
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
    vi.mocked(api.materializeCompanyReviewBundle).mockResolvedValue({
      review_id: 1,
      created_requirement_ids: [42],
      reused_requirement_ids: [],
      skipped_bundle_item_keys: [],
      items: [
        {
          bundle_item_key: 'signal:7',
          status: 'created',
          title: 'Release Bottleneck: Synapse-Network-Sdk - SDK critical release blocker',
          action: 'create_requirement',
          requirement_id: 42,
          source_ref: 'company-review-bundle:1:signal:7',
        },
      ],
    })
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
    expect(screen.getByTestId('next-cycle-bundle-panel')).toHaveTextContent('Next Cycle Requirement Bundle')
    expect(screen.getByTestId('operator-review-package-panel')).toHaveTextContent('Operator Review Package')
    expect(screen.getByTestId('company-review-incidents')).toHaveTextContent('automated_validation_failure')
    expect(screen.getByTestId('company-review-incidents')).toHaveTextContent('requirement #40')
    expect(screen.getByTestId('company-review-recommendations')).toHaveTextContent('approval_required')
    expect(screen.getByTestId('company-review-recommendations')).toHaveTextContent('needs operator approval')
    expect(screen.getByTestId('company-review-human-gates')).toHaveTextContent('max_tier')
    expect(screen.getByTestId('company-review-human-gates')).toHaveTextContent('count: 2')
    expect(screen.getByTestId('company-review-automation-candidates')).toHaveTextContent('publish_automation')
    expect(screen.getByText('completion %')).toBeInTheDocument()
    expect(screen.getByText('Prompt Cache')).toBeInTheDocument()
    expect(screen.getByText(/saved chars: 9200/)).toBeInTheDocument()
    expect(screen.getByText(/deduped bindings: 7/)).toBeInTheDocument()
    expect(screen.getByText(/escalations: 2/)).toBeInTheDocument()
    expect(screen.getByText(/tier mix: mini 1 \/ std 4 \/ max 1/i)).toBeInTheDocument()
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

  it('materializes the next cycle bundle', async () => {
    vi.mocked(api.getOrgTree).mockResolvedValue(mockOrgTree)
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('company-review-panel')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('materialize-company-review-bundle'))
    await waitFor(() => {
      expect(api.materializeCompanyReviewBundle).toHaveBeenCalledWith(1, {})
      expect(screen.getByTestId('company-review-bundle-result')).toHaveTextContent('created 1, reused 0')
    })
  })
})
