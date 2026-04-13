import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import OrgChart from '../src/pages/OrgChart'
import CompanyReviewPage from '../src/pages/CompanyReviewPage'
import RoleKpisPage from '../src/pages/RoleKpisPage'
import AutonomyPage from '../src/pages/AutonomyPage'
import RecurringWorkflowsPage from '../src/pages/RecurringWorkflowsPage'
import App from '../src/App'
import { api, DashboardStats, CompanyOperatingReview, RecurringWorkflow, RoleKpiSnapshot } from '../src/api'

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      getStats: vi.fn(),
      getCompanyOperatingReview: vi.fn(),
      getRoleKpis: vi.fn(),
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

const mockRoleKpis: RoleKpiSnapshot = {
  roles: [
    {
      role_id: 'dev_rel',
      display_name: 'DevRel Engineer',
      group: 'content',
      mission: 'Owns developer-facing delivery and execution.',
      task_count: 8,
      completed_count: 5,
      active_task_count: 1,
      pending_task_count: 2,
      failed_task_count: 1,
      backlog_count: 3,
      reopened_task_count: 1,
      approval_dependency_count: 2,
      completion_rate: 62.5,
      reopen_rate: 12.5,
      approval_dependency_rate: 25,
      average_token_cost: 3200,
      average_budget_cost_points: 14,
      tokens_used_total: 16000,
      budget_cost_points_total: 70,
      open_requirement_count: 2,
      status_mix: { completed: 5, running: 1, pending: 2 },
    },
  ],
  approval_roles: [
    {
      role_id: 'reviewer',
      assigned_count: 4,
      pending_count: 1,
      decided_count: 3,
      average_turnaround_hours: 6,
      disagreement_rate: 25,
      route_to_human_rate: 50,
      approve_recommendation_count: 2,
      revise_recommendation_count: 1,
      route_to_human_count: 2,
    },
  ],
  summary: {
    role_count: 1,
    total_backlog_count: 3,
    overloaded_role_count: 1,
    approval_pending_count: 1,
    approval_stale_count: 0,
  },
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
    open_bug_pressure: 3,
    unresolved_critical_bugs: 1,
    bug_requirements_created: 2,
    recurring_bug_fingerprint_count: 2,
    cross_project_bug_recoveries: 1,
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
      open_bug_count: 2,
      critical_bug_count: 1,
      converted_bug_count: 1,
      recurring_bug_count: 2,
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
  recurring_bug_fingerprints: [
    {
      bug_id: 7,
      bug_key: 'delivery_blocker_bug::synapse-network-sdk::fp-release-blocker',
      title: 'SDK release blocker keeps failing',
      severity: 'critical',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      fingerprint: 'fp-release-blocker',
      occurrence_count: 5,
      score_total: 96,
      source_key: 'delivery_blocker_bug',
      converted_requirement_id: null,
      last_seen_at: '2026-04-11T12:00:00Z',
    },
    {
      bug_id: 8,
      bug_key: 'workflow_incident::synapse-network-sdk::fp-runtime-chain',
      title: 'Runtime chain desync',
      severity: 'high',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      fingerprint: 'fp-runtime-chain',
      occurrence_count: 3,
      score_total: 84,
      source_key: 'workflow_incident',
      converted_requirement_id: 40,
      last_seen_at: '2026-04-11T12:10:00Z',
    },
  ],
  cross_project_bug_recoveries: [
    {
      item_key: 'cross-project-bug:9',
      title: 'Provider auth desync',
      severity: 'high',
      summary: 'Bug affects 2 projects: Synapse-Network, Synapse-Network-Provider. Occurrences: 4.',
      project_key: 'multi-project',
      project_display_name: 'Multiple Projects',
      recommendation: 'Coordinate a cross-project remediation and validate the recovery path across all affected repositories.',
      incident_family: 'cross_project_bug_recovery',
      incident_code: 'fp-provider-auth-desync',
      recovery_status: 'requirement_created',
      requirement_id: 51,
      source_ref: 'bug-intake:9',
      affected_project_keys: ['synapse-network', 'synapse-network-provider'],
      affected_project_display_names: ['Synapse-Network', 'Synapse-Network-Provider'],
      score_total: 91,
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
    autonomous_decision_count: 3,
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
  autonomous_coo_posture: {
    mode: 'autonomous_coo',
    operator_only_high_risk: true,
    autonomous_workflow_keys: ['bug_log_sweep', 'morning_intake_sweep', 'dispatcher_loop', 'closeout_and_compact_sweep', 'approval_sweep'],
    high_risk_decision_count: 1,
    autonomous_decision_count: 3,
    operator_queue_count: 2,
    pending_human_gate_count: 1,
    auto_approved_requirement_count: 4,
    stale_approval_count: 1,
    stuck_requirement_count: 1,
    critical_incident_count: 1,
    requires_operator_attention: true,
    autonomous_execution_rate: 50,
    summary_markdown: 'Autonomous COO mode keeps `5` daily loops self-running, while only `2` high-risk items remain in the operator queue.',
  },
  source_snapshot: {
    scheduler_generated_at: '2026-04-11T13:00:00Z',
    bug_backlog_summary: {
      open_bug_pressure: 3,
      unresolved_critical_bugs: 1,
      bug_requirements_created: 2,
      recurring_bug_fingerprint_count: 2,
      cross_project_bug_recoveries: 1,
    },
    workflow_rituals: {
      morning_intake_sweep: { operator_attention_count: 2, requires_operator_review: true },
      dispatcher_loop: { stuck_requirement_count: 1, approval_reminder_count: 1 },
      closeout_and_compact_sweep: { stale_requirement_count: 1, review_snapshot_count: 2 },
      approval_sweep: { auto_approved_count: 4, stale_approval_count: 1 },
    },
  },
  created_at: '2026-04-11T13:00:00Z',
  updated_at: '2026-04-11T13:05:00Z',
}

const mockRecurringWorkflows: RecurringWorkflow[] = [
  {
    id: 0,
    workflow_key: 'bug_log_sweep',
    display_name: 'Bug Log Sweep',
    description: 'Sweep runtime logs and auto-materialize high-value bugs.',
    status: 'active',
    trigger_type: 'scheduled',
    owner_role: 'runtime_reliability_engineer',
    schedule: { cadence: 'interval', interval_minutes: 5 },
    input_query: {},
    output_action: {},
    escalation_rule: {},
    validation_signal: {},
    is_builtin: true,
    last_run_at: '2026-04-11T08:55:00Z',
    last_result: {
      created_bug_ids: [7, 8],
      materialized_requirement_ids: [40],
    },
    created_at: '2026-04-11T08:00:00Z',
    updated_at: '2026-04-11T08:55:00Z',
  },
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
    <MemoryRouter>
      <OrgChart />
    </MemoryRouter>
  )
}

function renderCompanyReviewPage() {
  return render(
    <MemoryRouter>
      <CompanyReviewPage />
    </MemoryRouter>
  )
}

function renderRoleKpisPage() {
  return render(
    <MemoryRouter>
      <RoleKpisPage />
    </MemoryRouter>
  )
}

function renderAutonomyPage() {
  return render(
    <MemoryRouter>
      <AutonomyPage />
    </MemoryRouter>
  )
}

function renderRecurringWorkflowsPage() {
  return render(
    <MemoryRouter>
      <RecurringWorkflowsPage />
    </MemoryRouter>
  )
}

function renderApp(initialPath = '/overview') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>
  )
}

describe('OrgChart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getCompanyOperatingReview).mockResolvedValue(mockReview)
    vi.mocked(api.getRoleKpis).mockResolvedValue(mockRoleKpis)
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
    vi.mocked(api.getRoleKpis).mockRejectedValue(new Error('network'))
    renderOrgChart()
    await waitFor(() => {
      expect(screen.getByTestId('orgchart-error')).toBeInTheDocument()
    })
  })

  it('renders the slim overview dashboard', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
    })

    expect(screen.getByText('Company COO Dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('autonomous-coo-panel')).toHaveTextContent('Autonomous COO Mode')
    expect(screen.getByTestId('operator-priority-panel')).toHaveTextContent('Today Priorities')
    expect(screen.getByTestId('weekly-coo-package-panel')).toHaveTextContent('Weekly COO Review')
    expect(screen.queryByTestId('company-review-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('operator-rituals-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('overview-quick-links')).not.toBeInTheDocument()
  })

  it('explains that the homepage is now a lightweight entry page', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
    renderOrgChart()

    await waitFor(() => {
      expect(screen.getByText('首页现在只保留运营总览与入口，不再承载完整 COO 大盘。')).toBeInTheDocument()
    })
  })

  it('renders the company review page and materializes the next cycle bundle', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
    renderCompanyReviewPage()

    await waitFor(() => {
      expect(screen.getByTestId('company-review-panel')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('materialize-company-review-bundle'))
    await waitFor(() => {
      expect(api.materializeCompanyReviewBundle).toHaveBeenCalledWith(1, {})
      expect(screen.getByTestId('company-review-bundle-result')).toHaveTextContent('created 1, reused 0')
    })
  })

  it('renders the role KPI page', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderRoleKpisPage()

    await waitFor(() => {
      expect(screen.getByTestId('role-kpis-page')).toBeInTheDocument()
    })

    expect(screen.getByTestId('role-kpis-panel')).toHaveTextContent('Role KPI & Work Allocation')
    expect(screen.getByTestId('role-kpis-panel')).toHaveTextContent('DevRel Engineer')
    expect(screen.getByTestId('role-kpis-panel')).toHaveTextContent('reviewer')
  })

  it('renders the autonomy page', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderAutonomyPage()

    await waitFor(() => {
      expect(screen.getByTestId('autonomy-page')).toBeInTheDocument()
    })

    expect(screen.getByTestId('autonomous-coo-panel')).toHaveTextContent('operator queue')
    expect(screen.getByTestId('autonomous-coo-panel')).toHaveTextContent('pending human gates: 1')
  })

  it('runs recurring rituals from the recurring workflows page', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    vi.mocked(api.getRecurringWorkflows).mockResolvedValue(mockRecurringWorkflows)
    renderRecurringWorkflowsPage()

    await waitFor(() => {
      expect(screen.getByTestId('recurring-workflows-page')).toBeInTheDocument()
    })

    expect(screen.getByTestId('operator-rituals-panel')).toHaveTextContent('运营自动化控制台')
    expect(screen.getByTestId('ritual-bug_log_sweep')).toHaveTextContent('new bugs 2')
    expect(screen.getByTestId('ritual-weekly_operating_review')).toHaveTextContent('bundle 1')
    fireEvent.click(screen.getByTestId('run-dispatcher_loop'))
    await waitFor(() => {
      expect(api.runRecurringWorkflow).toHaveBeenCalledWith('dispatcher_loop', {})
      expect(screen.getByTestId('ritual-dispatcher_loop')).toHaveTextContent('follow-ups 2')
    })
  })

  it('shows the new overview tree and recurring workflow menu in app navigation', async () => {
    vi.mocked(api.getStats).mockResolvedValue(mockStats)
    renderApp('/overview')

    await waitFor(() => {
    expect(screen.getAllByText('运营总览').length).toBeGreaterThan(0)
  })

    expect(screen.getAllByText('定时任务').length).toBeGreaterThan(0)
    expect(screen.getAllByText('发布中心').length).toBeGreaterThan(0)
    expect(screen.getAllByText('公司复盘').length).toBeGreaterThan(0)
    expect(screen.getAllByText('角色 KPI').length).toBeGreaterThan(0)
    expect(screen.getAllByText('自治模式').length).toBeGreaterThan(0)
    expect(screen.getByTestId('orgchart-page')).toBeInTheDocument()
  })
})
