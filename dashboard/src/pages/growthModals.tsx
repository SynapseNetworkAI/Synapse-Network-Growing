import { GrowthResearchRun, GrowthSourceConfig } from '../api'
import { EmptyPane, OverlayModal, StateBadge } from '../components/workbench'

type AiVisibilityDraft = {
  query: string
  platform: string
  answer_summary: string
  next_action: string
  feed_key: string
  run_group: string
  synapse_mentioned: boolean
  synapse_cited: boolean
  cited_urls: string
  competitor_mentions: string
  missing_facts: string
  evidence_url: string
}

export function SourceConfigModal({ open, draft, setDraft, onClose, onCreate }: Readonly<{
  open: boolean
  draft: { name: string; config_type: string; seed_urls: string; queries: string }
  setDraft: (value: { name: string; config_type: string; seed_urls: string; queries: string }) => void
  onClose: () => void
  onCreate: () => void
}>) {
  return (
    <OverlayModal open={open} eyebrow="Growth Source" title="新增 Provider 采集配置" description="配置采集源；运行只会创建 lead 和人工审核草稿，不会外发消息。" onClose={onClose}>
      <div className="grid gap-4">
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="配置名称" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={draft.config_type} onChange={(e) => setDraft({ ...draft, config_type: e.target.value })}>
          <option value="github_mcp_repos">github_mcp_repos</option>
          <option value="github_provider_search">github_provider_search</option>
          <option value="mcp_directory_watch">mcp_directory_watch</option>
          <option value="api_provider_sites">api_provider_sites</option>
          <option value="package_ecosystem">package_ecosystem</option>
          <option value="manual_seed_list">manual_seed_list</option>
        </select>
        <textarea className="min-h-24 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" placeholder="Seed URLs, one per line" value={draft.seed_urls} onChange={(e) => setDraft({ ...draft, seed_urls: e.target.value })} />
        <textarea className="min-h-28 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" placeholder="Queries, one per line" value={draft.queries} onChange={(e) => setDraft({ ...draft, queries: e.target.value })} />
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onClose}>取消</button>
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2 text-sm text-white" onClick={onCreate}>创建配置</button>
        </div>
      </div>
    </OverlayModal>
  )
}

export function LeadCreateModal({ open, leadType, draft, setDraft, onClose, onCreate }: Readonly<{
  open: boolean
  leadType: string
  draft: { name: string; organization: string; source_url: string }
  setDraft: (value: { name: string; organization: string; source_url: string }) => void
  onClose: () => void
  onCreate: () => void
}>) {
  return (
    <OverlayModal open={open} eyebrow="Growth Lead" title={`新增 ${leadType} lead`} description="只记录 lead 和来源证据，不自动发送 outreach。" onClose={onClose}>
      <div className="grid gap-4">
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder={`${leadType} name`} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="organization" value={draft.organization} onChange={(e) => setDraft({ ...draft, organization: e.target.value })} />
        <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="source URL" value={draft.source_url} onChange={(e) => setDraft({ ...draft, source_url: e.target.value })} />
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={onClose}>取消</button>
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2 text-sm text-white" onClick={onCreate}>创建 Lead</button>
        </div>
      </div>
    </OverlayModal>
  )
}

export function RecordCreateModal(props: Readonly<{
  kind: null | 'ai' | 'mcp'
  aiDraft: AiVisibilityDraft
  setAiDraft: (value: AiVisibilityDraft) => void
  listingDraft: { surface: string; package_name: string; target_repo: string; listing_url: string }
  setListingDraft: (value: { surface: string; package_name: string; target_repo: string; listing_url: string }) => void
  onClose: () => void
  onCreateAi: () => void
  onCreateListing: () => void
}>) {
  return (
    <OverlayModal open={Boolean(props.kind)} eyebrow="Growth Record" title={props.kind === 'ai' ? '新增 AI Visibility Check' : '新增 MCP Discovery Listing'} onClose={props.onClose}>
      {props.kind === 'ai' ? (
        <div className="grid gap-4">
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="query" value={props.aiDraft.query} onChange={(e) => props.setAiDraft({ ...props.aiDraft, query: e.target.value })} />
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="platform" value={props.aiDraft.platform} onChange={(e) => props.setAiDraft({ ...props.aiDraft, platform: e.target.value })} />
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="answer summary" value={props.aiDraft.answer_summary} onChange={(e) => props.setAiDraft({ ...props.aiDraft, answer_summary: e.target.value })} />
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="next action" value={props.aiDraft.next_action} onChange={(e) => props.setAiDraft({ ...props.aiDraft, next_action: e.target.value })} />
          <button type="button" className="justify-self-end rounded-xl bg-blue-600 px-4 py-2 text-sm text-white" onClick={props.onCreateAi}>记录 Check</button>
        </div>
      ) : (
        <div className="grid gap-4">
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="surface" value={props.listingDraft.surface} onChange={(e) => props.setListingDraft({ ...props.listingDraft, surface: e.target.value })} />
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="package" value={props.listingDraft.package_name} onChange={(e) => props.setListingDraft({ ...props.listingDraft, package_name: e.target.value })} />
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="target repo" value={props.listingDraft.target_repo} onChange={(e) => props.setListingDraft({ ...props.listingDraft, target_repo: e.target.value })} />
          <input className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="listing url" value={props.listingDraft.listing_url} onChange={(e) => props.setListingDraft({ ...props.listingDraft, listing_url: e.target.value })} />
          <button type="button" className="justify-self-end rounded-xl bg-blue-600 px-4 py-2 text-sm text-white" onClick={props.onCreateListing}>记录 Listing</button>
        </div>
      )}
    </OverlayModal>
  )
}

export function SourceRunsModal({ source, runs, onClose }: Readonly<{ source: GrowthSourceConfig | null; runs?: GrowthResearchRun[]; onClose: () => void }>) {
  const safeRuns = Array.isArray(runs) ? runs : []
  return (
    <OverlayModal open={Boolean(source)} eyebrow="Run History" title={source?.name || ''} description="采集运行证据：found / reused / created / drafted / errors。" onClose={onClose}>
      <div className="space-y-3">
        {safeRuns.length ? safeRuns.map((run) => (
          <div key={run.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] p-4">
            <div className="flex items-center justify-between gap-3">
              <strong>Run #{run.id} · {run.dry_run ? 'dry-run' : 'apply'}</strong>
              <StateBadge tone={run.status === 'succeeded' ? 'delivered' : 'blocked'}>{run.status}</StateBadge>
            </div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">found {run.candidate_count} · created {run.created_count} · reused {run.reused_count} · drafted {run.drafted_count}</div>
            {run.error_summary ? <div className="mt-2 text-sm text-red-200">{run.error_summary}</div> : null}
          </div>
        )) : <EmptyPane>No runs yet.</EmptyPane>}
      </div>
    </OverlayModal>
  )
}
