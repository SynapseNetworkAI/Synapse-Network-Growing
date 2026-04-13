import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RequirementDetail from '../src/pages/RequirementDetail'

const mockApi = {
  getRequirement: vi.fn(),
  getRequirements: vi.fn(),
  startRequirement: vi.fn(),
  pauseRequirement: vi.fn(),
  publishRequirement: vi.fn(),
  syncRequirementReviewPr: vi.fn(),
  deployRequirementToStaging: vi.fn(),
  promoteRequirementToProduction: vi.fn(),
  rollbackRequirementDeployment: vi.fn(),
  reviseRequirement: vi.fn(),
  decideRequirementApproval: vi.fn(),
  updateRequirement: vi.fn(),
  updateRequirementPlan: vi.fn(),
  updateWorkflowStep: vi.fn(),
  getTaskOutputFile: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    startRequirement: (...args: unknown[]) => mockApi.startRequirement(...args),
    pauseRequirement: (...args: unknown[]) => mockApi.pauseRequirement(...args),
    publishRequirement: (...args: unknown[]) => mockApi.publishRequirement(...args),
    syncRequirementReviewPr: (...args: unknown[]) => mockApi.syncRequirementReviewPr(...args),
    deployRequirementToStaging: (...args: unknown[]) => mockApi.deployRequirementToStaging(...args),
    promoteRequirementToProduction: (...args: unknown[]) => mockApi.promoteRequirementToProduction(...args),
    rollbackRequirementDeployment: (...args: unknown[]) => mockApi.rollbackRequirementDeployment(...args),
    reviseRequirement: (...args: unknown[]) => mockApi.reviseRequirement(...args),
    decideRequirementApproval: (...args: unknown[]) => mockApi.decideRequirementApproval(...args),
    updateRequirement: (...args: unknown[]) => mockApi.updateRequirement(...args),
    updateRequirementPlan: (...args: unknown[]) => mockApi.updateRequirementPlan(...args),
    updateWorkflowStep: (...args: unknown[]) => mockApi.updateWorkflowStep(...args),
    getTaskOutputFile: (...args: unknown[]) => mockApi.getTaskOutputFile(...args),
  },
}))

const detail = {
  requirement: {
    id: 1,
    title: 'Verification contract hardening',
    description_markdown: 'Strengthen the validation gate and bugfix loop.',
    status: 'in_progress',
    priority: 'high',
    source: 'manual',
    source_ref: null,
    intake_metadata: {},
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
    acceptance_contract: {},
    approval_status: 'pending_approval',
    approval_contract: {
      approval_mode: 'auto_or_human',
      required_approver_roles: ['request_owner', 'reviewer', 'tester'],
    },
    approval_requested_at: '2026-04-11T08:00:00Z',
    approved_at: null,
    current_plan_version: 2,
    blocked_by_count: 0,
    active_workflow_run_id: 3,
    started_at: '2026-04-11T08:00:00Z',
    completed_at: null,
    created_at: '2026-04-11T07:50:00Z',
    updated_at: '2026-04-11T08:05:00Z',
  },
  workflow_run: {
    id: 3,
    requirement_id: 1,
    plan_version: 2,
    status: 'running',
    triggered_by: 'user',
    planner_artifact_id: 11,
    started_at: '2026-04-11T08:00:00Z',
    completed_at: null,
    created_at: '2026-04-11T08:00:00Z',
    updated_at: '2026-04-11T08:05:00Z',
    steps: [
      {
        id: 21,
        workflow_run_id: 3,
        requirement_id: 1,
        step_key: 'implementation',
        step_type: 'implementation',
        title: 'Implement requirement',
        status: 'running',
        sequence_no: 30,
        assigned_agent_id: 'dev_rel',
        assigned_workflow_role: 'implementer',
        branch_from_step_id: null,
        compatibility_task_id: null,
        retry_count: 0,
        handoff_summary_markdown: null,
        done_when_markdown: 'Implementation output is ready for review.',
        context_policy_json: JSON.stringify({
          max_prompt_chars: 14000,
          compact_after_chars: 11000,
          max_artifact_body_chars: 2600,
          max_handoff_chars: 1200,
          stale_after_minutes: 30,
        }),
        execution_profile_json: JSON.stringify({
          complexity_tier: 'standard',
          allow_escalation: true,
          escalation_rule: {
            next_tier: 'max',
          },
          budget_cap: {
            max_input_tokens: 14000,
            max_output_tokens: 4000,
            max_attempts: 3,
            max_runtime_seconds: 1800,
          },
        }),
        runtime_backend: 'codex_cli',
        runtime_provider: 'openai',
        runtime_model: 'gpt-5.4',
        runtime_session_id: 'session-123',
        runtime_selected_agent: 'codex_cli',
        execution_time_ms: 102000,
        tokens_used: 2480,
        started_at: '2026-04-11T08:00:00Z',
        completed_at: null,
      },
    ],
  },
  dependencies: [],
  acceptance_checks: [
    {
      id: 1,
      requirement_id: 1,
      check_key: 'review_passed',
      description: 'Review gate passes.',
      check_type: 'manual_review',
      owner_role: 'reviewer',
      status: 'passed',
      success_criteria_markdown: null,
      verified_by_step_id: 21,
      evidence_artifact_id: 31,
      created_at: '2026-04-11T08:00:00Z',
      updated_at: '2026-04-11T08:03:00Z',
    },
    {
      id: 2,
      requirement_id: 1,
      check_key: 'validation_passed',
      description: 'Automated validation passes.',
      check_type: 'content_assertion',
      owner_role: 'tester',
      status: 'failed',
      success_criteria_markdown: null,
      verified_by_step_id: 22,
      evidence_artifact_id: 32,
      created_at: '2026-04-11T08:00:00Z',
      updated_at: '2026-04-11T08:04:00Z',
    },
  ],
  artifacts: [
    {
      id: 11,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: null,
      producer_step_id: null,
      artifact_type: 'implementation_plan',
      path: null,
      content_summary: 'Plan v2',
      human_readable_body: '# Plan',
      machine_readable_payload: '{}',
      created_at: '2026-04-11T08:00:00Z',
    },
    {
      id: 12,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: null,
      producer_step_id: null,
      artifact_type: 'validation_plan',
      path: null,
      content_summary: 'Validation contract v2',
      human_readable_body: '# Validation Contract',
      machine_readable_payload: JSON.stringify({
        summary_markdown: 'Reviewer owns the manual review gate, tester owns automated validation and closeout.',
        bugfix_owner_role: 'implementer',
        closeout_owner_role: 'tester',
        gates: ['review_passed', 'validation_passed'],
        manual_checks: [
          { check_key: 'review_passed', owner_role: 'reviewer', method: 'manual_review' },
        ],
        automated_checks: [
          { check_key: 'validation_passed', owner_role: 'tester', method: 'agent_validation' },
        ],
      }),
      created_at: '2026-04-11T08:00:00Z',
    },
    {
      id: 13,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 22,
      producer_step_id: 22,
      artifact_type: 'bug_report',
      path: null,
      content_summary: 'Validation failed after test run',
      human_readable_body: 'Validation failed after test run',
      machine_readable_payload: JSON.stringify({
        step_type: 'test',
        verification_type: 'automated',
        failed_checks: [{ check_key: 'validation_passed' }],
      }),
      created_at: '2026-04-11T08:04:00Z',
    },
    {
      id: 14,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 21,
      producer_step_id: 21,
      artifact_type: 'prompt_cache_profile',
      path: null,
      content_summary: 'prompt cache profile for step implementation',
      human_readable_body: '# Prompt Cache Profile',
      machine_readable_payload: JSON.stringify({
        cache_key: 'cache-123',
        cache_applied: true,
        cached_chars_saved: 3200,
        deduped_binding_count: 2,
      }),
      created_at: '2026-04-11T08:01:00Z',
    },
    {
      id: 15,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 21,
      producer_step_id: 21,
      artifact_type: 'context_compaction',
      path: null,
      content_summary: 'context compacted for step implementation',
      human_readable_body: '## Context Compact Summary',
      machine_readable_payload: JSON.stringify({
        raw_chars: 18200,
        final_chars: 10800,
        section_count: 6,
        compacted: true,
      }),
      created_at: '2026-04-11T08:01:00Z',
    },
    {
      id: 16,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 21,
      producer_step_id: 21,
      artifact_type: 'stale_memory_verification',
      path: null,
      content_summary: 'fresh context verification for step implementation',
      human_readable_body: 'Verification status: fresh',
      machine_readable_payload: JSON.stringify({
        verification_status: 'fresh',
        stale_findings: [],
      }),
      created_at: '2026-04-11T08:01:00Z',
    },
    {
      id: 17,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 21,
      producer_step_id: 21,
      artifact_type: 'runtime_lifecycle',
      path: null,
      content_summary: 'running runtime lifecycle for step implementation',
      human_readable_body: '# Runtime Lifecycle',
      machine_readable_payload: JSON.stringify({
        phase: 'running',
        task_status: 'running',
        step_status: 'running',
        runtime_backend: 'copilot_sdk',
        runtime_session_id: 'session-running-123',
        runtime_selected_agent: 'editor',
      }),
      created_at: '2026-04-11T08:02:00Z',
    },
    {
      id: 18,
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 21,
      producer_step_id: 21,
      artifact_type: 'runtime_telemetry',
      path: null,
      content_summary: 'running runtime telemetry for step implementation',
      human_readable_body: '# Runtime Telemetry',
      machine_readable_payload: JSON.stringify({
        runtime_event_cursor: 6,
        transcript_available: false,
        subagent_counts: {
          selected: 1,
          started: 1,
          completed: 0,
          failed: 0,
        },
        recent_events: [
          { event_type: 'runtime_session_created', detail: 'session=session-running-123' },
          { event_type: 'subagent_started', detail: 'editor' },
        ],
      }),
      created_at: '2026-04-11T08:02:00Z',
    },
  ],
  task_outputs: [
    {
      task_id: 44,
      step_id: 21,
      step_key: 'implementation',
      step_type: 'implementation',
      step_title: 'Implement requirement',
      task_status: 'completed',
      output_files: ['server/routes/requirements.py'],
      changed_files: [
        {
          filename: 'server/routes/requirements.py',
          additions: 12,
          deletions: 1,
          patch: '@@ -1,1 +1,1 @@',
          target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        },
      ],
      target_project_paths: ['/Users/cliff/workspace/agent/Synapse-Network-Growing'],
      source: 'snapshot',
      captured_at: '2026-04-11T08:01:00Z',
      legacy_snapshot: false,
      change_warning: null,
    },
  ],
  merged_output_files: [
    {
      file_name: 'server/routes/requirements.py',
      task_ids: [44],
      step_keys: ['implementation'],
      step_types: ['implementation'],
      step_titles: ['Implement requirement'],
    },
  ],
  delivery_state: {
    branch_name: 'ops/req-1-verification-contract-hardening',
    branch_strategy: 'requirement_branch',
    base_branch: 'main',
    review_status: 'review_ready',
    publish_status: 'review_ready',
    release_mode: 'manual',
    requires_manual_approval: true,
    required_checks: ['pytest -q', 'npm run build'],
    confirmed_checks: ['pytest -q'],
    pending_checks: ['npm run build'],
    publish_blockers: ['required check pending: npm run build'],
    review_surface_summary: 'Requirement #1 is review-ready.',
    rollback_hint_markdown: 'Revert the promoted change from `main`.',
    review_ready_at: '2026-04-11T08:05:00Z',
    published_at: null,
    publish_note: null,
    vcs_status: 'delivered',
    vcs_remote_name: 'origin',
    vcs_repositories: [
      {
        repo_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        status: 'delivered',
        branch_name: 'ops/req-1-verification-contract-hardening',
        remote_url: 'git@github.com:openai/synapse-network-growing.git',
        commit_sha: 'abc123def456',
        remote_sha: 'abc123def456',
        committed: true,
        pushed: true,
        blockers: [],
      },
    ],
    compare_url: 'https://github.com/openai/synapse-network-growing/compare/main...ops/req-1-verification-contract-hardening',
    pr_status: 'draft',
    pr_number: 42,
    pr_url: 'https://github.com/openai/synapse-network-growing/pull/42',
    head_branch: 'ops/req-1-verification-contract-hardening',
    latest_commit_sha: 'abc123def456',
    latest_remote_sha: 'abc123def456',
    review_bundle_generated_at: '2026-04-11T08:05:00Z',
    last_pushed_at: '2026-04-11T08:04:30Z',
    pr_metadata: {
      title: 'ops(req-1): Verification contract hardening',
      head_branch: 'ops/req-1-verification-contract-hardening',
      base_branch: 'main',
      status: 'delivered',
      draft: true,
      delivered_repository_count: 1,
    },
    promotion_checklist: [
      {
        key: 'branch_delivery',
        label: 'Branch delivery pushed',
        status: 'completed',
        detail: 'Review branch committed and pushed to remote.',
      },
      {
        key: 'required_checks',
        label: 'Required checks confirmed',
        status: 'pending',
        detail: 'Pending checks: npm run build',
      },
    ],
    staging_status: {
      environment: 'staging',
      project_key: 'synapse-network-growing',
      deploy_repo_full_name: 'cliff-personal/Synapse-Network-Growing',
      host_label: 'staging-vm',
      deploy_strategy: 'github_actions_ssh',
      trigger_enabled: true,
      current_commit_sha: 'abc123def456',
      current_branch: 'ops/req-1-verification-contract-hardening',
      last_success_at: '2026-04-11T08:06:00Z',
      health_status: 'healthy',
      last_trigger_source: 'ops_console',
      last_external_url: 'https://github.com/openai/synapse-network-growing/actions/workflows/deploy-staging.yml',
      last_record_id: 7,
    },
    production_status: {
      environment: 'production',
      project_key: 'synapse-network-growing',
      deploy_repo_full_name: 'cliff-personal/Synapse-Network-Growing',
      host_label: 'prod-vm',
      deploy_strategy: 'github_actions_ssh',
      trigger_enabled: true,
      current_commit_sha: 'abc122200000',
      current_branch: 'main',
      last_success_at: '2026-04-10T08:06:00Z',
      health_status: 'healthy',
      last_trigger_source: 'ops_console',
      last_external_url: 'https://github.com/openai/synapse-network-growing/actions/workflows/deploy-production.yml',
      last_record_id: 6,
    },
    last_deployed_sha: 'abc123def456',
    last_deployed_at: '2026-04-11T08:06:00Z',
    deploy_readiness: {
      ready: true,
      blockers: [],
      project_key: 'synapse-network-growing',
      deploy_repo_full_name: 'cliff-personal/Synapse-Network-Growing',
      deliverable_commit_sha: 'abc123def456',
    },
  },
  deployment_records: [
    {
      id: 7,
      requirement_id: 1,
      project_policy_id: 1,
      project_key: 'synapse-network-growing',
      environment: 'staging',
      action: 'deploy',
      status: 'requested',
      commit_sha: 'abc123def456',
      branch_name: 'ops/req-1-verification-contract-hardening',
      workflow_file: 'deploy-staging.yml',
      external_run_id: null,
      external_url: 'https://github.com/openai/synapse-network-growing/actions/workflows/deploy-staging.yml',
      actor: 'operator',
      trigger_source: 'ops_console',
      rollback_target_sha: null,
      health_status: null,
      notes: null,
      metadata: {},
      started_at: '2026-04-11T08:06:00Z',
      finished_at: null,
      created_at: '2026-04-11T08:06:00Z',
      updated_at: '2026-04-11T08:06:00Z',
    },
  ],
  incidents: [
    {
      incident_key: 'bugfix_circuit_breaker:33',
      requirement_id: 1,
      workflow_run_id: 3,
      step_id: 22,
      source_artifact_id: 33,
      source_artifact_type: 'bugfix_circuit_breaker',
      incident_family: 'recovery_loop',
      incident_code: 'bugfix_circuit_breaker',
      severity: 'critical',
      recovery_status: 'operator_review_required',
      title: 'Recovery incident: bugfix circuit breaker',
      summary: 'Repeated validation failures triggered a circuit breaker.',
      recommended_action: 'Inspect the repeated error fingerprint and handle the operator review follow-up.',
      project_root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
      project_display_name: 'Synapse-Network-Growing',
      evidence: [],
      occurred_at: '2026-04-11T08:04:30Z',
    },
  ],
  attachments: [
    {
      id: 1,
      requirement_id: 1,
      file_name: 'staging-screenshot.png',
      stored_path: 'runtime/requirement_attachments/req-1/01-staging-screenshot.png',
      content_type: 'image/png',
      attachment_kind: 'image',
      source: 'clipboard',
      size_bytes: 18234,
      created_at: '2026-04-11T08:00:00Z',
    },
  ],
}

describe('RequirementDetail', () => {
  beforeEach(() => {
    mockApi.getRequirement.mockResolvedValue(detail)
    mockApi.getRequirements.mockResolvedValue([detail.requirement])
    mockApi.startRequirement.mockResolvedValue(detail)
    mockApi.pauseRequirement.mockResolvedValue(detail)
    mockApi.publishRequirement.mockResolvedValue(detail)
    mockApi.syncRequirementReviewPr.mockResolvedValue(detail)
    mockApi.deployRequirementToStaging.mockResolvedValue(detail.deployment_records[0])
    mockApi.promoteRequirementToProduction.mockResolvedValue({ ...detail.deployment_records[0], environment: 'production' })
    mockApi.rollbackRequirementDeployment.mockResolvedValue({ ...detail.deployment_records[0], action: 'rollback', rollback_target_sha: 'abc122200000' })
    mockApi.reviseRequirement.mockResolvedValue(detail)
    mockApi.decideRequirementApproval.mockResolvedValue({
      ...detail,
      requirement: {
        ...detail.requirement,
        approval_status: 'approved',
        approved_at: '2026-04-11T08:06:00Z',
      },
    })
    mockApi.updateRequirement.mockResolvedValue(detail)
    mockApi.updateRequirementPlan.mockResolvedValue(detail)
    mockApi.updateWorkflowStep.mockResolvedValue(detail)
    mockApi.getTaskOutputFile.mockResolvedValue({
      file_name: 'output.md',
      content: '# Output\n\nDone.',
      size_bytes: 24,
      truncated: false,
      content_type: 'text/markdown',
    })
  })

  it('renders validation contract and bug report context', async () => {
    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    const validationPanel = screen.getByTestId('validation-contract-panel')
    expect(validationPanel).toBeInTheDocument()
    expect(screen.getByText('Manual Checks')).toBeInTheDocument()
    expect(screen.getByText('Automated Checks')).toBeInTheDocument()
    expect(within(validationPanel).getAllByText('review_passed').length).toBeGreaterThan(0)
    expect(within(validationPanel).getAllByText('validation_passed').length).toBeGreaterThan(0)
    expect(screen.getByText('Bugfix: implementer')).toBeInTheDocument()

    const bugPanel = screen.getByTestId('bug-reports-panel')
    expect(bugPanel).toBeInTheDocument()
    expect(within(bugPanel).getAllByText('Validation failed after test run').length).toBeGreaterThan(0)
    expect(within(bugPanel).getByText(/Failed checks: validation_passed/)).toBeInTheDocument()

    expect(screen.getByTestId('release-handoff-panel')).toBeInTheDocument()
    expect(screen.getByTestId('context-governance-panel')).toBeInTheDocument()
    expect(screen.getByTestId('runtime-lifecycle-panel')).toBeInTheDocument()
    expect(screen.getByTestId('incident-panel')).toBeInTheDocument()
    expect(screen.getByText('Latest Compaction')).toBeInTheDocument()
    expect(screen.getByText('Prompt Cache')).toBeInTheDocument()
    expect(screen.getByText(/cache key: cache-123/)).toBeInTheDocument()
    expect(screen.getByText(/saved chars: 3200/)).toBeInTheDocument()
    expect(screen.getByText(/status: fresh/)).toBeInTheDocument()
    expect(screen.getAllByText(/tier standard/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/allow escalation: true/i)).toBeInTheDocument()
    expect(screen.getByText(/next tier: max/i)).toBeInTheDocument()
    expect(screen.getByText(/input tokens: 14000/i)).toBeInTheDocument()
    expect(screen.getByText(/phase: running/)).toBeInTheDocument()
    expect(screen.getByText(/selected agent: editor/)).toBeInTheDocument()
    expect(screen.getByText(/subagents:/)).toBeInTheDocument()
    expect(screen.getByText(/subagent_started/)).toBeInTheDocument()
    expect(screen.getAllByText(/editor/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Recovery incident: bugfix circuit breaker/)).toBeInTheDocument()
    expect(screen.getByText(/operator_review_required/)).toBeInTheDocument()
    expect(screen.getByText(/branch: ops\/req-1-verification-contract-hardening/)).toBeInTheDocument()
    expect(screen.getByText('PR Metadata')).toBeInTheDocument()
    expect(screen.getByText('Compare')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /https:\/\/github.com\/openai\/synapse-network-growing\/compare\/main...ops\/req-1-verification-contract-hardening/i })).toBeInTheDocument()
    expect(screen.getByText('number: 42')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /https:\/\/github.com\/openai\/synapse-network-growing\/pull\/42/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '前往发布中心' })).toHaveAttribute('href', '/deployments?requirement=1')
    expect(screen.getByTestId('requirement-approval-panel')).toBeInTheDocument()
    expect(screen.getByTestId('requirement-approval-badge')).toHaveTextContent('审批: 待审批')
    expect(screen.getByTestId('approval-banner')).toBeInTheDocument()
    expect(screen.getByTestId('requirement-task-outputs')).toHaveTextContent('Task #44')
    expect(screen.getByTestId('requirement-task-outputs')).toHaveTextContent('server/routes/requirements.py')
    expect(screen.getByTestId('workflow-step-runtime-21')).toHaveTextContent('gpt-5.4')
    expect(screen.getByTestId('workflow-step-runtime-21')).toHaveTextContent('耗时 1m 42s')
    expect(screen.getByTestId('workflow-step-runtime-21')).toHaveTextContent('tokens 2,480')
    expect(screen.getByTestId('requirement-attachments')).toHaveTextContent('staging-screenshot.png')
  })

  it('keeps release controls in the release center instead of requirement detail', async () => {
    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))
    expect(screen.queryByRole('button', { name: 'Create/Sync Review PR' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Deploy To Staging' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Promote To Production' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Rollback' })).not.toBeInTheDocument()
  })

  it('allows approving requirement execution from detail page', async () => {
    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    fireEvent.change(screen.getByTestId('requirement-approval-comment'), { target: { value: 'Proceed' } })
    fireEvent.click(screen.getByTestId('approve-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.decideRequirementApproval).toHaveBeenCalledWith(1, {
        action: 'approve',
        reviewer: 'cto',
        comment: 'Proceed',
      })
    })
  })

  it('sends empty string when approving without comment', async () => {
    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    fireEvent.click(screen.getByTestId('approve-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.decideRequirementApproval).toHaveBeenCalledWith(1, {
        action: 'approve',
        reviewer: 'cto',
        comment: '',
      })
    })
  })

  it('shows automatic planning state after approval and disables direct start', async () => {
    const planningDetail = {
      ...detail,
      requirement: {
        ...detail.requirement,
        status: 'planning',
        approval_status: 'approved',
        approved_at: '2026-04-11T08:06:00Z',
        current_plan_version: 0,
        active_workflow_run_id: null,
      },
      workflow_run: null,
    }
    mockApi.getRequirement.mockResolvedValueOnce(planningDetail)

    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    expect(screen.getByText('规划中')).toBeInTheDocument()
    expect(screen.getByTestId('planning-banner')).toBeInTheDocument()
    expect(screen.getByTestId('start-requirement-btn')).toBeDisabled()
  })

  it('allows editing requirement content and saving', async () => {
    mockApi.getRequirement.mockResolvedValueOnce({
      ...detail,
      requirement: {
        ...detail.requirement,
        status: 'paused',
      },
    })

    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    fireEvent.click(screen.getByTestId('toggle-edit-requirement-btn'))
    fireEvent.change(screen.getByTestId('edit-requirement-title'), { target: { value: 'Edited requirement title' } })
    fireEvent.change(screen.getByTestId('edit-requirement-priority'), { target: { value: 'normal' } })
    fireEvent.change(screen.getByTestId('edit-requirement-target-project-path'), { target: { value: '/tmp/project-a\n/tmp/project-b' } })
    fireEvent.change(screen.getByTestId('edit-requirement-description'), { target: { value: 'Edited requirement body' } })
    fireEvent.click(screen.getByTestId('save-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.updateRequirement).toHaveBeenCalledWith(1, {
        title: 'Edited requirement title',
        description_markdown: 'Edited requirement body',
        priority: 'normal',
        target_project_path: '/tmp/project-a\n/tmp/project-b',
      })
    })
  })

  it('allows editing plan markdown and saving', async () => {
    const user = userEvent.setup()
    mockApi.getRequirement.mockResolvedValueOnce({
      ...detail,
      requirement: {
        ...detail.requirement,
        status: 'paused',
      },
      workflow_run: {
        ...detail.workflow_run,
        status: 'paused',
      },
    })

    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    await user.click(screen.getByTestId('toggle-edit-plan-btn'))
    fireEvent.change(await screen.findByTestId('edit-plan-body'), { target: { value: '# Edited Plan\n\nUpdated plan body.' } })
    await user.click(screen.getByTestId('save-plan-btn'))

    await waitFor(() => {
      expect(mockApi.updateRequirementPlan).toHaveBeenCalledWith(1, {
        human_readable_body: '# Edited Plan\n\nUpdated plan body.',
      })
    })
  })

  it('allows editing a non-running workflow step and saving', async () => {
    const user = userEvent.setup()
    mockApi.getRequirement.mockResolvedValueOnce({
      ...detail,
      requirement: {
        ...detail.requirement,
        status: 'paused',
      },
      workflow_run: {
        ...detail.workflow_run,
        status: 'paused',
        steps: detail.workflow_run.steps.map((step) => ({
          ...step,
          status: 'ready',
          compatibility_task_id: 44,
        })),
      },
    })

    render(
      <MemoryRouter initialEntries={['/requirements/1']}>
        <Routes>
          <Route path="/requirements/:id" element={<RequirementDetail />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => expect(mockApi.getRequirement).toHaveBeenCalledWith(1))

    await user.click(screen.getByTestId('edit-workflow-step-21'))
    fireEvent.change(await screen.findByTestId('edit-step-title-21'), { target: { value: 'Edited step title' } })
    fireEvent.change(screen.getByTestId('edit-step-done-when-21'), { target: { value: 'Edited done when' } })
    fireEvent.change(screen.getByTestId('edit-step-handoff-21'), { target: { value: 'Edited handoff' } })
    await user.click(screen.getByTestId('save-workflow-step-21'))

    await waitFor(() => {
      expect(mockApi.updateWorkflowStep).toHaveBeenCalledWith(1, 21, {
        title: 'Edited step title',
        done_when_markdown: 'Edited done when',
        handoff_summary_markdown: 'Edited handoff',
      })
    })
  })
})
