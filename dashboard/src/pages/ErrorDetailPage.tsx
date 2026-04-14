import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ErrorFingerprintDetail, api } from '../api'
import { ActivityFeed, EmptyPane, FieldLabel, InspectorRail, LoadingPane, SectionFrame, StateBadge } from '../components/workbench'

function formatTime(value: string | null) {
  if (!value) return '-'
  return new Date(value.endsWith('Z') ? value : `${value}Z`).toLocaleString('zh-CN')
}

function toneForSeverity(value: string) {
  if (value === 'critical' || value === 'high') return 'blocked'
  if (value === 'normal') return 'running'
  return 'muted'
}

export default function ErrorDetailPage() {
  const { fingerprintKey = '' } = useParams<{ fingerprintKey: string }>()
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ErrorFingerprintDetail | null>(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      setDetail(await api.getErrorDetail(fingerprintKey))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load().catch(() => {})
  }, [fingerprintKey])

  if (loading || !detail) {
    return <LoadingPane>正在加载错误详情…</LoadingPane>
  }

  const fingerprint = detail.fingerprint

  return (
    <div className="space-y-[var(--ops-section-gap)]" data-testid="error-detail-page">
      <SectionFrame
        eyebrow="Error Fingerprint"
        title={fingerprint.service_name}
        description="错误详情页只负责稳定性治理：查看证据、关联 requirement/execution、以及通知历史。"
        actions={
          <div className="flex flex-wrap gap-2">
            <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate('/errors')}>
              返回错误列表
            </button>
            <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/requirements/${detail.requirement?.id}`)} disabled={!detail.requirement}>
              查看需求
            </button>
            <button className="rounded-2xl border border-[color:var(--ops-stroke-strong)] px-4 py-2 text-sm" onClick={() => navigate(`/executions/${detail.latest_execution?.id}`)} disabled={!detail.latest_execution}>
              查看执行
            </button>
          </div>
        }
      >
        <div className="flex flex-wrap gap-2">
          <StateBadge tone={toneForSeverity(fingerprint.severity)}>{fingerprint.severity}</StateBadge>
          <StateBadge tone="muted">{fingerprint.source_kind}</StateBadge>
          <StateBadge tone="muted">{fingerprint.status}</StateBadge>
        </div>
        <div className="mt-4 grid gap-3 text-sm text-[color:var(--ops-text-muted)] md:grid-cols-2 xl:grid-cols-4">
          <div>fingerprint: {fingerprint.fingerprint_key}</div>
          <div>occurrences: {fingerprint.occurrence_count}</div>
          <div>first seen: {formatTime(fingerprint.first_seen_at)}</div>
          <div>latest seen: {formatTime(fingerprint.latest_seen_at)}</div>
        </div>
        <div className="mt-4 text-sm leading-6 text-[color:var(--ops-text-muted)]">{fingerprint.summary}</div>
      </SectionFrame>

      <div className="grid gap-[var(--ops-section-gap)] xl:grid-cols-[minmax(0,1.5fr),minmax(300px,var(--ops-inspector-width))]">
        <div className="space-y-[var(--ops-section-gap)]">
          <SectionFrame eyebrow="Evidence" title="最新错误事件">
            {detail.events.length > 0 ? (
              <div className="space-y-4">
                {detail.events.map((event) => (
                  <article key={event.id} className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-white/74 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <StateBadge tone={toneForSeverity(event.severity)}>{event.severity}</StateBadge>
                      <StateBadge tone="muted">{event.source_kind}</StateBadge>
                      <div className="text-xs text-[color:var(--ops-text-caption)]">{formatTime(event.occurred_at)}</div>
                    </div>
                    <div className="mt-3 text-sm font-medium text-[color:var(--ops-text-title)]">{event.summary}</div>
                    <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-950/95 p-3 text-xs text-slate-100">{event.message}</pre>
                    {event.stack_trace ? <pre className="mt-3 overflow-x-auto rounded-xl bg-slate-950/90 p-3 text-xs text-slate-200">{event.stack_trace}</pre> : null}
                  </article>
                ))}
              </div>
            ) : (
              <EmptyPane>暂无错误事件。</EmptyPane>
            )}
          </SectionFrame>

          <ActivityFeed eyebrow="Notification History" title="通知历史">
            {detail.notifications.length > 0 ? (
              detail.notifications.map((delivery) => (
                <div key={delivery.id} className="rounded-[var(--ops-radius-panel)] border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] px-4 py-4 text-sm text-[color:var(--ops-text-muted)]">
                  <div className="flex flex-wrap items-center gap-2">
                    <StateBadge tone={delivery.status === 'sent' ? 'ready' : delivery.status === 'failed' ? 'blocked' : 'muted'}>{delivery.status}</StateBadge>
                    <StateBadge tone="muted">{delivery.channel}</StateBadge>
                    <div className="text-xs text-[color:var(--ops-text-caption)]">{delivery.event_type}</div>
                  </div>
                  <div className="mt-3">{String(delivery.payload.summary || '')}</div>
                  <div className="mt-2 text-xs text-[color:var(--ops-text-caption)]">{formatTime(delivery.delivered_at || delivery.created_at)}</div>
                </div>
              ))
            ) : (
              <EmptyPane>当前还没有通知投递记录。</EmptyPane>
            )}
          </ActivityFeed>
        </div>

        <div className="space-y-[var(--ops-section-gap)]">
          <InspectorRail eyebrow="Linked Requirement" title="需求与执行">
            <div>
              <FieldLabel>Requirement</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">
                {detail.requirement ? `#${detail.requirement.id} · ${detail.requirement.title}` : '-'}
              </div>
            </div>
            <div>
              <FieldLabel>Execution</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">
                {detail.latest_execution ? `#${detail.latest_execution.id} · ${detail.latest_execution.status}` : '-'}
              </div>
            </div>
            <div>
              <FieldLabel>Release</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">
                {detail.release ? `${detail.release.status} · PR ${detail.release.pr_number || '-'}` : '-'}
              </div>
            </div>
          </InspectorRail>

          <InspectorRail eyebrow="Signal Metadata" title="错误上下文">
            <div>
              <FieldLabel>Service</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{fingerprint.service_name}</div>
            </div>
            <div>
              <FieldLabel>Project</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{fingerprint.project_key || fingerprint.project_root_path || '-'}</div>
            </div>
            <div>
              <FieldLabel>Incident Code</FieldLabel>
              <div className="mt-2 text-[color:var(--ops-text-muted)]">{fingerprint.incident_code || '-'}</div>
            </div>
            <div>
              <FieldLabel>Evidence Excerpt</FieldLabel>
              <div className="mt-2 whitespace-pre-wrap text-[color:var(--ops-text-muted)]">{fingerprint.evidence_excerpt || '-'}</div>
            </div>
          </InspectorRail>
        </div>
      </div>
    </div>
  )
}
