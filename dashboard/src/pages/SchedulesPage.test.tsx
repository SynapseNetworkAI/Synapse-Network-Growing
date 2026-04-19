// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SchedulesPage from './SchedulesPage'

const apiMock = vi.hoisted(() => ({
  getRecurringWorkflows: vi.fn(),
  getRecurringWorkflowHealth: vi.fn(),
  getRecurringWorkflowRuns: vi.fn(),
  runRecurringWorkflow: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

const workflow = {
  workflow_key: 'bug_log_sweep',
  display_name: 'Bug Log Sweep',
  description: 'Scan bug logs',
  owner_role: 'reliability',
  cadence_type: 'interval',
  schedule: { cadence: 'interval', interval_minutes: 5 },
  status: 'active',
  last_run_at: null,
  last_result: { scanned: 0 },
  created_at: '2026-04-18T00:00:00Z',
  updated_at: '2026-04-18T00:00:00Z',
  next_run_at: '2026-04-18T01:00:00Z',
  is_due: false,
  health_status: 'healthy',
}

const health = {
  bug_log_scheduler: { enabled: true, running: true, last_error: null },
  notification_dispatcher: { enabled: true, running: true, queued_count: 0 },
  recurring_registry: { total: 1, active: 1, due: 0, failed: 0 },
}

describe('SchedulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getRecurringWorkflows.mockResolvedValue([workflow])
    apiMock.getRecurringWorkflowHealth.mockResolvedValue(health)
    apiMock.getRecurringWorkflowRuns.mockResolvedValue([
      {
        id: 12,
        workflow_key: 'bug_log_sweep',
        status: 'succeeded',
        triggered_by: 'operator',
        dry_run: true,
        params: { dry_run: true },
        result: { status: 'dry_run' },
        error_excerpt: null,
        started_at: '2026-04-18T00:00:00Z',
        completed_at: '2026-04-18T00:00:01Z',
        duration_ms: 1000,
      },
    ])
    apiMock.runRecurringWorkflow.mockResolvedValue({
      workflow_key: 'bug_log_sweep',
      status: 'completed',
      run_started_at: '2026-04-18T00:00:00Z',
      run_id: 13,
      result: { dry_run: true },
    })
  })

  it('shows scheduler health, registry and run history', async () => {
    render(<SchedulesPage />)

    expect(await screen.findByText('定时任务')).toBeTruthy()
    expect(screen.getByText('Bug Log Scheduler')).toBeTruthy()
    expect(screen.getByText('Notification Dispatcher')).toBeTruthy()
    expect(screen.getAllByText('Bug Log Sweep').length).toBeGreaterThan(0)

    await waitFor(() => expect(apiMock.getRecurringWorkflowRuns).toHaveBeenCalledWith('bug_log_sweep', 50))
    expect(screen.getByText(/#12/)).toBeTruthy()
  })

  it('runs dry run with safe defaults', async () => {
    const user = userEvent.setup()
    render(<SchedulesPage />)

    expect((await screen.findAllByText('Bug Log Sweep')).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: 'Dry Run' }))

    await waitFor(() => {
      expect(apiMock.runRecurringWorkflow).toHaveBeenCalledWith('bug_log_sweep', {
        dry_run: true,
        auto_start: false,
        auto_dispatch_acceptance: false,
      })
    })
  })
})
