import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { McpServer, McpServerPage, mcpServerReleasesApi } from '../mcpServerReleasesApi'
import { EmptyPane, FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { MCP_STATUS_LABEL, directoryProgress, mcpReleaseTone, openExternalUrl } from './mcpServerReleaseUi'

const PAGE_SIZE = 10

function emptyPage(): McpServerPage {
  return { items: [], total: 0, page: 1, page_size: PAGE_SIZE, total_pages: 0 }
}

export default function McpServersPanel({ search }: Readonly<{ search: string }>) {
  const toast = useToast()
  const navigate = useNavigate()
  const [pageData, setPageData] = useState<McpServerPage>(emptyPage())
  const [page, setPage] = useState(1)
  const [transport, setTransport] = useState('')
  const [surfaceCategory, setSurfaceCategory] = useState('')
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [draft, setDraft] = useState(defaultServerDraft())

  const load = async () => {
    setLoading(true)
    try {
      setPageData(await mcpServerReleasesApi.listCatalog({
        page,
        page_size: PAGE_SIZE,
        search: search.trim() || undefined,
        transport_kind: transport || undefined,
        surface_category: surfaceCategory || undefined,
      }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch((error) => toast.error(error instanceof Error ? error.message : '加载 MCP Server 矩阵失败'))
  }, [page, search, transport, surfaceCategory])

  useEffect(() => {
    setPage(1)
  }, [search, transport, surfaceCategory])

  const createServer = async () => {
    setBusy('create-server')
    try {
      const created = await mcpServerReleasesApi.createServer({ ...draft, tools: splitTools(draft.toolsText) })
      toast.success('MCP Server 已加入注册矩阵')
      setCreateOpen(false)
      setDraft(defaultServerDraft())
      navigate(`/releases/mcp-servers/${created.id}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建 MCP Server 失败')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4" data-testid="mcp-servers-panel">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={transport} onChange={(event) => setTransport(event.target.value)}>
            <option value="">全部 Transport</option>
            <option value="stdio">stdio</option>
            <option value="remote_http">remote_http</option>
            <option value="both">both</option>
          </select>
          <select className="rounded-full border border-[color:var(--ops-stroke-soft)] px-4 py-2 text-sm" value={surfaceCategory} onChange={(event) => setSurfaceCategory(event.target.value)}>
            <option value="">全部 Surface</option>
            <option value="artifact">Artifact</option>
            <option value="official_registry">Official Registry</option>
            <option value="directory">Directories</option>
            <option value="llm_platform">AI Platforms</option>
            <option value="client_config">Client Configs</option>
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm font-semibold" onClick={() => openExternalUrl('https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server')}>MCP GitHub repo</button>
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white" onClick={() => setCreateOpen(true)}>新增 MCP Server</button>
        </div>
      </div>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-5 py-4">
          <div>
            <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">MCP Server Registry Matrix</div>
            <div className="mt-2 text-sm text-[color:var(--ops-text-muted)]">
              多 MCP 仓库统一跟踪 npm artifact、Official MCP Registry、目录收录、OpenAI / Claude remote MCP readiness 和证据。
            </div>
          </div>
          <div className="text-sm text-[color:var(--ops-text-muted)]">共 {pageData.total} 个 server · 第 {pageData.page || page} / {pageData.total_pages || 1} 页</div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-[color:var(--ops-stroke-soft)] text-left text-sm">
            <thead className="bg-[color:var(--ops-panel-subtle)] text-xs uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">
              <tr>
                <th className="px-5 py-3">Server / Repo</th>
                <th className="px-5 py-3">Package</th>
                <th className="px-5 py-3">Transport</th>
                <th className="px-5 py-3">Latest</th>
                <th className="px-5 py-3">Official Registry</th>
                <th className="px-5 py-3">AI Platforms</th>
                <th className="px-5 py-3">Directories</th>
                <th className="px-5 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
              {pageData.items.map((item) => <McpServerRow key={item.id} item={item} onOpen={() => navigate(`/releases/mcp-servers/${item.id}`)} />)}
              {!loading && !pageData.items.length && (
                <tr>
                  <td colSpan={8} className="px-5 py-8">
                    <EmptyPane>还没有 MCP Server。先加入一个仓库，再创建 release 和 registry 提交账本。</EmptyPane>
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

      <OverlayModal open={createOpen} title="新增 MCP Server" description="把一个 MCP 仓库加入发布矩阵；真实发布仍由 release 和本地 runner 控制。" onClose={() => setCreateOpen(false)}>
        <div className="grid gap-4 md:grid-cols-2">
          <TextField label="Server key" value={draft.server_key} onChange={(value) => setDraft({ ...draft, server_key: value })} />
          <TextField label="Server name" value={draft.server_name} onChange={(value) => setDraft({ ...draft, server_name: value })} />
          <TextField label="Repo full name" value={draft.repo_full_name} onChange={(value) => setDraft({ ...draft, repo_full_name: value })} />
          <TextField label="Repo URL" value={draft.repo_url} onChange={(value) => setDraft({ ...draft, repo_url: value })} />
          <TextField label="Package name" value={draft.package_name} onChange={(value) => setDraft({ ...draft, package_name: value })} />
          <TextField label="Registry name" value={draft.registry_name} onChange={(value) => setDraft({ ...draft, registry_name: value })} />
          <div>
            <FieldLabel>Transport</FieldLabel>
            <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3" value={draft.transport_kind} onChange={(event) => setDraft({ ...draft, transport_kind: event.target.value })}>
              <option value="stdio">stdio</option>
              <option value="remote_http">remote_http</option>
              <option value="both">both</option>
            </select>
          </div>
          <TextField label="Remote endpoint" value={draft.remote_endpoint_url || ''} onChange={(value) => setDraft({ ...draft, remote_endpoint_url: value })} />
          <TextField label="Install command" value={draft.install_command} onChange={(value) => setDraft({ ...draft, install_command: value })} wide />
          <TextField label="Tools" value={draft.toolsText} onChange={(value) => setDraft({ ...draft, toolsText: value })} wide />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => setCreateOpen(false)}>取消</button>
          <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" disabled={busy === 'create-server'} onClick={createServer}>加入矩阵</button>
        </div>
      </OverlayModal>
    </div>
  )
}

function McpServerRow({ item, onOpen }: Readonly<{ item: McpServer; onOpen: () => void }>) {
  const latest = item.latest_release
  const surfaces = latest?.surfaces || []
  const official = surfaces.find((surface) => surface.surface_key === 'official_mcp_registry')
  const aiStatuses = surfaces.filter((surface) => surface.category === 'llm_platform').map((surface) => surface.status)
  const directoryStatuses = surfaces.filter((surface) => surface.category === 'directory').map((surface) => surface.status)
  return (
    <tr className="align-top">
      <td className="px-5 py-4">
        <button type="button" className="font-semibold text-[color:var(--ops-text-title)] hover:underline" onClick={onOpen}>{item.server_name}</button>
        <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.repo_full_name}</div>
      </td>
      <td className="px-5 py-4"><div className="font-mono text-xs">{item.package_name}</div><div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{item.registry_name}</div></td>
      <td className="px-5 py-4"><StateBadge tone={mcpReleaseTone(item.transport_kind === 'stdio' ? 'ready' : 'delivered')}>{item.transport_kind}</StateBadge></td>
      <td className="px-5 py-4">{latest ? <div><div className="font-mono text-xs">{latest.package_version}</div><StateBadge tone={mcpReleaseTone(latest.status)}>{MCP_STATUS_LABEL[latest.status] || latest.status}</StateBadge></div> : <span className="text-[color:var(--ops-text-caption)]">no release</span>}</td>
      <td className="px-5 py-4"><StateBadge tone={mcpReleaseTone(official?.status)}>{MCP_STATUS_LABEL[official?.status || 'candidate'] || official?.status || 'candidate'}</StateBadge></td>
      <td className="px-5 py-4">{aiStatuses.length ? directoryProgress(aiStatuses) : '-'}</td>
      <td className="px-5 py-4">{directoryStatuses.length ? directoryProgress(directoryStatuses) : '-'}</td>
      <td className="px-5 py-4 text-right"><button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={onOpen}>详情</button></td>
    </tr>
  )
}

function TextField({ label, value, onChange, wide }: Readonly<{ label: string; value: string; onChange: (value: string) => void; wide?: boolean }>) {
  return <div className={wide ? 'md:col-span-2' : ''}><FieldLabel>{label}</FieldLabel><input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3" value={value} onChange={(event) => onChange(event.target.value)} /></div>
}

function splitTools(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function defaultServerDraft() {
  return {
    server_key: 'synapse-network-mcp-server',
    server_name: 'SynapseNetwork MCP Server',
    repo_full_name: 'SynapseNetworkAI/Synapse-Network-MCP-Server',
    repo_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server',
    package_name: '@synapse-network-ai/mcp-server',
    package_registry: 'npm',
    registry_name: 'io.github.synapsenetworkai/synapse-network-mcp-server',
    transport_kind: 'stdio',
    remote_endpoint_url: '',
    install_command: 'npx -y @synapse-network-ai/mcp-server',
    toolsText: 'discover_services, invoke_and_pay, get_receipt',
  }
}
