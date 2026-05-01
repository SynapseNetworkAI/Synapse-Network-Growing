export const STATUS_LABEL: Record<string, string> = {
  pending: '待交付',
  preparing_branch: '准备分支',
  pushing: '推送中',
  opening_pr: '打开 PR',
  repairing: '交付修复中',
  blocked: '阻塞',
  pr_open: 'PR 已打开',
  pr_opened: 'PR 已打开',
  pr_closed: 'PR 已关闭',
  ready_for_merge: '等待合并',
  merged: '已合并',
  abandoned: '已废弃',
  no_deploy: '无需部署',
  requested: '待执行',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  succeeded: '上线成功',
  deploy: 'deploy',
  promote: 'promote',
  rollback: 'rollback',
}

export function releaseTone(state: string | null | undefined) {
  if (state === 'merged' || state === 'completed' || state === 'succeeded' || state === 'passed') return 'delivered'
  if (state === 'pr_open' || state === 'pr_opened' || state === 'ready_for_merge' || state === 'requested') return 'ready'
  if (state === 'repairing' || state === 'pushing' || state === 'opening_pr' || state === 'preparing_branch') return 'running'
  if (state === 'blocked' || state === 'pr_closed' || state === 'abandoned' || state === 'failed') return 'blocked'
  if (state === 'pending') return 'ready'
  return 'muted'
}
