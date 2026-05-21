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
  getSchedules: vi.fn(),
  getScheduleTemplates: vi.fn(),
  getRecurringWorkflowHealth: vi.fn(),
  getScheduleRuns: vi.fn(),
  runSchedule: vi.fn(),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getSchedules: (...args: unknown[]) => mockApi.getSchedules(...args),
    getScheduleTemplates: (...args: unknown[]) => mockApi.getScheduleTemplates(...args),
    getRecurringWorkflowHealth: (...args: unknown[]) => mockApi.getRecurringWorkflowHealth(...args),
    getScheduleRuns: (...args: unknown[]) => mockApi.getScheduleRuns(...args),
    runSchedule: (...args: unknown[]) => mockApi.runSchedule(...args),
    createSchedule: (...args: unknown[]) => mockApi.createSchedule(...args),
    updateSchedule: (...args: unknown[]) => mockApi.updateSchedule(...args),
    deleteSchedule: (...args: unknown[]) => mockApi.deleteSchedule(...args),
  },
}))

describe('SchedulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getSchedules.mockResolvedValue([workflow])
    mockApi.getScheduleTemplates.mockResolvedValue([])
    mockApi.getRecurringWorkflowHealth.mockResolvedValue({
      bug_log_scheduler: { enabled: true, running: true, last_tick_at: '2026-04-19T00:00:00Z' },
      notification_dispatcher: { enabled: true, running: true, queued_count: 0, dead_letter_count: 0 },
      recurring_registry: { enabled: true, running: true, workflow_count: 1 },
    })
    mockApi.getScheduleRuns.mockResolvedValue([run])
    mockApi.runSchedule.mockResolvedValue({ workflow_key: 'bug_log_sweep', status: 'succeeded', result: { created: 0 } })
  })

  it('shows scheduler health, run history, dry run and guarded run now actions', async () => {
    render(<SchedulesPage />)

    await waitFor(() => expect(mockApi.getSchedules).toHaveBeenCalled())
    expect(screen.getByTestId('schedules-page')).toHaveTextContent('定时任务控制台')
    expect(screen.getByTestId('schedule-health-overview')).toHaveTextContent('notification dispatcher backlog')
    expect(screen.getByText(/Attention Required/)).toBeTruthy()
    expect(screen.getByText(/System Health & Reliability/)).toBeTruthy()
    expect(screen.getAllByText('Bug Log Sweep').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('schedule-compact-ipo').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Dry Run' })).toBeNull()

    const lastRunButtons = screen.getAllByRole('button', { name: /Last Run/i })
    fireEvent.click(lastRunButtons[0])
    await waitFor(() => expect(screen.getByTestId('schedule-run-inspector')).toHaveTextContent('succeeded'))
    expect(screen.getByText('Debug params / result JSON')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Configuration' }))
    const inspector = screen.getByTestId('schedule-run-inspector')
    fireEvent.click(within(inspector).getByRole('button', { name: 'Dry Run' }))
    await waitFor(() =>
      expect(mockApi.runSchedule).toHaveBeenCalledWith('bug_log_sweep', {
        dry_run: true,
        auto_start: false,
        auto_dispatch_acceptance: false,
      }),
    )

    const firstCard = screen.getAllByTestId('scheduled-job-card')[0]
    fireEvent.click(within(firstCard).getByText('Run Now'))
    expect(await screen.findByRole('dialog', { name: /确认运行高影响任务/i })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '确认运行' }))
    expect(mockApi.runSchedule).toHaveBeenCalledWith('bug_log_sweep', {
      dry_run: false,
      auto_start: false,
      auto_dispatch_acceptance: false,
    })
  })
})
