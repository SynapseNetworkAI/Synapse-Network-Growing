import { ReleaseTask } from '../api'
import { FieldLabel, OverlayModal } from '../components/workbench'

export default function ProductionDeployModal({
  task,
  gate,
  gateStatus,
  confirmPhrase,
  busyAction,
  onConfirmPhraseChange,
  onClose,
  onDeploy,
}: Readonly<{
  task: ReleaseTask | null
  gate?: ReleaseTask['pr_gate']
  gateStatus?: 'idle' | 'loading' | 'ready' | 'error'
  confirmPhrase: string
  busyAction: string | null
  onConfirmPhraseChange: (value: string) => void
  onClose: () => void
  onDeploy: () => void
}>) {
  if (!task) {
    return null
  }
  const busyKey = task ? `release-task-${task.id}-deploy-production` : ''
  const effectiveGate = gate || task?.pr_gate
  const gateReady = Boolean(effectiveGate?.can_deploy_production)
  const isMcpRemoteTask = task.source_type === 'mcp_remote_gcloud'
    || (task.project_key === 'synapse-network-mcp-server' && task.service_key === 'remote-mcp')
  const expectedPhrase = isMcpRemoteTask ? 'DEPLOY_MCP_REMOTE_PROD' : 'YES'
  const gateLoading = gateStatus === 'loading'
  const directFrontend = task.project_key === 'synapse-network'
    && ['admin-front', 'user-front', 'docs-front'].includes(task.service_key || '')
    && gateReady
    && !effectiveGate?.staging_deployment_record_id
  return (
    <OverlayModal
      open={Boolean(task)}
      eyebrow="Human Gate"
      title={isMcpRemoteTask ? '确认发布 Remote MCP production' : '确认发布到 production'}
      description={isMcpRemoteTask ? 'Remote MCP 没有 staging 版本；确认后由 MCP release ledger 和本地 GCloud runner 记录真实状态。' : '生产发布会触发 GitHub Environment production 与 GCP WIF Cloud Run 工作流。不会自动 rollback。'}
      onClose={onClose}
    >
      {(
        <div className="space-y-5">
          <div className="rounded-2xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] p-4 text-sm text-[color:var(--ops-state-blocked-text)]">
            <div className="font-semibold">Production Human Gate</div>
            <p className="mt-2">
              请确认目标是 <span className="font-mono">synapse-network-prod</span>，分支为 <span className="font-mono">main</span>。
              {isMcpRemoteTask ? ' Remote MCP 无 staging 版本，必须依赖 readiness、secret preflight、public probe 和 OpenAI smoke。' : directFrontend ? ' 这是前端 direct production deploy，不强制要求同 commit 先通过 staging。' : ' 且同一 commit 已通过 staging。'}
              确认后仍需要 GitHub production environment reviewers 放行。
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoCard label="Project / Service" value={`${task.project_display_name || task.project_key} · ${task.service_key || '-'}`} />
            <InfoCard label="GCP Project" value="synapse-network-prod" mono />
            <InfoCard label="Main Commit" value={effectiveGate?.resolved_commit_sha || '-'} mono />
            <InfoCard
              label={isMcpRemoteTask ? 'Remote Evidence' : 'Staging Evidence'}
              value={isMcpRemoteTask ? 'MCP ledger + OpenAI smoke' : directFrontend ? 'Direct frontend deploy' : `Deployment #${effectiveGate?.staging_deployment_record_id || '-'}`}
            />
          </div>
          {directFrontend ? (
            <div className="rounded-2xl border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] p-4 text-sm text-[color:var(--ops-state-running-text)]">
              前端 production 可直接从 main 发布。建议先绑定 Prebuilt Image digest；未绑定时 workflow 会走 Cloud Build，成本和耗时会更高。
            </div>
          ) : null}
          {!gateReady ? (
            <div className="rounded-2xl border border-[color:var(--ops-state-running-border)] bg-[color:var(--ops-state-running-bg)] p-4 text-sm text-[color:var(--ops-state-running-text)]">
              {gateLoading ? 'Production gate 检查中…' : effectiveGate?.blocked_reason || '请先检查 production gate。'}
            </div>
          ) : null}
          <label className="block space-y-2">
            <FieldLabel>输入确认短语</FieldLabel>
            <input
              className="w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel)] px-4 py-3 font-mono text-sm"
              placeholder={expectedPhrase}
              value={confirmPhrase}
              onChange={(event) => onConfirmPhraseChange(event.target.value)}
            />
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onClose}>
              取消
            </button>
            <button
              type="button"
              className="rounded-xl border border-[color:var(--ops-state-blocked-border)] bg-[color:var(--ops-state-blocked-bg)] px-4 py-2.5 text-sm font-semibold text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
              disabled={confirmPhrase !== expectedPhrase || Boolean(busyAction) || !gateReady}
              onClick={onDeploy}
            >
              {busyAction === busyKey ? '发布中…' : '确认发布到 production'}
            </button>
          </div>
        </div>
      )}
    </OverlayModal>
  )
}

function InfoCard({ label, value, mono = false }: Readonly<{ label: string; value: string; mono?: boolean }>) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] p-4">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className={`mt-2 text-sm ${mono ? 'font-mono' : 'font-semibold'}`}>{value}</div>
    </div>
  )
}
