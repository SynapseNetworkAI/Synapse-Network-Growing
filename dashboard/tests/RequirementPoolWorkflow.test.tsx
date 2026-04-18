import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RequirementPool from '../src/pages/RequirementPool'

const requirement = {
  id: 4,
  title: 'Repair Ops Dashboard failure',
  description_markdown: 'Fix the declarative workflow UI.',
  acceptance_criteria_markdown: '',
  state: 'running',
  attention_reason: null,
  failure_reason: null,
  requirement_plan_summary: null,
  project: null,
  approval: {
    state: 'approved',
    reason: null,
    source: 'deterministic_policy',
    agent_recommendation: null,
    confidence: null,
    risk_flags: [],
    required_approver_roles: [],
  },
  current_attempt_id: null,
  current_delivery_id: null,
  latest_delivery_repair_attempt_id: null,
  delivery_repair_attempt_count: 0,
  status: 'running',
  priority: 'normal',
  source: 'manual',
  source_ref: null,
  linked_requirement_id: null,
  followup_requirement_id: null,
  resolution_path: null,
  project_id: null,
  project_key: 'synapse-network-growing',
  project_display_name: 'Synapse-Network-Growing',
  target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
  target_project_path_override: null,
  target_projects: ['Synapse-Network-Growing'],
  approval_required: false,
  approval_status: 'approved',
  phase: 'executing',
  allowed_actions: ['view', 'view_workflow'],
  pending_operations: [],
  recovery_status: null,
  recovery_scope: null,
  recovery_deadline_at: null,
  recovery_timeout_status: null,
  time_remaining_seconds: null,
  assets_status: 'ready',
  assets_error_message: null,
  created_at: '2026-04-18T10:00:00Z',
  updated_at: '2026-04-18T10:01:00Z',
  active_workflow_run_id: 77,
  active_workflow_run_summary: {
    id: 77,
    requirement_id: 4,
    workflow_key: 'agent_self_repair',
    current_state: 'awaiting_operator',
    status: 'awaiting_operator',
    resolution: 'route_to_human',
    risk_level: 'high',
    pending_human_gate_count: 1,
    updated_at: '2026-04-18T10:01:00Z',
    started_at: '2026-04-18T10:00:00Z',
    completed_at: null,
  },
  active_execution_run_id: null,
  latest_execution_run_id: null,
  latest_release_status: null,
}

const mockApi = {
  getRequirements: vi.fn(),
  getProjects: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRequirements: (...args: unknown[]) => mockApi.getRequirements(...args),
    getProjects: (...args: unknown[]) => mockApi.getProjects(...args),
  },
}))

describe('RequirementPool declarative workflow summary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getRequirements.mockResolvedValue([requirement])
    mockApi.getProjects.mockResolvedValue([])
  })

  it('shows active workflow state instead of legacy execution attempt', async () => {
    render(<MemoryRouter><RequirementPool /></MemoryRouter>)

    await waitFor(() => expect(mockApi.getRequirements).toHaveBeenCalled())
    expect(screen.getByText('Repair Ops Dashboard failure')).toBeInTheDocument()
    expect(screen.getByText(/agent_self_repair · awaiting_operator · awaiting_operator/)).toBeInTheDocument()
    expect(screen.getByText(/human gate 1/)).toBeInTheDocument()
    expect(screen.getByText('工作流')).toBeInTheDocument()
    expect(screen.queryByText(/attempt/)).not.toBeInTheDocument()
  })
})
