import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirementPool from '../src/pages/RequirementPool'
import ExecutionsPage from '../src/pages/ExecutionsPage'
import ReleasesPage from '../src/pages/ReleasesPage'
import ProjectsPage from '../src/pages/ProjectsPage'
import ErrorsPage from '../src/pages/ErrorsPage'
import { ToastProvider } from '../src/components/workbench'

const mockApi = {
  getRequirements: vi.fn(),
  getProjects: vi.fn(),
  createRequirement: vi.fn(),
  deleteRequirement: vi.fn(),
  updateRequirement: vi.fn(),
  submitRequirement: vi.fn(),
  regenerateRequirementAssets: vi.fn(),
  createExecution: vi.fn(),
  getExecutions: vi.fn(),
  startExecution: vi.fn(),
  getReleaseCandidates: vi.fn(),
  getErrors: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    getProjects: (...args: unknown[]) => mockApi.getProjects(...args),
    createRequirement: (...args: unknown[]) => mockApi.createRequirement(...args),
    deleteRequirement: (...args: unknown[]) => mockApi.deleteRequirement(...args),
    updateRequirement: (...args: unknown[]) => mockApi.updateRequirement(...args),
    submitRequirement: (...args: unknown[]) => mockApi.submitRequirement(...args),
    regenerateRequirementAssets: (...args: unknown[]) => mockApi.regenerateRequirementAssets(...args),
    createExecution: (...args: unknown[]) => mockApi.createExecution(...args),
    getExecutions: (...args: unknown[]) => mockApi.getExecutions(...args),
    startExecution: (...args: unknown[]) => mockApi.startExecution(...args),
    getReleaseCandidates: (...args: unknown[]) => mockApi.getReleaseCandidates(...args),
    getErrors: (...args: unknown[]) => mockApi.getErrors(...args),
  },
}))

describe('agent-first pages smoke', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi.deleteRequirement.mockResolvedValue(undefined)
    mockApi.getProjects.mockResolvedValue([
      {
        id: 7,
        project_key: 'synapse-network',
        display_name: 'Synapse-Network',
        root_path: '/Users/cliff/workspace/agent/Synapse-Network',
        status: 'active',
        repo_full_name: 'cliff-personal/Synapse-Network',
        default_branch: 'main',
        deploy_repo_full_name: 'cliff-personal/Synapse-Network',
        deploy_strategy: 'github_actions',
        deploy_trigger_enabled: true,
        staging_host_label: 'staging',
        production_host_label: 'production',
        staging_workflow_file: 'deploy-staging.yml',
        production_workflow_file: 'deploy-production.yml',
        notes: null,
        policy_id: 3,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    mockApi.getRequirements.mockResolvedValue([
      {
        id: 1,
        title: 'Launch FAQ',
        description_markdown: 'Validate FAQ launch path.',
        status: 'ready',
        priority: 'high',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_project_path_override: null,
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: 'Checks pass.',
        approval_required: false,
        approval_status: 'waived',
        assets_status: 'ready',
        assets_error_message: null,
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    mockApi.getExecutions.mockResolvedValue([
      {
        id: 11,
        requirement_id: 1,
        requirement_title: 'Launch FAQ',
        status: 'queued',
        phase: 'queued',
        is_current_execution: true,
        allowed_actions: ['start'],
        pending_operations: [],
        recovery_status: null,
        recovery_scope: null,
        recovery_deadline_at: null,
        recovery_timeout_status: null,
        time_remaining_seconds: null,
        recovery_mode: null,
        queue_reason: '等待启动',
        blocking_reason_code: null,
        blocking_reason_message: null,
        workspace_blocker: null,
        recovery_hint: null,
        execution_mode: 'direct',
        complexity: 'simple',
        planner_summary: 'Direct execute.',
        validation_profile: 'minimal',
        delivery_intent: 'pr_required',
        approval_required: false,
        target_projects: ['Synapse-Network'],
        latest_task_id: null,
        started_at: null,
        completed_at: null,
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    mockApi.getReleaseCandidates.mockResolvedValue([
      {
        requirement: {
          id: 1,
          title: 'Launch FAQ',
        status: 'done',
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_projects: ['Synapse-Network'],
        target_project_path_override: null,
        latest_execution_run_id: 11,
      },
      validation: {
          status: 'passed',
          summary_markdown: 'All checks green.',
          updated_at: '2026-04-14T00:00:00Z',
        },
        release: {
          project_id: 7,
          project_key: 'synapse-network',
          project_display_name: 'Synapse-Network',
          status: 'ready',
          branch_name: 'ops/req-1-launch-faq',
          commit_sha: 'abc1234',
          pr_number: 17,
          updated_at: '2026-04-14T00:00:00Z',
        },
      },
    ])
    mockApi.getErrors.mockResolvedValue([
      {
        fingerprint_key: 'runtime_log_error:abc123',
        source_kind: 'runtime_log_error',
        service_name: 'Synapse Gateway',
        project_key: 'synapse-network',
        project_root_path: '/Users/cliff/workspace/agent/Synapse-Network',
        incident_code: 'gateway_timeout',
        severity: 'high',
        summary: 'Gateway timeout while opening FAQ route',
        evidence_excerpt: 'TimeoutError: gateway request exceeded budget',
        status: 'open',
        occurrence_count: 3,
        first_seen_at: '2026-04-14T00:00:00Z',
        latest_seen_at: '2026-04-14T01:00:00Z',
        latest_error_event_id: 9,
        linked_requirement_id: 1,
        latest_execution_run_id: 11,
      },
    ])
  })

  it('renders requirement surface', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )
    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.getByText('需求列表')).toBeInTheDocument()
    expect(screen.getByText('Launch FAQ')).toBeInTheDocument()
  })

  it('does not show delete for requirement rows without delete action', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: '删除' })).not.toBeInTheDocument()
  })

  it('opens create and edit requirement drawers from the toolbar', async () => {
    mockApi.getRequirements.mockResolvedValueOnce([
      {
        id: 1,
        title: 'Launch FAQ',
        description_markdown: 'Validate FAQ launch path.',
        status: 'draft',
        priority: 'high',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_project_path_override: null,
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: 'Checks pass.',
        approval_required: false,
        approval_status: 'waived',
        assets_status: 'ready',
        assets_error_message: null,
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    mockApi.createRequirement.mockResolvedValue({
      requirement: {
        id: 2,
        title: 'Improve Queue Copy',
        description_markdown: 'Tighten the requirement queue copy.',
        status: 'draft',
        priority: 'normal',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        target_project_path_override: null,
        target_projects: ['Synapse-Network-Growing'],
        acceptance_criteria_markdown: 'Copy updated.',
        approval_required: false,
        approval_status: 'waived',
        assets_status: 'ready',
        assets_error_message: null,
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
      attachments: [],
      approval: {
        approval_decision: 'waived',
        approval_status: 'waived',
        approval_reason: null,
        approval_source: 'policy_waived',
        required_approver_roles: [],
        risk_flags: [],
        pending_execution_start: false,
        auto_started: false,
        execution_run_id: null,
      },
      assets_status: 'ready',
      assets_error_message: null,
      policy_summary_markdown: '',
      acceptance_contract: {
        done_criteria: [],
        verification_checks: [],
        scope_constraints: [],
        delivery_expectation: '',
        markdown: '',
      },
      execution_plan: {
        planning_mode: 'agent_plan_brief',
        goal_summary: 'Improve Queue Copy',
        summary_markdown: '',
        steps: [],
        planned_checks: [],
        risks: [],
      },
      latest_execution_id: null,
      latest_release_id: null,
      latest_release: null,
      project: null,
    })
    mockApi.updateRequirement.mockResolvedValue({
      requirement: {
        id: 1,
        title: 'Launch FAQ Updated',
        description_markdown: 'Validate FAQ launch path.',
        status: 'draft',
        priority: 'high',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_project_path_override: null,
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: 'Checks pass.',
        approval_required: false,
        approval_status: 'waived',
        assets_status: 'ready',
        assets_error_message: null,
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    })

    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.queryByRole('heading', { name: '新建需求' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '新建需求' }))
    expect(screen.getByRole('heading', { name: '新建需求' })).toBeInTheDocument()
    expect(screen.queryByText('验收标准')).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('输入需求标题'), {
      target: { value: 'Improve Queue Copy' },
    })
    fireEvent.change(screen.getByPlaceholderText('输入需求描述'), {
      target: { value: 'Tighten the requirement queue copy.' },
    })
    fireEvent.change(screen.getByDisplayValue('选择项目'), {
      target: { value: '7' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(mockApi.createRequirement).toHaveBeenCalledWith(expect.objectContaining({ project_id: 7 })))
    await waitFor(() => expect(screen.queryByRole('heading', { name: '新建需求' })).not.toBeInTheDocument())
    expect(await screen.findByText('需求已创建')).toBeInTheDocument()

    const editButton = screen.getAllByRole('button', { name: '编辑' })[0]
    expect(editButton).toBeEnabled()
    fireEvent.click(editButton)
    expect(screen.getByRole('heading', { name: '编辑需求' })).toBeInTheDocument()
    fireEvent.change(screen.getByDisplayValue('Launch FAQ'), {
      target: { value: 'Launch FAQ Updated' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => expect(mockApi.updateRequirement).toHaveBeenCalledWith(1, expect.objectContaining({ title: 'Launch FAQ Updated' })))
    expect(await screen.findByText('需求已更新')).toBeInTheDocument()
  })

  it('cancels deletion without calling the delete api', async () => {
    mockApi.getRequirements.mockResolvedValueOnce([
      {
        id: 1,
        title: 'Launch FAQ',
        description_markdown: 'Validate FAQ launch path.',
        status: 'draft',
        priority: 'high',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_project_path_override: null,
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: 'Checks pass.',
        approval_required: false,
        approval_status: 'waived',
        assets_status: 'ready',
        assets_error_message: null,
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])
    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(screen.getByRole('heading', { name: '删除需求' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: '删除需求' })).not.toBeInTheDocument())
    expect(mockApi.deleteRequirement).not.toHaveBeenCalled()
  })

  it('uploads attachment payloads during requirement creation', async () => {
    mockApi.createRequirement.mockResolvedValue({
      requirement: {
        id: 2,
        title: 'Requirement with screenshot',
        description_markdown: 'Use screenshot context.',
        status: 'draft',
        priority: 'normal',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_project_path_override: null,
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: '',
        approval_required: false,
        approval_status: 'waived',
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
      attachments: [],
      approval: {
        approval_decision: 'waived',
        approval_status: 'waived',
        approval_reason: null,
        approval_source: 'policy_waived',
        required_approver_roles: [],
        risk_flags: [],
        pending_execution_start: false,
        auto_started: false,
        execution_run_id: null,
      },
      policy_summary_markdown: '',
      acceptance_contract: { done_criteria: [], verification_checks: [], scope_constraints: [], delivery_expectation: '', markdown: '' },
      execution_plan: { planning_mode: 'agent_plan_brief', goal_summary: '', summary_markdown: '', steps: [], planned_checks: [], risks: [] },
      latest_execution_id: null,
      latest_release_id: null,
      latest_release: null,
      project: null,
    })

    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: '新建需求' }))
    fireEvent.change(screen.getByTestId('requirement-title'), { target: { value: 'Requirement with screenshot' } })
    fireEvent.change(screen.getByTestId('requirement-description'), { target: { value: 'Use screenshot context.' } })
    fireEvent.change(screen.getByTestId('requirement-project'), { target: { value: '7' } })

    const file = new File(['hello-image'], 'staging.png', { type: 'image/png' })
    Object.defineProperty(file, 'arrayBuffer', {
      value: vi.fn().mockResolvedValue(new TextEncoder().encode('hello-image').buffer),
    })
    fireEvent.change(screen.getByTestId('requirement-attachment-input'), {
      target: { files: [file] },
    })

    await waitFor(() => expect(screen.getByText('staging.png')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(mockApi.createRequirement).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Requirement with screenshot',
          attachments: [
            expect.objectContaining({
              file_name: 'staging.png',
              content_type: 'image/png',
              source: 'upload',
            }),
          ],
        }),
      ),
    )
  })

  it('disables submit while assets are still generating', async () => {
    mockApi.getRequirements.mockResolvedValueOnce([
      {
        id: 4,
        title: 'Pending assets requirement',
        description_markdown: 'Wait for generated assets.',
        status: 'draft',
        priority: 'normal',
        source: 'manual',
        source_ref: null,
        project_id: 7,
        project_key: 'synapse-network',
        project_display_name: 'Synapse-Network',
        target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
        target_project_path_override: null,
        target_projects: ['Synapse-Network'],
        acceptance_criteria_markdown: '',
        approval_required: false,
        approval_status: 'waived',
        assets_status: 'pending',
        assets_error_message: null,
        active_execution_run_id: null,
        latest_execution_run_id: null,
        latest_release_status: null,
        created_at: '2026-04-14T00:00:00Z',
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])

    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: '生成计划中…' })).toBeDisabled()
  })

  it('accepts pasted image attachments in the composer', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <RequirementPool />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: '新建需求' }))

    const file = new File(['clip-image'], 'clipboard.png', { type: 'image/png' })
    Object.defineProperty(file, 'arrayBuffer', {
      value: vi.fn().mockResolvedValue(new TextEncoder().encode('clip-image').buffer),
    })
    fireEvent.paste(screen.getByTestId('requirement-description'), {
      clipboardData: {
        files: [file],
      },
    })

    await waitFor(() => expect(screen.getByText('clipboard.png')).toBeInTheDocument())
  })

  it('renders execution surface', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <ExecutionsPage />
        </MemoryRouter>
      </ToastProvider>,
    )
    await waitFor(() => expect(mockApi.getExecutions).toHaveBeenCalled())
    expect(screen.getByText('执行列表')).toBeInTheDocument()
    expect(screen.getByText('Execution #11')).toBeInTheDocument()
    expect(screen.getByText('需求：Launch FAQ')).toBeInTheDocument()
    expect(screen.getByText(/恢复中的 execution 只影响当前需求/)).toBeInTheDocument()
  })

  it('filters execution rows by requirement title', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <ExecutionsPage />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getExecutions).toHaveBeenCalled())
    fireEvent.change(screen.getByPlaceholderText('搜索 execution / requirement'), { target: { value: 'launch faq' } })
    expect(screen.getByText('Execution #11')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('搜索 execution / requirement'), { target: { value: 'different requirement' } })
    expect(screen.queryByText('Execution #11')).not.toBeInTheDocument()
  })

  it('shows restart-current action for restartable blockers', async () => {
    mockApi.getExecutions.mockResolvedValueOnce([
      {
        id: 12,
        requirement_id: 1,
        requirement_title: 'Launch FAQ',
        status: 'blocked',
        phase: 'blocked',
        is_current_execution: true,
        allowed_actions: ['start', 'view', 'view_requirement'],
        pending_operations: [],
        recovery_status: null,
        recovery_scope: 'current_requirement',
        recovery_deadline_at: '2026-04-14T07:10:00Z',
        recovery_timeout_status: 'active',
        time_remaining_seconds: 180,
        recovery_mode: 'restart_current',
        queue_reason: null,
        blocking_reason_code: 'branch_preparation_blocked',
        blocking_reason_message: 'dirty worktree on `main` blocks automatic execution branch preparation',
        workspace_blocker: null,
        recovery_hint: '清理目标仓库工作树后可直接再次启动当前 execution。',
        execution_mode: 'direct',
        complexity: 'simple',
        planner_summary: 'Direct execute.',
        validation_profile: 'minimal',
        delivery_intent: 'pr_required',
        approval_required: false,
        target_projects: ['Synapse-Network'],
        latest_task_id: null,
        started_at: null,
        completed_at: null,
        updated_at: '2026-04-14T00:00:00Z',
      },
    ])

    render(
      <ToastProvider>
        <MemoryRouter>
          <ExecutionsPage />
        </MemoryRouter>
      </ToastProvider>,
    )

    await waitFor(() => expect(mockApi.getExecutions).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: '再次启动' })).toBeInTheDocument()
    expect(screen.getByText(/仅影响当前需求/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '创建新 run 重试' })).not.toBeInTheDocument()
  })

  it('renders release surface', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <ReleasesPage />
        </MemoryRouter>
      </ToastProvider>,
    )
    await waitFor(() => expect(mockApi.getReleaseCandidates).toHaveBeenCalled())
    expect(screen.getByText('发布列表')).toBeInTheDocument()
    expect(screen.getByText(/Launch FAQ/)).toBeInTheDocument()
  })

  it('renders project surface', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <ProjectsPage />
        </MemoryRouter>
      </ToastProvider>,
    )
    await waitFor(() => expect(mockApi.getProjects).toHaveBeenCalled())
    expect(screen.getByText('项目列表')).toBeInTheDocument()
    expect(screen.getByText('Synapse-Network')).toBeInTheDocument()
  })

  it('renders error surface', async () => {
    render(
      <ToastProvider>
        <MemoryRouter>
          <ErrorsPage />
        </MemoryRouter>
      </ToastProvider>,
    )
    await waitFor(() => expect(mockApi.getErrors).toHaveBeenCalled())
    expect(screen.getByText('错误列表')).toBeInTheDocument()
    expect(screen.getByText('Synapse Gateway')).toBeInTheDocument()
  })
})
