import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ProjectPolicy, ProjectWithPolicy, api } from '../api'
import { FieldLabel, LoadingPane, SectionFrame, useToast } from '../components/workbench'
import { PROJECT_DEPLOY_STRATEGIES } from '../projectDeployStrategies'

type ProjectFormState = {
  project_key: string
  display_name: string
  root_path: string
  status: string
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

function buildProjectForm(project: ProjectWithPolicy): ProjectFormState {
  return {
    project_key: project.project_key,
    display_name: project.display_name,
    root_path: project.root_path,
    status: project.status,
    repo_full_name: project.repo_full_name || '',
    default_branch: project.default_branch,
    deploy_repo_full_name: project.deploy_repo_full_name || '',
    deploy_strategy: project.deploy_strategy,
    deploy_trigger_enabled: project.deploy_trigger_enabled,
    staging_host_label: project.staging_host_label || '',
    production_host_label: project.production_host_label || '',
    staging_workflow_file: project.staging_workflow_file,
    production_workflow_file: project.production_workflow_file,
    notes: project.notes || '',
  }
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const toast = useToast()
  const projectId = Number(id)
  const [detail, setDetail] = useState<ProjectWithPolicy | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [policySaving, setPolicySaving] = useState(false)
  const [form, setForm] = useState<ProjectFormState | null>(null)
  const [policyForm, setPolicyForm] = useState<ProjectPolicy | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const project = await api.getProject(projectId)
      setDetail(project)
      setForm(buildProjectForm(project))
      setPolicyForm(project.policy)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [projectId])

  if (loading || !detail || !form || !policyForm) {
    return <LoadingPane>正在加载项目…</LoadingPane>
  }

  return (
    <div className="space-y-5" data-testid="project-detail-page">
      <SectionFrame
        eyebrow="Project"
        title={detail.display_name}
        actions={
          <button
            className="rounded-2xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm text-white disabled:opacity-50"
            disabled={saving}
            onClick={async () => {
              setSaving(true)
              try {
                const next = await api.updateProject(projectId, form)
                setDetail(next)
                setForm(buildProjectForm(next))
                setPolicyForm(next.policy)
                toast.success('项目已更新')
              } catch {
                toast.error('保存项目失败，请重试')
              } finally {
                setSaving(false)
              }
            }}
          >
            保存项目
          </button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>项目标识</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.project_key} onChange={(event) => setForm((current) => (current ? { ...current, project_key: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>显示名称</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.display_name} onChange={(event) => setForm((current) => (current ? { ...current, display_name: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>仓库根路径</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.root_path} onChange={(event) => setForm((current) => (current ? { ...current, root_path: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>GitHub 仓库</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.repo_full_name} onChange={(event) => setForm((current) => (current ? { ...current, repo_full_name: event.target.value } : current))} />
            <p className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">可填 git 地址或 owner/repo，保存后系统会归一化为 owner/repo。</p>
          </div>
          <div>
            <FieldLabel>默认分支</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.default_branch} onChange={(event) => setForm((current) => (current ? { ...current, default_branch: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>状态</FieldLabel>
            <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.status} onChange={(event) => setForm((current) => (current ? { ...current, status: event.target.value } : current))}>
              <option value="active">active</option>
              <option value="archived">archived</option>
            </select>
          </div>
        </div>
      </SectionFrame>

      <SectionFrame
        eyebrow="Delivery"
        title="GitHub 与部署"
        actions={
          <button
            className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm disabled:opacity-50"
            disabled={policySaving}
            onClick={async () => {
              setPolicySaving(true)
              try {
                const nextPolicy = await api.updateProjectPolicyForProject(projectId, {
                  deploy_repo_full_name: form.deploy_repo_full_name || null,
                  deploy_strategy: form.deploy_strategy,
                  deploy_trigger_enabled: form.deploy_trigger_enabled,
                  staging_host_label: form.staging_host_label || null,
                  production_host_label: form.production_host_label || null,
                  staging_workflow_file: form.staging_workflow_file,
                  production_workflow_file: form.production_workflow_file,
                  notes: form.notes || null,
                })
                setPolicyForm(nextPolicy)
                const next = await api.getProject(projectId)
                setDetail(next)
                setForm(buildProjectForm(next))
                toast.success('治理配置已更新')
              } catch {
                toast.error('保存治理配置失败，请重试')
              } finally {
                setPolicySaving(false)
              }
            }}
          >
            保存治理配置
          </button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>部署仓库</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.deploy_repo_full_name} onChange={(event) => setForm((current) => (current ? { ...current, deploy_repo_full_name: event.target.value } : current))} />
            <p className="mt-2 text-xs leading-5 text-[color:var(--ops-text-caption)]">通常与 GitHub 仓库相同；仅部署仓库不同的时候填写。</p>
          </div>
          <div>
            <FieldLabel>部署策略</FieldLabel>
            <select className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.deploy_strategy} onChange={(event) => setForm((current) => (current ? { ...current, deploy_strategy: event.target.value } : current))}>
              {PROJECT_DEPLOY_STRATEGIES.includes(form.deploy_strategy) ? null : <option value={form.deploy_strategy}>{form.deploy_strategy}</option>}
              {PROJECT_DEPLOY_STRATEGIES.map((strategy) => <option key={strategy} value={strategy}>{strategy}</option>)}
            </select>
          </div>
          <div>
            <FieldLabel>Staging 标签</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.staging_host_label} onChange={(event) => setForm((current) => (current ? { ...current, staging_host_label: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>Production 标签</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.production_host_label} onChange={(event) => setForm((current) => (current ? { ...current, production_host_label: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>Staging Workflow</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.staging_workflow_file} onChange={(event) => setForm((current) => (current ? { ...current, staging_workflow_file: event.target.value } : current))} />
          </div>
          <div>
            <FieldLabel>Production Workflow</FieldLabel>
            <input className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" value={form.production_workflow_file} onChange={(event) => setForm((current) => (current ? { ...current, production_workflow_file: event.target.value } : current))} />
          </div>
        </div>
        <label className="mt-4 flex items-center gap-3 text-sm text-[color:var(--ops-text-body)]">
          <input type="checkbox" checked={form.deploy_trigger_enabled} onChange={(event) => setForm((current) => (current ? { ...current, deploy_trigger_enabled: event.target.checked } : current))} />
          启用部署触发
        </label>
      </SectionFrame>

      <SectionFrame eyebrow="Governance" title="项目治理">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <FieldLabel>审批模式</FieldLabel>
            <div className="mt-2 rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 text-sm">{policyForm.requires_manual_approval ? 'manual approval' : 'auto approval'}</div>
          </div>
          <div>
            <FieldLabel>自治模式</FieldLabel>
            <div className="mt-2 rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 text-sm">{policyForm.autonomy_mode}</div>
          </div>
          <div>
            <FieldLabel>Required Checks</FieldLabel>
            <div className="mt-2 rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 text-sm">{policyForm.required_checks.join(', ') || '-'}</div>
          </div>
          <div>
            <FieldLabel>Allowed Write Globs</FieldLabel>
            <div className="mt-2 rounded-xl border border-[color:var(--ops-stroke-soft)] px-4 py-3 text-sm">{policyForm.allowed_write_globs.join(', ') || '-'}</div>
          </div>
        </div>
      </SectionFrame>
    </div>
  )
}
