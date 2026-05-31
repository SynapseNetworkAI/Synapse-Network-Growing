import { useMemo, useState } from 'react'
import {
  McpServerRelease,
  McpSubmissionReadiness,
  McpSubmissionReadinessItem,
  mcpServerReleasesApi,
} from '../mcpServerReleasesApi'
import { FieldLabel, OverlayModal, StateBadge, useToast } from '../components/workbench'
import { mcpReleaseTone } from './mcpServerReleaseUi'

export function McpSurfaceConfigsPanel({
  release,
  readiness,
  onReload,
}: Readonly<{
  release: McpServerRelease | null
  readiness: McpSubmissionReadiness | null
  onReload: () => Promise<void>
}>) {
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)
  const [editing, setEditing] = useState<ConfigDraft | null>(null)

  const rows = readiness?.items || []

  const run = async (key: string, fn: () => Promise<unknown>, message: string) => {
    setBusy(key)
    try {
      await fn()
      toast.success(message)
      await onReload()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'MCP surface 配置操作失败')
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">surface config</div>
          <h3 className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">渠道配置与提交就绪度</h3>
          <p className="mt-2 max-w-4xl text-sm leading-6 text-[color:var(--ops-text-muted)]">
            这里只记录 credential ref、提交模式和缺项检查；真实 token 只存在本地 runner env，不写入 DB、截图或 PR。
          </p>
        </div>
        <StateBadge tone={rows.length ? 'running' : 'muted'}>{rows.length} surfaces</StateBadge>
      </div>

      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        {rows.map((item) => (
          <ConfigCard
            key={item.surface_key}
            item={item}
            release={release}
            busy={busy}
            onEdit={() => setEditing(draftFromReadiness(item))}
            onVerify={() => run(`verify-${item.surface_key}`, () => mcpServerReleasesApi.verifySurfaceConfig(item.surface_key), '配置检查已完成')}
            onLiveCheck={() => release && run(`live-${item.surface_key}`, () => mcpServerReleasesApi.liveCheckSurface(release.id, { surface_key: item.surface_key, actor: 'operator' }), 'Live check 已记录')}
            onSubmit={() => release && run(`submit-${item.surface_key}`, () => mcpServerReleasesApi.submitSurface(release.id, { surface_key: item.surface_key, actor: 'operator' }), '提交状态已记录')}
          />
        ))}
      </div>

      <OverlayModal open={!!editing} title="编辑渠道配置" description="只填写本地凭据引用，例如 env:NODE_AUTH_TOKEN；不要填写真实 token。" onClose={() => setEditing(null)}>
        {editing && <ConfigEditor draft={editing} busy={busy === 'save-config'} onChange={setEditing} onCancel={() => setEditing(null)} onSave={() => run('save-config', async () => {
          await mcpServerReleasesApi.patchSurfaceConfig(editing.surface_key, {
            submission_mode: editing.submission_mode,
            auth_mode: editing.auth_mode,
            credential_ref: editing.credential_ref || null,
            required_env_vars: splitList(editing.required_env_vars_text),
            is_enabled: editing.is_enabled,
          })
          setEditing(null)
        }, '渠道配置已更新')} />}
      </OverlayModal>
    </section>
  )
}

function ConfigCard({
  item,
  release,
  busy,
  onEdit,
  onVerify,
  onLiveCheck,
  onSubmit,
}: Readonly<{
  item: McpSubmissionReadinessItem
  release: McpServerRelease | null
  busy: string | null
  onEdit: () => void
  onVerify: () => void
  onLiveCheck: () => void
  onSubmit: () => void
}>) {
  const eligible = item.readiness_status === 'submit_eligible'
  return (
    <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-semibold text-[color:var(--ops-text-title)]">{item.surface_label}</div>
          <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{item.category} · {item.surface_key}</div>
        </div>
        <StateBadge tone={mcpReleaseTone(item.readiness_status)}>{item.readiness_status}</StateBadge>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <MiniFact label="Config" value={item.config_status} />
        <MiniFact label="Surface" value={item.surface_status} />
        <MiniFact label="Mode" value={item.submission_mode} />
        <MiniFact label="Credential ref" value={item.credential_ref || 'none'} mono />
      </div>
      {item.reason && <div className="mt-3 rounded-lg border border-amber-300/30 bg-amber-400/10 px-3 py-2 text-sm text-amber-100">{item.reason}</div>}
      {item.missing_env_vars.length > 0 && <div className="mt-2 font-mono text-xs text-rose-100">missing: {item.missing_env_vars.join(', ')}</div>}
      <div className="mt-3 flex flex-wrap justify-end gap-2">
        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={onEdit}>编辑配置</button>
        <button type="button" className="rounded-lg border border-cyan-300/35 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50" disabled={busy === `verify-${item.surface_key}`} onClick={onVerify}>Verify config</button>
        <button type="button" className="rounded-lg border border-cyan-300/35 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50" disabled={!release || busy === `live-${item.surface_key}`} onClick={onLiveCheck}>Live check</button>
        <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50" disabled={!release || !eligible || busy === `submit-${item.surface_key}`} onClick={onSubmit}>提交账本</button>
      </div>
    </div>
  )
}

function ConfigEditor({
  draft,
  busy,
  onChange,
  onCancel,
  onSave,
}: Readonly<{
  draft: ConfigDraft
  busy: boolean
  onChange: (draft: ConfigDraft) => void
  onCancel: () => void
  onSave: () => void
}>) {
  const requiredPreview = useMemo(() => splitList(draft.required_env_vars_text), [draft.required_env_vars_text])
  return (
    <div className="space-y-4">
      <ReadOnlyField label="Surface" value={draft.surface_key} />
      <TextField label="Submission mode" value={draft.submission_mode} onChange={(value) => onChange({ ...draft, submission_mode: value })} />
      <TextField label="Auth mode" value={draft.auth_mode} onChange={(value) => onChange({ ...draft, auth_mode: value })} />
      <TextField label="Credential ref" value={draft.credential_ref} onChange={(value) => onChange({ ...draft, credential_ref: value })} mono />
      <TextField label="Required env vars" value={draft.required_env_vars_text} onChange={(value) => onChange({ ...draft, required_env_vars_text: value })} mono />
      <label className="flex items-center gap-2 text-sm text-[color:var(--ops-text-muted)]">
        <input type="checkbox" checked={draft.is_enabled} onChange={(event) => onChange({ ...draft, is_enabled: event.target.checked })} />
        Surface enabled
      </label>
      <div className="rounded-xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-subtle)] px-4 py-3 text-xs text-[color:var(--ops-text-muted)]">
        Parsed env refs: {requiredPreview.join(', ') || 'none'}
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={onCancel}>取消</button>
        <button type="button" className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60" disabled={busy} onClick={onSave}>保存配置</button>
      </div>
    </div>
  )
}

type ConfigDraft = {
  surface_key: string
  submission_mode: string
  auth_mode: string
  credential_ref: string
  required_env_vars_text: string
  is_enabled: boolean
}

function draftFromReadiness(item: McpSubmissionReadinessItem): ConfigDraft {
  return {
    surface_key: item.surface_key,
    submission_mode: item.submission_mode,
    auth_mode: item.credential_ref ? 'env_token' : 'manual',
    credential_ref: item.credential_ref || '',
    required_env_vars_text: item.required_env_vars.join(', '),
    is_enabled: item.readiness_status !== 'blocked',
  }
}

function splitList(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function MiniFact({ label, value, mono }: Readonly<{ label: string; value: string; mono?: boolean }>) {
  return <div className="rounded-lg border border-[color:var(--ops-stroke-soft)] px-3 py-2"><div className="text-[11px] uppercase tracking-[0.14em] text-[color:var(--ops-text-caption)]">{label}</div><div className={`mt-1 break-all text-xs text-[color:var(--ops-text-title)] ${mono ? 'font-mono' : ''}`}>{value}</div></div>
}

function ReadOnlyField({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div><FieldLabel>{label}</FieldLabel><div className="mt-2 rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 font-mono text-sm text-[color:var(--ops-text-muted)]">{value}</div></div>
}

function TextField({ label, value, onChange, mono }: Readonly<{ label: string; value: string; onChange: (value: string) => void; mono?: boolean }>) {
  return <div><FieldLabel>{label}</FieldLabel><input className={`mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 ${mono ? 'font-mono' : ''}`} value={value} onChange={(event) => onChange(event.target.value)} /></div>
}
