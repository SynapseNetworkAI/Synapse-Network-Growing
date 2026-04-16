import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RequirementDetail from '../src/pages/RequirementDetail'

const mockApi = {
  getRequirement: vi.fn(),
  getProjects: vi.fn(),
  updateRequirement: vi.fn(),
  submitRequirement: vi.fn(),
  regenerateRequirementAssets: vi.fn(),
  approveRequirement: vi.fn(),
  rejectRequirement: vi.fn(),
  startExecution: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    getProjects: (...args: unknown[]) => mockApi.getProjects(...args),
    updateRequirement: (...args: unknown[]) => mockApi.updateRequirement(...args),
    submitRequirement: (...args: unknown[]) => mockApi.submitRequirement(...args),
    regenerateRequirementAssets: (...args: unknown[]) => mockApi.regenerateRequirementAssets(...args),
    approveRequirement: (...args: unknown[]) => mockApi.approveRequirement(...args),
    rejectRequirement: (...args: unknown[]) => mockApi.rejectRequirement(...args),
    startExecution: (...args: unknown[]) => mockApi.startExecution(...args),
  },
}))

const baseDetail = {
  requirement: {
    id: 3,
    title: 'Bug Fix: Runtime traceback detected',
    description_markdown: 'Fix the runtime traceback surfaced by the intake pipeline.',
    acceptance_criteria_markdown: '- Traceback no longer appears\n- Targeted regression check passes',
    status: 'ready',
    priority: 'high',
    source: 'bug_intake',
    source_ref: 'error-fingerprint:runtime_log_error:abc123',
    project_id: 3,
    project_key: 'synapse-network-growing',
    project_display_name: 'Synapse-Network-Growing',
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    target_project_path_override: null,
    target_projects: ['/Users/cliff/workspace/agent/Synapse-Network-Growing'],
    approval_required: false,
    approval_status: 'waived',
    created_at: '2026-04-14T00:00:00Z',
    updated_at: '2026-04-14T00:00:00Z',
    active_execution_run_id: null,
    latest_execution_run_id: null,
    latest_release_status: null,
  },
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
  latest_execution_id: null,
  latest_release_id: null,
  latest_release: null,
  policy_summary_markdown: '',
  acceptance_contract: {
    done_criteria: ['Traceback no longer appears in runtime intake flow.'],
    verification_checks: [{ label: 'Run targeted regression check', command: 'pytest tests/test_runtime.py', kind: 'command' }],
    scope_constraints: ['Keep changes scoped to the runtime intake path.'],
    delivery_expectation: 'Prepare a PR-ready delivery record.',
    markdown: '### Done Criteria\n- Traceback no longer appears in runtime intake flow.',
  },
  execution_plan: {
    planning_mode: 'agent_plan_brief',
    goal_summary: 'Bug Fix: Runtime traceback detected',
    summary_markdown: '## Summary\n\nFix the runtime traceback surfaced by the intake pipeline.\n\n## Planned Changes\n\n- Patch the failing runtime path in the scoped project.\n- Keep the change narrow and capture clear execution evidence.\n\n## Verification Strategy\n\n- Run `pytest tests/test_runtime.py`.\n- Confirm the traceback no longer appears in the intake flow.',
    steps: [{ step_key: 'execute', title: 'Execute requirement' }],
    planned_checks: ['Run `pytest tests/test_runtime.py`', 'Confirm the traceback no longer appears in the intake flow.'],
    risks: ['Avoid changing unrelated projects.'],
  },
  project: {
    id: 3,
    project_key: 'synapse-network-growing',
    display_name: 'Synapse-Network-Growing',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    status: 'active',
    repo_full_name: 'cliff-personal/Synapse-Network-Growing',
    default_branch: 'main',
    deploy_repo_full_name: 'cliff-personal/Synapse-Network-Growing',
    deploy_strategy: 'github_actions',
    deploy_trigger_enabled: true,
    staging_host_label: 'staging',
    production_host_label: 'production',
    staging_workflow_file: 'deploy-staging.yml',
    production_workflow_file: 'deploy-production.yml',
    notes: null,
    policy_id: 4,
    created_at: '2026-04-14T00:00:00Z',
    updated_at: '2026-04-14T00:00:00Z',
  },
  attachments: [
    {
      id: 1,
      requirement_id: 3,
      file_name: 'traceback-screenshot.png',
      stored_path: 'runtime/requirement_attachments/req-3/01-traceback-screenshot.png',
      content_type: 'image/png',
      attachment_kind: 'image',
      source: 'clipboard',
      size_bytes: 18234,
      created_at: '2026-04-14T00:00:00Z',
    },
  ],
}

describe('RequirementDetail SaaS editing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    mockApi.getRequirement.mockResolvedValue(baseDetail)
    mockApi.getProjects.mockResolvedValue([baseDetail.project])
    mockApi.updateRequirement.mockResolvedValue(baseDetail)
  })

  it('allows editing only before execution has started', async () => {
    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.getByTestId('toggle-edit-requirement-btn')).toBeInTheDocument()
    expect(screen.queryByText('修订需求')).not.toBeInTheDocument()
    expect(screen.queryByText('执行许可')).not.toBeInTheDocument()
    expect(screen.queryByText('策略摘要')).not.toBeInTheDocument()
    expect(screen.queryByText('执行 / 发布跳转')).not.toBeInTheDocument()
    expect(screen.queryByTestId('requirement-approval-notice')).not.toBeInTheDocument()
    expect(screen.getByText('执行计划')).toBeInTheDocument()
    expect(screen.getByText('Traceback no longer appears in runtime intake flow.')).toBeInTheDocument()
    expect(screen.getByText(/Patch the failing runtime path/)).toBeInTheDocument()
    expect(screen.getByTestId('requirement-attachments')).toHaveTextContent('traceback-screenshot.png')

    fireEvent.click(screen.getByTestId('toggle-edit-requirement-btn'))
    fireEvent.change(screen.getByTestId('edit-requirement-title'), { target: { value: 'Bug Fix: Traceback removed' } })
    fireEvent.click(screen.getByRole('button', { name: '显示高级设置' }))
    fireEvent.change(screen.getByTestId('edit-requirement-path-override'), { target: { value: '/tmp/project-a' } })
    fireEvent.change(screen.getByTestId('edit-requirement-priority'), { target: { value: 'normal' } })
    fireEvent.change(screen.getByTestId('edit-requirement-description'), { target: { value: 'Updated description' } })
    fireEvent.change(screen.getByTestId('edit-requirement-acceptance'), { target: { value: '- Updated acceptance' } })
    fireEvent.change(screen.getByTestId('edit-requirement-plan'), { target: { value: '## Goal\n\nUpdated plan body.' } })
    fireEvent.click(screen.getByTestId('save-requirement-btn'))

    await waitFor(() =>
      expect(mockApi.updateRequirement).toHaveBeenCalledWith(
        3,
        expect.objectContaining({
          title: 'Bug Fix: Traceback removed',
          description_markdown: 'Updated description',
          acceptance_criteria_markdown: '- Updated acceptance',
          execution_plan: expect.objectContaining({
            summary_markdown: '## Goal\n\nUpdated plan body.',
          }),
          priority: 'normal',
          project_id: 3,
          target_project_path_override: '/tmp/project-a',
        }),
      ),
    )
  })

  it('hides the edit button after execution has started', async () => {
    mockApi.getRequirement.mockResolvedValueOnce({
      ...baseDetail,
      requirement: {
        ...baseDetail.requirement,
        status: 'running',
        latest_execution_run_id: 12,
      },
      latest_execution_id: 12,
    })

    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.queryByTestId('toggle-edit-requirement-btn')).not.toBeInTheDocument()
  })

  it('shows a compact approval notice only when manual approval is pending', async () => {
    mockApi.getRequirement.mockResolvedValueOnce({
      ...baseDetail,
      requirement: {
        ...baseDetail.requirement,
        status: 'blocked',
      },
      approval_decision: {
        state: 'pending',
        reason: 'manual approval required by contract',
        source: 'human_required_by_policy',
        agent_recommendation: 'approve',
        confidence: 0.99,
        recommendation_reason: 'requirement passed deterministic auto-approval policy',
        recommendation_source: 'deterministic_policy',
        risk_flags: [],
        required_approver_roles: ['operator'],
      },
      approval: {
        ...baseDetail.approval,
        approval_decision: 'pending_manual_approval',
        approval_status: 'pending_approval',
        approval_reason: 'manual approval required by contract',
        final_decision_source: 'human_required_by_policy',
        approval_recommendation: 'approve',
        approval_recommendation_reason: 'requirement passed deterministic auto-approval policy',
        recommendation_source: 'deterministic_policy',
        approval_confidence: 0.99,
        required_approver_roles: ['operator'],
      },
    })

    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.getByTestId('requirement-approval-notice')).toBeInTheDocument()
    expect(screen.getByText('待人工审批')).toBeInTheDocument()
    expect(screen.getByText('审批状态原因：manual approval required by contract')).toBeInTheDocument()
    expect(screen.getByText('系统推荐：批准 · 置信度 0.99')).toBeInTheDocument()
    expect(screen.getByText('推荐来源：deterministic policy')).toBeInTheDocument()
    expect(screen.getByText('推荐理由：requirement passed deterministic auto-approval policy')).toBeInTheDocument()
    expect(screen.queryByText('执行许可')).not.toBeInTheDocument()
  })

  it('shows asset generation notice and disables submit while planning is pending', async () => {
    mockApi.getRequirement.mockResolvedValueOnce({
      ...baseDetail,
      assets_status: 'pending',
      assets_error_message: null,
    })

    render(
      <MemoryRouter initialEntries={['/requirements/3']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(3))
    expect(screen.getByText('验收标准与执行计划正在生成，完成前不能提交。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '提交' })).not.toBeInTheDocument()
  })
})
