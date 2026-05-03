import type { ReactNode } from 'react'
import type { DeclarativeWorkflowRunDetail } from '../api'
import { ConfirmDialog } from '../components/workbench'

type WorkspaceRecovery = NonNullable<DeclarativeWorkflowRunDetail['workspace_recovery']>

function workspaceTrustClass(state: string) {
  if (state === 'clean') return 'border-emerald-300/35 bg-emerald-400/10 text-emerald-100'
  if (state === 'dirty_after_kill' || state === 'recovery_required') return 'border-amber-300/45 bg-amber-400/12 text-amber-100'
  if (state === 'recovery_failed') return 'border-rose-300/45 bg-rose-500/16 text-rose-50'
  return 'border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-subtle)] text-[color:var(--ops-text-body)]'
}

function RecoveryPanelFrame({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5" data-testid="workflow-workspace-recovery">
      <div className="text-xs uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Workspace Recovery</div>
      {children}
    </section>
  )
}

export function workspaceRetryLabel(detail: DeclarativeWorkflowRunDetail) {
  return detail.workspace_recovery?.requires_workspace_recovery ? 'Recover Workspace & Retry' : '继续让 Agent 修复'
}

export function WorkspaceRecoveryPanel({ recovery }: Readonly<{ recovery?: WorkspaceRecovery }>) {
  if (!recovery) return null
  return (
    <RecoveryPanelFrame>
      <div className="mt-4 grid gap-4 lg:grid-cols-[0.7fr_1.3fr]">
        <div className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="text-xs uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Trust State</div>
          <div className={['mt-3 inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em]', workspaceTrustClass(recovery.workspace_trust_state)].join(' ')}>
            {recovery.workspace_trust_state}
          </div>
          <div className="mt-3 text-sm text-[color:var(--ops-text-muted)]">
            {recovery.requires_workspace_recovery
              ? 'Retry 会先清理系统 workflow workspace；清理失败不会启动 Agent。'
              : '当前没有记录到必须恢复的 killed workspace。'}
          </div>
        </div>
        <div className="rounded-[var(--ops-radius-panel)] bg-[color:var(--ops-panel-subtle)] p-4">
          <div className="text-xs uppercase tracking-[0.2em] text-[color:var(--ops-text-caption)]">Recovery Preflight Log</div>
          <div className="mt-3 space-y-2 text-sm leading-6 text-[color:var(--ops-text-body)]">
            <div>repo: {recovery.repo_root || '-'}</div>
            <div>branch: {recovery.branch || recovery.expected_branch || '-'}</div>
            {recovery.root_cause ? <div>root cause: {recovery.root_cause}</div> : null}
            {(recovery.logs || []).slice(0, 4).map((line, index) => (
              <div key={`${line}-${index}`} className="font-mono text-xs text-[color:var(--ops-text-caption)]">{line}</div>
            ))}
          </div>
        </div>
      </div>
    </RecoveryPanelFrame>
  )
}

export function WorkspaceRecoveryConfirmDialog({
  open,
  loading,
  onClose,
  onConfirm,
}: Readonly<{
  open: boolean
  loading: boolean
  onClose: () => void
  onConfirm: () => void
}>) {
  return (
    <ConfirmDialog
      open={open}
      title="Recover Workspace & Retry"
      confirmLabel="Recover Workspace & Retry"
      cancelLabel="取消"
      loading={loading}
      description={(
        <div className="space-y-2">
          <p>系统会先清理这个 workflow 拥有的隔离工作区，再恢复 Agent。不会清理用户主工作区。</p>
          <p>如果发现 branch、repo root、git lock 或未提交改动不安全，系统会停在 Rework，不会启动 Agent。</p>
        </div>
      )}
      onClose={onClose}
      onConfirm={onConfirm}
    />
  )
}
