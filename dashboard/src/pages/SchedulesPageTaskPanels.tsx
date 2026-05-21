import { RecurringWorkflow, ScheduleTemplate } from '../api'
import { ActionButton, CockpitPanel } from '../components/controlPlane'
import { OverlayModal, StateBadge } from '../components/workbench'
import { JsonBlock, scheduleLabel, tone } from './SchedulesPageShared'

export type ScheduleDraft = {
  template_key: string
  workflow_key: string
  display_name: string
  owner_role: string
  suggested_local_time: string
}

export type ScheduleEditDraft = {
  workflow_key: string
  display_name: string
  owner_role: string
  suggested_local_time: string
  status: string
}

function categoryLabel(value: string | null | undefined) {
  const labels: Record<string, string> = {
    infra_cleanup: 'Infra Cleanup',
    release_runner: 'Release / Runner',
    system_health: 'System Health',
    planning: 'Planning',
    growth: 'Growth',
  }
  return labels[String(value || '')] || String(value || 'Uncategorized')
}

function riskLabel(value: string | null | undefined) {
  return String(value || 'low').toUpperCase()
}

export function ScheduleTaskTable({
  workflows,
  runningKey,
  onInspect,
  onRun,
  onEdit,
  onToggleStatus,
  onDelete,
}: Readonly<{
  workflows: RecurringWorkflow[]
  runningKey: string | null
  onInspect: (workflow: RecurringWorkflow) => void
  onRun: (workflow: RecurringWorkflow, dryRun: boolean) => void
  onEdit: (workflow: RecurringWorkflow) => void
  onToggleStatus: (workflow: RecurringWorkflow) => void
  onDelete: (workflow: RecurringWorkflow) => void
}>) {
  return (
    <CockpitPanel eyebrow="Tasks" title={`Schedule Tasks (${workflows.length})`} description="可查询、dry-run、run-now、禁用或删除自定义任务；built-in 任务只能禁用。">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
            <tr>
              <th className="px-3 py-3">Task</th>
              <th className="px-3 py-3">Category</th>
              <th className="px-3 py-3">Risk</th>
              <th className="px-3 py-3">Schedule</th>
              <th className="px-3 py-3">Status</th>
              <th className="px-3 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/8">
            {workflows.map((workflow) => (
              <tr key={workflow.workflow_key}>
                <td className="px-3 py-4">
                  <div className="font-semibold text-[color:var(--ops-text-title)]">{workflow.display_name}</div>
                  <div className="mt-1 font-mono text-xs text-[color:var(--ops-text-caption)]">{workflow.workflow_key}</div>
                </td>
                <td className="px-3 py-4">{categoryLabel(workflow.category)}</td>
                <td className="px-3 py-4"><StateBadge tone={workflow.risk_level === 'high' ? 'blocked' : workflow.risk_level === 'medium' ? 'validating' : 'ready'}>{riskLabel(workflow.risk_level)}</StateBadge></td>
                <td className="px-3 py-4">{scheduleLabel(workflow)}</td>
                <td className="px-3 py-4"><StateBadge tone={tone(workflow.status)}>{workflow.status}</StateBadge></td>
                <td className="px-3 py-4">
                  <div className="flex flex-wrap justify-end gap-2">
                    <ActionButton onClick={() => onInspect(workflow)}>详情</ActionButton>
                    <ActionButton onClick={() => onRun(workflow, true)}>Dry Run</ActionButton>
                    {workflow.editable ? <ActionButton onClick={() => onEdit(workflow)}>编辑</ActionButton> : null}
                    <ActionButton onClick={() => onToggleStatus(workflow)}>{workflow.status === 'active' ? '禁用' : '启用'}</ActionButton>
                    {workflow.deletable ? <ActionButton onClick={() => onDelete(workflow)}>删除</ActionButton> : null}
                    {runningKey === workflow.workflow_key ? <span className="rounded-xl border border-cyan-300/25 px-3 py-2 text-xs text-cyan-100">running</span> : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!workflows.length ? <div className="rounded-2xl border border-dashed border-white/10 px-4 py-6 text-center text-sm text-[color:var(--ops-text-muted)]">No schedules match current filters.</div> : null}
      </div>
    </CockpitPanel>
  )
}

export function TemplatesPanel({ templates, onCreate }: Readonly<{ templates: ScheduleTemplate[]; onCreate: (template: ScheduleTemplate) => void }>) {
  return (
    <CockpitPanel eyebrow="Templates" title="安全模板" description="新增任务只能从 allowlisted template 创建，不支持任意 shell cron。">
      <div className="grid gap-4 md:grid-cols-2">
        {templates.map((template) => (
          <article key={template.template_key} className="rounded-[24px] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel)] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="machine-label text-[color:var(--ops-text-caption)]">{template.category} · {template.handler_key}</div>
                <h3 className="mt-2 text-lg font-semibold text-[color:var(--ops-text-title)]">{template.display_name}</h3>
              </div>
              <StateBadge tone={template.risk_level === 'high' ? 'blocked' : 'ready'}>{riskLabel(template.risk_level)}</StateBadge>
            </div>
            <p className="mt-3 text-sm leading-6 text-[color:var(--ops-text-muted)]">{template.description}</p>
            <div className="mt-4"><JsonBlock value={{ schedule: template.schedule, input_query: template.input_query }} /></div>
            <div className="mt-4 flex justify-end"><ActionButton onClick={() => onCreate(template)}>创建任务</ActionButton></div>
          </article>
        ))}
      </div>
    </CockpitPanel>
  )
}

export function CreateScheduleModal({ draft, template, busy, onChange, onClose, onSubmit }: Readonly<{
  draft: ScheduleDraft | null
  template: ScheduleTemplate | null
  busy: boolean
  onChange: (patch: Partial<ScheduleDraft>) => void
  onClose: () => void
  onSubmit: () => void
}>) {
  return (
    <OverlayModal open={Boolean(draft)} eyebrow="Schedule Template" title="创建定时任务" description="只允许从安全模板创建；不会保存任意 shell command。" onClose={onClose} actions={<button type="button" disabled={busy || !draft?.workflow_key} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onSubmit}>{busy ? '创建中…' : '创建任务'}</button>}>
      {draft ? (
        <div className="space-y-4">
          <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.08] px-4 py-3 text-sm text-cyan-50">Template: <strong>{template?.display_name || draft.template_key}</strong></div>
          <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">workflow_key</span><input value={draft.workflow_key} onChange={(event) => onChange({ workflow_key: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 font-mono text-sm" placeholder="custom_artifact_cleanup_daily" /></label>
          <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Display name</span><input value={draft.display_name} onChange={(event) => onChange({ display_name: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm" /></label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Owner role</span><input value={draft.owner_role} onChange={(event) => onChange({ owner_role: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm" /></label>
            <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Suggested local time</span><input value={draft.suggested_local_time} onChange={(event) => onChange({ suggested_local_time: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm" placeholder="12:20" /></label>
          </div>
        </div>
      ) : null}
    </OverlayModal>
  )
}

export function EditScheduleModal({ draft, busy, onChange, onClose, onSubmit }: Readonly<{
  draft: ScheduleEditDraft | null
  busy: boolean
  onChange: (patch: Partial<ScheduleEditDraft>) => void
  onClose: () => void
  onSubmit: () => void
}>) {
  return (
    <OverlayModal open={Boolean(draft)} eyebrow="Schedule Task" title="修改定时任务" description="自定义任务可修改展示信息和日程；执行逻辑仍由 allowlisted handler 决定。" onClose={onClose} actions={<button type="button" disabled={busy || !draft?.display_name} className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" onClick={onSubmit}>{busy ? '保存中…' : '保存修改'}</button>}>
      {draft ? (
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 font-mono text-sm text-[color:var(--ops-text-muted)]">{draft.workflow_key}</div>
          <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Display name</span><input value={draft.display_name} onChange={(event) => onChange({ display_name: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm" /></label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Owner role</span><input value={draft.owner_role} onChange={(event) => onChange({ owner_role: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm" /></label>
            <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Suggested local time</span><input value={draft.suggested_local_time} onChange={(event) => onChange({ suggested_local_time: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm" placeholder="12:20" /></label>
          </div>
          <label className="block"><span className="machine-label text-[color:var(--ops-text-caption)]">Status</span><select value={draft.status} onChange={(event) => onChange({ status: event.target.value })} className="mt-2 w-full rounded-2xl border border-white/10 bg-white/[0.06] px-4 py-3 text-sm"><option value="active">active</option><option value="paused">paused</option><option value="disabled">disabled</option></select></label>
        </div>
      ) : null}
    </OverlayModal>
  )
}
