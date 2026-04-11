import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RequirementDetail from '../src/pages/RequirementDetail'

const mockApi = {
  getRequirement: vi.fn(),
  getRequirements: vi.fn(),
  startRequirement: vi.fn(),
  pauseRequirement: vi.fn(),
  publishRequirement: vi.fn(),
  reviseRequirement: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirement: (...args: unknown[]) => mockApi.getRequirement(...args),
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    startRequirement: (...args: unknown[]) => mockApi.startRequirement(...args),
    pauseRequirement: (...args: unknown[]) => mockApi.pauseRequirement(...args),
    publishRequirement: (...args: unknown[]) => mockApi.publishRequirement(...args),
    reviseRequirement: (...args: unknown[]) => mockApi.reviseRequirement(...args),
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
    target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
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
      id: 15,
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
  },
}

describe('RequirementDetail', () => {
  beforeEach(() => {
    mockApi.getRequirement.mockResolvedValue(detail)
    mockApi.getRequirements.mockResolvedValue([detail.requirement])
    mockApi.startRequirement.mockResolvedValue(detail)
    mockApi.pauseRequirement.mockResolvedValue(detail)
    mockApi.publishRequirement.mockResolvedValue(detail)
    mockApi.reviseRequirement.mockResolvedValue(detail)
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

    expect(screen.getByTestId('delivery-state-panel')).toBeInTheDocument()
    expect(screen.getByTestId('context-governance-panel')).toBeInTheDocument()
    expect(screen.getByText('Latest Compaction')).toBeInTheDocument()
    expect(screen.getByText(/status: fresh/)).toBeInTheDocument()
    expect(screen.getByText('ops/req-1-verification-contract-hardening')).toBeInTheDocument()
    expect(screen.getByText(/required check pending: npm run build/)).toBeInTheDocument()
    expect(screen.getByTestId('publish-requirement-btn')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('publish-requirement-btn'))

    await waitFor(() => {
      expect(mockApi.publishRequirement).toHaveBeenCalledTimes(1)
    })
    expect(mockApi.publishRequirement.mock.calls[0]?.[0]).toBe(1)
  })
})
