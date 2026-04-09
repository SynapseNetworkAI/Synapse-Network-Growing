import { useEffect, useState } from 'react'
import { api, Agent, DashboardStats } from '../api'

/* ── Group definitions ────────────────────────────────────── */
const GROUP_META: Record<string, { label: string; icon: string; color: string; border: string; bg: string; tag: string; tagText: string }> = {
  content:      { label: '内容与布道', icon: '📢', color: 'blue',   border: 'border-blue-300',   bg: 'bg-blue-50',   tag: 'bg-blue-100',   tagText: 'text-blue-700' },
  growth:       { label: '增长与发布', icon: '🚀', color: 'green',  border: 'border-green-300',  bg: 'bg-green-50',  tag: 'bg-green-100',  tagText: 'text-green-700' },
  optimization: { label: '优化与分析', icon: '📈', color: 'purple', border: 'border-purple-300', bg: 'bg-purple-50', tag: 'bg-purple-100', tagText: 'text-purple-700' },
}
const GROUP_ORDER = ['content', 'growth', 'optimization'] as const

export default function OrgChart() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [a, s] = await Promise.all([api.getAgents(), api.getStats()])
      if (a.length === 0) {
        await api.syncAgents()
        const [a2, s2] = await Promise.all([api.getAgents(), api.getStats()])
        setAgents(a2)
        setStats(s2)
      } else {
        setAgents(a)
        setStats(s)
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

  /* ── Group agents ────────────────────────────────────────── */
  const grouped = GROUP_ORDER.reduce<Record<string, Agent[]>>((acc, g) => {
    acc[g] = agents.filter(a => a.group === g)
    return acc
  }, {})

  /* Which agents to show in detail cards */
  const visibleAgents = selectedGroup
    ? agents.filter(a => a.group === selectedGroup)
    : agents

  const detail = selectedAgent ? agents.find(a => a.id === selectedAgent) : null

  /* ── Loading skeleton ────────────────────────────────────── */
  if (loading) {
    return (
      <div data-testid="orgchart-skeleton" className="animate-pulse space-y-6">
        <div className="grid grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="h-20 bg-gray-200 rounded-lg" />)}
        </div>
        <div className="h-10 bg-gray-200 rounded w-1/3" />
        <div className="flex justify-center"><div className="h-16 w-40 bg-gray-200 rounded-lg" /></div>
        <div className="grid grid-cols-3 gap-6">
          {[1,2,3].map(i => <div key={i} className="h-40 bg-gray-100 rounded-lg" />)}
        </div>
      </div>
    )
  }

  /* ── Error state ─────────────────────────────────────────── */
  if (error) {
    return (
      <div data-testid="orgchart-error" className="text-center py-20">
        <p className="text-red-600 text-lg mb-4">{error}</p>
        <button onClick={load} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          重试
        </button>
      </div>
    )
  }

  /* ── Empty state ─────────────────────────────────────────── */
  if (agents.length === 0) {
    return (
      <div data-testid="orgchart-empty" className="text-center py-20">
        <p className="text-gray-500 mb-4">暂无 Agent 数据</p>
        <button onClick={handleSync} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          同步 Roles
        </button>
      </div>
    )
  }

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
        <h2 className="text-xl font-bold">Agent 组织架构</h2>
        <button onClick={handleSync} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          同步 Roles
        </button>
      </div>

      {/* ── Manager node (center) ──────────────────────────── */}
      <div className="flex justify-center mb-2">
        <div
          data-testid="manager-node"
          className="bg-gray-800 text-white rounded-lg px-6 py-3 text-center shadow-lg cursor-default"
          onClick={() => { setSelectedAgent(null); setSelectedGroup(null) }}
        >
          <div className="text-lg font-bold">🧠 CTO / Manager</div>
          <div className="text-xs text-gray-300">CrewAI Orchestrator</div>
        </div>
      </div>

      {/* ── Connector lines from manager to groups ─────────── */}
      <div className="flex justify-center mb-2">
        <div className="w-px h-6 bg-gray-300" />
      </div>
      <div className="flex justify-center mb-6">
        <div className="flex items-start" style={{ width: '80%' }}>
          <div className="flex-1 border-t-2 border-gray-300" />
          <div className="flex-1 border-t-2 border-gray-300" />
        </div>
      </div>

      {/* ── Group columns ──────────────────────────────────── */}
      <div data-testid="group-columns" className="grid grid-cols-3 gap-6 mb-8">
        {GROUP_ORDER.map(groupKey => {
          const meta = GROUP_META[groupKey]
          const members = grouped[groupKey] || []
          const isSelected = selectedGroup === groupKey
          return (
            <div
              key={groupKey}
              data-testid={`group-${groupKey}`}
              className={`rounded-lg border-2 p-4 cursor-pointer transition-all duration-200
                ${meta.bg} ${meta.border}
                ${isSelected ? 'ring-2 ring-blue-500 scale-[1.02] shadow-md' : 'hover:shadow-md hover:-translate-y-0.5'}`}
              onClick={() => {
                setSelectedGroup(isSelected ? null : groupKey)
                setSelectedAgent(null)
              }}
            >
              <div className="text-center mb-3">
                <span className="text-2xl">{meta.icon}</span>
                <h3 className="font-bold text-sm mt-1">{meta.label}</h3>
              </div>
              <div className="space-y-2">
                {members.map(agent => {
                  const isAgentSelected = selectedAgent === agent.id
                  return (
                    <div
                      key={agent.id}
                      data-testid={`agent-node-${agent.id}`}
                      className={`bg-white rounded-md px-3 py-2 text-sm border cursor-pointer transition-all duration-200
                        ${isAgentSelected ? 'ring-2 ring-blue-500 scale-105 shadow-sm' : 'hover:shadow-sm'}`}
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedAgent(isAgentSelected ? null : agent.id)
                      }}
                    >
                      <div className="font-medium">{agent.display_name}</div>
                      <div className="text-xs text-gray-500 flex gap-3 mt-0.5">
                        <span>任务: {agent.task_count}</span>
                        <span>完成: {agent.completed_count}</span>
                      </div>
                    </div>
                  )
                })}
                {members.length === 0 && (
                  <p className="text-xs text-gray-400 text-center py-2">暂无成员</p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Selected agent detail card ─────────────────────── */}
      {detail && (
        <div data-testid="agent-detail" className="mb-8">
          <h3 className="text-lg font-bold mb-3">Agent 详情</h3>
          <AgentDetailCard agent={detail} />
        </div>
      )}

      {/* ── Agent card grid (filtered by group) ────────────── */}
      <div data-testid="agent-cards">
        <h3 className="text-lg font-bold mb-3">
          {selectedGroup ? `${GROUP_META[selectedGroup]?.label} 成员` : '全部 Agent'}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {visibleAgents.map(agent => (
            <AgentDetailCard key={agent.id} agent={agent} />
          ))}
        </div>
      </div>
    </div>
  )
}

/* ── Agent detail card component ────────────────────────────── */
function AgentDetailCard({ agent }: { agent: Agent }) {
  const skills = JSON.parse(agent.skills || '[]') as string[]
  const meta = GROUP_META[agent.group]
  return (
    <div data-testid={`agent-card-${agent.id}`} className="bg-white border rounded-lg p-4 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-semibold">{agent.display_name}</h4>
        <div className="flex gap-1.5 items-center">
          {meta && (
            <span className={`text-xs px-2 py-0.5 rounded ${meta.tag} ${meta.tagText}`}>
              {meta.label}
            </span>
          )}
          <span className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">{agent.id}</span>
        </div>
      </div>
      <p className="text-sm text-gray-600 mb-3">{agent.goal}</p>
      <div className="flex gap-1 flex-wrap mb-3">
        {skills.map((s) => (
          <span key={s} className={`text-xs px-2 py-0.5 rounded ${meta ? `${meta.tag} ${meta.tagText}` : 'bg-blue-50 text-blue-700'}`}>
            {s}
          </span>
        ))}
      </div>
      <div className="text-xs text-gray-500 flex gap-4">
        <span>任务: {agent.task_count}</span>
        <span>完成: {agent.completed_count}</span>
      </div>
    </div>
  )
}
