import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { McpServerRelease, McpServerReleaseEvent, mcpServerReleasesApi } from '../mcpServerReleasesApi'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { MCP_STATUS_LABEL, formatMcpTime, mcpReleaseTone, openExternalUrl } from './mcpServerReleaseUi'

export default function McpServerReleaseDetailPage() {
  const { id } = useParams()
  const releaseId = Number(id)
  const navigate = useNavigate()
  const toast = useToast()
  const [item, setItem] = useState<McpServerRelease | null>(null)
  const [events, setEvents] = useState<McpServerReleaseEvent[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [publishOpen, setPublishOpen] = useState(false)
  const [confirmPhrase, setConfirmPhrase] = useState('')

  const load = async () => {
    const [nextItem, nextEvents] = await Promise.all([
      mcpServerReleasesApi.get(releaseId),
      mcpServerReleasesApi.events(releaseId),
    ])
    setItem(nextItem)
    setEvents(nextEvents)
  }

  useEffect(() => {
    if (!Number.isFinite(releaseId)) return
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 MCP 发布详情失败'))
  }, [releaseId])

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

  if (!item) return <EmptyPane>记录不存在或仍在加载。</EmptyPane>

  const expectedPhrase = `PUBLISH_MCP_${item.package_version}`
  const canPublishNpm = item.status === 'ready_to_publish'
  const canSubmitRegistry = item.status === 'npm_published'
  const canRunSmoke = item.status === 'registry_listed'
  const canComplete = item.status === 'directories_pending'

  return (
    <div className="space-y-5" data-testid="mcp-release-detail">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">MCP Server Release</div>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">{item.server_name}</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
              {'npm stdio package -> official MCP Registry -> prod smoke -> directory distribution. Secrets stay in local runner env.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => navigate('/releases?tab=mcp-servers')}>返回列表</button>
            {item.status === 'planned' && <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" disabled={busy === 'readiness'} onClick={() => runAction('readiness', () => mcpServerReleasesApi.runReadiness(item.id, { actor: 'operator' }), 'Readiness 已触发')}>Run readiness</button>}
            {canPublishNpm && <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => setPublishOpen(true)}>Publish npm</button>}
            {canSubmitRegistry && <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" disabled={busy === 'registry'} onClick={() => runAction('registry', () => mcpServerReleasesApi.submitRegistry(item.id, { actor: 'operator' }), 'Registry submit 已触发')}>Submit Registry</button>}
            {canRunSmoke && <button type="button" className="rounded-xl border border-cyan-300/35 px-4 py-2.5 text-sm text-cyan-100" disabled={busy === 'smoke'} onClick={() => runAction('smoke', () => mcpServerReleasesApi.runProdSmoke(item.id, { actor: 'operator' }), 'Prod smoke 已触发')}>Run prod smoke</button>}
            {canComplete && <button type="button" className="rounded-xl border border-emerald-300/35 px-4 py-2.5 text-sm text-emerald-100" disabled={busy === 'complete'} onClick={() => runAction('complete', () => mcpServerReleasesApi.complete(item.id, { actor: 'operator' }), 'MCP release 已完成')}>Complete</button>}
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-4">
          <Fact label="Status"><StateBadge tone={mcpReleaseTone(item.status)}>{MCP_STATUS_LABEL[item.status] || item.status}</StateBadge></Fact>
          <Fact label="Package">{item.package_name}</Fact>
          <Fact label="Version">{item.package_version}</Fact>
          <Fact label="Updated">{formatMcpTime(item.updated_at)}</Fact>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="space-y-4">
          <InfoPanel title="Package" eyebrow="npm artifact">
            <KeyValue label="Install command" value={item.install_command} mono />
            <KeyValue label="npm URL" value={item.package_url || 'pending'} action={item.package_url ? () => openExternalUrl(item.package_url) : undefined} />
            <KeyValue label="Git tag" value={item.git_tag || '-'} mono />
          </InfoPanel>
          <InfoPanel title="Registry" eyebrow="official MCP registry">
            <KeyValue label="Registry name" value={item.registry_name} mono />
            <KeyValue label="Registry URL" value={item.registry_url || 'pending'} action={item.registry_url ? () => openExternalUrl(item.registry_url) : undefined} />
          </InfoPanel>
          <InfoPanel title="Smoke Evidence" eyebrow="production validation">
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4 text-xs text-[color:var(--ops-text-muted)]">{JSON.stringify(item.smoke_evidence || {}, null, 2)}</pre>
          </InfoPanel>
        </section>
        <section className="space-y-4">
          <InfoPanel title="Directory Distribution" eyebrow="discovery surfaces">
            <div className="space-y-2">
              {item.surfaces.map((surface) => (
                <div key={surface.surface_key} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-[color:var(--ops-text-title)]">{surface.surface_label}</div>
                      <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{surface.surface_key}</div>
                    </div>
                    <StateBadge tone={mcpReleaseTone(surface.status)}>{surface.status}</StateBadge>
                  </div>
                  {surface.listing_url && <button type="button" className="mt-2 text-left text-sm text-cyan-100 hover:underline" onClick={() => openExternalUrl(surface.listing_url)}>{surface.listing_url}</button>}
                  {surface.failure_reason && <div className="mt-2 text-sm text-rose-100">{surface.failure_reason}</div>}
                </div>
              ))}
            </div>
          </InfoPanel>
          <InfoPanel title="Events" eyebrow="append-only timeline">
            <div className="max-h-[480px] space-y-2 overflow-auto">
              {events.map((event) => (
                <div key={event.id} className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="font-semibold text-[color:var(--ops-text-title)]">{event.action}</div>
                    <div className="text-xs text-[color:var(--ops-text-caption)]">{formatMcpTime(event.created_at)}</div>
                  </div>
                  <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{`${event.from_status || '-'} -> ${event.to_status || '-'}`}</div>
                  {event.error_summary && <div className="mt-2 text-sm text-rose-100">{event.error_summary}</div>}
                </div>
              ))}
            </div>
          </InfoPanel>
        </section>
      </div>

      <OverlayModal open={publishOpen} title="Publish MCP npm package" description={`输入 ${expectedPhrase} 后，本地 runner 才会执行 npm publish。`} onClose={() => setPublishOpen(false)}>
        <div className="space-y-4">
          <div>
            <FieldLabel>Confirmation phrase</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 font-mono" value={confirmPhrase} onChange={(event) => setConfirmPhrase(event.target.value)} placeholder={expectedPhrase} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => setPublishOpen(false)}>取消</button>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" disabled={busy === 'publish' || confirmPhrase !== expectedPhrase} onClick={() => {
              runAction('publish', () => mcpServerReleasesApi.publishNpm(item.id, { actor: 'operator', confirm_phrase: confirmPhrase }), 'npm publish 已触发').then(() => {
                setPublishOpen(false)
                setConfirmPhrase('')
              })
            }}>触发 npm publish</button>
          </div>
        </div>
      </OverlayModal>
    </div>
  )
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
