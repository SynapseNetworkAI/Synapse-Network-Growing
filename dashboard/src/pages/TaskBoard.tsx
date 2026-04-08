import { useEffect, useState } from 'react'
import { api, Task, Agent, TaskLog } from '../api'

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  pending_approval: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  failed: 'bg-red-100 text-red-700',
}

export default function TaskBoard() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [filter, setFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ description: '', agent_id: '', requires_approval: false, priority: 'normal' })
  const [selectedLogs, setSelectedLogs] = useState<{ taskId: number; logs: TaskLog[] } | null>(null)

  const load = async () => {
    const [t, a] = await Promise.all([
      api.getTasks(filter ? { status: filter } : undefined),
      api.getAgents(),
    ])
    setTasks(t)
    setAgents(a)
  }

  useEffect(() => { load() }, [filter])

  const handleCreate = async () => {
    if (!form.description || !form.agent_id) return
    await api.createTask(form)
    setForm({ description: '', agent_id: '', requires_approval: false, priority: 'normal' })
    setShowCreate(false)
    await load()
  }

  const handleRun = async (id: number) => {
    await api.runTask(id)
    await load()
  }

  const handleViewLogs = async (taskId: number) => {
    const logs = await api.getTaskLogs(taskId)
    setSelectedLogs({ taskId, logs })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">任务看板</h2>
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="text-sm border rounded px-3 py-2"
          >
            <option value="">全部状态</option>
            <option value="pending">待执行</option>
            <option value="running">执行中</option>
            <option value="pending_approval">待审批</option>
            <option value="completed">已完成</option>
            <option value="rejected">已拒绝</option>
          </select>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
          >
            + 新建任务
          </button>
        </div>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-white border rounded-lg p-4 mb-4 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <input
              placeholder="任务描述"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="border rounded px-3 py-2 text-sm col-span-2"
            />
            <select
              value={form.agent_id}
              onChange={(e) => setForm({ ...form, agent_id: e.target.value })}
              className="border rounded px-3 py-2 text-sm"
            >
              <option value="">选择 Agent</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>{a.display_name} ({a.id})</option>
              ))}
            </select>
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
              className="border rounded px-3 py-2 text-sm"
            >
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">高</option>
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.requires_approval}
                onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
              />
              需要审批
            </label>
          </div>
          <div className="flex gap-2 mt-3">
            <button onClick={handleCreate} className="text-sm bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700">
              提交
            </button>
            <button onClick={() => setShowCreate(false)} className="text-sm text-gray-500 px-4 py-2">
              取消
            </button>
          </div>
        </div>
      )}

      {/* Task list */}
      <div className="space-y-2">
        {tasks.length === 0 && <p className="text-gray-500 text-sm">暂无任务</p>}
        {tasks.map((task) => (
          <div key={task.id} className="bg-white border rounded-lg p-4 shadow-sm flex items-center justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[task.status] || 'bg-gray-100'}`}>
                  {task.status}
                </span>
                <span className="text-xs text-gray-400 font-mono">#{task.id}</span>
                <span className="text-xs text-gray-400">@{task.agent_id}</span>
                {task.priority !== 'normal' && (
                  <span className={`text-xs px-2 py-0.5 rounded ${task.priority === 'high' ? 'bg-red-50 text-red-600' : 'bg-gray-50 text-gray-500'}`}>
                    {task.priority}
                  </span>
                )}
              </div>
              <p className="text-sm">{task.description}</p>
              {task.output_content && (
                <p className="text-xs text-gray-500 mt-1 truncate max-w-lg">{task.output_content}</p>
              )}
            </div>
            <div className="flex gap-2 ml-4">
              {task.status === 'pending' && (
                <button onClick={() => handleRun(task.id)} className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded hover:bg-blue-700">
                  执行
                </button>
              )}
              <button onClick={() => handleViewLogs(task.id)} className="text-xs border px-3 py-1.5 rounded hover:bg-gray-50">
                日志
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Logs modal */}
      {selectedLogs && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setSelectedLogs(null)}>
          <div className="bg-white rounded-lg p-6 max-w-lg w-full max-h-[70vh] overflow-auto shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-bold mb-3">Task #{selectedLogs.taskId} 日志</h3>
            {selectedLogs.logs.length === 0 && <p className="text-sm text-gray-500">暂无日志</p>}
            <div className="space-y-2">
              {selectedLogs.logs.map((log) => (
                <div key={log.id} className="text-sm border-l-2 border-gray-300 pl-3">
                  <span className="font-mono text-xs text-gray-400">{log.created_at}</span>
                  <span className="ml-2 font-semibold">{log.event_type}</span>
                  {log.detail && <p className="text-gray-600 text-xs mt-0.5">{log.detail}</p>}
                </div>
              ))}
            </div>
            <button onClick={() => setSelectedLogs(null)} className="mt-4 text-sm text-gray-500 hover:text-gray-700">
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
