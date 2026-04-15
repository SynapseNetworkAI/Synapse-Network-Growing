import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AgentRequirement, Project, RequirementAttachmentInput, api } from '../api'
import { ConfirmDialog, EmptyPane, FieldLabel, OverlayDrawer, OverlayModal, StateBadge, useToast } from '../components/workbench'

type DrawerMode = 'closed' | 'create' | 'edit'

type RequirementDraft = {
  title: string
  description_markdown: string
  priority: string
  project_id: number | null
  target_project_path_override: string
  attachments: ComposerAttachment[]
}

type ComposerAttachment = RequirementAttachmentInput & {
  local_id: string
  attachment_kind: 'image' | 'file'
  size_bytes: number
  preview_url: string | null
}

const MAX_ATTACHMENTS = 12
const MAX_ATTACHMENT_SIZE_BYTES = 3 * 1024 * 1024

const EMPTY_DRAFT: RequirementDraft = {
  title: '',
  description_markdown: '',
  priority: 'normal',
  project_id: null,
  target_project_path_override: '',
  attachments: [],
}

function attachmentKind(contentType: string, fileName: string): 'image' | 'file' {
  if (contentType.toLowerCase().startsWith('image/')) return 'image'
  const lower = fileName.toLowerCase()
  if (['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'].some((suffix) => lower.endsWith(suffix))) return 'image'
  return 'file'
}

function formatBytes(size: number) {
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  if (size >= 1024) return `${Math.round(size / 1024)} KB`
  return `${size} B`
}

async function fileToAttachment(file: File, source: string): Promise<ComposerAttachment> {
  const buffer = await file.arrayBuffer()
  const bytes = new Uint8Array(buffer)
  let binary = ''
  const chunkSize = 0x8000
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize))
  }
  const contentBase64 = btoa(binary)
  const kind = attachmentKind(file.type || 'application/octet-stream', file.name)
  return {
    local_id: `${Date.now()}-${file.name}-${Math.random().toString(36).slice(2, 8)}`,
    file_name: file.name,
    content_type: file.type || 'application/octet-stream',
    content_base64: contentBase64,
    source,
    attachment_kind: kind,
    size_bytes: file.size,
    preview_url: kind === 'image' ? URL.createObjectURL(file) : null,
  }
}

const STATUS_LABEL: Record<string, string> = {
  draft: '草稿',
  ready: '待执行',
  running: '执行中',
  blocked: '阻塞',
  needs_revision: '需修订',
  delivery_ready: '待发布',
  done: '已完成',
  cancelled: '已取消',
  deleted: '已删除',
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function statusTone(status: string) {
  if (status === 'done' || status === 'delivery_ready') return 'delivered'
  if (status === 'running') return 'running'
  if (status === 'blocked' || status === 'needs_revision' || status === 'cancelled') return 'blocked'
  if (status === 'ready') return 'ready'
  return 'muted'
}

function assetsLabel(requirement: AgentRequirement) {
  if (requirement.assets_status === 'ready') return '计划已就绪'
  if (requirement.assets_status === 'failed') return '计划生成失败'
  return '生成计划中'
}

function canEditRequirement(requirement: AgentRequirement) {
  return (requirement.allowed_actions ?? fallbackRequirementAllowedActions(requirement)).includes('edit')
}

function fallbackRequirementAllowedActions(requirement: AgentRequirement): string[] {
  const actions = new Set<string>(['view'])
  if (requirement.active_execution_run_id != null || requirement.latest_execution_run_id != null) {
    actions.add('view_execution')
  }
  if (requirement.latest_release_status) {
    actions.add('view_release')
  }
  if (requirement.status === 'draft' || requirement.status === 'ready' || requirement.status === 'blocked' || requirement.status === 'needs_revision') {
    actions.add('edit')
  }
  if (requirement.assets_status === 'ready' && (requirement.status === 'draft' || requirement.status === 'needs_revision')) {
    actions.add('submit')
  }
  if (requirement.assets_status === 'failed') {
    actions.add('regenerate_assets')
  }
  if (requirement.approval_status === 'pending_approval') {
    actions.add('approve')
    actions.add('reject')
  }
  if (requirement.latest_execution_run_id == null && ['draft', 'planning', 'needs_revision', 'blocked'].includes(requirement.phase || requirement.status)) {
    actions.add('delete')
  }
  return [...actions]
}

function phaseLabel(requirement: AgentRequirement) {
  if (requirement.recovery_timeout_status === 'timed_out') return '恢复超时，需人工介入'
  if (requirement.recovery_status === 'recovering') return '恢复中，仅影响当前需求'
  if (requirement.recovery_status) return `恢复: ${requirement.recovery_status}`
  const phase = requirement.phase || requirement.status
  if (phase === 'awaiting_execution_approval') return '等待执行审批'
  if (phase === 'branch_preparing') return '准备分支中'
  if (phase === 'branch_prepared') return '分支已就绪'
  if (phase === 'verifying') return '验证中'
  if (phase === 'pr_opened') return 'PR 已创建'
  if (phase === 'recovering') return '恢复中'
  return phase
}

function buildDraft(requirement?: AgentRequirement | null): RequirementDraft {
  if (!requirement) return { ...EMPTY_DRAFT }
  return {
    title: requirement.title,
    description_markdown: requirement.description_markdown,
    priority: requirement.priority,
    project_id: requirement.project_id,
    target_project_path_override: requirement.target_project_path_override || '',
    attachments: [],
  }
}

function RequirementForm({
  draft,
  projects,
  saving,
  onChange,
  onClose,
  onSubmit,
  onUploadError,
}: Readonly<{
  draft: RequirementDraft
  projects: Project[]
  saving: boolean
  onChange: (patch: Partial<RequirementDraft>) => void
  onClose: () => void
  onSubmit: () => Promise<void>
  onUploadError: (message: string) => void
}>) {
  const [showAdvanced, setShowAdvanced] = useState(Boolean(draft.target_project_path_override))
  const [dragActive, setDragActive] = useState(false)
  const fileInputId = useId()
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const addFiles = async (files: FileList | File[] | null, source: string) => {
    if (!files || files.length === 0) return
    const selected = Array.from(files)
    if (draft.attachments.length + selected.length > MAX_ATTACHMENTS) {
      onUploadError(`最多只能添加 ${MAX_ATTACHMENTS} 个附件`)
      return
    }
    const oversized = selected.find((file) => file.size > MAX_ATTACHMENT_SIZE_BYTES)
    if (oversized) {
      onUploadError(`${oversized.name} 超过 ${(MAX_ATTACHMENT_SIZE_BYTES / (1024 * 1024)).toFixed(0)} MB 限制`)
      return
    }
    try {
      const next = await Promise.all(selected.map((file) => fileToAttachment(file, source)))
      onChange({ attachments: [...draft.attachments, ...next] })
    } catch {
      onUploadError('附件读取失败，请重试')
    }
  }

  const removeAttachment = (localId: string) => {
    const removed = draft.attachments.find((item) => item.local_id === localId)
    if (removed?.preview_url) URL.revokeObjectURL(removed.preview_url)
    onChange({ attachments: draft.attachments.filter((item) => item.local_id !== localId) })
  }

  return (
    <div className="grid gap-5">
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <FieldLabel>标题</FieldLabel>
          <input
            data-testid="requirement-title"
            className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            placeholder="输入需求标题"
            value={draft.title}
            onChange={(event) => onChange({ title: event.target.value })}
          />
        </div>
        <div>
          <FieldLabel>所属项目</FieldLabel>
          <select
            data-testid="requirement-project"
            className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            value={draft.project_id ?? ''}
            onChange={(event) => onChange({ project_id: event.target.value ? Number(event.target.value) : null })}
          >
            <option value="">选择项目</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.display_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <FieldLabel>需求描述</FieldLabel>
        <div
          className={[
            'mt-2 rounded-2xl border bg-white transition',
            dragActive ? 'border-[color:var(--ops-accent-strong)] ring-2 ring-[color:var(--ops-accent-soft)]' : 'border-[color:var(--ops-stroke-strong)]',
          ].join(' ')}
          onDragEnter={(event) => {
            event.preventDefault()
            setDragActive(true)
          }}
          onDragOver={(event) => {
            event.preventDefault()
            setDragActive(true)
          }}
          onDragLeave={(event) => {
            event.preventDefault()
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
            setDragActive(false)
          }}
          onDrop={(event) => {
            event.preventDefault()
            setDragActive(false)
            addFiles(event.dataTransfer.files, 'drag_drop').catch(() => {})
          }}
          onPaste={(event) => {
            const files = Array.from(event.clipboardData?.files || [])
            if (!files.length) return
            event.preventDefault()
            addFiles(files, 'clipboard').catch(() => {})
          }}
        >
          <textarea
            data-testid="requirement-description"
            className="min-h-[220px] w-full rounded-t-2xl border-0 px-4 py-3 text-sm outline-none"
            placeholder="输入需求描述"
            value={draft.description_markdown}
            onChange={(event) => onChange({ description_markdown: event.target.value })}
          />
          <div className="border-t border-[color:var(--ops-stroke-soft)] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-xs text-[color:var(--ops-text-caption)]">
                支持拖拽、粘贴截图或上传文件。图片、PDF、日志和设计参考都会作为 requirement context 进入后续 agent 流程。
              </div>
              <div className="flex items-center gap-2">
                <input
                  id={fileInputId}
                  ref={fileInputRef}
                  data-testid="requirement-attachment-input"
                  type="file"
                  multiple
                  className="hidden"
                  accept="image/*,.pdf,.md,.txt,.json,.csv,.log,.zip"
                  onChange={(event) => {
                    addFiles(event.target.files, 'upload').catch(() => {})
                    event.currentTarget.value = ''
                  }}
                />
                <button
                  type="button"
                  className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Add photos & files
                </button>
              </div>
            </div>
            {draft.attachments.length ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {draft.attachments.map((attachment) => (
                  <div
                    key={attachment.local_id}
                    className="overflow-hidden rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/80"
                  >
                    {attachment.attachment_kind === 'image' && attachment.preview_url ? (
                      <img
                        src={attachment.preview_url}
                        alt={attachment.file_name}
                        className="h-36 w-full object-cover"
                      />
                    ) : null}
                    <div className="space-y-2 px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-[color:var(--ops-text-title)]">{attachment.file_name}</div>
                          <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">
                            {attachment.attachment_kind === 'image' ? '图片' : '文件'} · {attachment.content_type || 'application/octet-stream'} · {formatBytes(attachment.size_bytes)}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-2 py-1 text-xs"
                          onClick={() => removeAttachment(attachment.local_id)}
                        >
                          删除
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-slate-50/70 px-4 py-4">
        <button type="button" className="text-sm font-medium text-[color:var(--ops-text-title)]" onClick={() => setShowAdvanced((current) => !current)}>
          {showAdvanced ? '隐藏高级设置' : '显示高级设置'}
        </button>
        {showAdvanced ? (
          <div className="mt-4">
            <FieldLabel>路径覆盖（可选）</FieldLabel>
            <input
              className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
              placeholder="仅在当前需求需要覆盖项目默认路径时填写"
              value={draft.target_project_path_override}
              onChange={(event) => onChange({ target_project_path_override: event.target.value })}
            />
          </div>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-[220px,1fr]">
        <div>
          <FieldLabel>优先级</FieldLabel>
          <select
            className="mt-2 w-full rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm"
            value={draft.priority}
            onChange={(event) => onChange({ priority: event.target.value })}
          >
            <option value="low">low</option>
            <option value="normal">normal</option>
            <option value="high">high</option>
          </select>
        </div>
        <div className="flex items-end justify-end gap-3">
          <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-3 text-sm" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="rounded-xl bg-[color:var(--ops-accent-strong)] px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
            disabled={saving || !draft.title.trim() || !draft.description_markdown.trim() || !draft.project_id}
            onClick={() => {
              onSubmit().catch(() => {})
            }}
          >
            {saving ? '提交中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RequirementComposer({
  mode,
  open,
  draft,
  projects,
  saving,
  selected,
  onChange,
  onClose,
  onSubmit,
  onUploadError,
}: Readonly<{
  mode: DrawerMode
  open: boolean
  draft: RequirementDraft
  projects: Project[]
  saving: boolean
  selected: AgentRequirement | null
  onChange: (patch: Partial<RequirementDraft>) => void
  onClose: () => void
  onSubmit: () => Promise<void>
  onUploadError: (message: string) => void
}>) {
  const editing = mode === 'edit'
  const Container = editing ? OverlayDrawer : OverlayModal

  return (
    <Container open={open} title={editing ? '编辑需求' : '新建需求'} eyebrow={editing ? `Requirement #${selected?.id ?? '-'}` : 'New Requirement'} onClose={onClose}>
      <RequirementForm draft={draft} projects={projects} saving={saving} onChange={onChange} onClose={onClose} onSubmit={onSubmit} onUploadError={onUploadError} />
    </Container>
  )
}

export default function RequirementPool() {
  const navigate = useNavigate()
  const [requirements, setRequirements] = useState<AgentRequirement[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [submittingId, setSubmittingId] = useState<number | null>(null)
  const [confirmingRequirement, setConfirmingRequirement] = useState<AgentRequirement | null>(null)
  const [selectedRequirementId, setSelectedRequirementId] = useState<number | null>(null)
  const [drawerMode, setDrawerMode] = useState<DrawerMode>('closed')
  const [draft, setDraft] = useState<RequirementDraft>({ ...EMPTY_DRAFT })
  const toast = useToast()

  const load = async () => {
    setLoading(true)
    try {
      const [nextRequirements, nextProjects] = await Promise.all([
        api.getRequirements(status || undefined, undefined, search || undefined),
        api.getProjects('active'),
      ])
      setRequirements(nextRequirements)
      setProjects(nextProjects)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [status])

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return requirements
    return requirements.filter((item) =>
      [
        item.title,
        item.source_ref || '',
        item.project_display_name || '',
        item.project_key || '',
        item.target_project_path || '',
        String(item.id),
      ]
        .join('\n')
        .toLowerCase()
        .includes(needle),
    )
  }, [requirements, search])

  useEffect(() => {
    if (selectedRequirementId && filtered.some((item) => item.id === selectedRequirementId)) return
    setSelectedRequirementId(filtered[0]?.id ?? null)
  }, [filtered, selectedRequirementId])

  const selectedRequirement = filtered.find((item) => item.id === selectedRequirementId) ?? null

  const openCreate = () => {
    setDraft({ ...EMPTY_DRAFT })
    setDrawerMode('create')
  }

  const openEdit = (requirement: AgentRequirement) => {
    if (!canEditRequirement(requirement)) return
    setSelectedRequirementId(requirement.id)
    setDraft(buildDraft(requirement))
    setDrawerMode('edit')
  }

  const closeComposer = () => {
    draft.attachments.forEach((item) => {
      if (item.preview_url) URL.revokeObjectURL(item.preview_url)
    })
    setDrawerMode('closed')
    setDraft({ ...EMPTY_DRAFT })
  }

  const handleSubmit = async () => {
    setSaving(true)
    try {
      const basePayload = {
        title: draft.title,
        description_markdown: draft.description_markdown,
        priority: draft.priority,
        project_id: draft.project_id ?? undefined,
        target_project_path_override: draft.target_project_path_override || undefined,
      }
      if (drawerMode === 'create') {
        await api.createRequirement({
          ...basePayload,
          attachments: draft.attachments.map(({ local_id: _localId, attachment_kind: _attachmentKind, size_bytes: _sizeBytes, preview_url: _previewUrl, ...attachment }) => attachment),
        })
        toast.success('需求已创建')
      } else if (drawerMode === 'edit' && selectedRequirement) {
        await api.updateRequirement(selectedRequirement.id, basePayload)
        toast.success('需求已更新')
      }
      await load()
      closeComposer()
    } catch {
      toast.error(drawerMode === 'create' ? '创建失败，请重试' : '保存失败，请重试')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5" data-testid="agent-first-requirements-page">
      <section className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white px-5 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-[0.22em] text-[color:var(--ops-text-caption)]">Requirements</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[color:var(--ops-text-title)]">需求列表</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">全部状态</option>
              <option value="draft">草稿</option>
              <option value="ready">待执行</option>
              <option value="running">执行中</option>
              <option value="blocked">阻塞</option>
              <option value="needs_revision">需修订</option>
              <option value="delivery_ready">待发布</option>
              <option value="done">已完成</option>
            </select>
            <input
              className="w-72 rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm"
              placeholder="搜索标题 / 项目 / ID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <button type="button" className="rounded-xl border border-[color:var(--ops-stroke-strong)] px-4 py-2.5 text-sm" onClick={() => load().catch(() => {})}>
              刷新
            </button>
            <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2.5 text-sm font-medium text-white" onClick={openCreate}>
              新建需求
            </button>
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse">
            <thead className="bg-slate-50/90">
              <tr className="text-left text-xs uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
                <th className="px-5 py-4 font-medium">标题</th>
                <th className="px-4 py-4 font-medium">项目</th>
                <th className="px-4 py-4 font-medium">状态</th>
                <th className="px-4 py-4 font-medium">优先级</th>
                <th className="px-4 py-4 font-medium">审批</th>
                <th className="px-4 py-4 font-medium">执行 / 发布</th>
                <th className="px-4 py-4 font-medium">更新时间</th>
                <th className="px-5 py-4 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr
                  key={item.id}
                  className={[
                    'border-t border-[color:var(--ops-stroke-soft)] transition hover:bg-slate-50/80',
                    item.id === selectedRequirementId ? 'bg-slate-50/70' : '',
                  ].join(' ')}
                  onClick={() => setSelectedRequirementId(item.id)}
                >
                  <td className="px-5 py-4">
                    <button type="button" className="text-left" onClick={() => navigate(`/requirements/${item.id}`)}>
                      <div className="text-base font-semibold text-[color:var(--ops-text-title)]">{item.title}</div>
                      <div className="mt-1 text-xs text-[color:var(--ops-text-caption)]">#{item.id}</div>
                    </button>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.project_display_name || item.project_key || '-'}</td>
                  <td className="px-4 py-4">
                    <StateBadge tone={statusTone(item.status)}>{STATUS_LABEL[item.status] || item.status}</StateBadge>
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-body)]">{item.priority}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{item.approval_required ? item.approval_status : 'waived'}</td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                    {assetsLabel(item)} · {phaseLabel(item)} · execution {item.active_execution_run_id ?? item.latest_execution_run_id ?? '-'} · {item.latest_release_status ?? '-'}
                  </td>
                  <td className="px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">{formatTime(item.updated_at)}</td>
                  <td className="px-5 py-4">
                    <div className="flex flex-wrap justify-end gap-2">
                      {(() => {
                        const allowedActions = item.allowed_actions ?? fallbackRequirementAllowedActions(item)
                        return (
                          <>
                      <button
                        type="button"
                        className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-50"
                        disabled={!allowedActions.includes('edit')}
                        onClick={() => openEdit(item)}
                      >
                        编辑
                      </button>
                      {allowedActions.includes('delete') ? (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
                          disabled={deletingId === item.id}
                          onClick={() => setConfirmingRequirement(item)}
                        >
                          {deletingId === item.id ? '删除中…' : '删除'}
                        </button>
                      ) : null}
                      <button type="button" className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm" onClick={() => navigate(`/requirements/${item.id}`)}>
                        查看
                      </button>
                      {item.assets_status === 'failed' ? (
                        <button
                          type="button"
                          className="rounded-lg border border-[color:var(--ops-state-blocked-border)] px-3 py-2 text-sm text-[color:var(--ops-state-blocked-text)] disabled:opacity-50"
                          disabled={submittingId === item.id || !allowedActions.includes('regenerate_assets')}
                          onClick={async () => {
                            setSubmittingId(item.id)
                            try {
                              await api.regenerateRequirementAssets(item.id)
                              toast.success('已重新开始生成验收标准与执行计划')
                            } catch (error) {
                              const message = error instanceof Error ? error.message : '重新生成失败，请重试'
                              toast.error(message)
                            } finally {
                              await load()
                              setSubmittingId(null)
                            }
                          }}
                        >
                          重新生成
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="rounded-lg bg-[color:var(--ops-text-title)] px-3 py-2 text-sm text-white disabled:opacity-50"
                        disabled={
                          submittingId === item.id ||
                          !allowedActions.includes('submit')
                        }
                        onClick={async () => {
                          setSubmittingId(item.id)
                          try {
                            const detail = await api.submitRequirement(item.id)
                            toast.success('需求已提交')
                            if (detail.approval.execution_run_id && detail.approval.auto_started) {
                              navigate(`/executions/${detail.approval.execution_run_id}`)
                              return
                            }
                            navigate(`/requirements/${item.id}`)
                          } catch (error) {
                            const message = error instanceof Error ? error.message : '提交失败，请重试'
                            toast.error(message)
                          } finally {
                            await load()
                            setSubmittingId(null)
                          }
                        }}
                      >
                        {submittingId === item.id ? '提交中…' : item.assets_status === 'pending' ? '生成计划中…' : item.assets_status === 'failed' ? '计划生成失败' : '提交'}
                      </button>
                          </>
                        )
                      })()}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 ? (
          <div className="p-6">
            <EmptyPane>
              <button type="button" className="rounded-xl bg-[color:var(--ops-accent-strong)] px-4 py-2 text-sm font-medium text-white" onClick={openCreate}>
                新建需求
              </button>
            </EmptyPane>
          </div>
        ) : null}
      </section>

      <RequirementComposer
        mode={drawerMode}
        open={drawerMode !== 'closed'}
        draft={draft}
        projects={projects}
        saving={saving}
        selected={selectedRequirement}
        onChange={(patch) => setDraft((current) => ({ ...current, ...patch }))}
        onClose={closeComposer}
        onSubmit={handleSubmit}
        onUploadError={(message) => toast.error(message)}
      />

      <ConfirmDialog
        open={Boolean(confirmingRequirement)}
        title="删除需求"
        description={
          confirmingRequirement
            ? `删除后，需求 #${confirmingRequirement.id} 会进入 deleted 状态，并从当前主队列视图中移除。`
            : undefined
        }
        confirmLabel="确认删除"
        cancelLabel="取消"
        tone="destructive"
        loading={Boolean(confirmingRequirement && deletingId === confirmingRequirement.id)}
        onClose={() => {
          if (deletingId) return
          setConfirmingRequirement(null)
        }}
        onConfirm={() => {
          if (!confirmingRequirement) return
          const requirementId = confirmingRequirement.id
          setDeletingId(requirementId)
          ;(async () => {
            try {
              await api.deleteRequirement(requirementId)
              toast.success('需求已删除')
              setConfirmingRequirement(null)
              await load()
            } catch (error) {
              const message = error instanceof Error ? error.message : '删除失败，请重试'
              toast.error(message)
            } finally {
              setDeletingId(null)
            }
          })().catch(() => {})
        }}
      />
    </div>
  )
}
