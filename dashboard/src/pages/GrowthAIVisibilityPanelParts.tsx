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
