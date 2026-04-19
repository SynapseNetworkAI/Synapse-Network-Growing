import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import SchedulesPage from '../src/pages/SchedulesPage'

const workflow = {
  id: 1,
  workflow_key: 'bug_log_sweep',
  display_name: 'Bug Log Sweep',
  description: 'Sweep logs and materialize high-signal bugs.',
  status: 'active',
  trigger_type: 'scheduler',
  owner_role: 'reliability',
  schedule: { cadence: 'interval', interval_minutes: 5 },
  input_query: {},
  output_action: {},
  escalation_rule: {},
  validation_signal: {},
  is_builtin: true,
  last_run_at: null,
  next_run_at: '2026-04-19T01:00:00Z',
  is_due: true,
  health_status: 'healthy',
  last_result: { created: 0 },
  created_at: '2026-04-19T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
}

const run = {
  id: 11,
  workflow_key: 'bug_log_sweep',
  status: 'succeeded',
  triggered_by: 'operator',
  dry_run: true,
  params: { dry_run: true },
  result: { created: 0, suppressed: 0 },
  error_excerpt: null,
  started_at: '2026-04-19T00:00:00Z',
  completed_at: '2026-04-19T00:00:01Z',
  duration_ms: 1000,
}

const mockApi = {
  getRecurringWorkflows: vi.fn(),
  getRecurringWorkflowHealth: vi.fn(),
  getRecurringWorkflowRuns: vi.fn(),
  runRecurringWorkflow: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getRecurringWorkflows: (...args: unknown[]) => mockApi.getRecurringWorkflows(...args),
    getRecurringWorkflowHealth: (...args: unknown[]) => mockApi.getRecurringWorkflowHealth(...args),
    getRecurringWorkflowRuns: (...args: unknown[]) => mockApi.getRecurringWorkflowRuns(...args),
    runRecurringWorkflow: (...args: unknown[]) => mockApi.runRecurringWorkflow(...args),
  },
}))

describe('SchedulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockApi.getRecurringWorkflows.mockResolvedValue([workflow])
    mockApi.getRecurringWorkflowHealth.mockResolvedValue({
      bug_log_scheduler: { enabled: true, running: true, last_tick_at: '2026-04-19T00:00:00Z' },
      notification_dispatcher: { enabled: true, running: true, queued_count: 0, dead_letter_count: 0 },
      recurring_registry: { enabled: true, running: true, workflow_count: 1 },
    })
    mockApi.getRecurringWorkflowRuns.mockResolvedValue([run])
    mockApi.runRecurringWorkflow.mockResolvedValue({ workflow_key: 'bug_log_sweep', status: 'succeeded', result: { created: 0 } })
  })

  it('shows scheduler health, run history, dry run and guarded run now actions', async () => {
    render(<SchedulesPage />)

    await waitFor(() => expect(mockApi.getRecurringWorkflows).toHaveBeenCalled())
    expect(screen.getByTestId('schedules-page')).toHaveTextContent('定时任务')
    expect(screen.getByTestId('schedule-health-overview')).toHaveTextContent('Notification Dispatcher')
    expect(screen.getAllByText('Bug Log Sweep').length).toBeGreaterThan(0)
    await waitFor(() => expect(screen.getByTestId('schedule-run-history-item')).toHaveTextContent('succeeded'))

    const registryRow = screen.getAllByText('Bug Log Sweep')[0].closest('tr') as HTMLElement
    fireEvent.click(within(registryRow).getByText('Dry Run'))
    await waitFor(() =>
      expect(mockApi.runRecurringWorkflow).toHaveBeenCalledWith('bug_log_sweep', {
        dry_run: true,
        auto_start: false,
        auto_dispatch_acceptance: false,
      }),
    )

    fireEvent.click(within(registryRow).getByText('Run Now'))
    await waitFor(() => expect(window.confirm).toHaveBeenCalled())
    expect(mockApi.runRecurringWorkflow).toHaveBeenCalledWith('bug_log_sweep', {
      dry_run: false,
      auto_start: false,
      auto_dispatch_acceptance: false,
    })
  })
})
