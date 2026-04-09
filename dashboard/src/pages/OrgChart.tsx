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
      <div data-testid="orgchart-skeleton" className="animate-pulse space-y-6">
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-20 bg-gray-200 rounded-lg" />)}
        </div>
        <div className="flex justify-center"><div className="h-16 w-40 bg-gray-200 rounded-lg" /></div>
        <div className="grid grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-32 bg-gray-100 rounded-lg" />)}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div data-testid="orgchart-error" className="text-center py-20">
        <p className="text-red-600 text-lg mb-4">{error}</p>
        <button onClick={load} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">重试</button>
      </div>
    )
  }

  if (!orgTree) {
    return (
      <div data-testid="orgchart-empty" className="text-center py-20">
        <p className="text-gray-500 mb-4">暂无组织数据</p>
        <button onClick={handleSync} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">同步 Roles</button>
      </div>
    )
  }

  const root = orgTree.root
  const domains = root.children || []

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
        <button onClick={handleSync} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          同步 Roles
        </button>
      </div>

      {/* ── Level 0: CTO node ──────────────────────────────── */}
      <div className="flex justify-center mb-1">
        <div
          data-testid="cto-node"
          className={`bg-gray-800 text-white rounded-lg px-6 py-3 text-center shadow-lg cursor-pointer transition-all duration-200
            ${selectedNode === root.id ? 'ring-2 ring-blue-400 scale-105' : 'hover:shadow-xl'}`}
          onClick={() => setSelectedNode(selectedNode === root.id ? null : root.id)}
        >
          <div className="text-lg font-bold">{root.icon} {root.display_name}</div>
          <div className="text-xs text-gray-300">{root.goal?.slice(0, 30)}</div>
        </div>
      </div>

      {/* ── Vertical connector ─────────────────────────────── */}
      <div className="flex justify-center"><div className="w-px h-5 bg-gray-300" /></div>

      {/* ── Horizontal fan-out line ────────────────────────── */}
      <div className="flex justify-center mb-1">
        <div className="border-t-2 border-gray-300" style={{ width: `${Math.min(domains.length * 18, 90)}%` }} />
      </div>

      {/* ── Level 1: Domain nodes ──────────────────────────── */}
      <div data-testid="domain-row" className="flex justify-center gap-4 mb-6 flex-wrap">
        {domains.map(domain => {
          const c = getColor(domain.color)
          const isExpanded = expandedDomains.has(domain.id)
          const isSelected = selectedNode === domain.id
          return (
            <div key={domain.id} className="flex flex-col items-center" style={{ minWidth: '140px', maxWidth: '200px', flex: '1 1 0' }}>
              {/* Vertical line down from fan-out */}
              <div className="w-px h-4 bg-gray-300" />
              <div
                data-testid={`domain-${domain.id}`}
                className={`rounded-lg border-2 px-4 py-3 text-center cursor-pointer transition-all duration-200 w-full
                  ${c.bg} ${c.border}
                  ${isSelected ? 'ring-2 ring-blue-500 scale-105 shadow-md' : 'hover:shadow-md hover:-translate-y-0.5'}`}
                onClick={() => {
                  toggleDomain(domain.id)
                  setSelectedNode(isSelected ? null : domain.id)
                }}
              >
                <div className="text-xl">{domain.icon}</div>
                <div className="font-bold text-sm mt-1">{domain.display_name}</div>
                <div className="text-xs text-gray-500 mt-0.5">{domain.children?.length || 0} 子节点</div>
                <div className="text-xs mt-1">{isExpanded ? '▼' : '▶'}</div>
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Level 2+: Expanded domain children ─────────────── */}
      {domains.filter(d => expandedDomains.has(d.id)).map(domain => (
        <DomainDetail
          key={domain.id}
          domain={domain}
          selectedNode={selectedNode}
          onSelectNode={(id) => setSelectedNode(selectedNode === id ? null : id)}
        />
      ))}

      {/* ── Selected node detail ───────────────────────────── */}
      {selectedDetail && (
        <div data-testid="node-detail" className="mt-6 bg-white border rounded-lg p-5 shadow-sm">
          <h3 className="text-lg font-bold mb-2">节点详情</h3>
          <NodeDetailView node={selectedDetail} />
        </div>
      )}
    </div>
  )
}

/* ── Domain expanded detail ──────────────────────────────────── */
function DomainDetail({ domain, selectedNode, onSelectNode }: {
  domain: OrgNode
  selectedNode: string | null
  onSelectNode: (id: string) => void
}) {
  const c = getColor(domain.color)
  const children = domain.children || []

  if (children.length === 0) return null

  // Check if this domain has team sub-groups (Growth domain pattern)
  const hasTeams = children.some(ch => ch.type === 'team')

  return (
    <div data-testid={`domain-detail-${domain.id}`} className={`mb-6 rounded-lg border-2 p-4 ${c.bg} ${c.border}`}>
      <h3 className="font-bold text-sm mb-3 flex items-center gap-2">
        <span>{domain.icon}</span>
        <span>{domain.display_name}</span>
        {domain.project && <span className="text-xs font-mono text-gray-400">({domain.project})</span>}
      </h3>

      {hasTeams ? (
        /* ── Team-based layout (Growth domain) ───────────── */
        <div data-testid={`teams-${domain.id}`} className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {children.map(team => {
            const tc = getColor(team.color)
            return (
              <div key={team.id} data-testid={`team-${team.id}`}
                className={`rounded-lg border p-3 ${tc.lightBg} ${tc.border}`}>
                <div className="text-center mb-2">
                  <span className="text-lg">{team.icon}</span>
                  <h4 className="font-bold text-xs mt-0.5">{team.display_name}</h4>
                </div>
                <div className="space-y-1.5">
                  {(team.children || []).map(agent => (
                    <div
                      key={agent.id}
                      data-testid={`node-${agent.id}`}
                      className={`bg-white rounded-md px-3 py-2 text-sm border cursor-pointer transition-all duration-200
                        ${selectedNode === agent.id ? 'ring-2 ring-blue-500 scale-[1.02] shadow-sm' : 'hover:shadow-sm'}`}
                      onClick={() => onSelectNode(agent.id)}
                    >
                      <div className="font-medium">{agent.display_name}</div>
                      <div className="text-xs text-gray-500 truncate">{agent.goal}</div>
                      {agent.skills && agent.skills.length > 0 && (
                        <div className="flex gap-1 flex-wrap mt-1">
                          {agent.skills.slice(0, 3).map(s => (
                            <span key={s} className={`text-[10px] px-1.5 py-0.5 rounded ${tc.tag} ${tc.tagText}`}>{s}</span>
                          ))}
                          {agent.skills.length > 3 && (
                            <span className="text-[10px] text-gray-400">+{agent.skills.length - 3}</span>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        /* ── Service-based layout ────────────────────────── */
        <div data-testid={`services-${domain.id}`} className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {children.map(service => (
            <div
              key={service.id}
              data-testid={`node-${service.id}`}
              className={`bg-white rounded-md px-3 py-2.5 border cursor-pointer transition-all duration-200
                ${selectedNode === service.id ? 'ring-2 ring-blue-500 scale-[1.02] shadow-sm' : 'hover:shadow-sm'}`}
              onClick={() => onSelectNode(service.id)}
            >
              <div className="font-medium text-sm">{service.display_name}</div>
              <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{service.goal}</div>
              {service.project && (
                <div className="text-[10px] font-mono text-gray-400 mt-1 truncate">{service.project}</div>
              )}
            </div>
          ))}
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
          <h4 className="font-bold text-lg">{node.display_name}</h4>
          <span className={`text-xs px-2 py-0.5 rounded ${c.tag} ${c.tagText}`}>{node.type}</span>
          <span className="text-xs font-mono text-gray-400 ml-2">{node.id}</span>
        </div>
      </div>
      <p className="text-sm text-gray-600 mb-3">{node.goal}</p>
      {node.project && (
        <p className="text-xs text-gray-400 mb-2">项目: <span className="font-mono">{node.project}</span></p>
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
