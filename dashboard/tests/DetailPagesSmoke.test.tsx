import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ErrorDetailPage from '../src/pages/ErrorDetailPage'
import ProjectDetailPage from '../src/pages/ProjectDetailPage'
import ReleaseDetailPage from '../src/pages/ReleaseDetailPage'
import { ToastProvider } from '../src/components/workbench'

const mockApi = {
  getReleaseDetail: vi.fn(),
  prepareRelease: vi.fn(),
  openReleasePr: vi.fn(),
  deployReleaseToStaging: vi.fn(),
  deployReleaseToProduction: vi.fn(),
  rollbackRelease: vi.fn(),
  getProject: vi.fn(),
  updateProject: vi.fn(),
  updateProjectPolicyForProject: vi.fn(),
  getErrorDetail: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getReleaseDetail: (...args: unknown[]) => mockApi.getReleaseDetail(...args),
    prepareRelease: (...args: unknown[]) => mockApi.prepareRelease(...args),
    openReleasePr: (...args: unknown[]) => mockApi.openReleasePr(...args),
    deployReleaseToStaging: (...args: unknown[]) => mockApi.deployReleaseToStaging(...args),
    deployReleaseToProduction: (...args: unknown[]) => mockApi.deployReleaseToProduction(...args),
    rollbackRelease: (...args: unknown[]) => mockApi.rollbackRelease(...args),
    getProject: (...args: unknown[]) => mockApi.getProject(...args),
    updateProject: (...args: unknown[]) => mockApi.updateProject(...args),
    updateProjectPolicyForProject: (...args: unknown[]) => mockApi.updateProjectPolicyForProject(...args),
    getErrorDetail: (...args: unknown[]) => mockApi.getErrorDetail(...args),
  },
}))

const requirement = {
  id: 5,
  title: 'GoalB requirement',
  status: 'completed',
  project_key: 'synapse-network-growing',
  project_display_name: 'Synapse-Network-Growing',
  active_workflow_run_id: 9,
  active_workflow_run_summary: null,
}

const project = {
  id: 7,
  project_key: 'synapse-network-growing',
  display_name: 'Synapse-Network-Growing',
  root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
  status: 'active',
  repo_full_name: 'SynapseNetworkAI/Synapse-Network-Growing',
  default_branch: 'main',
  deploy_repo_full_name: 'SynapseNetworkAI/Synapse-Network-Growing',
  deploy_strategy: 'github_actions',
  deploy_trigger_enabled: false,
  staging_host_label: 'staging',
  production_host_label: 'production',
  staging_workflow_file: 'deploy-staging.yml',
  production_workflow_file: 'deploy-production.yml',
  notes: 'Control plane',
  policy_id: 3,
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
  policy: {
    id: 3,
    project_id: 7,
    project_key: 'synapse-network-growing',
    display_name: 'Synapse-Network-Growing',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    status: 'active',
    allowed_write_globs: ['**'],
    forbidden_globs: ['.git/**'],
    required_checks: ['npm test'],
    release_mode: 'manual',
    requires_manual_approval: true,
    autonomy_mode: 'execute_autonomously',
    allow_rebalance: true,
    allow_preemption: true,
    capability_matrix: { shell_access: true, git_read: true, git_write: true, git_push: false, network_access: false, publish: false },
    interrupt_policy: { operator_confirmation_actions: ['git_push'], auto_pause_on_events: [], auto_abort_on_events: [] },
    scheduler_weight: 1,
    max_parallel_requirements: 1,
    portfolio_budget_points: 100,
    deploy_repo_full_name: 'SynapseNetworkAI/Synapse-Network-Growing',
    deploy_strategy: 'github_actions',
    deploy_trigger_enabled: false,
    staging_host_label: 'staging',
    production_host_label: 'production',
    staging_workflow_file: 'deploy-staging.yml',
    production_workflow_file: 'deploy-production.yml',
    notes: 'Manual release',
    created_at: '2026-04-19T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
  },
}

describe('detail pages smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getReleaseDetail.mockResolvedValue({
      requirement,
      validation: { status: 'passed', summary_markdown: 'All checks passed.', updated_at: '2026-04-19T00:00:00Z' },
      release: {
        id: 2,
        requirement_id: 5,
        status: 'branch_prepared',
        state: 'branch_prepared',
        project_key: 'synapse-network-growing',
        project_display_name: 'Synapse-Network-Growing',
        branch_name: 'ops/req-5-goalb',
        commit_sha: 'abc123',
        pr_url: null,
        compare_url: 'https://github.com/example/repo/compare/main...ops/req-5-goalb',
        prepared_at: '2026-04-19T00:00:00Z',
        delivered_at: null,
        updated_at: '2026-04-19T00:00:00Z',
        repairable: true,
        repair_attempt_count: 0,
        next_action: 'open_pr',
      },
      deployments: [],
      events: [],
    })
    mockApi.prepareRelease.mockResolvedValue({})
    mockApi.openReleasePr.mockResolvedValue({})
    mockApi.getProject.mockResolvedValue(project)
    mockApi.updateProject.mockResolvedValue(project)
    mockApi.updateProjectPolicyForProject.mockResolvedValue(project.policy)
    mockApi.getErrorDetail.mockResolvedValue({
      fingerprint: {
        fingerprint_key: 'runtime_log_error:goalb',
        source_kind: 'runtime_log_error',
        service_name: 'Synapse Ops',
        project_key: 'synapse-network-growing',
        project_root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        incident_code: 'goalb_demo',
        severity: 'high',
        summary: 'GoalB demo error fingerprint',
        evidence_excerpt: 'Traceback: goalb',
        status: 'open',
        occurrence_count: 2,
        first_seen_at: '2026-04-19T00:00:00Z',
        latest_seen_at: '2026-04-19T00:01:00Z',
        latest_error_event_id: 1,
        linked_requirement_id: 5,
        active_workflow_run_id: 9,
        active_workflow_run_summary: null,
        discovery_status: 'linked_requirement',
        discovery_recommendation: { discovery_action: 'reuse_requirement', reason: 'Active workflow exists.' },
      },
      events: [
        {
          id: 1,
          severity: 'high',
          source_kind: 'runtime_log_error',
          occurred_at: '2026-04-19T00:01:00Z',
          summary: 'GoalB traceback',
          message: 'Traceback: goalb',
          stack_trace: null,
        },
      ],
      requirement,
      release: null,
      notifications: [
        {
          id: 1,
          channel: 'alert',
          event_type: 'error_logged',
          status: 'skipped',
          payload: { summary: 'Dry-run notification.' },
          delivered_at: null,
          created_at: '2026-04-19T00:01:00Z',
        },
      ],
    })
  })

  it('renders release detail and exposes workflow/release actions', async () => {
    render(
      <MemoryRouter initialEntries={['/releases/5']}>
        <Routes><Route path="/releases/:requirementId" element={<ReleaseDetailPage />} /></Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getReleaseDetail).toHaveBeenCalledWith(5))
    expect(screen.getByTestId('release-detail-page')).toHaveTextContent('Requirement #5 发布详情')
    expect(screen.getByText('查看工作流')).toBeInTheDocument()
    fireEvent.click(screen.getByText('打开 PR'))
    await waitFor(() => expect(mockApi.openReleasePr).toHaveBeenCalled())
  })

  it('renders project detail and saves project metadata', async () => {
    render(
      <ToastProvider>
        <MemoryRouter initialEntries={['/projects/7']}>
          <Routes><Route path="/projects/:id" element={<ProjectDetailPage />} /></Routes>
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getProject).toHaveBeenCalledWith(7))
    expect(screen.getByTestId('project-detail-page')).toHaveTextContent('Synapse-Network-Growing')
    fireEvent.click(screen.getByText('保存项目'))
    await waitFor(() => expect(mockApi.updateProject).toHaveBeenCalled())
  })

  it('renders error detail with linked requirement and workflow actions', async () => {
    render(
      <MemoryRouter initialEntries={['/errors/runtime_log_error%3Agoalb']}>
        <Routes><Route path="/errors/:fingerprintKey" element={<ErrorDetailPage />} /></Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getErrorDetail).toHaveBeenCalledWith('runtime_log_error:goalb'))
    expect(screen.getByTestId('error-detail-page')).toHaveTextContent('GoalB demo error fingerprint')
    expect(screen.getByText('查看需求')).toBeInTheDocument()
    expect(screen.getByText('查看工作流')).toBeInTheDocument()
    expect(screen.getByTestId('error-detail-page')).toHaveTextContent('error_logged')
  })
})
