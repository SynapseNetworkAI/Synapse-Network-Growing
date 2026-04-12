import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Approval, Requirement } from '../api'

type RequirementApprovalItem = {
  kind: 'requirement'
  id: number
  status: string
  reviewer: string | null
  comment: string | null
  created_at: string | null
  decided_at: string | null
  requirement: Requirement
}

type ApprovalListItem =
  | { kind: 'task'; approval: Approval }
  | { kind: 'requirement'; approval: RequirementApprovalItem }

function statusClassName(status: string) {
  if (status === 'pending' || status === 'pending_approval') return 'bg-yellow-100 text-yellow-700'
  if (status === 'approved' || status === 'waived') return 'bg-green-100 text-green-700'
  return 'bg-red-100 text-red-700'
}

function statusLabel(status: string) {
  if (status === 'pending_approval') return '待审批'
  if (status === 'approved') return '已批准'
  if (status === 'rejected') return '已拒绝'
  if (status === 'waived') return '已豁免'
  return status
}

function buildRequirementApprovalItem(requirement: Requirement): RequirementApprovalItem {
  return {
    kind: 'requirement',
    id: requirement.id,
    status: requirement.approval_status,
    reviewer: null,
    comment: null,
    created_at: requirement.approval_requested_at || requirement.created_at,
    decided_at: requirement.approved_at,
    requirement,
  }
}

export default function Approvals() {
  const [taskApprovals, setTaskApprovals] = useState<Approval[]>([])
  const [requirementApprovals, setRequirementApprovals] = useState<RequirementApprovalItem[]>([])
  const [filter, setFilter] = useState('pending')
  const [commenting, setCommenting] = useState<Record<string, string>>({})
  const [selectedApprovalIds, setSelectedApprovalIds] = useState<number[]>([])
  const [bulkComment, setBulkComment] = useState('')

  const normalizedFilter = filter === 'pending' ? 'pending_approval' : filter

  const load = async () => {
    const [taskData, requirementData] = await Promise.all([
      api.getApprovals(filter || undefined),
      api.getRequirements(),
    ])
    setTaskApprovals(taskData)
    setRequirementApprovals(
      requirementData
        .filter((requirement) => requirement.approval_status !== 'waived' && requirement.status !== 'deleted')
        .map(buildRequirementApprovalItem),
    )
  }

  useEffect(() => { load().catch(() => {}) }, [filter])

  const items = useMemo<ApprovalListItem[]>(() => {
    const filteredTaskItems = taskApprovals
      .filter((approval) => !filter || approval.status === filter)
      .map((approval) => ({ kind: 'task', approval }) as const)
    const filteredRequirementItems = requirementApprovals
      .filter((approval) => !filter || approval.status === normalizedFilter)
      .map((approval) => ({ kind: 'requirement', approval }) as const)
    return [...filteredRequirementItems, ...filteredTaskItems].sort((a, b) => {
      const aTime = Date.parse((a.approval.created_at || '') as string) || 0
      const bTime = Date.parse((b.approval.created_at || '') as string) || 0
      return bTime - aTime
    })
  }, [filter, normalizedFilter, requirementApprovals, taskApprovals])

  useEffect(() => {
    setSelectedApprovalIds((prev) => prev.filter((id) => taskApprovals.some((approval) => approval.id === id && approval.status === 'pending')))
  }, [taskApprovals])

  const pendingTaskApprovalIds = useMemo(
    () => taskApprovals.filter((approval) => approval.status === 'pending').map((approval) => approval.id),
    [taskApprovals],
  )
  const allPendingSelected = pendingTaskApprovalIds.length > 0 && pendingTaskApprovalIds.every((id) => selectedApprovalIds.includes(id))

  const toggleApprovalSelection = (approvalId: number) => {
    setSelectedApprovalIds((prev) => (
      prev.includes(approvalId) ? prev.filter((id) => id !== approvalId) : [...prev, approvalId]
    ))
  }

  const handleTaskDecide = async (approvalId: number, action: 'approve' | 'reject') => {
    await api.decideApproval(approvalId, {
      action,
      comment: commenting[`task-${approvalId}`] || '',
      reviewer: 'cto',
    })
    setCommenting((prev) => {
      const next = { ...prev }
      delete next[`task-${approvalId}`]
      return next
    })
    await load()
  }

  const handleRequirementDecide = async (requirementId: number, action: 'approve' | 'reject' | 'waive') => {
    await api.decideRequirementApproval(requirementId, {
      action,
      comment: commenting[`requirement-${requirementId}`] || '',
      reviewer: 'cto',
    })
    setCommenting((prev) => {
      const next = { ...prev }
      delete next[`requirement-${requirementId}`]
      return next
    })
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
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-bold">审批中心</h2>
        <select
          data-testid="approval-filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="rounded border px-3 py-2 text-sm"
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
            <div className="text-sm text-emerald-900">已选择 {selectedApprovalIds.length} 个任务审批项</div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                data-testid="select-all-approvals"
                onClick={() => setSelectedApprovalIds(allPendingSelected ? [] : pendingTaskApprovalIds)}
                className="rounded border border-emerald-300 px-3 py-1.5 text-xs hover:bg-white"
              >
                {allPendingSelected ? '取消全选' : '全选待审批'}
              </button>
              <button
                data-testid="clear-approval-selection"
                onClick={() => setSelectedApprovalIds([])}
                className="rounded border border-emerald-300 px-3 py-1.5 text-xs hover:bg-white"
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
              className="flex-1 rounded border px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <button
                data-testid="bulk-approve"
                onClick={() => handleBulkDecide('approve')}
                className="rounded bg-green-600 px-4 py-2 text-xs text-white hover:bg-green-700"
              >
                批量批准
              </button>
              <button
                data-testid="bulk-reject"
                onClick={() => handleBulkDecide('reject')}
                className="rounded bg-red-600 px-4 py-2 text-xs text-white hover:bg-red-700"
              >
                批量拒绝
              </button>
            </div>
          </div>
        </div>
      )}

      {items.length === 0 && <p className="text-sm text-gray-500">暂无审批项</p>}

      <div className="space-y-3">
        {items.map((item) => {
          if (item.kind === 'task') {
            const a = item.approval
            return (
              <div key={`task-${a.id}`} className="rounded-lg border bg-white p-4 shadow-sm" data-testid={`approval-${a.id}`}>
                <div className="mb-2 flex items-center gap-2">
                  {a.status === 'pending' && (
                    <input
                      data-testid={`select-approval-${a.id}`}
                      type="checkbox"
                      checked={selectedApprovalIds.includes(a.id)}
                      onChange={() => toggleApprovalSelection(a.id)}
                    />
                  )}
                  <span className={`rounded px-2 py-0.5 text-xs ${statusClassName(a.status)}`}>{statusLabel(a.status)}</span>
                  <span className="text-xs text-gray-400">任务审批 #{a.id} · 任务 #{a.task_id}</span>
                  {a.reviewer && <span className="text-xs text-gray-400">· 审批人: {a.reviewer}</span>}
                </div>
                {a.task && (
                  <div className="mb-3">
                    <p className="text-sm font-medium">{a.task.description}</p>
                    <p className="text-xs text-gray-500">Agent: @{a.task.agent_id}</p>
                    {a.task.output_content && (
                      <div className="mt-2 rounded bg-gray-50 p-3 text-xs whitespace-pre-wrap text-gray-700">
                        {a.task.output_content}
                      </div>
                    )}
                  </div>
                )}
                {a.comment && <p className="mb-2 text-sm italic text-gray-600">"{a.comment}"</p>}
                {a.status === 'pending' && (
                  <div>
                    <input
                      data-testid={`approval-comment-${a.id}`}
                      placeholder="审批意见（可选）"
                      value={commenting[`task-${a.id}`] || ''}
                      onChange={(e) => setCommenting((prev) => ({ ...prev, [`task-${a.id}`]: e.target.value }))}
                      className="mb-2 w-full rounded border px-3 py-1.5 text-sm"
                    />
                    <div className="flex gap-2">
                      <button
                        data-testid={`approve-${a.id}`}
                        onClick={() => handleTaskDecide(a.id, 'approve')}
                        className="rounded bg-green-600 px-4 py-1.5 text-xs text-white hover:bg-green-700"
                      >
                        批准
                      </button>
                      <button
                        data-testid={`reject-${a.id}`}
                        onClick={() => handleTaskDecide(a.id, 'reject')}
                        className="rounded bg-red-600 px-4 py-1.5 text-xs text-white hover:bg-red-700"
                      >
                        拒绝
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )
          }

          const a = item.approval
          const req = a.requirement
          return (
            <div key={`requirement-${a.id}`} className="rounded-lg border bg-white p-4 shadow-sm" data-testid={`requirement-approval-${a.id}`}>
              <div className="mb-2 flex items-center gap-2">
                <span className={`rounded px-2 py-0.5 text-xs ${statusClassName(a.status)}`}>{statusLabel(a.status)}</span>
                <span className="text-xs text-gray-400">需求审批 · Requirement #{req.id}</span>
                {a.reviewer && <span className="text-xs text-gray-400">· 审批人: {a.reviewer}</span>}
              </div>
              <div className="mb-3">
                <Link to={`/requirements/${req.id}`} className="text-sm font-medium text-blue-700 hover:underline">
                  {req.title}
                </Link>
                <p className="mt-1 text-xs text-gray-500">
                  priority: {req.priority} · approval mode: {String(req.approval_contract?.approval_mode || '-')}
                </p>
                {req.target_project_path && (
                  <div className="mt-2 rounded bg-gray-50 p-3 text-xs font-mono whitespace-pre-wrap text-gray-700">
                    {req.target_project_path}
                  </div>
                )}
              </div>
              {a.status === 'pending_approval' && (
                <div>
                  <input
                    data-testid={`requirement-approval-comment-${req.id}`}
                    placeholder="审批意见（可选）"
                    value={commenting[`requirement-${req.id}`] || ''}
                    onChange={(e) => setCommenting((prev) => ({ ...prev, [`requirement-${req.id}`]: e.target.value }))}
                    className="mb-2 w-full rounded border px-3 py-1.5 text-sm"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      data-testid={`requirement-approve-${req.id}`}
                      onClick={() => handleRequirementDecide(req.id, 'approve')}
                      className="rounded bg-green-600 px-4 py-1.5 text-xs text-white hover:bg-green-700"
                    >
                      批准执行
                    </button>
                    <button
                      data-testid={`requirement-waive-${req.id}`}
                      onClick={() => handleRequirementDecide(req.id, 'waive')}
                      className="rounded bg-slate-700 px-4 py-1.5 text-xs text-white hover:bg-slate-800"
                    >
                      豁免审批
                    </button>
                    <button
                      data-testid={`requirement-reject-${req.id}`}
                      onClick={() => handleRequirementDecide(req.id, 'reject')}
                      className="rounded bg-red-600 px-4 py-1.5 text-xs text-white hover:bg-red-700"
                    >
                      拒绝
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
