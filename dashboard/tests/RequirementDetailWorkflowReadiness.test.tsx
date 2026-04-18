import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RequirementDetail from '../src/pages/RequirementDetail'
import { ToastProvider } from '../src/components/workbench'

const baseRequirementDetail = {
  requirement: {
    id: 5,
    title: 'Gateway runtime issue',
    description_markdown: 'Bug intake created this requirement.',
    acceptance_criteria_markdown: 'Restore healthy workflow.',
    state: 'planning',
    attention_reason: null,
    failure_reason: null,
    requirement_plan_summary: null,
    project: null,
    approval: null,
    current_attempt_id: null,
    current_delivery_id: null,
    status: 'planning',
    priority: 'normal',
    source: 'bug_intake',
    source_ref: 'error-fingerprint:abc',
    linked_requirement_id: null,
    followup_requirement_id: null,
    resolution_path: null,
    project_id: 1,
    project_key: 'synapse-network-growing',
    project_display_name: 'Synapse-Network-Growing',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    target_project_path_override: null,
    target_projects: ['Synapse-Network-Growing'],
    approval_required: false,
    approval_status: 'waived',
    phase: 'planning',
    allowed_actions: ['delete', 'edit', 'view'],
    pending_operations: [],
    recovery_status: null,
    recovery_scope: null,
    recovery_deadline_at: null,
    recovery_timeout_status: null,
    time_remaining_seconds: null,
    assets_status: 'pending',
    assets_error_message: null,
    created_at: '2026-04-18T10:00:00Z',
    updated_at: '2026-04-18T10:00:00Z',
    active_workflow_run_id: null,
    active_workflow_run_summary: null,
    latest_release_status: null,
  },
  state: 'planning',
  attention_reason: null,
  failure_reason: null,
  policy_summary_markdown: '',
  project: {
    id: 1,
    project_key: 'synapse-network-growing',
    display_name: 'Synapse-Network-Growing',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    status: 'active',
    repo_full_name: null,
    default_branch: 'main',
    deploy_repo_full_name: null,
    deploy_strategy: 'disabled',
    deploy_trigger_enabled: false,
    staging_host_label: null,
    production_host_label: null,
    staging_workflow_file: 'deploy-staging.yml',
    production_workflow_file: 'deploy-production.yml',
    notes: null,
    policy_id: null,
    created_at: '2026-04-18T10:00:00Z',
    updated_at: '2026-04-18T10:00:00Z',
  },
  active_workflow_run_id: null,
  active_workflow_run_summary: null,
  latest_release_id: null,
  latest_release: null,
  approval: {
    approval_decision: 'waived',
    approval_status: 'waived',
    approval_reason: null,
    approval_source: 'policy_waived',
    final_decision_source: 'waived',
    required_approver_roles: [],
    risk_flags: [],
    pending_execution_start: false,
    auto_started: false,
    workflow_run_id: null,
  },
  approval_decision: null,
  phase: 'planning',
  allowed_actions: ['delete', 'edit', 'view'],
  pending_operations: [],
  recovery_status: null,
  recovery_scope: null,
  recovery_deadline_at: null,
  recovery_timeout_status: null,
  time_remaining_seconds: null,
  assets_status: 'pending',
  assets_error_message: null,
  acceptance_contract: {
    done_criteria: ['Workflow is healthy'],
    verification_checks: [],
    scope_constraints: [],
    delivery_expectation: '',
    markdown: '## Done Criteria\n- Workflow is healthy',
  },
  execution_plan: {},
  workflow_readiness: {
    requirement_id: 5,
    assets_status: 'pending',
    active_workflow_run_id: null,
    active_workflow_run_summary: null,
    blocking_reason: 'acceptance_or_plan_pending',
    next_action: 'generate_workflow_assets',
    can_start_workflow: true,
    recommended_workflow_key: 'gateway_reliability_repair',
  },
  attachments: [],
  followup_requirement_id: null,
  resolution_path: null,
}

const startedWorkflow = {
  id: 55,
  requirement_id: 5,
  requirement_title: 'Gateway runtime issue',
  workflow_key: 'gateway_reliability_repair',
  current_state: 'awaiting_operator',
  status: 'awaiting_operator',
  resolution: 'route_to_human',
  risk_level: 'normal',
  pending_human_gate_count: 1,
  updated_at: '2026-04-18T10:01:00Z',
  started_at: '2026-04-18T10:01:00Z',
  completed_at: null,
  retry_counters: {},
  blackboard: {},
  events: [],
  artifacts: [],
  atom_invocations: [],
  human_gates: [],
}

const mockApi = {
  getRequirement: vi.fn(),
  getProjects: vi.fn(),
  generateRequirementWorkflow: vi.fn(),
  startRequirementWorkflow: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    getProjects: (...args: unknown[]) => mockApi.getProjects(...args),
    generateRequirementWorkflow: (...args: unknown[]) => mockApi.generateRequirementWorkflow(...args),
    startRequirementWorkflow: (...args: unknown[]) => mockApi.startRequirementWorkflow(...args),
  },
}))

function renderPage() {
  render(
    <ToastProvider>
      <MemoryRouter initialEntries={['/requirements/5']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
          <Route path="/workflows/:id" element={<div>Workflow detail route</div>} />
        </Routes>
      </MemoryRouter>
    </ToastProvider>,
  )
}

describe('RequirementDetail workflow readiness', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getRequirement.mockResolvedValue(baseRequirementDetail)
    mockApi.getProjects.mockResolvedValue([])
    mockApi.generateRequirementWorkflow.mockResolvedValue({
      ...baseRequirementDetail,
      assets_status: 'ready',
      workflow_readiness: {
        ...baseRequirementDetail.workflow_readiness,
        assets_status: 'ready',
        blocking_reason: null,
        next_action: 'start_workflow',
      },
    })
    mockApi.startRequirementWorkflow.mockResolvedValue(startedWorkflow)
  })

  it('shows pending workflow readiness and can start a declarative workflow run', async () => {
    renderPage()

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(5))
    expect(screen.getByTestId('workflow-readiness-panel')).toHaveTextContent('Workflow 未生成')
    expect(screen.getByTestId('workflow-readiness-panel')).toHaveTextContent('assets: pending')
    expect(screen.getByTestId('workflow-readiness-panel')).toHaveTextContent('recommended: gateway_reliability_repair')

    fireEvent.click(screen.getByTestId('generate-workflow-assets-btn'))
    await waitFor(() => expect(mockApi.generateRequirementWorkflow).toHaveBeenCalledWith(5))

    fireEvent.click(screen.getByTestId('start-workflow-btn'))
    await waitFor(() =>
      expect(mockApi.startRequirementWorkflow).toHaveBeenCalledWith(5, {
        workflow_key: 'gateway_reliability_repair',
        run_immediately: true,
        triggered_by: 'operator',
      }),
    )
    expect(await screen.findByText('Workflow detail route')).toBeInTheDocument()
  })
})
