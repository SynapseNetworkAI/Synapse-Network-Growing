import { useEffect, useMemo, useState } from 'react'
import { api, Approval } from '../api'

export default function Approvals() {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [filter, setFilter] = useState('pending')
  const [commenting, setCommenting] = useState<{ id: number; comment: string } | null>(null)
  const [selectedApprovalIds, setSelectedApprovalIds] = useState<number[]>([])
  const [bulkComment, setBulkComment] = useState('')

  const load = async () => {
    const data = await api.getApprovals(filter || undefined)
    setApprovals(data)
  }

  useEffect(() => { load() }, [filter])

  useEffect(() => {
    setSelectedApprovalIds((prev) => prev.filter((id) => approvals.some((approval) => approval.id === id && approval.status === 'pending')))
  }, [approvals])

  const pendingApprovalIds = useMemo(
    () => approvals.filter((approval) => approval.status === 'pending').map((approval) => approval.id),
    [approvals],
  )

  const allPendingSelected = pendingApprovalIds.length > 0 && pendingApprovalIds.every((id) => selectedApprovalIds.includes(id))

  const toggleApprovalSelection = (approvalId: number) => {
    setSelectedApprovalIds((prev) => (
      prev.includes(approvalId) ? prev.filter((id) => id !== approvalId) : [...prev, approvalId]
    ))
  }

  const statusClassName = (status: string) => {
    if (status === 'pending') return 'bg-yellow-100 text-yellow-700'
    if (status === 'approved') return 'bg-green-100 text-green-700'
    return 'bg-red-100 text-red-700'
  }

  const handleDecide = async (approvalId: number, action: 'approve' | 'reject') => {
    await api.decideApproval(approvalId, {
      action,
      comment: commenting?.id === approvalId ? commenting.comment : '',
      reviewer: 'cto',
    })
    setCommenting(null)
    await load()
  }

  const handleBulkDecide = async (action: 'approve' | 'reject') => {
    if (selectedApprovalIds.length === 0) return
    await api.bulkDecideApprovals({
      approval_ids: selectedApprovalIds,
      action,
      comment: bulkComment,
      reviewer: 'cto',
    })
    setBulkComment('')
    setSelectedApprovalIds([])
    await load()
  }

  return (
    <div data-testid="approvals-page">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold">审批中心</h2>
        <select
          data-testid="approval-filter"
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

      {selectedApprovalIds.length > 0 && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3" data-testid="bulk-approval-bar">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="text-sm text-emerald-900">已选择 {selectedApprovalIds.length} 个待审批项</div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                data-testid="select-all-approvals"
                onClick={() => setSelectedApprovalIds(allPendingSelected ? [] : pendingApprovalIds)}
                className="text-xs border border-emerald-300 px-3 py-1.5 rounded hover:bg-white"
              >
                {allPendingSelected ? '取消全选' : '全选待审批'}
              </button>
              <button
                data-testid="clear-approval-selection"
                onClick={() => setSelectedApprovalIds([])}
                className="text-xs border border-emerald-300 px-3 py-1.5 rounded hover:bg-white"
              >
                清空选择
              </button>
            </div>
          </div>
          <div className="mt-3 flex flex-col gap-2 lg:flex-row lg:items-center">
            <input
              data-testid="bulk-approval-comment"
              placeholder="批量审批意见（可选）"
              value={bulkComment}
              onChange={(e) => setBulkComment(e.target.value)}
              className="border rounded px-3 py-2 text-sm flex-1"
            />
            <div className="flex gap-2">
              <button
                data-testid="bulk-approve"
                onClick={() => handleBulkDecide('approve')}
                className="text-xs bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
              >
                批量批准
              </button>
              <button
                data-testid="bulk-reject"
                onClick={() => handleBulkDecide('reject')}
                className="text-xs bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
              >
                批量拒绝
              </button>
            </div>
          </div>
        </div>
      )}

      {approvals.length === 0 && <p className="text-gray-500 text-sm">暂无审批项</p>}

      <div className="space-y-3">
        {approvals.map((a) => (
          <div key={a.id} className="bg-white border rounded-lg p-4 shadow-sm" data-testid={`approval-${a.id}`}>
            <div className="flex items-center gap-2 mb-2">
              {a.status === 'pending' && (
                <input
                  data-testid={`select-approval-${a.id}`}
                  type="checkbox"
                  checked={selectedApprovalIds.includes(a.id)}
                  onChange={() => toggleApprovalSelection(a.id)}
                />
              )}
              <span className={`text-xs px-2 py-0.5 rounded ${statusClassName(a.status)}`}>
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
                  data-testid={`approval-comment-${a.id}`}
                  placeholder="审批意见（可选）"
                  value={commenting?.id === a.id ? commenting.comment : ''}
                  onChange={(e) => setCommenting({ id: a.id, comment: e.target.value })}
                  className="border rounded px-3 py-1.5 text-sm w-full mb-2"
                />
                <div className="flex gap-2">
                  <button
                    data-testid={`approve-${a.id}`}
                    onClick={() => handleDecide(a.id, 'approve')}
                    className="text-xs bg-green-600 text-white px-4 py-1.5 rounded hover:bg-green-700"
                  >
                    批准
                  </button>
                  <button
                    data-testid={`reject-${a.id}`}
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
