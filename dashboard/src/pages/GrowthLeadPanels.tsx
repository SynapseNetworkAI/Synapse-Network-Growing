import { api, type GrowthLead, type GrowthLeadDetail } from '../api'
import { EmptyPane, OverlayModal, StateBadge } from '../components/workbench'

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

export function LeadPanel(props: Readonly<{
  leadType: string
  search: string
  status: string
  setSearch: (value: string) => void
  setStatus: (value: string) => void
  leads: GrowthLead[]
  total: number
  offset: number
  limit: number
  onSearch: () => void
  onPrevious: () => void
  onNext: () => void
  onCreate: () => void
  onOpen: (lead: GrowthLead) => void
}>) {
  const end = Math.min(props.total, props.offset + props.limit)
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
      <div className="grid gap-3 md:grid-cols-6">
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm md:col-span-2" placeholder="搜索 name / org / source" value={props.search} onChange={(event) => props.setSearch(event.target.value)} />
        <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={props.status} onChange={(event) => props.setStatus(event.target.value)}>
          <option value="">全部状态</option>
          {['new', 'researched', 'drafted', 'approved', 'queued', 'sent', 'replied', 'interested', 'do_not_contact'].map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm text-white" onClick={props.onSearch}>查询</button>
      </div>
      <div className="mt-4 flex justify-end">
        <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" onClick={props.onCreate}>新增 Lead</button>
      </div>
      <div className="mt-5 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">
        {props.leads.length ? props.leads.map((lead) => (
          <button key={lead.id} type="button" className="flex w-full items-center justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 text-left last:border-b-0 hover:bg-[color:var(--ops-panel-subtle)]" onClick={() => props.onOpen(lead)}>
            <span>
              <span className="block font-semibold text-[color:var(--ops-text-title)]">{lead.name}</span>
              <span className="mt-1 block text-sm text-[color:var(--ops-text-muted)]">{lead.organization || '-'} · score {lead.fit_score} · {lead.next_action || 'no next action'}</span>
            </span>
            <StateBadge tone={tone(lead.status)}>{lead.status}</StateBadge>
          </button>
        )) : <div className="p-6"><EmptyPane>No leads in this view.</EmptyPane></div>}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-[color:var(--ops-text-muted)]">
        <span>{props.total ? `${props.offset + 1}-${end} / ${props.total}` : '0 / 0'}</span>
        <span className="flex gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={props.offset <= 0} onClick={props.onPrevious}>上一页</button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 disabled:opacity-40" disabled={props.offset + props.limit >= props.total} onClick={props.onNext}>下一页</button>
        </span>
      </div>
    </section>
  )
}

export function LeadDetailModal({ detail, busy, onClose, action }: Readonly<{
  detail: GrowthLeadDetail | null
  busy: boolean
  onClose: () => void
  action: (fn: () => Promise<unknown>, message: string) => Promise<void>
}>) {
  const firstMessage = detail?.messages[0]
  const contactEmail = contactEmailFrom(detail)
  const contactProvenance = firstMessage?.metadata?.contact_provenance || detail?.lead.metadata?.contact_provenance
  const draftUrl = typeof firstMessage?.metadata?.draft_url === 'string' ? firstMessage.metadata.draft_url : ''
  const hasGmailDraft = Boolean(firstMessage?.metadata?.gmail_draft_id)
  return (
    <OverlayModal open={Boolean(detail)} eyebrow="Growth Lead" title={detail?.lead.name || ''} description={detail?.lead.organization || ''} onClose={onClose}>
      {detail && (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Info label="Status" value={detail.lead.status} />
            <Info label="Fit score" value={String(detail.lead.fit_score)} />
            <Info label="Contact" value={contactEmail || 'no trusted email'} />
            <Info label="Updated" value={time(detail.lead.updated_at)} />
          </div>
          <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Provider Evidence</div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
              <div>source: {detail.lead.source_url || '-'}</div>
              <div>why: {String(detail.lead.metadata.why_this_provider || detail.lead.next_action || '-')}</div>
              <div>contact provenance: {formatContactProvenance(contactProvenance)}</div>
            </div>
          </div>
          <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Messages</div>
            {detail.messages.length ? detail.messages.map((message) => (
              <div key={message.id} className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>{message.subject}</strong>
                  <StateBadge tone={tone(message.status)}>{message.status}</StateBadge>
                </div>
                <div className="mt-2 text-xs text-[color:var(--ops-text-muted)]">
                  Gmail: {String(message.metadata.gmail_status || 'not_created')}
                  {message.metadata.contact_email ? ` · ${String(message.metadata.contact_email)}` : ''}
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-muted)]">{message.body}</p>
              </div>
            )) : <EmptyPane>No outreach messages yet.</EmptyPane>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button disabled={busy || detail.lead.status === 'do_not_contact'} className="rounded-xl border border-cyan-300/35 px-4 py-2 text-sm text-cyan-100" onClick={() => action(() => api.draftGrowthMessage(detail.lead.id, { actor: 'codex' }), 'Agent 已生成草稿')}>生成草稿</button>
            {firstMessage && <button disabled={busy || firstMessage.status !== 'needs_review'} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => action(() => api.approveGrowthMessage(firstMessage.id, { actor: 'operator' }), 'Message 已批准')}>批准</button>}
            {firstMessage && <button disabled={busy || firstMessage.status !== 'approved' || hasGmailDraft} className="rounded-xl border border-cyan-300/35 px-4 py-2 text-sm text-cyan-100" onClick={() => action(() => api.createGrowthGmailDraft(firstMessage.id, { actor: 'operator', metadata: { human_gate: true } }), 'Gmail 草稿已创建，未自动发送')}>创建 Gmail Draft</button>}
            {draftUrl && <a className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" href={draftUrl} target="_blank" rel="noreferrer">打开 Gmail 草稿</a>}
            {firstMessage && <button disabled={busy || firstMessage.status !== 'approved'} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => action(() => api.queueGrowthMessage(firstMessage.id, { actor: 'operator' }), 'Message 已进入 operator/runner 队列')}>加入待发送队列</button>}
            {firstMessage && <button disabled={busy || !['approved', 'queued'].includes(firstMessage.status)} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => action(() => api.markGrowthMessageSent(firstMessage.id, { actor: 'operator', metadata: { manual_confirmation: true } }), '已记录为人工发送')}>标记已人工发送</button>}
            <button disabled={busy} className="rounded-xl border border-red-300/35 px-4 py-2 text-sm text-red-100" onClick={() => action(() => api.doNotContactGrowthLead(detail.lead.id, { actor: 'operator', summary: 'Stopped by operator.' }), '已设为 do-not-contact')}>Do not contact</button>
          </div>
          <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Events</div>
            {detail.events.map((event) => <div key={event.id} className="mt-3 text-sm text-[color:var(--ops-text-muted)]">{event.event_type} · {event.to_status || '-'} · {time(event.created_at)}</div>)}
          </div>
        </div>
      )}
    </OverlayModal>
  )
}

function contactEmailFrom(detail: GrowthLeadDetail | null) {
  const fromMessage = detail?.messages[0]?.metadata?.contact_email
  if (typeof fromMessage === 'string' && fromMessage) return fromMessage
  for (const channel of detail?.lead.contact_channels || []) {
    if (typeof channel.value === 'string' && channel.value.includes('@')) return channel.value
  }
  return ''
}

function formatContactProvenance(value: unknown) {
  if (!Array.isArray(value) || !value.length) return '-'
  return value.map((item) => {
    if (!item || typeof item !== 'object') return ''
    const record = item as Record<string, unknown>
    return String(record.source_url || record.provenance || record.reason || '')
  }).filter(Boolean).join(' · ') || '-'
}

function Info({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4"><div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div><div className="mt-2 text-sm text-[color:var(--ops-text-title)]">{value}</div></div>
}
