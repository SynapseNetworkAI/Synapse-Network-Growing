import { useEffect, useState } from 'react'
import { api, ProjectPolicy } from '../api'

function parseLines(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

export default function ProjectPolicies() {
  const [policies, setPolicies] = useState<ProjectPolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [drafts, setDrafts] = useState<Record<number, {
    display_name: string
    root_path: string
    status: string
    release_mode: string
    requires_manual_approval: boolean
    allowed_write_globs: string
    forbidden_globs: string
    required_checks: string
    notes: string
  }>>({})

  const loadPolicies = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.getProjectPolicies()
      setPolicies(data)
      setDrafts(
        Object.fromEntries(
          data.map((policy) => [
            policy.id,
            {
              display_name: policy.display_name,
              root_path: policy.root_path,
              status: policy.status,
              release_mode: policy.release_mode,
              requires_manual_approval: policy.requires_manual_approval,
              allowed_write_globs: policy.allowed_write_globs.join('\n'),
              forbidden_globs: policy.forbidden_globs.join('\n'),
              required_checks: policy.required_checks.join('\n'),
              notes: policy.notes || '',
            },
          ]),
        ),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载项目策略失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadPolicies().catch(() => {})
  }, [])

  if (loading) {
    return <div data-testid="project-policies-loading" className="rounded-xl border bg-white p-6 text-sm text-gray-500">正在加载项目策略…</div>
  }

  if (error) {
    return <div data-testid="project-policies-error" className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-700">{error}</div>
  }

  return (
    <div data-testid="project-policies-page" className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">项目策略</h2>
          <p className="text-sm text-gray-500">为每个受管项目定义可写范围、禁止范围、必跑检查和发布模式。</p>
        </div>
        <button
          className="rounded-lg border px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
          onClick={() => loadPolicies().catch(() => {})}
        >
          刷新
        </button>
      </div>

      <div className="grid gap-4">
        {policies.map((policy) => {
          const draft = drafts[policy.id]
          if (!draft) return null
          return (
            <div key={policy.id} data-testid={`project-policy-card-${policy.id}`} className="space-y-4 rounded-xl border bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">{policy.display_name}</h3>
                  <p className="font-mono text-xs text-gray-500">{policy.project_key}</p>
                </div>
                <div className="text-right text-xs text-gray-500">
                  <div>更新时间: {formatTime(policy.updated_at)}</div>
                  <div>发布模式: {policy.release_mode}</div>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">显示名称</span>
                  <input
                    className="w-full rounded border px-3 py-2"
                    value={draft.display_name}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, display_name: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">项目根路径</span>
                  <input
                    className="w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.root_path}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, root_path: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">状态</span>
                  <select
                    className="w-full rounded border px-3 py-2"
                    value={draft.status}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, status: e.target.value } }))}
                  >
                    <option value="active">active</option>
                    <option value="disabled">disabled</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">发布模式</span>
                  <select
                    className="w-full rounded border px-3 py-2"
                    value={draft.release_mode}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, release_mode: e.target.value } }))}
                  >
                    <option value="disabled">disabled</option>
                    <option value="manual">manual</option>
                    <option value="auto">auto</option>
                  </select>
                </label>
              </div>

              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={draft.requires_manual_approval}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, requires_manual_approval: e.target.checked } }))}
                />
                需要人工审批
              </label>

              <div className="grid gap-4 md:grid-cols-3">
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">允许写入 globs</span>
                  <textarea
                    className="min-h-[120px] w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.allowed_write_globs}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, allowed_write_globs: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">禁止写入 globs</span>
                  <textarea
                    className="min-h-[120px] w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.forbidden_globs}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, forbidden_globs: e.target.value } }))}
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-gray-500">必跑检查</span>
                  <textarea
                    className="min-h-[120px] w-full rounded border px-3 py-2 font-mono text-xs"
                    value={draft.required_checks}
                    onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, required_checks: e.target.value } }))}
                  />
                </label>
              </div>

              <label className="space-y-1 text-sm">
                <span className="text-gray-500">备注</span>
                <textarea
                  className="min-h-[80px] w-full rounded border px-3 py-2 text-sm"
                  value={draft.notes}
                  onChange={(e) => setDrafts((prev) => ({ ...prev, [policy.id]: { ...draft, notes: e.target.value } }))}
                />
              </label>

              <div className="flex justify-end">
                <button
                  data-testid={`project-policy-save-${policy.id}`}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  disabled={savingId === policy.id}
                  onClick={async () => {
                    setSavingId(policy.id)
                    try {
                      await api.updateProjectPolicy(policy.id, {
                        display_name: draft.display_name,
                        root_path: draft.root_path,
                        status: draft.status,
                        release_mode: draft.release_mode,
                        requires_manual_approval: draft.requires_manual_approval,
                        allowed_write_globs: parseLines(draft.allowed_write_globs),
                        forbidden_globs: parseLines(draft.forbidden_globs),
                        required_checks: parseLines(draft.required_checks),
                        notes: draft.notes || null,
                      })
                      await loadPolicies()
                    } catch (err) {
                      alert(err instanceof Error ? err.message : '保存项目策略失败')
                    } finally {
                      setSavingId(null)
                    }
                  }}
                >
                  {savingId === policy.id ? '保存中…' : '保存策略'}
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
