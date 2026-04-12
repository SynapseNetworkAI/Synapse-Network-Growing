import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import OrgChart from '../src/pages/OrgChart'
import { api, DashboardStats, CompanyOperatingReview, RecurringWorkflow } from '../src/api'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      getStats: vi.fn(),
      getCompanyOperatingReview: vi.fn(),
      materializeCompanyReviewBundle: vi.fn(),
      getRecurringWorkflows: vi.fn(),
      runRecurringWorkflow: vi.fn(),
    },
  }
})

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
    workflow_rituals: {
      morning_intake_sweep: { operator_attention_count: 2, requires_operator_review: true },
      dispatcher_loop: { stuck_requirement_count: 1, approval_reminder_count: 1 },
      closeout_and_compact_sweep: { stale_requirement_count: 1, review_snapshot_count: 2 },
    },
  },
  created_at: '2026-04-11T13:00:00Z',
  updated_at: '2026-04-11T13:05:00Z',
}

const mockRecurringWorkflows: RecurringWorkflow[] = [
  {
    id: 1,
    workflow_key: 'morning_intake_sweep',
    display_name: 'Morning Intake Sweep',
    description: 'Refresh intake sources.',
    status: 'active',
    trigger_type: 'scheduled',
    owner_role: 'ops_intake_manager',
    schedule: { cadence: 'daily' },
    input_query: {},
    output_action: {},
    escalation_rule: {},
    validation_signal: {},
    is_builtin: true,
    last_run_at: '2026-04-11T09:00:00Z',
    last_result: {
      created_requirement_ids: [11, 12],
      operator_attention_items: [{ title: 'Signal A' }, { title: 'Incident B' }],
    },
    created_at: '2026-04-11T08:00:00Z',
    updated_at: '2026-04-11T09:00:00Z',
  },
  {
    id: 2,
    workflow_key: 'dispatcher_loop',
    display_name: 'Dispatcher Loop',
    description: 'Advance queue and follow through.',
    status: 'active',
    trigger_type: 'scheduled',
    owner_role: 'portfolio_operator',
    schedule: { cadence: 'hourly' },
    input_query: {},
    output_action: {},
    escalation_rule: {},
    validation_signal: {},
    is_builtin: true,
    last_run_at: '2026-04-11T11:00:00Z',
    last_result: {
      started_ids: [31],
      follow_up_actions: [{ action: 'approval_reminder' }],
    },
    created_at: '2026-04-11T08:00:00Z',
    updated_at: '2026-04-11T11:00:00Z',
  },
  {
    id: 3,
    workflow_key: 'closeout_and_compact_sweep',
    display_name: 'Closeout And Compact Sweep',
    description: 'Sweep acceptance and stale requirements.',
    status: 'active',
    trigger_type: 'scheduled',
    owner_role: 'tester',
    schedule: { cadence: 'daily' },
    input_query: {},
    output_action: {},
    escalation_rule: {},
    validation_signal: {},
    is_builtin: true,
    last_run_at: '2026-04-11T18:00:00Z',
    last_result: {
      acceptance_candidates: 2,
      review_snapshot_requirement_ids: [40, 41],
    },
    created_at: '2026-04-11T08:00:00Z',
    updated_at: '2026-04-11T18:00:00Z',
  },
  {
    id: 4,
    workflow_key: 'weekly_operating_review',
    display_name: 'Weekly Operating Review',
    description: 'Refresh company review.',
    status: 'active',
    trigger_type: 'scheduled',
    owner_role: 'company_reviewer',
    schedule: { cadence: 'weekly' },
    input_query: {},
    output_action: {},
    escalation_rule: {},
    validation_signal: {},
    is_builtin: true,
    last_run_at: '2026-04-11T10:00:00Z',
    last_result: {
      bundle_item_count: 1,
      automation_candidate_count: 2,
    },
    created_at: '2026-04-11T08:00:00Z',
    updated_at: '2026-04-11T10:00:00Z',
  },
]

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
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
    vi.mocked(api.runRecurringWorkflow).mockResolvedValue({
      workflow_key: 'dispatcher_loop',
      status: 'completed',
      run_started_at: '2026-04-12T09:00:00Z',
      result: {
        started_ids: [71],
        follow_up_actions: [{ action: 'replan' }, { action: 'approval_reminder' }],
      },
    })
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
    vi.mocked(api.getStats).mockReturnValue(new Promise(() => {}))
    vi.mocked(api.getCompanyOperatingReview).mockReturnValue(new Promise(() => {}))
    renderOrgChart()
    expect(screen.getByTestId('orgchart-skeleton')).toBeInTheDocument()
  })

  it('shows error state when api calls fail', async () => {
    vi.mocked(api.getStats).mockRejectedValue(new Error('network'))
    vi.mocked(api.getCompanyOperatingReview).mockRejectedValue(new Error('network'))
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-error')).toBeInTheDocument()
    })
  })

  it('renders the operator dashboard', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
    })

    expect(screen.getByText('Company COO Dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('company-review-panel')).toHaveTextContent('Company Operating Review')
    expect(screen.getAllByText('SDK critical release blocker').length).toBeGreaterThan(0)
    expect(screen.getByTestId('next-cycle-bundle-panel')).toHaveTextContent('Next Cycle Requirement Bundle')
    expect(screen.getByTestId('operator-review-package-panel')).toHaveTextContent('Operator Review Package')
    expect(screen.getByTestId('operator-rituals-panel')).toHaveTextContent('Daily / Weekly Ritual Board')
    expect(screen.getByTestId('operator-priority-panel')).toHaveTextContent('Today Priorities')
    expect(screen.getByTestId('weekly-coo-package-panel')).toHaveTextContent('Weekly COO Review')
    expect(screen.getByTestId('ritual-morning_intake_sweep')).toHaveTextContent('operator attention: 2')
    expect(screen.getByTestId('ritual-dispatcher_loop')).toHaveTextContent('follow-ups: 1')
    expect(screen.getByTestId('ritual-closeout_and_compact_sweep')).toHaveTextContent('snapshots: 2')
    expect(screen.getByTestId('ritual-weekly_operating_review')).toHaveTextContent('automation: 2')
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

  it('explains that the homepage is now ritual-driven', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByText('首页聚焦 operating review、ritual、bundle 和 operator decisions。')).toBeInTheDocument()
      expect(screen.queryByText('同步 Roles')).not.toBeInTheDocument()
      expect(screen.queryByText('刷新 Review')).not.toBeInTheDocument()
    })
  })

  it('materializes the next cycle bundle', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
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

  it('runs recurring rituals from the operator dashboard', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('ritual-dispatcher_loop')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('run-dispatcher_loop'))
    await waitFor(() => {
      expect(api.runRecurringWorkflow).toHaveBeenCalledWith('dispatcher_loop', {})
      expect(screen.getByTestId('ritual-dispatcher_loop')).toHaveTextContent('follow-ups: 2')
    })
  })
})
