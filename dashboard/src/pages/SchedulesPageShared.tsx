import { RecurringWorkflow } from '../api'

export interface ScheduleJsonObject {
  [key: string]: unknown
}

export function recordFrom(value: unknown): ScheduleJsonObject {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as ScheduleJsonObject : {}
}

export function tone(value: string) {
  if (['healthy', 'succeeded', 'completed', 'active'].includes(value)) return 'ready'
  if (['due', 'running'].includes(value)) return 'running'
  if (['failed', 'error', 'dead_letter'].includes(value)) return 'blocked'
  return 'muted'
}

export function scheduleLabel(workflow: RecurringWorkflow) {
  const schedule = workflow.schedule || {}
  const cadence = String(schedule.cadence || '-')
  if (cadence === 'interval') return `Every ${String(schedule.interval_minutes || '?')} min`
  if (cadence === 'hourly') return `Every ${String(schedule.interval_hours || '?')} h`
  if (cadence === 'daily') return `Daily ${String(schedule.suggested_local_time || '')}`.trim()
  if (cadence === 'weekly') return `Weekly ${String(schedule.day || '')} ${String(schedule.suggested_local_time || '')}`.trim()
  return cadence
}

export function copyJson(value: unknown) {
  const text = JSON.stringify(value ?? {}, null, 2)
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    void navigator.clipboard.writeText(text)
  }
}

export function JsonBlock({ value }: Readonly<{ value: unknown }>) {
  const text = JSON.stringify(value ?? {}, null, 2)
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <span className="machine-label text-slate-400">JSON</span>
        <button
          type="button"
          className="rounded-lg border border-white/12 px-2 py-1 text-xs font-semibold text-slate-200 hover:bg-white/10"
          onClick={() => copyJson(value)}
        >
          Copy JSON
        </button>
      </div>
      <pre className="max-h-[360px] overflow-auto p-4 text-xs leading-relaxed text-slate-100">
        {text}
      </pre>
    </div>
  )
}
