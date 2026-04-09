import { useEffect, useState } from 'react'
import { api, DashboardStats, OrgNode, OrgTree } from '../api'

/* ── Color mapping ──────────────────────────────────────────── */
const COLOR_MAP: Record<string, { bg: string; border: string; tag: string; tagText: string; lightBg: string }> = {
  amber:  { bg: 'bg-amber-50',  border: 'border-amber-300',  tag: 'bg-amber-100',  tagText: 'text-amber-700',  lightBg: 'bg-amber-50' },
  green:  { bg: 'bg-green-50',  border: 'border-green-300',  tag: 'bg-green-100',  tagText: 'text-green-700',  lightBg: 'bg-green-50' },
  blue:   { bg: 'bg-blue-50',   border: 'border-blue-300',   tag: 'bg-blue-100',   tagText: 'text-blue-700',   lightBg: 'bg-blue-50' },
  purple: { bg: 'bg-purple-50', border: 'border-purple-300', tag: 'bg-purple-100', tagText: 'text-purple-700', lightBg: 'bg-purple-50' },
  sky:    { bg: 'bg-sky-50',    border: 'border-sky-300',    tag: 'bg-sky-100',    tagText: 'text-sky-700',    lightBg: 'bg-sky-50' },
  rose:   { bg: 'bg-rose-50',   border: 'border-rose-300',   tag: 'bg-rose-100',   tagText: 'text-rose-700',   lightBg: 'bg-rose-50' },
  indigo: { bg: 'bg-indigo-50', border: 'border-indigo-300', tag: 'bg-indigo-100', tagText: 'text-indigo-700', lightBg: 'bg-indigo-50' },
  gray:   { bg: 'bg-gray-50',   border: 'border-gray-300',   tag: 'bg-gray-100',   tagText: 'text-gray-700',   lightBg: 'bg-gray-50' },
}

function getColor(color?: string) {
  return COLOR_MAP[color || 'gray'] || COLOR_MAP.gray
}

export default function OrgChart() {
  const [orgTree, setOrgTree] = useState<OrgTree | null>(null)
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [expandedDomains, setExpandedDomains] = useState<Set<string>>(new Set())

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [tree, s] = await Promise.all([api.getOrgTree(), api.getStats()])
      setOrgTree(tree)
      setStats(s)
      // Auto-expand all domains
      if (tree?.root?.children) {
        setExpandedDomains(new Set(tree.root.children.map(d => d.id)))
      }
    } catch {
      setError('无法连接后端，请启动 sh scripts/local/start.sh')
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleSync = async () => {
    await api.syncAgents()
    await load()
  }

  const toggleDomain = (id: string) => {
    setExpandedDomains(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectedDetail = selectedNode && orgTree
    ? findNode(orgTree.root, selectedNode) : null

  /* ── Loading skeleton ──────────────────────────────────────── */
  if (loading) {
    return (
      <div data-testid="orgchart-skeleton" className="space-y-6 animate-pulse">
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-20 bg-gray-200 rounded-lg" />)}
        </div>
        <div className="flex justify-center"><div className="w-40 h-16 bg-gray-200 rounded-lg" /></div>
        <div className="grid grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-32 bg-gray-100 rounded-lg" />)}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div data-testid="orgchart-error" className="py-20 text-center">
        <p className="mb-4 text-lg text-red-600">{error}</p>
        <button onClick={load} className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700">重试</button>
      </div>
    )
  }

  if (!orgTree) {
    return (
      <div data-testid="orgchart-empty" className="py-20 text-center">
        <p className="mb-4 text-gray-500">暂无组织数据</p>
        <button onClick={handleSync} className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700">同步 Roles</button>
      </div>
    )
  }

  const root = orgTree.root
  const groups = root.children || []

  return (
    <div data-testid="orgchart-page">
      {/* ── Stats bar ──────────────────────────────────────── */}
      {stats && (
        <div data-testid="stats-bar" className="grid grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Agent 总数', value: stats.agent_count, cls: 'bg-blue-50 border-blue-200' },
            { label: '任务总数', value: stats.task_total, cls: 'bg-gray-50 border-gray-200' },
            { label: '已完成', value: stats.task_completed, cls: 'bg-green-50 border-green-200' },
            { label: '待审批', value: stats.approval_pending, cls: 'bg-yellow-50 border-yellow-200' },
          ].map((s) => (
            <div key={s.label} className={`border rounded-lg p-4 ${s.cls}`}>
              <div className="text-2xl font-bold" data-testid={`stat-${s.label}`}>{s.value}</div>
              <div className="text-sm text-gray-600">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">全局组织架构</h2>
        <button onClick={handleSync} className="px-4 py-2 text-sm text-white bg-blue-600 rounded hover:bg-blue-700">
          同步 Roles
        </button>
      </div>

      <div data-testid="org-root" className="p-5 mb-6 border rounded-xl bg-slate-50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-sm font-semibold text-slate-900">{root.display_name}</div>
            <div className="mt-1 text-sm text-slate-600">{root.goal}</div>
          </div>
          <button
            data-testid="root-detail-toggle"
            className="px-3 py-2 text-sm border rounded hover:bg-white"
            onClick={() => setSelectedNode(selectedNode === root.id ? null : root.id)}
          >
            查看详情
          </button>
        </div>
        <div className="mt-3 text-xs text-slate-500">
          动态分组: {groups.length} · 真实角色: {groups.reduce((count, group) => count + (group.children?.length || 0), 0)}
        </div>
      </div>

      <div data-testid="group-grid" className="grid gap-4 lg:grid-cols-2">
        {groups.map(group => {
          const c = getColor(group.color)
          const isExpanded = expandedDomains.has(group.id)
          const isSelected = selectedNode === group.id
          return (
            <section key={group.id} data-testid={`group-${group.id}`} className={`rounded-xl border-2 p-4 ${c.bg} ${c.border}`}>
              <div
                className={`rounded-lg border bg-white px-4 py-3 cursor-pointer transition-all duration-200
                  ${isSelected ? 'ring-2 ring-blue-500 scale-105 shadow-md' : 'hover:shadow-md hover:-translate-y-0.5'}`}
                onClick={() => {
                  toggleDomain(group.id)
                  setSelectedNode(isSelected ? null : group.id)
                }}
              >
                <div className="mt-1 text-sm font-bold">{group.display_name}</div>
                <div className="text-xs text-gray-500 mt-0.5">{group.children?.length || 0} 个角色</div>
                <div className="mt-1 text-xs">{isExpanded ? '▼' : '▶'}</div>
              </div>
              {isExpanded && (
                <div className="grid gap-3 mt-4 md:grid-cols-2">
                  {(group.children || []).map(agent => (
                    <div
                      key={agent.id}
                      data-testid={`node-${agent.id}`}
                      className={`bg-white rounded-md px-3 py-3 border cursor-pointer transition-all duration-200
                        ${selectedNode === agent.id ? 'ring-2 ring-blue-500 scale-[1.02] shadow-sm' : 'hover:shadow-sm'}`}
                      onClick={() => setSelectedNode(selectedNode === agent.id ? null : agent.id)}
                    >
                      <div className="text-sm font-medium">{agent.display_name}</div>
                      <div className="mt-1 text-xs text-gray-500 line-clamp-2">{agent.goal}</div>
                      {agent.skills && agent.skills.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {agent.skills.slice(0, 4).map(skill => (
                            <span key={skill} className={`text-[10px] px-1.5 py-0.5 rounded ${c.tag} ${c.tagText}`}>{skill}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </section>
          )
        })}
      </div>

      {/* ── Selected node detail ───────────────────────────── */}
      {selectedDetail && (
        <div data-testid="node-detail" className="p-5 mt-6 bg-white border rounded-lg shadow-sm">
          <h3 className="mb-2 text-lg font-bold">节点详情</h3>
          <NodeDetailView node={selectedDetail} />
        </div>
      )}
    </div>
  )
}

/* ── Node detail view ────────────────────────────────────────── */
function NodeDetailView({ node }: { node: OrgNode }) {
  const c = getColor(node.color)
  return (
    <div data-testid={`detail-${node.id}`}>
      <div className="flex items-center gap-3 mb-2">
        {node.icon && <span className="text-2xl">{node.icon}</span>}
        <div>
          <h4 className="text-lg font-bold">{node.display_name}</h4>
          <span className={`text-xs px-2 py-0.5 rounded ${c.tag} ${c.tagText}`}>{node.type}</span>
          <span className="ml-2 font-mono text-xs text-gray-400">{node.id}</span>
        </div>
      </div>
      <p className="mb-3 text-sm text-gray-600">{node.goal}</p>
      {node.project && (
        <p className="mb-2 text-xs text-gray-400">项目: <span className="font-mono">{node.project}</span></p>
      )}
      {node.skills && node.skills.length > 0 && (
        <div className="flex gap-1.5 flex-wrap mb-3">
          {node.skills.map(s => (
            <span key={s} className={`text-xs px-2 py-0.5 rounded ${c.tag} ${c.tagText}`}>{s}</span>
          ))}
        </div>
      )}
      {node.children && node.children.length > 0 && (
        <div className="text-xs text-gray-500">
          下级节点: {node.children.map(c => c.display_name).join(', ')}
        </div>
      )}
    </div>
  )
}

/* ── Helper: find node by id in tree ─────────────────────────── */
function findNode(node: OrgNode, id: string): OrgNode | null {
  if (node.id === id) return node
  for (const child of node.children || []) {
    const found = findNode(child, id)
    if (found) return found
  }
  return null
}
