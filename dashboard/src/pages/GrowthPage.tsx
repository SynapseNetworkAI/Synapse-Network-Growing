import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  api,
  GrowthDiscoveryListing,
  GrowthLead,
  GrowthLeadDetail,
  GrowthProviderProfile,
  GrowthProviderReply,
  GrowthResearchRun,
  GrowthSourceConfig,
} from '../api'
import { EmptyPane, StateBadge, useToast } from '../components/workbench'
import { LeadCreateModal, RecordCreateModal, SourceConfigModal, SourceRunsModal } from './growthModals'
import { GrowthAIVisibilityPanel } from './GrowthAIVisibilityPanel'
import { GrowthProviderProfilesPanel } from './GrowthProviderProfilesPanel'
import { GrowthProviderReplyInboxPanel } from './GrowthProviderReplyInboxPanel'
import { LeadDetailModal, LeadPanel } from './GrowthLeadPanels'
import { SourcesPanel } from './GrowthSourcesPanel'
import { useGrowthAIVisibilityData } from './useGrowthAIVisibilityData'

type TabKey = 'sources' | 'investors' | 'providers' | 'ai' | 'mcp'

const tabs: Array<{ key: TabKey; label: string; description: string }> = [
  { key: 'sources', label: 'Sources', description: 'Provider acquisition source configs and run history' },
  { key: 'investors', label: 'Investors', description: 'Pre-seed / seed outreach queue' },
  { key: 'providers', label: 'Providers', description: 'First provider acquisition' },
  { key: 'ai', label: 'AI Visibility', description: 'Answer-engine citation checks' },
  { key: 'mcp', label: 'MCP Discovery', description: 'Registry and directory listings' },
]
const LEAD_PAGE_SIZE = 10
const tabAliases: Record<string, TabKey> = {
  sources: 'sources',
  investors: 'investors',
  providers: 'providers',
  ai: 'ai',
  'ai-visibility': 'ai',
  mcp: 'mcp',
  'mcp-discovery': 'mcp',
}

function tabFromSearch(search: string): TabKey {
  const value = new URLSearchParams(search).get('tab')?.trim() || ''
  return tabAliases[value] || 'sources'
}

function tabSearchValue(tab: TabKey) {
  if (tab === 'ai') return 'ai-visibility'
  if (tab === 'mcp') return 'mcp-discovery'
  return tab
}

function tone(value: string) {
  if (['sent', 'listed', 'verified', 'interested'].includes(value)) return 'delivered'
  if (['approved', 'queued', 'researched', 'drafted'].includes(value)) return 'running'
  if (['needs_fix', 'failed', 'do_not_contact', 'invalid'].includes(value)) return 'blocked'
  return 'muted'
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
  const [active, setActive] = useState<TabKey>(() => tabFromSearch(window.location.search))
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [leads, setLeads] = useState<GrowthLead[]>([])
  const [leadTotal, setLeadTotal] = useState(0)
  const [leadOffset, setLeadOffset] = useState(0)
  const [providerProfiles, setProviderProfiles] = useState<GrowthProviderProfile[]>([])
  const [providerReplies, setProviderReplies] = useState<GrowthProviderReply[]>([])
  const aiVisibility = useGrowthAIVisibilityData()
  const [listings, setListings] = useState<GrowthDiscoveryListing[]>([])
  const [overview, setOverview] = useState({ leads: 0, messages: 0, citations: 0, listings: 0 })
  const [detail, setDetail] = useState<GrowthLeadDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [sourceConfigs, setSourceConfigs] = useState<GrowthSourceConfig[]>([])
  const [sourceRuns, setSourceRuns] = useState<GrowthResearchRun[]>([])
  const [sourceModal, setSourceModal] = useState(false)
  const [leadModal, setLeadModal] = useState(false)
  const [recordModal, setRecordModal] = useState<null | 'ai' | 'mcp'>(null)
  const [activeSource, setActiveSource] = useState<GrowthSourceConfig | null>(null)
  const [leadDraft, setLeadDraft] = useState({ name: '', organization: '', source_url: '' })
  const [sourceDraft, setSourceDraft] = useState({
    name: 'Provider Discovery: MCP + API Services',
    config_type: 'github_mcp_repos',
    seed_urls: 'https://github.com/firecrawl/firecrawl-mcp-server',
    queries: 'mcp server search api\nmodel-context-protocol web scraping API\nagent tools API',
  })
  const defaultRunGroup = new Date().toISOString().slice(0, 10)
  const [aiDraft, setAiDraft] = useState({
    query: '',
    platform: 'chatgpt',
    answer_summary: '',
    next_action: '',
    feed_key: 'agent_payment_category_pages',
    run_group: `${defaultRunGroup}-baseline`,
    synapse_mentioned: false,
    synapse_cited: false,
    cited_urls: '',
    competitor_mentions: '',
    missing_facts: '',
    evidence_url: '',
  })
  const [listingDraft, setListingDraft] = useState({ surface: 'official_mcp_registry', package_name: '', target_repo: '', listing_url: '' })

  const leadType = active === 'providers' ? 'provider' : 'investor'

  const setActiveTab = (tab: TabKey) => {
    setActive(tab)
    const nextUrl = new URL(window.location.href)
    nextUrl.searchParams.set('tab', tabSearchValue(tab))
    window.history.replaceState(null, '', nextUrl.toString())
  }

  const load = async (nextLeadOffset = leadOffset) => {
    const [summary, leadPayload, profilePayload, replyPayload, listingPayload, sourcePayload] = await Promise.all([
      api.getGrowthOverview(),
      api.getGrowthLeads({ lead_type: leadType, q: search || undefined, status: status || undefined, limit: LEAD_PAGE_SIZE, offset: nextLeadOffset }),
      api.getGrowthProviderProfiles({ q: active === 'providers' ? search || undefined : undefined, limit: 50 }),
      api.getGrowthProviderReplies({ q: active === 'providers' ? search || undefined : undefined, limit: 20 }),
      api.getGrowthDiscoveryListings({ status: status || undefined, limit: 100 }),
      api.getGrowthSourceConfigs(),
      aiVisibility.load({ includeRuntimeEvidence: active === 'ai', search }),
    ])
    setOverview({
      leads: Object.values(summary.lead_counts).reduce((sum, value) => sum + value, 0),
      messages: Object.values(summary.message_counts).reduce((sum, value) => sum + value, 0),
      citations: summary.ai_visibility.cited || 0,
      listings: Object.values(summary.discovery_counts).reduce((sum, value) => sum + value, 0),
    })
    setLeads(leadPayload.items)
    setLeadTotal(leadPayload.total)
    setProviderProfiles(profilePayload.items)
    setProviderReplies(replyPayload.items)
    setListings(listingPayload.items)
    setSourceConfigs(sourcePayload.items)
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

  const openLeadById = async (leadId: number) => {
    setBusy(true)
    try {
      setDetail(await api.getGrowthLead(leadId))
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
    setLeadModal(false)
  }

  const createAiCheck = async () => {
    await action(
      () => api.createGrowthAIVisibilityCheck({
        ...aiDraft,
        cited_urls: splitLines(aiDraft.cited_urls),
        competitor_mentions: splitLines(aiDraft.competitor_mentions),
        missing_facts: splitLines(aiDraft.missing_facts),
      }),
      'AI visibility check 已记录',
    )
    setAiDraft({
      query: '',
      platform: 'chatgpt',
      answer_summary: '',
      next_action: '',
      feed_key: 'agent_payment_category_pages',
      run_group: `${defaultRunGroup}-baseline`,
      synapse_mentioned: false,
      synapse_cited: false,
      cited_urls: '',
      competitor_mentions: '',
      missing_facts: '',
      evidence_url: '',
    })
    setRecordModal(null)
  }

  const createListing = async () => {
    await action(() => api.createGrowthDiscoveryListing({ ...listingDraft, status: 'candidate' }), 'MCP discovery listing 已记录')
    setListingDraft({ surface: 'official_mcp_registry', package_name: '', target_repo: '', listing_url: '' })
    setRecordModal(null)
  }

  const createSourceConfig = async () => {
    await action(
      () => api.createGrowthSourceConfig({
        name: sourceDraft.name,
        config_type: sourceDraft.config_type,
        status: 'enabled',
        description: 'Find API/MCP providers that agents can invoke through metered Synapse rails.',
        query: {
          seed_urls: sourceDraft.seed_urls.split('\n').map((item) => item.trim()).filter(Boolean),
          queries: sourceDraft.queries.split('\n').map((item) => item.trim()).filter(Boolean),
          lead_type: 'provider',
          max_results: 25,
          send_policy: 'manual_gmail_draft_only',
        },
        cadence: { cadence: 'daily', suggested_local_time: '10:30' },
        thresholds: { create_lead_score: 70, auto_draft_score: 80 },
      }),
      'Source config 已创建',
    )
    setSourceModal(false)
  }

  const ensureDefaultSource = async () => {
    await action(() => api.ensureDefaultGrowthProviderSource(), 'Firecrawl provider source 已准备好')
  }

  const runSource = async (source: GrowthSourceConfig, dryRun: boolean) => {
    await action(
      async () => {
        const run = await api.runGrowthSourceConfig(source.id, { dry_run: dryRun, create_drafts: true, actor: 'operator' })
        setActiveSource(source)
        const runs = await api.getGrowthSourceRuns(source.id)
        setSourceRuns(runs.items)
        return run
      },
      dryRun ? 'Dry run 完成' : 'Provider 采集已执行',
    )
  }

  const openRuns = async (source: GrowthSourceConfig) => {
    setActiveSource(source)
    const runs = await api.getGrowthSourceRuns(source.id)
    setSourceRuns(runs.items)
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
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <p className="mt-3 text-sm text-[color:var(--ops-text-muted)]">{tabs.find((tab) => tab.key === active)?.description}</p>
      </section>

      {active === 'sources' && (
        <SourcesPanel
          sources={sourceConfigs}
          onCreate={() => setSourceModal(true)}
          onEnsureDefault={ensureDefaultSource}
          onRun={runSource}
          onOpenRuns={openRuns}
        />
      )}
      {(active === 'investors' || active === 'providers') && (
        <>
          <LeadPanel
            leadType={leadType}
            search={search}
            status={status}
            setSearch={setSearch}
            setStatus={setStatus}
            leads={visibleLeads}
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
            onCreate={() => setLeadModal(true)}
            onOpen={openDetail}
          />
          {active === 'providers' && (
            <>
              <GrowthProviderReplyInboxPanel items={providerReplies} onOpenLead={openLeadById} />
              <GrowthProviderProfilesPanel items={providerProfiles} />
            </>
          )}
        </>
      )}
      {active === 'ai' && (
        <GrowthAIVisibilityPanel
          items={aiVisibility.items}
          comparisons={aiVisibility.comparisons}
          feedPackages={aiVisibility.feedPackages}
          feedCycles={aiVisibility.feedCycles}
          feedScorecard={aiVisibility.feedScorecard}
          docsBlueprint={aiVisibility.docsBlueprint}
          designHandoff={aiVisibility.designHandoff}
          weeklyReport={aiVisibility.weeklyReport}
          nextCycle={aiVisibility.nextCycle}
          goalAudit={aiVisibility.goalAudit}
          releasePlan={aiVisibility.releasePlan}
          releaseSnapshot={aiVisibility.releaseSnapshot}
          handoffBundle={aiVisibility.handoffBundle}
          optimizationBrief={aiVisibility.optimizationBrief}
          liveReadiness={aiVisibility.liveReadiness}
          externalProbeGate={aiVisibility.externalProbeGate}
          officialSources={aiVisibility.officialSources}
          probeMatrix={aiVisibility.probeMatrix}
          plan={aiVisibility.plan}
          onCreate={() => setRecordModal('ai')}
        />
      )}
      {active === 'mcp' && <McpDiscoveryPanel items={listings} onCreate={() => setRecordModal('mcp')} />}

      <LeadDetailModal detail={detail} busy={busy} onClose={() => setDetail(null)} action={action} />
      <SourceConfigModal open={sourceModal} draft={sourceDraft} setDraft={setSourceDraft} onClose={() => setSourceModal(false)} onCreate={createSourceConfig} />
      <LeadCreateModal open={leadModal} leadType={leadType} draft={leadDraft} setDraft={setLeadDraft} onClose={() => setLeadModal(false)} onCreate={createLead} />
      <RecordCreateModal
        kind={recordModal}
        aiDraft={aiDraft}
        setAiDraft={setAiDraft}
        listingDraft={listingDraft}
        setListingDraft={setListingDraft}
        onClose={() => setRecordModal(null)}
        onCreateAi={createAiCheck}
        onCreateListing={createListing}
      />
      <SourceRunsModal source={activeSource} runs={sourceRuns} onClose={() => setActiveSource(null)} />
    </div>
  )
}

function splitLines(value: string) {
  return value
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function McpDiscoveryPanel({ items, onCreate }: Readonly<{
  items: GrowthDiscoveryListing[]
  onCreate: () => void
}>) {
  return <RecordPanel title="MCP Discovery Listings" actionLabel="新增 Listing" onCreate={onCreate}>{items.map((item) => <Row key={item.id} title={item.surface} meta={`${item.package_name || '-'} · ${item.listing_url || 'no listing URL'}`} status={item.status} />)}</RecordPanel>
}

function RecordPanel({ title, actionLabel, children, onCreate }: Readonly<{ title: string; actionLabel: string; children: ReactNode; onCreate: () => void }>) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xl font-semibold text-[color:var(--ops-text-title)]">{title}</h3>
        <button className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" onClick={onCreate}>{actionLabel}</button>
      </div>
      <div className="mt-5 overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)]">{children || <div className="p-6"><EmptyPane>No records yet.</EmptyPane></div>}</div>
    </section>
  )
}

function Row({ title, meta, status }: Readonly<{ title: string; meta: string; status: string }>) {
  return <div className="flex items-center justify-between gap-4 border-b border-[color:var(--ops-stroke-soft)] px-5 py-4 last:border-b-0"><span><strong>{title}</strong><span className="mt-1 block text-sm text-[color:var(--ops-text-muted)]">{meta}</span></span><StateBadge tone={tone(status)}>{status}</StateBadge></div>
}
