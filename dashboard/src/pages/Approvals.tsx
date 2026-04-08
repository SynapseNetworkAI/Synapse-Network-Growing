import { useEffect, useState } from 'react'
import { api, Approval } from '../api'

export default function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [filter, setFilter] = useState('pending')
  const [commenting, setCommenting] = useState<{ id: number; comment: string } | null>(null)

  const load = async () => {
    const data = await api.getApprovals(filter || undefined)
    setApprovals(data)
  }

  useEffect(() => { load() }, [filter])

  const handleDecide = async (approvalId: number, action: 'approve' | 'reject') => {
    await api.decideApproval(approvalId, {
      action,
      comment: commenting?.id === approvalId ? commenting.comment : '',
      reviewer: 'cto',
    })
    setCommenting(null)
    await load()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">审批中心</h2>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="text-sm border rounded px-3 py-2"
        >
          <option value="">全部</option>
          <option value="pending">待审批</option>
          <option value="approved">已批准</option>
          <option value="rejected">已拒绝</option>
        </select>
      </div>

      {approvals.length === 0 && <p className="text-gray-500 text-sm">暂无审批项</p>}

      <div className="space-y-3">
        {approvals.map((a) => (
          <div key={a.id} className="bg-white border rounded-lg p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-xs px-2 py-0.5 rounded ${
                a.status === 'pending' ? 'bg-yellow-100 text-yellow-700' :
                a.status === 'approved' ? 'bg-green-100 text-green-700' :
                'bg-red-100 text-red-700'
              }`}>
                {a.status}
              </span>
              <span className="text-xs text-gray-400">审批 #{a.id} · 任务 #{a.task_id}</span>
              {a.reviewer && <span className="text-xs text-gray-400">· 审批人: {a.reviewer}</span>}
            </div>

            {a.task && (
              <div className="mb-3">
                <p className="text-sm font-medium">{a.task.description}</p>
                <p className="text-xs text-gray-500">Agent: @{a.task.agent_id}</p>
                {a.task.output_content && (
                  <div className="mt-2 bg-gray-50 rounded p-3 text-xs text-gray-700 whitespace-pre-wrap">
                    {a.task.output_content}
                  </div>
                )}
              </div>
            )}

            {a.comment && (
              <p className="text-sm text-gray-600 italic mb-2">"{a.comment}"</p>
            )}

            {a.status === 'pending' && (
              <div>
                <input
                  placeholder="审批意见（可选）"
                  value={commenting?.id === a.id ? commenting.comment : ''}
                  onChange={(e) => setCommenting({ id: a.id, comment: e.target.value })}
                  className="border rounded px-3 py-1.5 text-sm w-full mb-2"
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => handleDecide(a.id, 'approve')}
                    className="text-xs bg-green-600 text-white px-4 py-1.5 rounded hover:bg-green-700"
                  >
                    批准
                  </button>
                  <button
                    onClick={() => handleDecide(a.id, 'reject')}
                    className="text-xs bg-red-600 text-white px-4 py-1.5 rounded hover:bg-red-700"
                  >
                    拒绝
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
