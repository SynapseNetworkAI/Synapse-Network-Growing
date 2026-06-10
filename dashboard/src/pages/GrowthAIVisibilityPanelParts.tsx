import { StateBadge } from '../components/workbench'
import type { GrowthAIVisibilitySourceHostAction } from '../apiGrowthAiVisibility'

export function EvidenceList({ title, empty, items, className = '' }: Readonly<{ title: string; empty: string; items: string[]; className?: string }>) {
  const visibleItems = items.slice(0, 9)
  return (
    <div className={`rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2 ${className}`}>
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{title}</div>
      <div className="mt-2 space-y-2">
        {visibleItems.length ? (
          visibleItems.map((item) => (
            <div key={item} className="text-sm leading-5 text-[color:var(--ops-text-muted)]">
              {item}
            </div>
          ))
        ) : (
          <div className="text-sm leading-5 text-[color:var(--ops-text-muted)]">{empty}</div>
        )}
      </div>
    </div>
  )
}

function priorityTone(priority: string) {
  return priority === 'p0' ? 'blocked' : priority === 'p1' ? 'running' : 'muted'
}

export function SourceHostActionList({ actions }: Readonly<{ actions: GrowthAIVisibilitySourceHostAction[] }>) {
  if (!actions.length) return null
  return (
    <div className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-3 py-3" data-testid="ai-visibility-source-host-actions">
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">Source-host action targets</div>
      <div className="mt-3 space-y-2">
        {actions.slice(0, 4).map((action) => (
          <div key={`${action.host}-${action.surface}-${action.draft_type}`} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-mono text-sm text-[color:var(--ops-text-title)]">{action.host}</div>
              <div className="flex flex-wrap items-center gap-2">
                <StateBadge tone={priorityTone(action.priority)}>{action.priority}</StateBadge>
                <span className="text-xs text-[color:var(--ops-text-caption)]">{action.observed_count}x</span>
              </div>
            </div>
            <div className="mt-1 text-xs leading-5 text-[color:var(--ops-text-caption)]">
              {action.surface} · {action.draft_type}
            </div>
            <div className="mt-2 text-sm leading-5 text-[color:var(--ops-text-muted)]">{action.rationale}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function CommandBlock({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-1 break-words text-xs leading-5 text-[color:var(--ops-text-muted)]">{value}</div>
    </div>
  )
}

export function CommandList({ label, commands }: Readonly<{ label: string; commands: string[] }>) {
  return (
    <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 space-y-2">
        {commands.length ? (
          commands.slice(0, 6).map((command) => (
            <div key={command} className="break-words text-xs leading-5 text-[color:var(--ops-text-muted)]">
              {command}
            </div>
          ))
        ) : (
          <div className="text-sm leading-5 text-[color:var(--ops-text-muted)]">-</div>
        )}
      </div>
    </div>
  )
}

export function Info({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 text-sm text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  )
}

export function signed(value: number) {
  return value > 0 ? `+${value}` : String(value)
}
