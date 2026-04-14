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
    complexity: 'simple',
    status: 'running',
    validation_profile: 'minimal',
    delivery_intent: 'pr_required',
    approval_required: false,
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
    verification_agent_id: 'verification_agent',
    verification_agent_label: 'Verification Agent',
    evidence_used: ['raw_output:92 chars', 'changed_files:1'],
    reasoning_markdown: 'The execution evidence satisfies the acceptance contract.',
    suggested_next_action: 'release_ready',
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
    verification_agent_id: 'verification_agent',
    verification_agent_label: 'Verification Agent',
    evidence_used: ['raw_output:92 chars', 'changed_files:1'],
    reasoning_markdown: 'The execution evidence satisfies the acceptance contract.',
    suggested_next_action: 'release_ready',
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
    expect(screen.getByText(/release_ready/)).toBeInTheDocument()
    expect(screen.getByText('执行计划')).toBeInTheDocument()
    expect(screen.getByText('原始执行输出')).toBeInTheDocument()
    expect(screen.getByText(/Applied the requested change\./)).toBeInTheDocument()
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
