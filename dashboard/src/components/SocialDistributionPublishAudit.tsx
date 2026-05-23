import type { SocialDistributionTask } from '../api'
import { Field, InfoBlock, inputClass } from './SocialDistributionWidgets'

interface LastPublishAudit {
  note?: unknown
  source?: unknown
}

export function PublishAuditSummary({ task }: { task: SocialDistributionTask }) {
  const visibilityStatus = stringValue(task.metadata.visibility_status) || (task.status === 'live' ? 'unverified' : 'not_published')
  const layoutStatus = stringValue(task.metadata.layout_status) || 'unknown'
  const visibilityIssue = ['removed_by_filter', 'flagged', 'not_found', 'blocked'].includes(visibilityStatus) || layoutStatus === 'needs_fix'
  const audit = objectValue(task.metadata.last_publish_audit)
  return (
    <section className="grid gap-3 md:grid-cols-3">
      <InfoBlock title="外部可见性">
        {visibilityStatus}
        {visibilityIssue ? ' · Visibility issue' : ''}
      </InfoBlock>
      <InfoBlock title="页面排版">{layoutStatus}</InfoBlock>
      <InfoBlock title="最近审计">
        {stringValue(audit?.note) || stringValue(audit?.source) || '尚未审计'}
      </InfoBlock>
    </section>
  )
}

export function PublishAuditControls({
  visible,
  auditVisibility,
  auditLayout,
  onAuditVisibilityChange,
  onAuditLayoutChange,
}: {
  visible: boolean
  auditVisibility: string
  auditLayout: string
  onAuditVisibilityChange: (value: string) => void
  onAuditLayoutChange: (value: string) => void
}) {
  if (!visible) return null
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <Field label="页面可见性">
        <select className={inputClass} value={auditVisibility} onChange={(event) => onAuditVisibilityChange(event.target.value)}>
          <option value="visible">visible</option>
          <option value="removed_by_filter">removed_by_filter</option>
          <option value="flagged">flagged</option>
          <option value="not_found">not_found</option>
          <option value="blocked">blocked</option>
          <option value="unverified">unverified</option>
        </select>
      </Field>
      <Field label="页面排版">
        <select className={inputClass} value={auditLayout} onChange={(event) => onAuditLayoutChange(event.target.value)}>
          <option value="passed">passed</option>
          <option value="needs_fix">needs_fix</option>
          <option value="unknown">unknown</option>
        </select>
      </Field>
    </div>
  )
}

function objectValue(value: unknown): LastPublishAudit | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as LastPublishAudit
    : null
}

function stringValue(value: unknown): string {
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' ? value : ''
}
