import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import PlanningPage from '../src/pages/PlanningPage'

const goalbCandidate = {
  id: 42,
  manifest_id: 1,
  goal_key: 'goalb',
  candidate_fingerprint: 'goalb-fingerprint',
  title: 'Advance goal: 验证 Growing 可以根据目标自动拆分任务',
  description_markdown: 'GoalB candidate generated from the Operating Manifest.',
  project_id: 7,
  project_key: 'synapse-network-growing',
  workflow_key: 'gateway_reliability_repair',
  priority: 'normal',
  risk_level: 'normal',
  confidence: 0.72,
  rationale: 'Active goal has no active requirement and has candidate capacity.',
  expected_evidence: ['accepted candidate', 'created requirement', 'workflow evidence'],
  status: 'pending',
  suppression_reason: null,
  reject_reason: null,
  reject_comment: null,
  approved_by: null,
  materialized_requirement_id: null,
  metadata: { generated_by: 'deterministic_planner_sweep_v1' },
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  approved_at: null,
  rejected_at: null,
}

const mission = {
  manifest: {
    id: 1,
    manifest_key: 'active',
    active_slot: 'global',
    version_name: 'GoalB Dogfood',
    cycle_label: '2026-W16',
    status: 'active',
    revision: 2,
    payload: {
      global_budget: { daily_usd_limit: 25, max_concurrent_workers: 2 },
      focus_weights: { reliability: 0.6, growth: 0.3, ops: 0.1 },
      global_constraints: ['No production deploy without human approval.'],
      goals: [
        {
          goal_key: 'goalb',
          domain: 'ops',
          status: 'active',
          intent: '验证 Growing 可以根据目标自动拆分任务，转成正式需求，并由 declarative workflow 自动执行跑通。',
          success_metric: 'goalb_demo_workflow_completed == true',
          workflow_key: 'gateway_reliability_repair',
          project_key: 'synapse-network-growing',
          priority: 'normal',
          risk_level: 'normal',
          weight: 0.1,
        },
      ],
    },
    review_summary: null,
    created_at: '2026-04-19T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    archived_at: null,
  },
  global_steering: {
    focus_weights: { reliability: 0.6, growth: 0.3, ops: 0.1 },
    global_budget: { daily_usd_limit: 25, max_concurrent_workers: 2 },
    global_constraints: ['No production deploy without human approval.'],
  },
  goal_lanes: [
    {
      goal_key: 'goalb',
      goal: {
        goal_key: 'goalb',
        domain: 'ops',
        status: 'active',
        intent: '验证 Growing 可以根据目标自动拆分任务，转成正式需求，并由 declarative workflow 自动执行跑通。',
        success_metric: 'goalb_demo_workflow_completed == true',
        weight: 0.1,
      },
      rollup: {
        manifest_id: 1,
        goal_key: 'goalb',
        goal: { goal_key: 'goalb', status: 'active' },
        candidate_status_counts: { pending: 1 },
        requirement_status_counts: {},
        workflow_status_counts: {},
        release_status_counts: {},
        candidates: [],
        requirements: [],
        workflow_runs: [],
        releases: [],
      },
      candidates: [goalbCandidate],
    },
  ],
  candidate_totals: { pending: 1, approved: 0, materialized: 0, rejected: 0, suppressed: 0 },
  history_preview: { items: [], total: 0, page: 1, page_size: 10, total_pages: 1 },
  last_sweep: null,
}

const mockApi = {
  getPlanningMissionControl: vi.fn(),
  getPlanningManifestHistory: vi.fn(),
  saveActivePlanningManifest: vi.fn(),
  runPlannerSweep: vi.fn(),
  approveRequirementCandidate: vi.fn(),
  approveAndRunRequirementCandidate: vi.fn(),
  rejectRequirementCandidate: vi.fn(),
  materializeRequirementCandidate: vi.fn(),
  archiveAndStartPlanningCycle: vi.fn(),
  dropPlanningGoal: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getPlanningMissionControl: (...args: unknown[]) => mockApi.getPlanningMissionControl(...args),
    getPlanningManifestHistory: (...args: unknown[]) => mockApi.getPlanningManifestHistory(...args),
    saveActivePlanningManifest: (...args: unknown[]) => mockApi.saveActivePlanningManifest(...args),
    runPlannerSweep: (...args: unknown[]) => mockApi.runPlannerSweep(...args),
    approveRequirementCandidate: (...args: unknown[]) => mockApi.approveRequirementCandidate(...args),
    approveAndRunRequirementCandidate: (...args: unknown[]) => mockApi.approveAndRunRequirementCandidate(...args),
    rejectRequirementCandidate: (...args: unknown[]) => mockApi.rejectRequirementCandidate(...args),
    materializeRequirementCandidate: (...args: unknown[]) => mockApi.materializeRequirementCandidate(...args),
    archiveAndStartPlanningCycle: (...args: unknown[]) => mockApi.archiveAndStartPlanningCycle(...args),
    dropPlanningGoal: (...args: unknown[]) => mockApi.dropPlanningGoal(...args),
  },
}))

describe('PlanningPage GoalB mission control', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getPlanningMissionControl.mockResolvedValue(mission)
    mockApi.getPlanningManifestHistory.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10, total_pages: 1 })
    mockApi.saveActivePlanningManifest.mockResolvedValue(mission.manifest)
    mockApi.runPlannerSweep.mockResolvedValue({
      id: 9,
      manifest_id: 1,
      status: 'succeeded',
      triggered_by: 'operator',
      dry_run: false,
      input_snapshot: {},
      parsed_output: {},
      created_candidate_ids: [42],
      suppressed_items: [],
      error_excerpt: null,
      started_at: '2026-04-19T00:00:00Z',
      completed_at: '2026-04-19T00:00:01Z',
      duration_ms: 1000,
    })
    mockApi.approveRequirementCandidate.mockResolvedValue({ ...goalbCandidate, status: 'approved', approved_by: 'operator' })
    mockApi.approveAndRunRequirementCandidate.mockResolvedValue({
      candidate: { ...goalbCandidate, status: 'materialized', materialized_requirement_id: 88 },
      requirement_id: 88,
      workflow_run_id: 12,
      workflow_status: 'succeeded',
      workflow_current_state: 'done',
      auto_run_status: 'workflow_completed',
      next_action: 'view_completion_evidence',
    })
    mockApi.rejectRequirementCandidate.mockResolvedValue({ ...goalbCandidate, status: 'rejected', reject_reason: 'operator_rejected' })
    mockApi.materializeRequirementCandidate.mockResolvedValue({
      candidate: { ...goalbCandidate, status: 'materialized', materialized_requirement_id: 88 },
      requirement_id: 88,
    })
  })

  it('renders GoalB inside Mission Control and runs planner/candidate actions from the goal lane', async () => {
    render(<PlanningPage />)

    await waitFor(() => expect(mockApi.getPlanningMissionControl).toHaveBeenCalled())
    const missionTab = screen.getByTestId('mission-control-tab')
    expect(missionTab).toHaveTextContent('goalb')
    expect(missionTab).toHaveTextContent('Advance goal: 验证 Growing 可以根据目标自动拆分任务')
    expect(missionTab).not.toHaveTextContent('GoalB candidate generated from the Operating Manifest.')
    expect(missionTab).toHaveTextContent('gateway_reliability_repair')

    fireEvent.click(screen.getByText('Dry Run Planner'))
    await waitFor(() => expect(mockApi.runPlannerSweep).toHaveBeenCalledWith({ dry_run: true, triggered_by: 'operator' }))

    fireEvent.click(within(missionTab).getByText('Approve & Run'))
    await waitFor(() => expect(mockApi.approveAndRunRequirementCandidate).toHaveBeenCalledWith(42, { operator: 'operator' }))

    fireEvent.click(screen.getByText('Debug'))
    expect(screen.getByTestId('planning-debug-tab')).toHaveTextContent('Raw Manifest')
  })
})
