import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

type Tone = 'default' | 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted'
type ConfirmTone = 'default' | 'destructive'
type ToastTone = 'success' | 'error' | 'info'

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

const toastToneClasses: Record<ToastTone, string> = {
  success: 'border-[color:var(--ops-state-ready-border)] bg-[color:var(--ops-state-ready-bg)] text-[color:var(--ops-state-ready-text)]',
  error: 'border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] text-[color:var(--ops-state-blocked-text)]',
  info: 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]',
}

type ToastItem = {
  id: number
  tone: ToastTone
  message: string
}

type ToastContextValue = {
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

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

export function ToastProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const pushToast = useCallback((tone: ToastTone, message: string) => {
    setToasts((current) => [...current, { id: Date.now() + Math.random(), tone, message }])
  }, [])

  const api = useMemo<ToastContextValue>(
    () => ({
      success: (message) => pushToast('success', message),
      error: (message) => pushToast('error', message),
      info: (message) => pushToast('info', message),
    }),
    [pushToast],
  )

  useEffect(() => {
    if (!toasts.length) return
    const timer = window.setTimeout(() => {
      setToasts((current) => current.slice(1))
    }, 2800)
    return () => window.clearTimeout(timer)
  }, [toasts])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed right-5 top-5 z-[70] flex w-[min(360px,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cx(
              'rounded-2xl border px-4 py-3 text-sm font-medium shadow-[0_18px_60px_rgba(15,23,42,0.12)] backdrop-blur-xl',
              toastToneClasses[toast.tone],
            )}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (context) return context
  return {
    success: () => {},
    error: () => {},
    info: () => {},
  }
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

export function WorkbenchToolbar({
  children,
  className,
}: Readonly<{
  children: ReactNode
  className?: string
}>) {
  return (
    <div
      className={cx(
        'flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--ops-stroke-soft)] pb-4',
        className,
      )}
    >
      {children}
    </div>
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

export function SelectionInspector({
  eyebrow,
  title,
  empty,
  active,
  className,
}: Readonly<{
  eyebrow?: string
  title?: string
  empty: ReactNode
  active?: ReactNode
  className?: string
}>) {
  return (
    <InspectorRail eyebrow={eyebrow} title={title} className={className}>
      {active ?? <div className="leading-6 text-[color:var(--ops-text-muted)]">{empty}</div>}
    </InspectorRail>
  )
}

export function OverlayDrawer({
  open,
  eyebrow,
  title,
  description,
  actions,
  onClose,
  children,
}: Readonly<{
  open: boolean
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
  onClose: () => void
  children: ReactNode
}>) {
  return (
    <div
      className={cx(
        'pointer-events-none fixed inset-0 z-40 transition-opacity duration-200',
        open ? 'opacity-100' : 'opacity-0',
      )}
      aria-hidden={!open}
    >
      <button
        type="button"
        aria-label="关闭抽屉"
        className={cx(
          'absolute inset-0 bg-slate-950/20 transition-opacity duration-200',
          open ? 'pointer-events-auto opacity-100' : 'opacity-0',
        )}
        onClick={onClose}
      />
      <aside
        className={cx(
          'absolute right-0 top-0 flex h-full w-full max-w-[720px] flex-col border-l border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] shadow-[0_20px_60px_rgba(15,23,42,0.18)] backdrop-blur-xl',
          open ? 'pointer-events-auto' : 'pointer-events-none',
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-6 py-5">
          <div className="min-w-0 flex-1">
            {eyebrow ? <div className="text-[11px] uppercase tracking-[0.24em] text-[color:var(--ops-text-caption)]">{eyebrow}</div> : null}
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{title}</h2>
            {description ? <div className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{description}</div> : null}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]"
              onClick={onClose}
            >
              关闭
            </button>
          </div>
        </div>
        {actions ? (
          <div className="flex shrink-0 justify-start gap-2 border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] px-6 py-4">
            {actions}
          </div>
        ) : null}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">{children}</div>
      </aside>
    </div>
  )
}

export function OverlayModal({
  open,
  eyebrow,
  title,
  description,
  actions,
  onClose,
  children,
}: Readonly<{
  open: boolean
  eyebrow?: string
  title: string
  description?: ReactNode
  actions?: ReactNode
  onClose: () => void
  children: ReactNode
}>) {
  return (
    <div
      className={cx(
        'pointer-events-none fixed inset-0 z-40 transition-opacity duration-200',
        open ? 'opacity-100' : 'opacity-0',
      )}
      aria-hidden={!open}
    >
      <button
        type="button"
        aria-label="关闭浮层"
        className={cx(
          'absolute inset-0 bg-slate-950/32 backdrop-blur-[2px] transition-opacity duration-200',
          open ? 'pointer-events-auto opacity-100' : 'opacity-0',
        )}
        onClick={onClose}
      />
      <div className="absolute inset-0 flex items-center justify-center p-4 md:p-8">
        <section
          role="dialog"
          aria-modal="true"
          aria-label={title}
          className={cx(
            'w-full max-w-[980px] translate-y-6 rounded-[calc(var(--ops-radius-shell)-4px)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] shadow-[0_28px_90px_rgba(15,23,42,0.24)] backdrop-blur-xl transition duration-200',
            open ? 'pointer-events-auto translate-y-0' : '',
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-6 py-5">
            <div className="min-w-0">
              {eyebrow ? <div className="text-[11px] uppercase tracking-[0.24em] text-[color:var(--ops-text-caption)]">{eyebrow}</div> : null}
              <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{title}</h2>
              {description ? <div className="mt-2 max-w-2xl text-sm leading-6 text-[color:var(--ops-text-muted)]">{description}</div> : null}
            </div>
            <div className="flex items-center gap-2">
              {actions}
              <button
                type="button"
                className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm text-[color:var(--ops-text-body)]"
                onClick={onClose}
              >
                关闭
              </button>
            </div>
          </div>
          <div className="max-h-[calc(100vh-12rem)] overflow-y-auto px-6 py-6">{children}</div>
        </section>
      </div>
    </div>
  )
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  cancelLabel = '取消',
  tone = 'default',
  loading = false,
  onConfirm,
  onClose,
}: Readonly<{
  open: boolean
  title: string
  description?: ReactNode
  confirmLabel?: string
  cancelLabel?: string
  tone?: ConfirmTone
  loading?: boolean
  onConfirm: () => void
  onClose: () => void
}>) {
  return (
    <div
      className={cx(
        'pointer-events-none fixed inset-0 z-50 transition-opacity duration-200',
        open ? 'opacity-100' : 'opacity-0',
      )}
      aria-hidden={!open}
    >
      <button
        type="button"
        aria-label="关闭确认弹窗"
        className={cx(
          'absolute inset-0 bg-slate-950/28 backdrop-blur-[2px] transition-opacity duration-200',
          open ? 'pointer-events-auto opacity-100' : 'opacity-0',
        )}
        onClick={onClose}
      />
      <div className="absolute inset-0 flex items-center justify-center p-4">
        <section
          className={cx(
            'w-full max-w-[460px] translate-y-4 rounded-[28px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] px-6 py-6 shadow-[0_28px_90px_rgba(15,23,42,0.18)] transition duration-200',
            open ? 'pointer-events-auto translate-y-0' : '',
          )}
        >
          <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Confirm action</div>
          <h2 className="mt-3 text-xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{title}</h2>
          {description ? <div className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{description}</div> : null}
          <div className="mt-6 flex justify-end gap-3">
            <button
              type="button"
              className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm text-[color:var(--ops-text-body)]"
              onClick={onClose}
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              className={cx(
                'rounded-xl px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60',
                tone === 'destructive' ? 'bg-rose-600' : 'bg-[color:var(--ops-accent-strong)]',
              )}
              disabled={loading}
              onClick={onConfirm}
            >
              {loading ? '处理中…' : confirmLabel}
            </button>
          </div>
        </section>
      </div>
    </div>
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
