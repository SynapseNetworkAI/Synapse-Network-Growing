import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Project, api } from '../api'
import { EmptyPane, FieldLabel, OverlayModal, useToast } from '../components/workbench'

type ProjectDraft = {
  project_key: string
  display_name: string
  root_path: string
  repo_full_name: string
  default_branch: string
  deploy_repo_full_name: string
  deploy_strategy: string
  deploy_trigger_enabled: boolean
  staging_host_label: string
  production_host_label: string
  staging_workflow_file: string
  production_workflow_file: string
  notes: string
}

const EMPTY_DRAFT: ProjectDraft = {
  project_key: '',
  display_name: '',
  root_path: '',
  repo_full_name: '',
  default_branch: 'main',
  deploy_repo_full_name: '',
  deploy_strategy: 'disabled',
  deploy_trigger_enabled: false,
  staging_host_label: '',
  production_host_label: '',
  staging_workflow_file: 'deploy-staging.yml',
  production_workflow_file: 'deploy-production.yml',
  notes: '',
}

function ProjectForm({
  draft,
  saving,
  onChange,
  onClose,
  onSubmit,
}: Readonly<{
  draft: ProjectDraft
  saving: boolean
  onChange: (patch: Partial<ProjectDraft>) => void
  onClose: () => void
  onSubmit: () => Promise<void>
}>) {
  return (
    <div className="grid gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <FieldLabel>项目标识</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.project_key} onChange={(event) => onChange({ project_key: event.target.value })} />
        </div>
        <div>
          <FieldLabel>显示名称</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.display_name} onChange={(event) => onChange({ display_name: event.target.value })} />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <FieldLabel>仓库根路径</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.root_path} onChange={(event) => onChange({ root_path: event.target.value })} />
        </div>
        <div>
          <FieldLabel>GitHub 仓库</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.repo_full_name} onChange={(event) => onChange({ repo_full_name: event.target.value })} />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div>
          <FieldLabel>默认分支</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.default_branch} onChange={(event) => onChange({ default_branch: event.target.value })} />
        </div>
        <div>
          <FieldLabel>部署仓库</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.deploy_repo_full_name} onChange={(event) => onChange({ deploy_repo_full_name: event.target.value })} />
        </div>
        <div>
          <FieldLabel>部署策略</FieldLabel>
          <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.deploy_strategy} onChange={(event) => onChange({ deploy_strategy: event.target.value })}>
            <option value="disabled">disabled</option>
            <option value="github_actions">github_actions</option>
            <option value="manual">manual</option>
            <option value="github_actions_ssh">github_actions_ssh</option>
          </select>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <FieldLabel>Staging 环境标签</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.staging_host_label} onChange={(event) => onChange({ staging_host_label: event.target.value })} />
        </div>
        <div>
          <FieldLabel>Production 环境标签</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.production_host_label} onChange={(event) => onChange({ production_host_label: event.target.value })} />
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <FieldLabel>Staging Workflow</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.staging_workflow_file} onChange={(event) => onChange({ staging_workflow_file: event.target.value })} />
        </div>
        <div>
          <FieldLabel>Production Workflow</FieldLabel>
          <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.production_workflow_file} onChange={(event) => onChange({ production_workflow_file: event.target.value })} />
        </div>
      </div>
      <label className="flex items-center gap-3 text-sm text-[color:var(--ops-text-body)]">
        <input type="checkbox" checked={draft.deploy_trigger_enabled} onChange={(event) => onChange({ deploy_trigger_enabled: event.target.checked })} />
        启用部署触发
      </label>
      <div>
        <FieldLabel>备注</FieldLabel>
        <textarea className="mt-2 min-h-[120px] w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={draft.notes} onChange={(event) => onChange({ notes: event.target.value })} />
      </div>
      <div className="flex justify-end gap-3">
        <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" onClick={onClose}>
          取消
        </button>
        <button
          type="button"
          className="rounded-xl bg-[color:var(--ops-accent-strong)] px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
          disabled={saving || !draft.project_key.trim() || !draft.display_name.trim() || !draft.root_path.trim()}
          onClick={() => {
            onSubmit().catch(() => {})
          }}
        >
          {saving ? '提交中…' : '保存'}
        </button>
      </div>
    </div>
  )
}

export default function ProjectsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const [projects, setProjects] = useState<Project[]>([])
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState<ProjectDraft>({ ...EMPTY_DRAFT })

  const load = async () => {
    setLoading(true)
    try {
      setProjects(await api.getProjects())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return projects
    return projects.filter((project) => [project.project_key, project.display_name, project.root_path, project.repo_full_name || ''].join('\n').toLowerCase().includes(needle))
  }, [projects, search])

  return (
    <div className="space-y-5" data-testid="projects-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Projects</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">项目列表</h2>
          </div>
          <div className="flex items-center gap-2">
            <input className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" placeholder="搜索项目" value={search} onChange={(event) => setSearch(event.target.value)} />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2.5 text-sm font-medium text-white" onClick={() => setOpen(true)}>
              新建项目
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-slate-50/90">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">项目</th>
                <th className="px-4 py-4 font-medium">仓库路径</th>
                <th className="px-4 py-4 font-medium">GitHub</th>
                <th className="px-4 py-4 font-medium">部署</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((project) => (
                <tr key={project.id} className="border-t border-[color:var(--ops-stroke-soft)] hover:bg-slate-50/80">
                  <td className="px-5 py-4">
                    <div className="text-sm font-semibold text-[color:var(--ops-text-title)]">{project.display_name}</div>
                    <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">{project.project_key}</div>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{project.root_path}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{project.repo_full_name || '-'}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{project.deploy_strategy}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{project.status}</td>
                  <td className="px-5 py-4">
                    <div className="flex justify-end gap-2">
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/projects/${project.id}`)}>
                        查看
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && filtered.length === 0 ? (
          <div className="p-6">
            <EmptyPane>暂无项目。</EmptyPane>
          </div>
        ) : null}
      </section>

      <OverlayModal open={open} title="新建项目" eyebrow="New Project" onClose={() => setOpen(false)}>
        <ProjectForm
          draft={draft}
          saving={saving}
          onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
          onClose={() => setOpen(false)}
          onSubmit={async () => {
            setSaving(true)
            try {
              const created = await api.createProject(draft)
              toast.success('项目已创建')
              setOpen(false)
              setDraft({ ...EMPTY_DRAFT })
              await load()
              navigate(`/projects/${created.id}`)
            } catch {
              toast.error('创建项目失败，请重试')
            } finally {
              setSaving(false)
            }
          }}
        />
      </OverlayModal>
    </div>
  )
}
