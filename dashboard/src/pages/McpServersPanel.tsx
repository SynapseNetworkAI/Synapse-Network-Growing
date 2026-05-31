import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { McpServerRelease, McpServerReleasePage, mcpServerReleasesApi } from '../mcpServerReleasesApi'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { MCP_STATUS_LABEL, MCP_STATUS_OPTIONS, directoryProgress, formatMcpTime, isSemVer, mcpReleaseTone, openExternalUrl } from './mcpServerReleaseUi'

const PAGE_SIZE = 10

function emptyPage(): McpServerReleasePage {
  return { items: [], total: 0, page: 1, page_size: PAGE_SIZE, total_pages: 0 }
}

export default function McpServersPanel({ search }: Readonly<{ search: string }>) {
  const toast = useToast()
  const navigate = useNavigate()
  const [pageData, setPageData] = useState<McpServerReleasePage>(emptyPage())
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [draft, setDraft] = useState({ package_version: '0.1.0', release_notes: '' })

  const load = async () => {
    setLoading(true)
    try {
      setPageData(await mcpServerReleasesApi.list({ page, page_size: PAGE_SIZE, search: search.trim() || undefined, status: status || undefined }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 MCP Server 发布记录失败'))
  }, [page, status, search])

  useEffect(() => {
    setPage(1)
  }, [search])

  const createRecord = async () => {
    if (!isSemVer(draft.package_version)) {
      toast.error('版本格式必须是 SemVer，例如 0.1.0')
      return
    }
    setBusy('create')
    try {
      const created = await mcpServerReleasesApi.create({
        package_version: draft.package_version.trim(),
        release_notes: draft.release_notes || null,
      })
      toast.success('MCP Server 发布记录已创建')
      setCreateOpen(false)
      setDraft({ package_version: '0.1.0', release_notes: '' })
      navigate(`/releases/mcp-servers/${created.id}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建失败')
    } finally {
      setBusy(null)
    }
  }

  const runReadiness = async (item: McpServerRelease) => {
    setBusy(`readiness-${item.id}`)
    try {
      await mcpServerReleasesApi.runReadiness(item.id, { actor: 'operator' })
      toast.success('Readiness 已触发，本地 MCP runner 会回写结果')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '触发 readiness 失败')
    } finally {
      setBusy(null)
    }
  }

  const sync = async () => {
    setBusy('sync')
    try {
      await mcpServerReleasesApi.syncStatuses()
      toast.success('MCP release 状态已同步')
      await load()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '同步失败')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4" data-testid="mcp-servers-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={status} onChange={(event) => {
            setStatus(event.target.value)
            setPage(1)
          }}>
            {MCP_STATUS_OPTIONS.map((item) => <option key={item || 'all'} value={item}>{item ? MCP_STATUS_LABEL[item] : '全部状态'}</option>)}
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-state-running-border)] px-4 py-2.5 text-sm font-semibold text-[color:var(--ops-state-running-text)]" onClick={sync} disabled={busy === 'sync'}>同步状态</button>
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm font-semibold" onClick={() => openExternalUrl('https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server')}>MCP GitHub repo</button>
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => setCreateOpen(true)}>新增 MCP 发布</button>
        </div>
      </div>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">MCP Server Release Ledger</div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
              独立管理 MCP npm artifact、official MCP Registry、prod smoke 和目录分发；不混入 SDK Packages。
            </div>
          </div>
          <div className="text-sm text-[color:var(--ops-text-muted)]">共 {pageData.total} 条 · 第 {pageData.page || page} / {pageData.total_pages || 1} 页</div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[color:var(--ops-stroke-soft)] text-left text-sm">
            <thead className="bg-[color:var(--ops-panel-subtle)] text-xs uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">
              <tr>
                <th className="px-5 py-3">Server / Version</th>
                <th className="px-5 py-3">npm</th>
                <th className="px-5 py-3">Registry</th>
                <th className="px-5 py-3">Prod Smoke</th>
                <th className="px-5 py-3">Directories</th>
                <th className="px-5 py-3">更新时间</th>
                <th className="px-5 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
              {pageData.items.map((item) => <McpRow key={item.id} item={item} busy={busy} onOpen={() => navigate(`/releases/mcp-servers/${item.id}`)} onReadiness={() => runReadiness(item)} />)}
              {!loading && !pageData.items.length && (
                <tr>
                  <td colSpan={7} className="px-5 py-8">
                    <EmptyPane>创建 SynapseNetwork MCP Server 的 npm + MCP Registry 发布记录。</EmptyPane>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="flex items-center justify-end gap-2">
        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-sm disabled:opacity-50" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-sm disabled:opacity-50" disabled={page >= (pageData.total_pages || 1)} onClick={() => setPage((value) => value + 1)}>下一页</button>
      </div>

      <OverlayModal open={createOpen} title="新增 MCP Server 发布" description="创建 npm stdio MCP server 发布记录；实际 publish 由本地 runner 执行。" onClose={() => setCreateOpen(false)}>
        <div className="space-y-4">
          <div>
            <FieldLabel>Package version</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3" value={draft.package_version} onChange={(event) => setDraft({ ...draft, package_version: event.target.value })} />
          </div>
          <div>
            <FieldLabel>Release notes</FieldLabel>
            <textarea className="mt-2 min-h-28 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3" value={draft.release_notes} onChange={(event) => setDraft({ ...draft, release_notes: event.target.value })} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => setCreateOpen(false)}>取消</button>
            <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" disabled={busy === 'create'} onClick={createRecord}>创建发布记录</button>
          </div>
        </div>
      </OverlayModal>
    </div>
  )
}

function McpRow({ item, busy, onOpen, onReadiness }: Readonly<{ item: McpServerRelease; busy: string | null; onOpen: () => void; onReadiness: () => void }>) {
  const statuses = item.surfaces.map((surface) => surface.status)
  const smokeStatus = Object.keys(item.smoke_evidence || {}).length ? String(item.smoke_evidence.status || 'recorded') : '-'
  return (
    <tr className="align-top">
      <td className="px-5 py-4">
        <button type="button" className="font-semibold text-[color:var(--ops-text-title)] hover:underline" onClick={onOpen}>{item.server_name}</button>
        <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.package_version} · {item.package_registry}</div>
        <div className="mt-2"><StateBadge tone={mcpReleaseTone(item.status)}>{MCP_STATUS_LABEL[item.status] || item.status}</StateBadge></div>
      </td>
      <td className="px-5 py-4"><div className="font-mono text-xs">{item.package_name}</div><div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.package_url ? 'published' : 'pending'}</div></td>
      <td className="px-5 py-4"><div className="font-mono text-xs">{item.registry_name}</div><div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.registry_url ? 'listed' : 'pending'}</div></td>
      <td className="px-5 py-4">{smokeStatus}</td>
      <td className="px-5 py-4">{directoryProgress(statuses)}</td>
      <td className="px-5 py-4 text-[color:var(--ops-text-muted)]">{formatMcpTime(item.updated_at)}</td>
      <td className="px-5 py-4 text-right">
        <div className="flex justify-end gap-2">
          <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={onOpen}>详情</button>
          {item.status === 'planned' && <button type="button" className="rounded-lg border border-cyan-300/35 px-3 py-2 text-sm text-cyan-100" disabled={busy === `readiness-${item.id}`} onClick={onReadiness}>Run readiness</button>}
        </div>
      </td>
    </tr>
  )
}
