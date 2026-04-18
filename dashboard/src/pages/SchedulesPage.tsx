import { useEffect, useState } from 'react'
import { api, RecurringWorkflow, RecurringWorkflowHealth, RecurringWorkflowRun } from '../api'

function formatTime(value: string | null | undefined) {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

function tone(value: string) {
  if (['healthy', 'succeeded', 'completed', 'active'].includes(value)) return 'border-emerald-200 bg-emerald-50 text-emerald-700'
  if (['due', 'running'].includes(value)) return 'border-blue-200 bg-blue-50 text-blue-700'
  if (['failed', 'error', 'dead_letter'].includes(value)) return 'border-rose-200 bg-rose-50 text-rose-700'
  return 'border-slate-200 bg-slate-50 text-slate-600'
}

function JsonBlock({ value }: Readonly<{ value: unknown }>) {
  return (
    <pre className="max-h-[360px] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-relaxed text-slate-100">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  )
}

function scheduleLabel(workflow: RecurringWorkflow) {
  const schedule = workflow.schedule || {}
  const cadence = String(schedule.cadence || '-')
  if (cadence === 'interval') return `Every ${String(schedule.interval_minutes || '?')} min`
  if (cadence === 'hourly') return `Every ${String(schedule.interval_hours || '?')} h`
  if (cadence === 'daily') return `Daily ${String(schedule.suggested_local_time || '')}`.trim()
  if (cadence === 'weekly') return `Weekly ${String(schedule.day || '')} ${String(schedule.suggested_local_time || '')}`.trim()
  return cadence
}

function HealthCard({ title, data }: Readonly<{ title: string; data: Record<string, unknown> }>) {
  const status = data.running === true || data.enabled === true ? 'running' : 'inactive'
  return (
    <div className="rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-white p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Health</div>
          <div className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{title}</div>
        </div>
        <span className={['rounded-full border px-3 py-1 text-xs font-medium', tone(status)].join(' ')}>{status}</span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs text-[color:var(--ops-text-muted)]">
        {Object.entries(data).slice(0, 8).map(([key, value]) => (
          <div key={key} className="rounded-2xl bg-slate-50 px-3 py-2">
            <div className="font-mono text-[10px] text-[color:var(--ops-text-caption)]">{key}</div>
            <div className="mt-1 truncate">{String(value ?? '-')}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function SchedulesPage() {
  const [items, setItems] = useState<RecurringWorkflow[]>([])
  const [health, setHealth] = useState<RecurringWorkflowHealth | null>(null)
  const [selected, setSelected] = useState<RecurringWorkflow | null>(null)
  const [runs, setRuns] = useState<RecurringWorkflowRun[]>([])
  const [loading, setLoading] = useState(true)
  const [runningKey, setRunningKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const [nextItems, nextHealth] = await Promise.all([
        api.getRecurringWorkflows(),
        api.getRecurringWorkflowHealth(),
      ])
      setItems(nextItems)
      setHealth(nextHealth)
      if (!selected && nextItems.length) setSelected(nextItems[0])
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载定时任务失败')
    } finally {
      setLoading(false)
    }
  }

  async function loadRuns(workflowKey: string) {
    setRuns(await api.getRecurringWorkflowRuns(workflowKey, 50))
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  useEffect(() => {
    if (selected) loadRuns(selected.workflow_key).catch(() => {})
  }, [selected?.workflow_key])

  async function runWorkflow(workflow: RecurringWorkflow, dryRun: boolean) {
    const risky = ['bug_log_sweep', 'morning_intake_sweep'].includes(workflow.workflow_key)
    if (!dryRun && risky) {
      const confirmed = window.confirm(`${workflow.display_name} 可能创建或复用 requirement。默认不会 auto-start，确认现在运行吗？`)
      if (!confirmed) return
    }
    setRunningKey(workflow.workflow_key)
    setError(null)
    try {
      await api.runRecurringWorkflow(workflow.workflow_key, {
        dry_run: dryRun,
        auto_start: false,
        auto_dispatch_acceptance: false,
      })
      await load()
      setSelected(workflow)
      await loadRuns(workflow.workflow_key)
    } catch (err) {
      setError(err instanceof Error ? err.message : '运行定时任务失败')
    } finally {
      setRunningKey(null)
    }
  }

  const stats = {
    total: items.length,
    active: items.filter((item) => item.status === 'active').length,
    due: items.filter((item) => item.is_due).length,
    failed: items.filter((item) => item.health_status === 'failed').length,
  }

  return (
    <div className="space-y-5" data-testid="schedules-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Scheduled Jobs</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">定时任务</h2>
            <p className="mt-2 text-sm text-[color:var(--ops-text-muted)]">查看后台机制、手动 dry run / run now，并追踪最近运行历史。</p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
            刷新
          </button>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <section className="grid gap-3 md:grid-cols-4">
        {Object.entries(stats).map(([label, value]) => (
          <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-white px-4 py-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
            <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
          </div>
        ))}
      </section>

      {health ? (
        <section className="grid gap-4 xl:grid-cols-3" data-testid="schedule-health-overview">
          <HealthCard title="Bug Log Scheduler" data={health.bug_log_scheduler} />
          <HealthCard title="Notification Dispatcher" data={health.notification_dispatcher} />
          <HealthCard title="Recurring Registry" data={health.recurring_registry} />
        </section>
      ) : null}

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <div className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
          <div className="border-b border-[color:var(--ops-stroke-soft)] px-5 py-4">
            <div className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Registry</div>
            <h3 className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">Recurring Workflow Registry</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <thead className="bg-slate-50/90">
                <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                  <th className="px-5 py-4 font-medium">任务</th>
                  <th className="px-4 py-4 font-medium">Owner</th>
                  <th className="px-4 py-4 font-medium">Schedule</th>
                  <th className="px-4 py-4 font-medium">Health</th>
                  <th className="px-4 py-4 font-medium">Last / Next</th>
                  <th className="px-5 py-4 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.workflow_key} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-slate-50/80">
                    <td className="px-5 py-4">
                      <button type="button" className="text-left" onClick={() => setSelected(item)}>
                        <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{item.display_name}</div>
                        <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.workflow_key}</div>
                        <div className="mt-1 max-w-[320px] text-xs text-[color:var(--ops-text-muted)]">{item.description}</div>
                      </button>
                    </td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.owner_role}</td>
                    <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">{scheduleLabel(item)}</td>
                    <td className="px-4 py-4">
                      <span className={['rounded-full border px-3 py-1 text-xs font-medium', tone(item.health_status)].join(' ')}>{item.health_status}</span>
                    </td>
                    <td className="px-4 py-4 text-xs text-[color:var(--ops-text-muted)]">
                      <div>last: {formatTime(item.last_run_at)}</div>
                      <div className="mt-1">next: {formatTime(item.next_run_at)}</div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-xs" onClick={() => runWorkflow(item, true)} disabled={runningKey === item.workflow_key}>
                          Dry Run
                        </button>
                        <button type="button" className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50" onClick={() => runWorkflow(item, false)} disabled={runningKey === item.workflow_key}>
                          Run Now
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && !items.length ? (
                  <tr>
                    <td className="px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]" colSpan={6}>暂无 recurring workflow。</td>
                  </tr>
                ) : null}
                {loading ? (
                  <tr>
                    <td className="px-5 py-8 text-center text-sm text-[color:var(--ops-text-muted)]" colSpan={6}>加载中…</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <aside className="space-y-4">
          <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Run History</div>
            <h3 className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">{selected?.display_name || '选择一个任务'}</h3>
            <div className="mt-4 space-y-3">
              {runs.map((run) => (
                <details key={run.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4" data-testid="schedule-run-history-item">
                  <summary className="cursor-pointer">
                    <div className="inline-flex items-center gap-2">
                      <span className={['rounded-full border px-3 py-1 text-xs font-medium', tone(run.status)].join(' ')}>{run.status}</span>
                      <span className="text-xs text-[color:var(--ops-text-muted)]">#{run.id} · {run.dry_run ? 'dry run' : run.triggered_by} · {run.duration_ms}ms</span>
                    </div>
                    <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{formatTime(run.started_at)}</div>
                  </summary>
                  <div className="mt-4 space-y-3">
                    {run.error_excerpt ? <div className="rounded-xl bg-rose-50 p-3 text-xs text-rose-700">{run.error_excerpt}</div> : null}
                    <details>
                      <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Params</summary>
                      <div className="mt-2"><JsonBlock value={run.params} /></div>
                    </details>
                    <details>
                      <summary className="cursor-pointer text-sm font-semibold text-[color:var(--ops-text-title)]">Result</summary>
                      <div className="mt-2"><JsonBlock value={run.result} /></div>
                    </details>
                  </div>
                </details>
              ))}
              {selected && !runs.length ? <div className="text-sm text-[color:var(--ops-text-muted)]">暂无运行历史。</div> : null}
            </div>
          </div>

          {selected ? (
            <div className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white p-5">
              <div className="text-[11px] uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Result Inspector</div>
              <h3 className="mt-1 text-lg font-semibold text-[color:var(--ops-text-title)]">Last Result</h3>
              <div className="mt-4"><JsonBlock value={selected.last_result} /></div>
            </div>
          ) : null}
        </aside>
      </section>
    </div>
  )
}
