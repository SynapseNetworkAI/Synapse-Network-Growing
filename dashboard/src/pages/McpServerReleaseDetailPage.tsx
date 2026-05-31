import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { McpServer, McpServerRelease, McpServerReleaseEvent, McpServerSurface, McpSubmissionReadiness, mcpServerReleasesApi } from '../mcpServerReleasesApi'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { MCP_STATUS_LABEL, formatMcpTime, isSemVer, mcpReleaseTone, openExternalUrl } from './mcpServerReleaseUi'
import { McpSurfaceConfigsPanel } from './McpSurfaceConfigsPanel'

type DetailTab = 'overview' | 'releases' | 'configs' | 'registries' | 'ai' | 'clients' | 'evidence' | 'events'

export default function McpServerReleaseDetailPage() {
  const { id } = useParams()
  const serverId = Number(id)
  const navigate = useNavigate()
  const toast = useToast()
  const [server, setServer] = useState<McpServer | null>(null)
  const [release, setRelease] = useState<McpServerRelease | null>(null)
  const [events, setEvents] = useState<McpServerReleaseEvent[]>([])
  const [readiness, setReadiness] = useState<McpSubmissionReadiness | null>(null)
  const [tab, setTab] = useState<DetailTab>('overview')
  const [busy, setBusy] = useState<string | null>(null)
  const [releaseOpen, setReleaseOpen] = useState(false)
  const [publishOpen, setPublishOpen] = useState(false)
  const [confirmPhrase, setConfirmPhrase] = useState('')
  const [draftRelease, setDraftRelease] = useState({ package_version: '0.1.0', release_notes: '' })

  const load = async () => {
    const nextServer = await mcpServerReleasesApi.getServer(serverId)
    setServer(nextServer)
    const latest = nextServer.latest_release
    setRelease(latest)
    setReadiness(await mcpServerReleasesApi.getSubmissionReadiness(serverId))
    setEvents(latest ? await mcpServerReleasesApi.events(latest.id) : [])
  }

  useEffect(() => {
    if (!Number.isFinite(serverId)) return
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 MCP Server 详情失败'))
  }, [serverId])

  const runAction = async (key: string, fn: () => Promise<unknown>, message: string) => {
    setBusy(key)
    try {
      await fn()
      toast.success(message)
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    } finally {
      setBusy(null)
    }
  }

  const createRelease = async () => {
    if (!isSemVer(draftRelease.package_version)) {
      toast.error('版本格式必须是 SemVer，例如 0.1.0')
      return
    }
    await runAction(
      'create-release',
      () => mcpServerReleasesApi.createReleaseForServer(serverId, {
        package_version: draftRelease.package_version,
        release_notes: draftRelease.release_notes || null,
      }),
      'MCP release 已创建',
    )
    setReleaseOpen(false)
  }

  if (!server) return <EmptyPane>记录不存在或仍在加载。</EmptyPane>

  const expectedPhrase = release ? `PUBLISH_MCP_${release.package_version}` : ''

  return (
    <div className="space-y-5" data-testid="mcp-release-detail">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">MCP Server Registry Matrix</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{server.server_name}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              一个 server 绑定一个仓库；每个 release 持有 npm、Official MCP Registry、目录、OpenAI / Claude 和 client config 的提交账本。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => navigate('/releases?tab=mcp-servers')}>返回矩阵</button>
            <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" onClick={() => setReleaseOpen(true)}>新增 Release</button>
            {release?.status === 'planned' && <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" disabled={busy === 'readiness'} onClick={() => runAction('readiness', () => mcpServerReleasesApi.runReadiness(release.id, { actor: 'operator' }), 'Readiness 已触发')}>Run readiness</button>}
            {release?.status === 'ready_to_publish' && <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => setPublishOpen(true)}>Publish npm</button>}
            {release?.status === 'npm_published' && <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" disabled={busy === 'registry'} onClick={() => runAction('registry', () => mcpServerReleasesApi.submitRegistry(release.id, { actor: 'operator' }), 'Registry submit 已触发')}>Submit Registry</button>}
            {release?.status === 'registry_listed' && <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" disabled={busy === 'smoke'} onClick={() => runAction('smoke', () => mcpServerReleasesApi.runProdSmoke(release.id, { actor: 'operator' }), 'Prod smoke 已触发')}>Run prod smoke</button>}
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <Fact label="Transport"><StateBadge tone={mcpReleaseTone(server.status)}>{server.transport_kind}</StateBadge></Fact>
          <Fact label="Package">{server.package_name}</Fact>
          <Fact label="Latest">{release?.package_version || 'no release'}</Fact>
          <Fact label="Updated">{formatMcpTime(server.updated_at)}</Fact>
        </div>
      </section>

      <nav className="flex flex-wrap gap-2">
        {(['overview', 'releases', 'configs', 'registries', 'ai', 'clients', 'evidence', 'events'] as DetailTab[]).map((item) => (
          <button key={item} type="button" className={`rounded-full border px-4 py-2 text-sm ${tab === item ? 'border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] text-[color:var(--ops-state-running-text)]' : 'border-[color:var(--ops-stroke-soft)] text-[color:var(--ops-text-muted)]'}`} onClick={() => setTab(item)}>{tabLabel(item)}</button>
        ))}
      </nav>

      {tab === 'overview' && <OverviewTab server={server} release={release} />}
      {tab === 'releases' && <ReleasesTab release={release} />}
      {tab === 'configs' && <McpSurfaceConfigsPanel release={release} readiness={readiness} onReload={load} />}
      {tab === 'registries' && <SurfaceTab title="Official Registry / Directories" surfaces={(release?.surfaces || []).filter((surface) => ['official_registry', 'directory', 'artifact'].includes(surface.category))} release={release} readiness={readiness} onSubmit={(surface) => submitSurface(surface)} />}
      {tab === 'ai' && <SurfaceTab title="AI Platforms" surfaces={(release?.surfaces || []).filter((surface) => surface.category === 'llm_platform')} release={release} readiness={readiness} onSubmit={(surface) => submitSurface(surface)} />}
      {tab === 'clients' && <SurfaceTab title="Client Configs" surfaces={(release?.surfaces || []).filter((surface) => surface.category === 'client_config')} release={release} readiness={readiness} onSubmit={(surface) => submitSurface(surface)} />}
      {tab === 'evidence' && <EvidenceTab release={release} />}
      {tab === 'events' && <EventsTab events={events} />}

      <OverlayModal open={releaseOpen} title="新增 MCP Release" description="为当前 MCP Server 创建一个版本发布账本。" onClose={() => setReleaseOpen(false)}>
        <div className="space-y-4">
          <TextField label="Package version" value={draftRelease.package_version} onChange={(value) => setDraftRelease({ ...draftRelease, package_version: value })} />
          <div>
            <FieldLabel>Release notes</FieldLabel>
            <textarea className="mt-2 min-h-28 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3" value={draftRelease.release_notes} onChange={(event) => setDraftRelease({ ...draftRelease, release_notes: event.target.value })} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => setReleaseOpen(false)}>取消</button>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" disabled={busy === 'create-release'} onClick={createRelease}>创建 Release</button>
          </div>
        </div>
      </OverlayModal>

      <OverlayModal open={publishOpen} title="Publish MCP npm package" description={`输入 ${expectedPhrase} 后，本地 runner 才会执行 npm publish。`} onClose={() => setPublishOpen(false)}>
        <div className="space-y-4">
          <TextField label="Confirmation phrase" value={confirmPhrase} onChange={setConfirmPhrase} mono />
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => setPublishOpen(false)}>取消</button>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" disabled={!release || busy === 'publish' || confirmPhrase !== expectedPhrase} onClick={() => release && runAction('publish', () => mcpServerReleasesApi.publishNpm(release.id, { actor: 'operator', confirm_phrase: confirmPhrase }), 'npm publish 已触发').then(() => setPublishOpen(false))}>触发 npm publish</button>
          </div>
        </div>
      </OverlayModal>
    </div>
  )

  function submitSurface(surface: McpServerSurface) {
    if (!release) return
    runAction(
      `submit-${surface.surface_key}`,
      () => mcpServerReleasesApi.submitSurface(release.id, { surface_key: surface.surface_key, actor: 'operator' }),
      '提交状态已记录',
    )
  }
}

function OverviewTab({ server, release }: Readonly<{ server: McpServer; release: McpServerRelease | null }>) {
  return <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]"><InfoPanel title="Server" eyebrow="catalog"><KeyValue label="Repo" value={server.repo_url} action={() => openExternalUrl(server.repo_url)} /><KeyValue label="Install command" value={server.install_command} mono /><KeyValue label="Tools" value={server.tools.join(', ') || '-'} /></InfoPanel><InfoPanel title="Latest release" eyebrow="release ledger"><KeyValue label="Status" value={release?.status || 'no release'} /><KeyValue label="npm URL" value={release?.package_url || 'blocked_missing_artifact'} action={release?.package_url ? () => openExternalUrl(release.package_url) : undefined} /><KeyValue label="Registry URL" value={release?.registry_url || 'pending'} action={release?.registry_url ? () => openExternalUrl(release.registry_url) : undefined} /></InfoPanel></div>
}

function ReleasesTab({ release }: Readonly<{ release: McpServerRelease | null }>) {
  if (!release) return <EmptyPane>当前 MCP Server 还没有 release 账本。</EmptyPane>
  return <InfoPanel title="Latest Release" eyebrow="version history v1"><KeyValue label="Version" value={release.package_version} mono /><KeyValue label="Status" value={MCP_STATUS_LABEL[release.status] || release.status} /><KeyValue label="Failure" value={release.failure_summary || '-'} /></InfoPanel>
}

function SurfaceTab({ title, surfaces, release, readiness, onSubmit }: Readonly<{ title: string; surfaces: McpServerSurface[]; release: McpServerRelease | null; readiness: McpSubmissionReadiness | null; onSubmit: (surface: McpServerSurface) => void }>) {
  if (!release) return <EmptyPane>创建 release 后才会生成平台提交账本。</EmptyPane>
  return <InfoPanel title={title} eyebrow="submission ledger"><div className="grid gap-3 lg:grid-cols-2">{surfaces.map((surface) => <SurfaceCard key={surface.surface_key} surface={surface} readinessStatus={readiness?.items.find((item) => item.surface_key === surface.surface_key)?.readiness_status || null} readinessReason={readiness?.items.find((item) => item.surface_key === surface.surface_key)?.reason || null} onSubmit={() => onSubmit(surface)} />)}</div></InfoPanel>
}

function SurfaceCard({ surface, readinessStatus, readinessReason, onSubmit }: Readonly<{ surface: McpServerSurface; readinessStatus: string | null; readinessReason: string | null; onSubmit: () => void }>) {
  const blocked = surface.status.startsWith('blocked_') || readinessStatus !== 'submit_eligible'
  return <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3"><div className="flex items-start justify-between gap-3"><div><div className="font-semibold text-[color:var(--ops-text-title)]">{surface.surface_label}</div><div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{surface.category} · {surface.surface_key}</div></div><StateBadge tone={mcpReleaseTone(surface.status)}>{MCP_STATUS_LABEL[surface.status] || surface.status}</StateBadge></div>{surface.submission_url && <button type="button" className="mt-2 break-all text-left text-sm text-cyan-100 hover:underline" onClick={() => openExternalUrl(surface.submission_url)}>{surface.submission_url}</button>}{readinessStatus && <div className="mt-2 font-mono text-xs text-[color:var(--ops-text-caption)]">readiness: {readinessStatus}</div>}{readinessReason && <div className="mt-2 text-sm text-amber-100">{readinessReason}</div>}{surface.failure_reason && <div className="mt-2 text-sm text-rose-100">{surface.failure_reason}</div>}<div className="mt-3 flex justify-end"><button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50" disabled={blocked || surface.category === 'artifact'} onClick={onSubmit}>记录提交</button></div></div>
}

function EvidenceTab({ release }: Readonly<{ release: McpServerRelease | null }>) {
  return <InfoPanel title="Smoke Evidence" eyebrow="production validation"><pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 text-xs text-[color:var(--ops-text-muted)]">{JSON.stringify(release?.smoke_evidence || {}, null, 2)}</pre></InfoPanel>
}

function EventsTab({ events }: Readonly<{ events: McpServerReleaseEvent[] }>) {
  return <InfoPanel title="Events" eyebrow="append-only timeline"><div className="max-h-[520px] space-y-2 overflow-auto">{events.map((event) => <div key={event.id} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3"><div className="flex items-start justify-between gap-3"><div className="font-semibold text-[color:var(--ops-text-title)]">{event.action}</div><div className="text-xs text-[color:var(--ops-text-caption)]">{formatMcpTime(event.created_at)}</div></div><div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{`${event.from_status || '-'} -> ${event.to_status || '-'}`}</div>{event.error_summary && <div className="mt-2 text-sm text-rose-100">{event.error_summary}</div>}</div>)}</div></InfoPanel>
}

function Fact({ label, children }: Readonly<{ label: string; children: ReactNode }>) {
  return <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--ops-text-caption)]">{label}</div><div className="mt-2 text-sm text-[color:var(--ops-text-title)]">{children}</div></div>
}

function InfoPanel({ title, eyebrow, children }: Readonly<{ title: string; eyebrow: string; children: ReactNode }>) {
  return <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5"><div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{eyebrow}</div><h3 className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{title}</h3><div className="mt-4 space-y-3">{children}</div></section>
}

function KeyValue({ label, value, mono, action }: Readonly<{ label: string; value: string; mono?: boolean; action?: () => void }>) {
  return <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3"><div className="text-xs text-[color:var(--ops-text-caption)]">{label}</div><button type="button" className={`mt-1 break-all text-left text-sm ${mono ? 'font-mono' : ''} ${action ? 'text-cyan-100 hover:underline' : 'text-[color:var(--ops-text-title)]'}`} onClick={action}>{value}</button></div>
}

function TextField({ label, value, onChange, mono }: Readonly<{ label: string; value: string; onChange: (value: string) => void; mono?: boolean }>) {
  return <div><FieldLabel>{label}</FieldLabel><input className={`mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 ${mono ? 'font-mono' : ''}`} value={value} onChange={(event) => onChange(event.target.value)} /></div>
}

function tabLabel(tab: DetailTab) {
  return {
    overview: 'Overview',
    releases: 'Releases',
    configs: 'Configs',
    registries: 'Registries',
    ai: 'AI Platforms',
    clients: 'Client Configs',
    evidence: 'Smoke Evidence',
    events: 'Events',
  }[tab]
}
