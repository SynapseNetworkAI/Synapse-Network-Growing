import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ExecutionDetailPage from '../src/pages/ExecutionDetailPage'

const mockApi = {
  getExecution: vi.fn(),
  getExecutionFilePreview: vi.fn(),
  startExecution: vi.fn(),
  pauseExecution: vi.fn(),
  retryExecution: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getExecution: (...args: unknown[]) => mockApi.getExecution(...args),
    getExecutionFilePreview: (...args: unknown[]) => mockApi.getExecutionFilePreview(...args),
    startExecution: (...args: unknown[]) => mockApi.startExecution(...args),
    pauseExecution: (...args: unknown[]) => mockApi.pauseExecution(...args),
    retryExecution: (...args: unknown[]) => mockApi.retryExecution(...args),
  },
}))

const detail = {
  execution: {
    id: 1,
    requirement_id: 6,
    execution_mode: 'direct',
    execution_kind: 'implementation',
    complexity: 'simple',
    status: 'running',
    phase: 'executing',
    is_current_execution: true,
    allowed_actions: ['pause'],
    pending_operations: [],
    recovery_status: null,
    recovery_scope: null,
    recovery_deadline_at: null,
    recovery_timeout_status: null,
    time_remaining_seconds: null,
    recovery_mode: null,
    queue_reason: null,
    blocking_reason_code: null,
    blocking_reason_message: null,
    workspace_blocker: null,
    recovery_hint: null,
    validation_profile: 'minimal',
    delivery_intent: 'pr_required',
    approval_required: false,
    source_release_id: null,
    source_delivery_blocker_type: null,
    planner_summary: 'Direct execution.',
    target_projects: ['/Users/cliff/workspace/agent/Synapse-Network'],
    latest_task_id: 7,
    agent_id: 'execution_observability_agent',
    agent_label: 'Software Engineer',
    runtime_backend: 'codex_cli',
    runtime_provider: 'openai',
    runtime_model: 'gpt-5.4',
    tokens_used_total: 321,
    elapsed_ms: 42000,
    current_branch: 'feature/execution-observability',
    started_at: '2026-04-14T06:53:19Z',
    completed_at: null,
    created_at: '2026-04-14T06:53:10Z',
    updated_at: '2026-04-14T06:53:32Z',
  },
  requirement: {
    id: 6,
    title: 'Improve execution observability',
    description_markdown: 'Track execution runtime evidence.',
    acceptance_criteria_markdown: '- execution detail shows tokens and changed files',
    status: 'running',
    priority: 'normal',
    source: 'manual',
    source_ref: null,
    project_id: 1,
    project_key: 'synapse-network',
    project_display_name: 'Synapse-Network',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
    target_project_path_override: null,
    target_projects: ['/Users/cliff/workspace/agent/Synapse-Network'],
    approval_required: false,
    approval_status: 'approved',
    active_execution_run_id: 1,
    latest_execution_run_id: 1,
    latest_release_status: 'ready',
    created_at: '2026-04-14T06:53:00Z',
    updated_at: '2026-04-14T06:53:32Z',
  },
  phase: 'executing',
  is_current_execution: true,
  allowed_actions: ['pause'],
  pending_operations: [],
  recovery_status: null,
  recovery_scope: null,
  recovery_deadline_at: null,
  recovery_timeout_status: null,
  time_remaining_seconds: null,
  recovery_mode: null,
  queue_reason: null,
  blocking_reason_code: null,
  blocking_reason_message: null,
  workspace_blocker: null,
  recovery_hint: null,
  nodes: [
    {
      id: 1,
      execution_run_id: 1,
      requirement_id: 6,
      node_key: 'execute',
      node_type: 'execute',
      title: 'Execute requirement',
      status: 'completed',
      sequence_no: 1,
      task_id: 7,
      task_status: 'completed',
      agent_id: 'execution_observability_agent',
      agent_label: 'Software Engineer',
      runtime_backend: 'codex_cli',
      runtime_provider: 'openai',
      runtime_model: 'gpt-5.4',
      tokens_used: 321,
      elapsed_ms: 42000,
      summary_markdown: 'Applied the requested change.',
      started_at: '2026-04-14T06:53:19Z',
      completed_at: '2026-04-14T06:54:01Z',
    },
  ],
  validation: {
    id: 1,
    requirement_id: 6,
    execution_run_id: 1,
    profile: 'minimal',
    status: 'passed',
    summary_markdown: 'Validation passed.',
    checks: [],
    verification_plan: {
      mode: 'command_checks',
      summary: 'Replay the targeted pytest command from execution evidence and review the changed file.',
      checks: ['PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/pytest tests/test_agent_first_api.py -q'],
      evidence_expectations: ['Changed files should match the requested observability scope.'],
      why_no_verification: null,
    },
    verification_agent_id: 'verification_agent',
    verification_agent_label: 'Verification Agent',
    evidence_used: ['raw_output:92 chars', 'changed_files:1'],
    reasoning_markdown: 'The execution evidence satisfies the acceptance contract.',
    suggested_next_action: 'release_ready',
    resolution_recommendation: null,
    resolution_confidence: null,
    resolution_reason: null,
    resolution_path: 'release_ready',
    followup_requirement_id: null,
    followup_requirement_payload: {},
    created_at: '2026-04-14T06:54:10Z',
    updated_at: '2026-04-14T06:54:30Z',
  },
  verification_result: {
    id: 1,
    requirement_id: 6,
    execution_run_id: 1,
    profile: 'minimal',
    status: 'passed',
    summary_markdown: 'Validation passed.',
    checks: [],
    verification_plan: {
      mode: 'command_checks',
      summary: 'Replay the targeted pytest command from execution evidence and review the changed file.',
      checks: ['PYTHONPATH=. /Users/cliff/workspace/agent/.venv/bin/pytest tests/test_agent_first_api.py -q'],
      evidence_expectations: ['Changed files should match the requested observability scope.'],
      why_no_verification: null,
    },
    verification_agent_id: 'verification_agent',
    verification_agent_label: 'Verification Agent',
    evidence_used: ['raw_output:92 chars', 'changed_files:1'],
    reasoning_markdown: 'The execution evidence satisfies the acceptance contract.',
    suggested_next_action: 'release_ready',
    resolution_recommendation: null,
    resolution_confidence: null,
    resolution_reason: null,
    resolution_path: 'release_ready',
    followup_requirement_id: null,
    followup_requirement_payload: {},
    created_at: '2026-04-14T06:54:10Z',
    updated_at: '2026-04-14T06:54:30Z',
  },
  changed_files: [
    {
      path: 'src/feature.py',
      change_type: 'modified',
      additions: 3,
      deletions: 1,
      preview_available: true,
    },
  ],
  runtime_summary: {
    tokens_used_total: 321,
    elapsed_ms: 42000,
    agent_id: 'execution_observability_agent',
    agent_label: 'Software Engineer',
    runtime_backend: 'codex_cli',
    runtime_provider: 'openai',
    runtime_model: 'gpt-5.4',
    current_branch: 'feature/execution-observability',
  },
  delivery_summary: {
    id: 3,
    requirement_id: 6,
    execution_run_id: 1,
    project_id: 1,
    project_key: 'synapse-network',
    project_display_name: 'Synapse-Network',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network',
    status: 'ready',
    branch_name: 'feature/execution-observability',
    base_branch: 'main',
    commit_sha: 'abc1234',
    compare_url: 'https://github.com/example/repo/compare/main...feature/execution-observability',
    pr_url: 'https://github.com/example/repo/pull/42',
    pr_number: 42,
    notes: null,
    delivery_blocker_type: null,
    delivery_failure_excerpt: null,
    delivery_failure_raw_output: null,
    repairable: false,
    repair_attempt_count: 0,
    next_action: null,
    prepared_at: '2026-04-14T06:54:35Z',
    delivered_at: null,
    created_at: '2026-04-14T06:54:35Z',
    updated_at: '2026-04-14T06:54:35Z',
  },
  activity_stream: [
    {
      ts: '2026-04-14T06:53:10Z',
      event: 'run_created',
      status: 'completed',
      message: 'Execution run created.',
    },
    {
      ts: '2026-04-14T06:54:30Z',
      event: 'validation_completed',
      status: 'passed',
      message: 'Validation passed.',
    },
  ],
  incidents: [],
  plan_summary: {
    planning_mode: 'agent_plan_brief',
    goal_summary: 'Improve execution observability',
    summary_markdown: '## Summary\n\nImprove execution observability.\n\n## Planned Changes\n\n- Add execution detail metrics and observability fields.\n- Capture files, validation, and raw output in one view.\n\n## Verification Strategy\n\n- Run `pytest tests/test_agent_first_api.py`.\n- Confirm runtime metrics render in the execution detail page.',
    steps: [{ step_key: 'execute', title: 'Execute requirement' }],
    planned_checks: ['Run `pytest tests/test_agent_first_api.py`'],
    risks: ['Avoid regressing execution detail loading.'],
  },
  raw_task_output: '## Execute requirement\n\nApplied the requested change.\n- Commands run: `pytest tests/test_agent_first_api.py`\n',
  raw_task_output_truncated: false,
}

describe('Execution detail observability', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi.getExecution.mockResolvedValue(detail)
    mockApi.getExecutionFilePreview.mockResolvedValue({
      path: 'src/feature.py',
      diff_patch: "@@ -1 +1 @@\n-print('before')\n+print('after')\n",
      current_content: "print('after')\n",
      truncated: false,
    })
  })

  it('renders runtime metrics and changed files', async () => {
    render(
      <MemoryRouter initialEntries={['/executions/1']}>
        <Routes>
          <Route path="/executions/:id" element={<ExecutionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getExecution).toHaveBeenCalledWith(1))
    expect(screen.getAllByText('Software Engineer').length).toBeGreaterThan(0)
    expect(screen.getAllByText('gpt-5.4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('feature/execution-observability').length).toBeGreaterThan(0)
    expect(screen.getByText('src/feature.py')).toBeInTheDocument()
    expect(screen.getAllByText('321').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Validation passed.').length).toBeGreaterThan(0)
    expect(screen.getByText('Verification Agent')).toBeInTheDocument()
    expect(screen.getByText(/resolution: release_ready/)).toBeInTheDocument()
    expect(screen.getByText('执行计划')).toBeInTheDocument()
    expect(screen.getByText('验证方案')).toBeInTheDocument()
    expect(screen.getByText(/Replay the targeted pytest command/)).toBeInTheDocument()
    expect(screen.getByText('原始执行输出')).toBeInTheDocument()
    expect(screen.getByText(/Applied the requested change\./)).toBeInTheDocument()
  })

  it('renders blocking reason for historical blocked run', async () => {
    mockApi.getExecution.mockResolvedValue({
      ...detail,
      execution: {
        ...detail.execution,
        status: 'blocked',
        phase: 'blocked',
        is_current_execution: false,
        allowed_actions: ['view', 'view_requirement'],
        queue_reason: null,
        blocking_reason_code: 'verification_needs_revision',
        blocking_reason_message: 'Verification agent requested revisions before retrying.',
      },
      phase: 'blocked',
      is_current_execution: false,
      allowed_actions: ['view', 'view_requirement'],
      blocking_reason_code: 'verification_needs_revision',
      blocking_reason_message: 'Verification agent requested revisions before retrying.',
    })

    render(
      <MemoryRouter initialEntries={['/executions/1']}>
        <Routes>
          <Route path="/executions/:id" element={<ExecutionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getExecution).toHaveBeenCalledWith(1))
    expect(screen.getByText('历史 run')).toBeInTheDocument()
    expect(screen.getByText(/verification_needs_revision/)).toBeInTheDocument()
    expect(screen.getByText(/Verification agent requested revisions/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '创建新 run 重试' })).not.toBeInTheDocument()
  })

  it('shows restart-current guidance for dirty workspace blockers', async () => {
    mockApi.getExecution.mockResolvedValue({
      ...detail,
      execution: {
        ...detail.execution,
        status: 'blocked',
        phase: 'blocked',
        execution_kind: 'delivery_repair',
        allowed_actions: ['start', 'view', 'view_requirement'],
        recovery_scope: 'current_requirement',
        recovery_deadline_at: '2026-04-14T07:10:00Z',
        recovery_timeout_status: 'active',
        time_remaining_seconds: 180,
        recovery_mode: 'restart_current',
        blocking_reason_code: 'branch_preparation_blocked',
        blocking_reason_message: 'dirty worktree on `main` blocks automatic execution branch preparation',
        workspace_blocker: {
          repo_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
          base_branch: 'main',
          current_branch: 'main',
          dirty_file_count: 2,
          dirty_files_preview: ['server/services/workflows/agent_first.py', 'dashboard/src/pages/ExecutionsPage.tsx'],
          has_untracked: false,
        },
        recovery_hint: '清理目标仓库工作树后可直接再次启动当前 execution。',
      },
      phase: 'blocked',
      allowed_actions: ['start', 'view', 'view_requirement'],
      recovery_scope: 'current_requirement',
      recovery_deadline_at: '2026-04-14T07:10:00Z',
      recovery_timeout_status: 'active',
      time_remaining_seconds: 180,
      recovery_mode: 'restart_current',
      blocking_reason_code: 'branch_preparation_blocked',
      blocking_reason_message: 'dirty worktree on `main` blocks automatic execution branch preparation',
      workspace_blocker: {
        repo_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        base_branch: 'main',
        current_branch: 'main',
        dirty_file_count: 2,
        dirty_files_preview: ['server/services/workflows/agent_first.py', 'dashboard/src/pages/ExecutionsPage.tsx'],
        has_untracked: false,
      },
      recovery_hint: '清理目标仓库工作树后可直接再次启动当前 execution。',
      delivery_summary: {
        ...detail.delivery_summary,
        status: 'release_blocked',
        delivery_blocker_type: 'repo_gate_failed',
        delivery_failure_excerpt: '[ci:docs] documentation validation failed',
        repairable: true,
        repair_attempt_count: 1,
        next_action: 'repair_delivery',
      },
    })

    render(
      <MemoryRouter initialEntries={['/executions/1']}>
        <Routes>
          <Route path="/executions/:id" element={<ExecutionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getExecution).toHaveBeenCalledWith(1))
    expect(screen.getByRole('button', { name: '再次启动' })).toBeInTheDocument()
    expect(screen.getByText('工作区阻塞详情')).toBeInTheDocument()
    expect(screen.getByText(/脏文件数量：2/)).toBeInTheDocument()
    expect(screen.getByText(/agent_first\.py/)).toBeInTheDocument()
    expect(screen.getByText(/交付门禁阻塞/)).toBeInTheDocument()
    expect(screen.getByText(/仅影响当前需求/)).toBeInTheDocument()
    expect(screen.getAllByText(/repo_gate_failed/).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '创建新 run 重试' })).not.toBeInTheDocument()
  })

  it('renders timed-out recovery as operator-only blocker', async () => {
    mockApi.getExecution.mockResolvedValue({
      ...detail,
      execution: {
        ...detail.execution,
        status: 'blocked',
        phase: 'blocked',
        allowed_actions: ['view', 'view_requirement'],
        recovery_status: 'timed_out',
        recovery_scope: 'current_requirement',
        recovery_deadline_at: '2026-04-14T07:10:00Z',
        recovery_timeout_status: 'timed_out',
        time_remaining_seconds: 0,
        recovery_mode: 'none',
        blocking_reason_code: 'runtime_recovery_timed_out',
        blocking_reason_message: 'Execution recovery timed out and now requires operator review.',
        recovery_hint: '恢复已超时，需要人工介入；不会阻塞其他需求执行。',
      },
      phase: 'blocked',
      allowed_actions: ['view', 'view_requirement'],
      recovery_status: 'timed_out',
      recovery_scope: 'current_requirement',
      recovery_deadline_at: '2026-04-14T07:10:00Z',
      recovery_timeout_status: 'timed_out',
      time_remaining_seconds: 0,
      recovery_mode: 'none',
      blocking_reason_code: 'runtime_recovery_timed_out',
      blocking_reason_message: 'Execution recovery timed out and now requires operator review.',
      recovery_hint: '恢复已超时，需要人工介入；不会阻塞其他需求执行。',
    })

    render(
      <MemoryRouter initialEntries={['/executions/1']}>
        <Routes>
          <Route path="/executions/:id" element={<ExecutionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getExecution).toHaveBeenCalledWith(1))
    expect(screen.getByText(/runtime_recovery_timed_out/)).toBeInTheDocument()
    expect(screen.getByText(/恢复超时，需人工介入/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '再次启动' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '创建新 run 重试' })).not.toBeInTheDocument()
  })

  it('opens file preview modal with diff first', async () => {
    render(
      <MemoryRouter initialEntries={['/executions/1']}>
        <Routes>
          <Route path="/executions/:id" element={<ExecutionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getExecution).toHaveBeenCalledWith(1))
    fireEvent.click(screen.getByRole('button', { name: '预览' }))

    await waitFor(() => expect(mockApi.getExecutionFilePreview).toHaveBeenCalledWith(1, 'src/feature.py'))
    expect(screen.getByText(/print\('before'\)/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '当前内容' })).toBeInTheDocument()
  })
})
