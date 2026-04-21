// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
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

function workflow(overrides: Record<string, unknown>) {
  return {
    id: 1,
    workflow_key: 'bug_log_sweep',
    display_name: 'Bug Log Sweep',
    description: 'Scan bug logs',
    owner_role: 'reliability',
    trigger_type: 'scheduled',
    schedule: { cadence: 'interval', interval_minutes: 5 },
    input_query: { sources: ['runtime_log_error'] },
    output_action: { kind: 'update_bug_backlog' },
    escalation_rule: {},
    validation_signal: { success_metric: 'materialized_requirement_ids' },
    is_builtin: true,
    status: 'active',
    last_run_at: '2026-04-18T00:00:00Z',
    last_result: { materialized_requirement_ids: [8], status: 'ok' },
    created_at: '2026-04-18T00:00:00Z',
    updated_at: '2026-04-18T00:00:00Z',
    next_run_at: '2026-04-18T01:00:00Z',
    is_due: false,
    health_status: 'healthy',
    ...overrides,
  }
}

const health = {
  bug_log_scheduler: { enabled: true, running: true, last_error: null },
  notification_dispatcher: { enabled: true, running: true, queued_count: 0 },
  recurring_registry: { total: 4, active: 4, due: 1, failed: 1 },
}

const runs = [
  {
    id: 12,
    workflow_key: 'bug_log_sweep',
    status: 'succeeded',
    triggered_by: 'operator',
    dry_run: true,
    params: { dry_run: true },
    result: { materialized_requirement_ids: [8], status: 'dry_run' },
    error_excerpt: null,
    started_at: '2026-04-18T00:00:00Z',
    completed_at: '2026-04-18T00:00:01Z',
    duration_ms: 1000,
  },
]

describe('SchedulesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiMock.getRecurringWorkflows.mockResolvedValue([
      workflow({ workflow_key: 'goal_planner_sweep', display_name: 'Goal Planner Sweep', owner_role: 'portfolio_planner', is_due: true, health_status: 'due', next_run_at: '2020-01-01T00:00:00Z' }),
      workflow({ workflow_key: 'forum_feedback_sweep', display_name: 'Forum Feedback Sweep', owner_role: 'support_triage_agent' }),
      workflow({ workflow_key: 'ci_status_sweep', display_name: 'CI Status Sweep', owner_role: 'runtime_reliability_engineer' }),
      workflow({ workflow_key: 'bug_log_sweep', display_name: 'Bug Log Sweep', owner_role: 'runtime_reliability_engineer', health_status: 'failed', last_result: { status: 'failed', reason: 'log parser failed' } }),
      workflow({ workflow_key: 'new_unknown_sweep', display_name: 'New Unknown Sweep', owner_role: 'operator', input_query: { source: 'custom' }, output_action: { kind: 'custom_output' }, validation_signal: { success_metric: 'custom_metric' } }),
    ])
    apiMock.getRecurringWorkflowHealth.mockResolvedValue(health)
    apiMock.getRecurringWorkflowRuns.mockResolvedValue(runs)
    apiMock.runRecurringWorkflow.mockResolvedValue({
      workflow_key: 'bug_log_sweep',
      status: 'completed',
      run_started_at: '2026-04-18T00:00:00Z',
      run_id: 12,
      result: { dry_run: true },
    })
  })

  it('groups recurring workflows by operating domain with attention and uncategorized lanes', async () => {
    render(<SchedulesPage />)

    expect(await screen.findByText('定时任务')).toBeTruthy()
    expect(screen.getByText(/Attention Required/)).toBeTruthy()
    expect(screen.getByText(/Strategy & Planning/)).toBeTruthy()
    expect(screen.getByText(/Intake & Support/)).toBeTruthy()
    expect(screen.getByText(/System Health & Reliability/)).toBeTruthy()
    expect(screen.getByText(/New \/ Uncategorized Initiates/)).toBeTruthy()
    expect(screen.getAllByText('Missing Presentation Metadata').length).toBeGreaterThan(0)
  })

  it('shows compact input action output for scheduled job cards', async () => {
    render(<SchedulesPage />)

    expect((await screen.findAllByText('Active goals + Operating Manifest')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Planner Agent 拆解目标').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Requirement Candidates | Fail-Closed Intercepts').length).toBeGreaterThan(0)
    expect(screen.getAllByTestId('schedule-compact-ipo').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Show definition').length).toBeGreaterThan(0)
    expect(screen.getByText('Final Regression 收口')).toBeTruthy()
    expect(screen.getAllByText('awaiting_ci workflow runs').length).toBeGreaterThan(0)
  })

  it('marks overdue jobs with delayed duration and likely reason', async () => {
    render(<SchedulesPage />)

    expect(await screen.findByText('OVERDUE')).toBeTruthy()
    expect(screen.getByTestId('schedule-overdue-alert').textContent).toContain('Delayed')
    expect(screen.getByTestId('schedule-overdue-alert').textContent).toContain('Scheduler tick missed after next_run_at')
  })

  it('opens run inspector from last run and keeps raw JSON collapsed', async () => {
    const user = userEvent.setup()
    render(<SchedulesPage />)

    const lastRunButtons = await screen.findAllByRole('button', { name: /Last Run/i })
    await user.click(lastRunButtons[0])

    const inspector = await screen.findByTestId('schedule-run-inspector')
    expect(within(inspector).getByRole('button', { name: 'Run History' })).toBeTruthy()
    expect(within(inspector).getByRole('button', { name: 'Configuration' })).toBeTruthy()
    expect(apiMock.getRecurringWorkflowRuns).toHaveBeenCalledWith(expect.any(String), 50)
    expect(within(inspector).getAllByText(/materialized_requirement_ids/).length).toBeGreaterThan(0)
    expect(within(inspector).getByText('Debug params / result JSON')).toBeTruthy()
    expect(within(inspector).getAllByText('Copy JSON').length).toBeGreaterThan(0)
    expect(within(inspector).getByText(/#12/)).toBeTruthy()
  })

  it('opens history drawer immediately while run action is still pending', async () => {
    const user = userEvent.setup()
    let resolveRun: (value: unknown) => void = () => {}
    apiMock.runRecurringWorkflow.mockReturnValue(new Promise((resolve) => { resolveRun = resolve }))
    render(<SchedulesPage />)

    expect((await screen.findAllByText('Bug Log Sweep')).length).toBeGreaterThan(0)
    await user.click(screen.getAllByRole('button', { name: 'View History' })[0])
    await user.click(await screen.findByRole('button', { name: 'Configuration' }))
    await user.click(screen.getByRole('button', { name: 'Dry Run' }))

    const inspector = await screen.findByTestId('schedule-run-inspector')
    expect(within(inspector).getAllByText('Running...').length).toBeGreaterThan(0)
    expect(within(inspector).getAllByText('DRY RUN').length).toBeGreaterThan(0)
    expect(within(inspector).getByText('Sandbox preview only. No auto-start or acceptance dispatch.')).toBeTruthy()
    resolveRun({
      workflow_key: 'goal_planner_sweep',
      status: 'completed',
      run_started_at: '2026-04-18T00:00:00Z',
      run_id: 12,
      result: {},
    })
  })

  it('runs dry run with safe defaults and opens the created run inspector', async () => {
    const user = userEvent.setup()
    render(<SchedulesPage />)

    expect((await screen.findAllByText('Bug Log Sweep')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Dry Run' })).toBeNull()
    await user.click(screen.getAllByRole('button', { name: 'View History' })[0])
    await user.click(await screen.findByRole('button', { name: 'Configuration' }))
    await user.click(screen.getByRole('button', { name: 'Dry Run' }))

    await waitFor(() => {
      expect(apiMock.runRecurringWorkflow).toHaveBeenCalledWith(expect.any(String), {
        dry_run: true,
        auto_start: false,
        auto_dispatch_acceptance: false,
      })
    })
    const inspector = await screen.findByTestId('schedule-run-inspector')
    expect(within(inspector).getAllByText('DRY RUN').length).toBeGreaterThan(0)
    expect(within(inspector).getByText('Sandbox preview only. No auto-start or acceptance dispatch.')).toBeTruthy()
  })

  it('reruns selected history with safe params instead of raw payload replay', async () => {
    const user = userEvent.setup()
    render(<SchedulesPage />)

    const lastRunButtons = await screen.findAllByRole('button', { name: /Last Run/i })
    await user.click(lastRunButtons[0])
    await user.click(await screen.findByRole('button', { name: 'Re-run with this context' }))

    await waitFor(() => {
      expect(apiMock.runRecurringWorkflow).toHaveBeenCalledWith(expect.any(String), {
        dry_run: true,
        auto_start: false,
        auto_dispatch_acceptance: false,
      })
    })
  })

  it('refreshes run history and falls back when the selected run leaves the latest 50', async () => {
    const user = userEvent.setup()
    apiMock.getRecurringWorkflowRuns
      .mockResolvedValueOnce(runs)
      .mockResolvedValueOnce([{ ...runs[0], id: 99, dry_run: false, status: 'succeeded', result: { created_requirement_ids: [99] } }])
    render(<SchedulesPage />)

    const lastRunButtons = await screen.findAllByRole('button', { name: /Last Run/i })
    await user.click(lastRunButtons[0])
    expect(await screen.findByText(/#12/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(await screen.findByText(/#99/)).toBeTruthy()
  })

  it('locks the running card while Run Now is in flight', async () => {
    const user = userEvent.setup()
    let resolveRun: (value: unknown) => void = () => {}
    apiMock.runRecurringWorkflow.mockReturnValue(new Promise((resolve) => { resolveRun = resolve }))
    render(<SchedulesPage />)

    expect((await screen.findAllByText('Bug Log Sweep')).length).toBeGreaterThan(0)
    const runNowButtons = screen.getAllByRole('button', { name: 'Run Now' })
    await user.click(runNowButtons[0])

    expect((await screen.findAllByText('Running...')).length).toBeGreaterThan(0)
    expect(runNowButtons[0]).toBeDisabled()
    resolveRun({
      workflow_key: 'goal_planner_sweep',
      status: 'completed',
      run_started_at: '2026-04-18T00:00:00Z',
      run_id: 12,
      result: {},
    })
  })
})
