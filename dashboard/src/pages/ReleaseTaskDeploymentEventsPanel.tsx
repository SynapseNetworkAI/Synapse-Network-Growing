import { useEffect, useState } from 'react'
import { ReleaseTask } from '../api'
import { getDeploymentEvents, type DeploymentEvent } from '../apiReleaseTasks'

function deploymentEventsShouldPoll(task: ReleaseTask | null) {
  if (!task?.deployment_record_id) return false
  const tokens = [task.status, task.deployment_status, task.deployment_health_status].map((value) => String(value || '').toLowerCase())
  return tokens.some((value) => ['requested', 'deploying', 'running', 'pending', 'checking'].includes(value))
}

function eventTone(eventType: string) {
  if (eventType === 'stderr') return 'text-[color:var(--ops-state-blocked-text)]'
  if (eventType === 'local_deploy_force_reset') return 'text-[color:var(--ops-state-running-text)]'
  if (eventType === 'step_started' || eventType === 'step_finished') return 'text-[color:var(--ops-text-title)]'
  return 'text-[color:var(--ops-text-muted)]'
}

export function ReleaseTaskDeploymentEventsPanel({
  task,
  onResetRunningDeployment,
}: Readonly<{
  task: ReleaseTask
  onResetRunningDeployment?: (
    task: ReleaseTask,
    payload: { confirm_phrase: string; reason: string },
  ) => Promise<void>
}>) {
  const [events, setEvents] = useState<DeploymentEvent[]>([])
  const [eventsCursor, setEventsCursor] = useState(0)
  const [eventsHasMore, setEventsHasMore] = useState(false)
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventsError, setEventsError] = useState<string | null>(null)
  const [resetConfirm, setResetConfirm] = useState('')
  const [resetReason, setResetReason] = useState('')
  const [resetBusy, setResetBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    const deploymentId = task.deployment_record_id
    setEvents([])
    setEventsCursor(0)
    setEventsHasMore(false)
    setEventsError(null)
    if (!deploymentId) return undefined

    const loadEvents = async (afterSequence: number) => {
      setEventsLoading(true)
      try {
        const page = await getDeploymentEvents(deploymentId, { after_sequence: afterSequence, limit: 200 })
        if (cancelled) return
        setEvents((current) => (afterSequence > 0 ? [...current, ...page.items] : page.items))
        setEventsCursor(page.next_sequence)
        setEventsHasMore(page.has_more)
        setEventsError(null)
      } catch (error) {
        if (!cancelled) setEventsError(error instanceof Error ? error.message : '读取部署日志失败')
      } finally {
        if (!cancelled) setEventsLoading(false)
      }
    }

    void loadEvents(0)
    if (!deploymentEventsShouldPoll(task)) return () => { cancelled = true }
    const timer = window.setInterval(() => {
      setEventsCursor((cursor) => {
        void loadEvents(cursor)
        return cursor
      })
    }, 3000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [task.deployment_record_id, task.status, task.deployment_status, task.deployment_health_status])

  const loadMoreEvents = async () => {
    if (!task.deployment_record_id || eventsLoading) return
    setEventsLoading(true)
    try {
      const page = await getDeploymentEvents(task.deployment_record_id, { after_sequence: eventsCursor, limit: 200 })
      setEvents((current) => [...current, ...page.items])
      setEventsCursor(page.next_sequence)
      setEventsHasMore(page.has_more)
      setEventsError(null)
    } catch (error) {
      setEventsError(error instanceof Error ? error.message : '读取部署日志失败')
    } finally {
      setEventsLoading(false)
    }
  }

  const reloadEvents = async () => {
    if (!task.deployment_record_id || eventsLoading) return
    setEventsLoading(true)
    try {
      const page = await getDeploymentEvents(task.deployment_record_id, { after_sequence: 0, limit: 200 })
      setEvents(page.items)
      setEventsCursor(page.next_sequence)
      setEventsHasMore(page.has_more)
      setEventsError(null)
    } catch (error) {
      setEventsError(error instanceof Error ? error.message : '读取部署日志失败')
    } finally {
      setEventsLoading(false)
    }
  }

  const canResetDeployment = Boolean(onResetRunningDeployment)
    && Boolean(task.deployment_record_id)
    && !['completed', 'cancelled'].includes(String(task.status || '').toLowerCase())
  const submitResetDeployment = async () => {
    if (!onResetRunningDeployment) return
    setResetBusy(true)
    try {
      await onResetRunningDeployment(task, {
        confirm_phrase: resetConfirm.trim(),
        reason: resetReason.trim() || 'Operator force reset local deploy attempt.',
      })
      setResetConfirm('')
      setResetReason('')
    } finally {
      setResetBusy(false)
    }
  }

  return (
    <>
      <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-3">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Local Runner Event Log</div>
            <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">Append-only stdout/stderr stream. Full messages are preserved.</div>
          </div>
          <button
            type="button"
            className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-1.5 text-xs"
            disabled={eventsLoading}
            onClick={() => void reloadEvents()}
          >
            {eventsLoading ? '读取中…' : '刷新日志'}
          </button>
        </div>
        {eventsError ? (
          <div className="mb-3 rounded-lg border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-3 py-2 text-xs text-[color:var(--ops-state-blocked-text)]">
            {eventsError}
          </div>
        ) : null}
        {events.length ? (
          <div className="max-h-80 overflow-auto rounded-lg bg-black/20 p-3 font-mono text-xs">
            {events.map((event) => (
              <div key={`${event.deployment_record_id}-${event.sequence}`} className="mb-2 whitespace-pre-wrap break-words">
                <span className="mr-2 text-[color:var(--ops-text-caption)]">#{event.sequence}</span>
                <span className={`mr-2 ${eventTone(event.event_type)}`}>{event.event_type}</span>
                {event.step_key ? <span className="mr-2 text-[color:var(--ops-text-caption)]">[{event.step_key}]</span> : null}
                <span className={eventTone(event.event_type)}>{event.message}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg bg-[color:var(--ops-panel-subtle)] px-3 py-2 text-sm text-[color:var(--ops-text-muted)]">
            暂无本地 runner 日志。启动本地 deploy runner 后，stdout / stderr 会以 append-only 事件流写入这里。
          </div>
        )}
        {eventsHasMore ? (
          <button
            type="button"
            className="mt-3 rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-1.5 text-xs"
            disabled={eventsLoading}
            onClick={() => void loadMoreEvents()}
          >
            加载更多日志
          </button>
        ) : null}
      </div>
      {canResetDeployment ? (
        <div className="rounded-xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-3">
          <div className="text-sm font-semibold text-[color:var(--ops-state-blocked-text)]">Force Reset Local Deploy</div>
          <div className="mt-1 text-xs text-[color:var(--ops-state-blocked-text)]">
            仅用于本地 runner 卡住或被 Kill 后恢复。旧日志不会删除；本次 DeploymentRecord 会保留为失败证据，任务回到待执行。
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-[1fr_1fr_auto]">
            <input
              className="rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-3 py-2 font-mono text-xs text-[color:var(--ops-text-title)]"
              value={resetConfirm}
              onChange={(event) => setResetConfirm(event.target.value)}
              placeholder="RESET_LOCAL_DEPLOY"
            />
            <input
              className="rounded-xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-3 py-2 text-xs text-[color:var(--ops-text-title)]"
              value={resetReason}
              onChange={(event) => setResetReason(event.target.value)}
              placeholder="reset reason"
            />
            <button
              type="button"
              className="rounded-xl border border-[color:var(--ops-state-blocked-border)] px-4 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
              disabled={resetBusy || resetConfirm.trim() !== 'RESET_LOCAL_DEPLOY'}
              onClick={submitResetDeployment}
            >
              {resetBusy ? '重置中…' : '重置为待执行'}
            </button>
          </div>
        </div>
      ) : null}
    </>
  )
}
