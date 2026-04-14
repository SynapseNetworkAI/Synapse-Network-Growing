import type { ReactNode } from 'react'

type Tone = 'default' | 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted'

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

const badgeToneClasses: Record<Tone, string> = {
  default: 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] text-[color:var(--ops-text-body)]',
  ready: 'border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] text-[color:var(--ops-state-ready-text)]',
  running: 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]',
  blocked: 'border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] text-[color:var(--ops-state-blocked-text)]',
  validating: 'border-[color:var(--ops-state-validating-border)] bg-[color:var(--ops-state-validating-bg)] text-[color:var(--ops-state-validating-text)]',
  delivered: 'border-[color:var(--ops-state-delivered-border)] bg-[color:var(--ops-state-delivered-bg)] text-[color:var(--ops-state-delivered-text)]',
  muted: 'border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] text-[color:var(--ops-text-muted)]',
}

export function StateBadge({
  children,
  tone = 'muted',
  className,
}: Readonly<{ children: ReactNode; tone?: Tone; className?: string }>) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-[0.16em]',
        badgeToneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

export function SectionFrame({
  eyebrow,
  title,
  description,
  actions,
  children,
  className,
}: Readonly<{
  eyebrow?: string
  title?: string
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}>) {
  return (
    <section
      className={cx(
        'ops-section-frame rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-5 md:px-6',
        className,
      )}
    >
      {(eyebrow || title || description || actions) && (
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] pb-4">
          <div className="max-w-3xl">
            {eyebrow ? <div className="text-[11px] uppercase tracking-[0.24em] text-[color:var(--ops-text-caption)]">{eyebrow}</div> : null}
            {title ? <h2 className="mt-2 text-xl font-semibold tracking-tight text-[color:var(--ops-text-title)] md:text-2xl">{title}</h2> : null}
            {description ? <div className="mt-2 text-sm leading-6 text-[color:var(--ops-text-muted)]">{description}</div> : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      )}
      {children}
    </section>
  )
}

export function InspectorRail({
  eyebrow,
  title,
  children,
  className,
}: Readonly<{
  eyebrow?: string
  title?: string
  children: ReactNode
  className?: string
}>) {
  return (
    <aside
      className={cx(
        'rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] px-5 py-5',
        className,
      )}
    >
      {eyebrow ? <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">{eyebrow}</div> : null}
      {title ? <h3 className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{title}</h3> : null}
      <div className={cx(title || eyebrow ? 'mt-4' : '', 'space-y-4 text-sm text-[color:var(--ops-text-body)]')}>{children}</div>
    </aside>
  )
}

export function ActivityFeed({
  eyebrow,
  title,
  children,
}: Readonly<{
  eyebrow?: string
  title?: string
  children: ReactNode
}>) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] px-5 py-5">
      {eyebrow ? <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">{eyebrow}</div> : null}
      {title ? <h3 className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{title}</h3> : null}
      <div className={cx(title || eyebrow ? 'mt-4' : '', 'space-y-3')}>{children}</div>
    </section>
  )
}

export function LoadingPane({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="rounded-[var(--ops-radius-panel)] border border-dashed border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] px-6 py-8 text-sm text-[color:var(--ops-text-muted)]">
      {children}
    </div>
  )
}

export function EmptyPane({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="rounded-[var(--ops-radius-panel)] border border-dashed border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] px-6 py-8 text-sm text-[color:var(--ops-text-muted)]">
      {children}
    </div>
  )
}

export function FieldLabel({ children }: Readonly<{ children: ReactNode }>) {
  return <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{children}</div>
}
