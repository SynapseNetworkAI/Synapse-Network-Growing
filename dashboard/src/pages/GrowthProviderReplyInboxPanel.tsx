import type { GrowthProviderReply } from '../api'
import { EmptyPane, StateBadge } from '../components/workbench'

function tone(value: string) {
  if (['sent', 'listed', 'verified', 'interested'].includes(value)) return 'delivered'
  if (['approved', 'queued', 'researched', 'drafted'].includes(value)) return 'running'
  if (['needs_fix', 'failed', 'do_not_contact', 'invalid'].includes(value)) return 'blocked'
  return 'muted'
}

function time(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export function GrowthProviderReplyInboxPanel({ items, onOpenLead }: Readonly<{
  items: GrowthProviderReply[]
  onOpenLead: (leadId: number) => void
}>) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5" data-testid="provider-reply-inbox">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Gmail Provider Reply Monitor</div>
          <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">Provider Reply Inbox</h3>
        </div>
        <StateBadge tone={items.length ? 'running' : 'muted'}>{items.length ? `${items.length} replies` : 'no replies'}</StateBadge>
      </div>
      <div className="mt-4 space-y-3">
        {items.length ? items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{item.from_name || item.from_email}</div>
                <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{item.from_email} · {time(item.received_at)}</div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <StateBadge tone={tone(item.classification)}>{item.classification}</StateBadge>
                <span className="text-xs text-[color:var(--ops-text-caption)]">{item.confidence_score}%</span>
              </div>
            </div>
            <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.snippet || item.body_excerpt || '-'}</p>
            {item.suggested_reply_body ? (
              <div className="mt-4 rounded-xl border border-cyan-300/20 bg-cyan-300/[0.06] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <strong className="text-sm text-cyan-100">{item.suggested_reply_subject || 'Suggested reply'}</strong>
                  <StateBadge tone={tone(item.suggested_reply_status || item.status)}>{item.suggested_reply_status || item.status}</StateBadge>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-muted)]">{item.suggested_reply_body}</p>
              </div>
            ) : null}
            <div className="mt-4 flex justify-end">
              <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => onOpenLead(item.lead_id)}>打开 Lead</button>
            </div>
          </article>
        )) : <EmptyPane>No provider replies captured yet.</EmptyPane>}
      </div>
    </section>
  )
}
