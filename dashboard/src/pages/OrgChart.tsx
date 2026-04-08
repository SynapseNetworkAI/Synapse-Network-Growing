import { useEffect, useState } from 'react'
import { api, Agent, DashboardStats } from '../api'

export default function OrgChart() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const [a, s] = await Promise.all([api.getAgents(), api.getStats()])
      setAgents(a)
      setStats(s)
    } catch {
      // If no agents yet, try sync first
      await api.syncAgents()
      const [a, s] = await Promise.all([api.getAgents(), api.getStats()])
      setAgents(a)
      setStats(s)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleSync = async () => {
    await api.syncAgents()
    await load()
  }

  if (loading) return <p className="text-gray-500">加载中...</p>

  return (
    <div>
      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Agent 总数', value: stats.agent_count, color: 'blue' },
            { label: '任务总数', value: stats.task_total, color: 'gray' },
            { label: '已完成', value: stats.task_completed, color: 'green' },
            { label: '待审批', value: stats.approval_pending, color: 'yellow' },
          ].map((s) => (
            <div key={s.label} className={`bg-${s.color}-50 border border-${s.color}-200 rounded-lg p-4`}>
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-sm text-gray-600">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">Agent 组织架构</h2>
        <button onClick={handleSync} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
          同步 Roles
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {agents.map((agent) => {
          const skills = JSON.parse(agent.skills || '[]') as string[]
          return (
            <div key={agent.id} className="bg-white border rounded-lg p-4 shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold">{agent.display_name}</h3>
                <span className="text-xs bg-gray-100 px-2 py-1 rounded font-mono">{agent.id}</span>
              </div>
              <p className="text-sm text-gray-600 mb-3">{agent.goal}</p>
              <div className="flex gap-1 flex-wrap mb-3">
                {skills.map((s) => (
                  <span key={s} className="text-xs bg-blue-50 text-blue-700 px-2 py-0.5 rounded">{s}</span>
                ))}
              </div>
              <div className="text-xs text-gray-500 flex gap-4">
                <span>任务: {agent.task_count}</span>
                <span>完成: {agent.completed_count}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
