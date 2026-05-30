import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, GrowthAIVisibilityCheck, GrowthDiscoveryListing, GrowthLead, GrowthLeadDetail } from '../api'
import { EmptyPane, OverlayModal, StateBadge, useToast } from '../components/workbench'

type TabKey = 'investors' | 'providers' | 'ai' | 'mcp'

const tabs: Array<{ key: TabKey; label: string; description: string }> = [
  { key: 'investors', label: 'Investors', description: 'Pre-seed / seed outreach queue' },
  { key: 'providers', label: 'Providers', description: 'First provider acquisition' },
  { key: 'ai', label: 'AI Visibility', description: 'Answer-engine citation checks' },
  { key: 'mcp', label: 'MCP Discovery', description: 'Registry and directory listings' },
]
const LEAD_PAGE_SIZE = 10

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

function metric(values: Array<[string, number]>) {
  return values.map(([label, value]) => (
    <div key={label} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  ))
}

export default function GrowthPage() {
  const toast = useToast()
  const [active, setActive] = useState<TabKey>('investors')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [leads, setLeads] = useState<GrowthLead[]>([])
  const [leadTotal, setLeadTotal] = useState(0)
  const [leadOffset, setLeadOffset] = useState(0)
  const [aiChecks, setAiChecks] = useState<GrowthAIVisibilityCheck[]>([])
  const [listings, setListings] = useState<GrowthDiscoveryListing[]>([])
  const [overview, setOverview] = useState({ leads: 0, messages: 0, citations: 0, listings: 0 })
  const [detail, setDetail] = useState<GrowthLeadDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [leadDraft, setLeadDraft] = useState({ name: '', organization: '', source_url: '' })
  const [aiDraft, setAiDraft] = useState({ query: '', platform: 'chatgpt', answer_summary: '', next_action: '' })
  const [listingDraft, setListingDraft] = useState({ surface: 'official_mcp_registry', package_name: '', target_repo: '', listing_url: '' })

  const leadType = active === 'providers' ? 'provider' : 'investor'

  const load = async (nextLeadOffset = leadOffset) => {
    const [summary, leadPayload, aiPayload, listingPayload] = await Promise.all([
      api.getGrowthOverview(),
      api.getGrowthLeads({ lead_type: leadType, q: search || undefined, status: status || undefined, limit: LEAD_PAGE_SIZE, offset: nextLeadOffset }),
      api.getGrowthAIVisibilityChecks({ q: search || undefined, limit: 100 }),
      api.getGrowthDiscoveryListings({ status: status || undefined, limit: 100 }),
    ])
    setOverview({
      leads: Object.values(summary.lead_counts).reduce((sum, value) => sum + value, 0),
      messages: Object.values(summary.message_counts).reduce((sum, value) => sum + value, 0),
      citations: summary.ai_visibility.cited || 0,
      listings: Object.values(summary.discovery_counts).reduce((sum, value) => sum + value, 0),
    })
    setLeads(leadPayload.items)
    setLeadTotal(leadPayload.total)
    setAiChecks(aiPayload.items)
    setListings(listingPayload.items)
  }

  useEffect(() => {
    setLeadOffset(0)
    load(0).catch(() => {})
  }, [active])

  const visibleLeads = useMemo(() => leads.filter((lead) => lead.lead_type === leadType), [leads, leadType])

  const openDetail = async (lead: GrowthLead) => {
    setBusy(true)
    try {
      setDetail(await api.getGrowthLead(lead.id))
    } finally {
      setBusy(false)
    }
  }

  const refreshDetail = async () => {
    if (detail) setDetail(await api.getGrowthLead(detail.lead.id))
    await load(leadOffset)
  }

  const action = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true)
    try {
      await fn()
      toast.success(message)
      await refreshDetail()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  const createLead = async () => {
    await action(
      () => api.createGrowthLead({ ...leadDraft, lead_type: leadType, project_key: 'growing', status: 'new' }),
      'Lead 已创建',
    )
    setLeadDraft({ name: '', organization: '', source_url: '' })
  }

  const createAiCheck = async () => {
    await action(() => api.createGrowthAIVisibilityCheck(aiDraft), 'AI visibility check 已记录')
    setAiDraft({ query: '', platform: 'chatgpt', answer_summary: '', next_action: '' })
  }

  const createListing = async () => {
    await action(() => api.createGrowthDiscoveryListing({ ...listingDraft, status: 'candidate' }), 'MCP discovery listing 已记录')
    setListingDraft({ surface: 'official_mcp_registry', package_name: '', target_repo: '', listing_url: '' })
  }

  return (
    <div className="space-y-5" data-testid="growth-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Growth Acquisition + AI Discovery</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">Growth</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              Investor radar、provider acquisition、AI search visibility 和 MCP discovery 的半自动账本。V1 只生成草稿和记录证据，不自动外发消息。
            </p>
          </div>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>刷新</button>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          {metric([
            ['Leads', overview.leads],
            ['Messages', overview.messages],
            ['AI cited', overview.citations],
            ['MCP listings', overview.listings],
          ])}
        </div>
      </section>

      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-4">
        <div className="flex flex-wrap gap-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`rounded-2xl border px-4 py-2 text-sm ${active === tab.key ? 'border-cyan-300/40 bg-cyan-300/[0.12] text-cyan-100' : 'border-[color:var(--ops-stroke-strong)] text-[color:var(--ops-text-muted)]'}`}
              onClick={() => setActive(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <p className="mt-3 text-sm text-[color:var(--ops-text-muted)]">{tabs.find((tab) => tab.key === active)?.description}</p>
      </section>

      {(active === 'investors' || active === 'providers') && (
        <LeadPanel
          leadType={leadType}
          search={search}
          status={status}
          setSearch={setSearch}
          setStatus={setStatus}
          leads={visibleLeads}
          leadDraft={leadDraft}
          setLeadDraft={setLeadDraft}
          total={leadTotal}
          offset={leadOffset}
          limit={LEAD_PAGE_SIZE}
          onSearch={() => {
            setLeadOffset(0)
            load(0).catch(() => {})
          }}
          onPrevious={() => {
            const nextOffset = Math.max(0, leadOffset - LEAD_PAGE_SIZE)
            setLeadOffset(nextOffset)
            load(nextOffset).catch(() => {})
          }}
          onNext={() => {
            const nextOffset = leadOffset + LEAD_PAGE_SIZE
            setLeadOffset(nextOffset)
            load(nextOffset).catch(() => {})
          }}
          onCreate={createLead}
          onOpen={openDetail}
        />
      )}
      {active === 'ai' && <AiVisibilityPanel items={aiChecks} draft={aiDraft} setDraft={setAiDraft} onCreate={createAiCheck} />}
      {active === 'mcp' && <McpDiscoveryPanel items={listings} draft={listingDraft} setDraft={setListingDraft} onCreate={createListing} />}

      <LeadDetailModal detail={detail} busy={busy} onClose={() => setDetail(null)} action={action} />
    </div>
  )
}

function LeadPanel(props: Readonly<{
  leadType: string
  search: string
  status: string
  setSearch: (value: string) => void
  setStatus: (value: string) => void
  leads: GrowthLead[]
  leadDraft: { name: string; organization: string; source_url: string }
  setLeadDraft: (value: { name: string; organization: string; source_url: string }) => void
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
      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder={`${props.leadType} name`} value={props.leadDraft.name} onChange={(event) => props.setLeadDraft({ ...props.leadDraft, name: event.target.value })} />
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="organization" value={props.leadDraft.organization} onChange={(event) => props.setLeadDraft({ ...props.leadDraft, organization: event.target.value })} />
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="source URL" value={props.leadDraft.source_url} onChange={(event) => props.setLeadDraft({ ...props.leadDraft, source_url: event.target.value })} />
        <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" onClick={props.onCreate}>创建 Lead</button>
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

function LeadDetailModal({ detail, busy, onClose, action }: Readonly<{
  detail: GrowthLeadDetail | null
  busy: boolean
  onClose: () => void
  action: (fn: () => Promise<unknown>, message: string) => Promise<void>
}>) {
  const firstMessage = detail?.messages[0]
  return (
    <OverlayModal open={Boolean(detail)} eyebrow="Growth Lead" title={detail?.lead.name || ''} description={detail?.lead.organization || ''} onClose={onClose}>
      {detail && (
        <div className="space-y-5">
          <div className="grid gap-3 md:grid-cols-4">
            <Info label="Status" value={detail.lead.status} />
            <Info label="Fit score" value={String(detail.lead.fit_score)} />
            <Info label="Source" value={detail.lead.source_url || '-'} />
            <Info label="Updated" value={time(detail.lead.updated_at)} />
          </div>
          <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Messages</div>
            {detail.messages.length ? detail.messages.map((message) => (
              <div key={message.id} className="mt-3 rounded-xl border border-[color:var(--ops-stroke-soft)] p-4">
                <div className="flex items-center justify-between gap-3">
                  <strong>{message.subject}</strong>
                  <StateBadge tone={tone(message.status)}>{message.status}</StateBadge>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-muted)]">{message.body}</p>
              </div>
            )) : <EmptyPane>No outreach messages yet.</EmptyPane>}
          </div>
          <div className="flex flex-wrap gap-2">
            <button disabled={busy || detail.lead.status === 'do_not_contact'} className="rounded-xl border border-cyan-300/35 px-4 py-2 text-sm text-cyan-100" onClick={() => action(() => api.draftGrowthMessage(detail.lead.id, { actor: 'codex' }), 'Agent 已生成草稿')}>生成草稿</button>
            {firstMessage && <button disabled={busy || firstMessage.status !== 'needs_review'} className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => action(() => api.approveGrowthMessage(firstMessage.id, { actor: 'operator' }), 'Message 已批准')}>批准</button>}
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

function AiVisibilityPanel({ items, draft, setDraft, onCreate }: Readonly<{
  items: GrowthAIVisibilityCheck[]
  draft: { query: string; platform: string; answer_summary: string; next_action: string }
  setDraft: (value: { query: string; platform: string; answer_summary: string; next_action: string }) => void
  onCreate: () => void
}>) {
  return <RecordPanel title="AI Visibility Checks" fields={[
    <input key="query" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="query" value={draft.query} onChange={(e) => setDraft({ ...draft, query: e.target.value })} />,
    <input key="platform" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="platform" value={draft.platform} onChange={(e) => setDraft({ ...draft, platform: e.target.value })} />,
    <input key="summary" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="answer summary" value={draft.answer_summary} onChange={(e) => setDraft({ ...draft, answer_summary: e.target.value })} />,
    <input key="next" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="next action" value={draft.next_action} onChange={(e) => setDraft({ ...draft, next_action: e.target.value })} />,
  ]} onCreate={onCreate}>{items.map((item) => <Row key={item.id} title={item.query} meta={`${item.platform} · cited ${item.synapse_cited ? 'yes' : 'no'} · ${item.next_action || '-'}`} status={item.synapse_cited ? 'cited' : 'not_cited'} />)}</RecordPanel>
}

function McpDiscoveryPanel({ items, draft, setDraft, onCreate }: Readonly<{
  items: GrowthDiscoveryListing[]
  draft: { surface: string; package_name: string; target_repo: string; listing_url: string }
  setDraft: (value: { surface: string; package_name: string; target_repo: string; listing_url: string }) => void
  onCreate: () => void
}>) {
  return <RecordPanel title="MCP Discovery Listings" fields={[
    <input key="surface" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="surface" value={draft.surface} onChange={(e) => setDraft({ ...draft, surface: e.target.value })} />,
    <input key="pkg" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="package" value={draft.package_name} onChange={(e) => setDraft({ ...draft, package_name: e.target.value })} />,
    <input key="repo" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="target repo" value={draft.target_repo} onChange={(e) => setDraft({ ...draft, target_repo: e.target.value })} />,
    <input key="url" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="listing url" value={draft.listing_url} onChange={(e) => setDraft({ ...draft, listing_url: e.target.value })} />,
  ]} onCreate={onCreate}>{items.map((item) => <Row key={item.id} title={item.surface} meta={`${item.package_name || '-'} · ${item.listing_url || 'no listing URL'}`} status={item.status} />)}</RecordPanel>
}

function RecordPanel({ title, fields, children, onCreate }: Readonly<{ title: string; fields: ReactNode[]; children: ReactNode; onCreate: () => void }>) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
      <h3 className="text-xl font-semibold text-[color:var(--ops-text-title)]">{title}</h3>
      <div className="mt-4 grid gap-3 md:grid-cols-5">{fields}<button className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" onClick={onCreate}>记录</button></div>
      <div className="mt-5 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">{children || <div className="p-6"><EmptyPane>No records yet.</EmptyPane></div>}</div>
    </section>
  )
}

function Row({ title, meta, status }: Readonly<{ title: string; meta: string; status: string }>) {
  return <div className="flex items-center justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 last:border-b-0"><span><strong>{title}</strong><span className="mt-1 block text-sm text-[color:var(--ops-text-muted)]">{meta}</span></span><StateBadge tone={tone(status)}>{status}</StateBadge></div>
}

function Info({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4"><div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div><div className="mt-2 text-sm text-[color:var(--ops-text-title)]">{value}</div></div>
}
