import type { ReactNode } from 'react'
import { EmptyPane, StateBadge, type useToast } from './workbench'

export const inputClass = 'w-full rounded-2xl border border-[color:var(--ops-stroke-strong)] bg-[color:var(--ops-panel-strong)] px-4 py-3 text-sm text-[color:var(--ops-text-body)] outline-none transition focus:border-cyan-300/50'
export const textareaClass = `${inputClass} min-h-[120px]`
export const pageSize = 8

export function statusTone(status: string): 'ready' | 'running' | 'blocked' | 'validating' | 'delivered' | 'muted' {
  if (['active', 'registered', 'draft_ready', 'needs_review', 'approved', 'ready'].includes(status)) return 'ready'
  if (['submitted', 'generating'].includes(status)) return 'running'
  if (['live', 'published'].includes(status)) return 'delivered'
  if (['removed', 'failed', 'rejected'].includes(status)) return 'blocked'
  if (['skipped', 'retired', 'archived'].includes(status)) return 'muted'
  return 'validating'
}

export function pageSlice<T>(items: T[], page: number) {
  return items.slice((page - 1) * pageSize, page * pageSize)
}

export function copyText(value: string, toast: ReturnType<typeof useToast>) {
  navigator.clipboard
    ?.writeText(value)
    .then(() => toast.success('已复制到剪贴板'))
    .catch(() => toast.error('复制失败，请手动选择文本'))
}

export function TaskLikeTable({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  if (!rows.length) return <EmptyPane>暂无数据。</EmptyPane>
  return (
    <div className="overflow-hidden rounded-[20px] border border-[color:var(--ops-stroke-soft)]">
      <table className="w-full min-w-[860px] border-collapse text-left text-sm">
        <thead className="bg-[color:var(--ops-panel-subtle)] text-[10px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">
          <tr>{headers.map((header) => <th key={header} className="px-4 py-3 font-medium">{header}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--ops-stroke-soft)]">
          {rows.map((row, index) => (
            <tr key={index} className="bg-[color:var(--ops-workspace-bg)] align-top">
              {row.map((cell, cellIndex) => <td key={cellIndex} className="px-4 py-4">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Pager({ page, total, onPageChange }: { page: number; total: number; onPageChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="mt-4 flex justify-end gap-2">
      <button
        disabled={page <= 1}
        className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-sm disabled:opacity-40"
        onClick={() => onPageChange(page - 1)}
      >
        上一页
      </button>
      <button
        disabled={page >= pages}
        className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2 text-sm disabled:opacity-40"
        onClick={() => onPageChange(page + 1)}
      >
        下一页
      </button>
    </div>
  )
}

export function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-[color:var(--ops-text-title)]">{value}</div>
    </div>
  )
}

export function InfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4">
      <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">{title}</div>
      <div className="whitespace-pre-wrap text-sm leading-6 text-[color:var(--ops-text-body)]">{children}</div>
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-2 text-sm text-[color:var(--ops-text-muted)]"><span>{label}</span>{children}</label>
}

export function AssetForm({
  form,
  onChange,
}: {
  form: { title: string; summary: string; body: string; canonical_url: string; asset_type: string }
  onChange: (value: { title: string; summary: string; body: string; canonical_url: string; asset_type: string }) => void
}) {
  return (
    <div className="grid gap-4">
      <Field label="标题"><input className={inputClass} value={form.title} onChange={(event) => onChange({ ...form, title: event.target.value })} /></Field>
      <Field label="Canonical URL"><input className={inputClass} value={form.canonical_url} onChange={(event) => onChange({ ...form, canonical_url: event.target.value })} /></Field>
      <Field label="摘要"><textarea className={textareaClass} value={form.summary} onChange={(event) => onChange({ ...form, summary: event.target.value })} /></Field>
      <Field label="正文 / Markdown"><textarea className={`${textareaClass} min-h-[180px]`} value={form.body} onChange={(event) => onChange({ ...form, body: event.target.value })} /></Field>
    </div>
  )
}

export function AccountForm({
  form,
  onChange,
}: {
  form: {
    profile_url: string
    status: string
    email_hint: string
    two_factor_status: string
    publish_mode: string
    api_capability: string
    credential_ref: string
    notes: string
  }
  onChange: (value: {
    profile_url: string
    status: string
    email_hint: string
    two_factor_status: string
    publish_mode: string
    api_capability: string
    credential_ref: string
    notes: string
  }) => void
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field label="Profile URL"><input className={inputClass} value={form.profile_url} onChange={(event) => onChange({ ...form, profile_url: event.target.value })} /></Field>
      <Field label="账号状态"><input className={inputClass} value={form.status} onChange={(event) => onChange({ ...form, status: event.target.value })} /></Field>
      <Field label="邮箱提示"><input className={inputClass} value={form.email_hint} onChange={(event) => onChange({ ...form, email_hint: event.target.value })} /></Field>
      <Field label="2FA 状态"><input className={inputClass} value={form.two_factor_status} onChange={(event) => onChange({ ...form, two_factor_status: event.target.value })} /></Field>
      <Field label="发布模式"><input className={inputClass} value={form.publish_mode} onChange={(event) => onChange({ ...form, publish_mode: event.target.value })} /></Field>
      <Field label="API 能力"><input className={inputClass} value={form.api_capability} onChange={(event) => onChange({ ...form, api_capability: event.target.value })} /></Field>
      <Field label="Credential ref"><input className={inputClass} value={form.credential_ref} onChange={(event) => onChange({ ...form, credential_ref: event.target.value })} placeholder="仅保存 secret ref，不填明文 token" /></Field>
      <Field label="备注"><textarea className={`${textareaClass} md:col-span-2`} value={form.notes} onChange={(event) => onChange({ ...form, notes: event.target.value })} /></Field>
    </div>
  )
}

export { StateBadge }
