import type { ReactNode } from 'react'
import { StateBadge } from './workbench'

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted'

const toneClasses: Record<Tone, string> = {
  default: 'border-[color:var(--ops-glass-border)] bg-[color:var(--ops-panel)] text-[color:var(--ops-text-body)]',
  success: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-200',
  warning: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  danger: 'border-rose-400/25 bg-rose-400/10 text-rose-200',
  info: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
  muted: 'border-white/8 bg-white/[0.03] text-[color:var(--ops-text-muted)]',
}

export function CockpitPanel({
  eyebrow,
  title,
  description,
  actions,
  children,
  className = '',
}: Readonly<{
  eyebrow?: string
  title?: string
  description?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}>) {
  return (
    <section className={`cockpit-panel ${className}`}>
      {(eyebrow || title || description || actions) ? (
        <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            {eyebrow ? <div className="machine-label text-[color:var(--ops-text-caption)]">{eyebrow}</div> : null}
            {title ? <h2 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-[color:var(--ops-text-title)] md:text-2xl">{title}</h2> : null}
            {description ? <div className="mt-2 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{description}</div> : null}
          </div>
          {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

export function MetricTile({
  label,
  value,
  detail,
  tone = 'default',
}: Readonly<{
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: Tone
}>) {
  return (
    <div className={`rounded-2xl border px-4 py-4 ${toneClasses[tone]}`}>
      <div className="machine-label opacity-80">{label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-[color:var(--ops-text-title)]">{value}</div>
      {detail ? <div className="mt-2 text-xs leading-5 text-[color:var(--ops-text-muted)]">{detail}</div> : null}
    </div>
  )
}

export function AgentReasoningCard({
  title,
  summary,
  metadata,
  tone = 'info',
}: Readonly<{
  title: string
  summary: ReactNode
  metadata?: ReactNode
  tone?: Tone
}>) {
  return (
    <div className={`reasoning-card ${tone === 'danger' ? 'reasoning-card-danger' : tone === 'warning' ? 'reasoning-card-warning' : ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="machine-label text-[color:var(--ops-text-caption)]">Agent Output</div>
          <h3 className="mt-2 text-base font-semibold text-[color:var(--ops-text-title)]">{title}</h3>
        </div>
        <StateBadge tone={tone === 'danger' ? 'blocked' : tone === 'warning' ? 'validating' : 'running'}>{tone}</StateBadge>
      </div>
      <div className="mt-3 text-sm leading-6 text-[color:var(--ops-text-body)]">{summary}</div>
      {metadata ? <div className="mt-4 border-t border-white/8 pt-3 text-xs text-[color:var(--ops-text-muted)]">{metadata}</div> : null}
    </div>
  )
}

export function EmptyCockpitState({
  title,
  description,
  actions,
}: Readonly<{
  title: string
  description: ReactNode
  actions?: ReactNode
}>) {
  return (
    <div className="rounded-3xl border border-dashed border-white/14 bg-white/[0.025] px-6 py-10">
      <div className="machine-label text-[color:var(--ops-text-caption)]">Empty State</div>
      <h3 className="mt-3 text-xl font-semibold text-[color:var(--ops-text-title)]">{title}</h3>
      <div className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{description}</div>
      {actions ? <div className="mt-6 flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  )
}

export function ActionButton({
  children,
  onClick,
  href,
  tone = 'default',
}: Readonly<{
  children: ReactNode
  onClick?: () => void
  href?: string
  tone?: 'default' | 'primary' | 'danger'
}>) {
  const className = [
    'inline-flex items-center justify-center rounded-xl border px-4 py-2.5 text-sm font-semibold transition',
    tone === 'primary'
      ? 'border-cyan-300/30 bg-cyan-300/15 text-cyan-100 hover:bg-cyan-300/22'
      : tone === 'danger'
        ? 'border-rose-300/30 bg-rose-400/15 text-rose-100 hover:bg-rose-400/22'
        : 'border-white/12 bg-white/[0.04] text-[color:var(--ops-text-body)] hover:bg-white/[0.08]',
  ].join(' ')
  if (href) {
    return (
      <a className={className} href={href}>
        {children}
      </a>
    )
  }
  return (
    <button type="button" className={className} onClick={onClick}>
      {children}
    </button>
  )
}
