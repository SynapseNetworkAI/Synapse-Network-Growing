// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReleasesPage from './ReleasesPage'

const apiMock = vi.hoisted(() => ({
  getReleaseCandidates: vi.fn(),
  prepareRelease: vi.fn(),
  openReleasePr: vi.fn(),
  syncReleasePrStatuses: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

function candidate(overrides: Record<string, unknown> = {}) {
  const release = {
    id: 6,
    requirement_id: 9,
    workflow_run_id: 9,
    state: 'merged',
    project_id: null,
    project_key: 'synapse-network-growing',
    project_display_name: 'Synapse-Network-Growing',
    target_project_path: '/repo',
    status: 'merged',
    branch_name: 'ops/req-9-quality-gates',
    planned_branch_name: null,
    actual_branch_name: null,
    branch_reuse_status: null,
    base_branch: 'main',
    commit_sha: 'abc123',
    compare_url: null,
    pr_url: 'https://github.com/cliff-personal/Synapse-Network-Growing/pull/31',
    pr_number: 31,
    pr_status: 'merged',
    merged_at: '2026-04-21T11:19:24Z',
    merge_commit_sha: 'abc123',
    last_pr_status_synced_at: '2026-04-22T01:00:00Z',
    pr_sync_failure_summary: null,
    notes: null,
    blocker_kind: null,
    delivery_blocker_type: null,
    delivery_failure_excerpt: null,
    delivery_failure_raw_output: null,
    repairable: false,
    repairability: 'manual_only',
    repair_attempt_count: 0,
    next_action: null,
    workspace_blocker: null,
    workspace_mode: 'shared_checkout',
    prepared_at: null,
    delivered_at: '2026-04-21T11:20:00Z',
    created_at: '2026-04-21T10:00:00Z',
    updated_at: '2026-04-22T01:00:00Z',
    ...(overrides.release as Record<string, unknown> | undefined),
  }
  return {
    requirement: {
      id: 9,
      title: 'Quality gate release',
      project_display_name: 'Synapse-Network-Growing',
      project_key: 'synapse-network-growing',
      active_workflow_run_id: 9,
      active_workflow_run_summary: { id: 9, workflow_key: 'agent_self_repair', current_state: 'done' },
    },
    validation: { status: 'passed', updated_at: '2026-04-22T01:00:00Z' },
    release,
    ...overrides,
  }
}

describe('ReleasesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getReleaseCandidates.mockResolvedValue([
      candidate(),
      candidate({
        requirement: {
          id: 10,
          title: 'Closed PR release',
          project_display_name: 'Synapse-Network-Growing',
          project_key: 'synapse-network-growing',
          active_workflow_run_id: null,
          active_workflow_run_summary: null,
        },
        release: {
          id: 7,
          requirement_id: 10,
          workflow_run_id: null,
          state: 'abandoned',
          status: 'pr_closed',
          pr_number: 404,
          pr_status: 'not_found',
          pr_sync_failure_summary: 'PR removed from GitHub or no longer accessible',
        },
      }),
    ])
    apiMock.syncReleasePrStatuses.mockResolvedValue({
      workflow_key: 'release_pr_status_sweep',
      status: 'completed',
      run_started_at: '2026-04-22T01:00:00Z',
      run_id: 33,
      result: { processed_count: 2, merged_ids: [6], closed_ids: [], missing_ids: [7] },
    })
  })

  it('shows merged and closed PR sync states', async () => {
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    expect(await screen.findByText('已合并')).toBeTruthy()
    expect(screen.getByText('PR 已关闭')).toBeTruthy()
    expect(screen.getByText(/GitHub: merged/)).toBeTruthy()
    expect(screen.getByText(/PR removed from GitHub/)).toBeTruthy()
  })

  it('runs PR status sync from the releases page', async () => {
    const user = userEvent.setup()
    render(<ReleasesPage />, { wrapper: MemoryRouter })

    const button = await screen.findByRole('button', { name: '同步 PR 状态' })
    await user.click(button)

    await waitFor(() => {
      expect(apiMock.syncReleasePrStatuses).toHaveBeenCalledTimes(1)
      expect(apiMock.getReleaseCandidates).toHaveBeenCalledTimes(2)
    })
  })
})
