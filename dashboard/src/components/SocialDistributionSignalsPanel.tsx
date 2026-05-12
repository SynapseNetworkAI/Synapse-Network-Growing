import { useEffect, useState } from 'react'
import { api } from '../api'
import { MetricCard, StateBadge } from './SocialDistributionWidgets'
import { SectionFrame, useToast } from './workbench'

export function DistributionSignalsMetricsPanel({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [trends, setTrends] = useState<Array<{ id: number; topic: string; summary: string; source_url: string | null; author_handle: string | null; relevance_score: number; collected_at: string | null }>>([])
  const [summary, setSummary] = useState<{ observed_post_count: number; total_impressions: number; total_likes: number; total_replies: number; total_reposts: number; total_link_clicks: number; last_observed_at: string | null; diagnostic?: string | null } | null>(null)

  async function load() {
    try {
      const [trendRows, metricSummary] = await Promise.all([api.getSocialTrends(), api.getSocialPostMetricSummary()])
      setTrends(trendRows.slice(0, 20))
      setSummary(metricSummary)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载 Signals & Metrics 失败')
    }
  }
  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <SectionFrame eyebrow="Signals & Metrics" title="Signals & Metrics" description="这里只读本地 DB：趋势、watchlist 信号、已发布效果摘要，不在页面刷新时触发 X read。">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Observed posts" value={summary?.observed_post_count ?? 0} />
        <MetricCard label="Impressions" value={summary?.total_impressions ?? 0} />
        <MetricCard label="Engagement" value={(summary?.total_likes ?? 0) + (summary?.total_replies ?? 0) + (summary?.total_reposts ?? 0)} />
      </div>
      {summary?.diagnostic ? <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)] p-4 text-sm text-[color:var(--ops-text-muted)]">{summary.diagnostic}</div> : null}
      <div className="mt-5 space-y-3">
        {trends.map((trend) => (
          <div key={trend.id} className="rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-workspace-bg)] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-[color:var(--ops-text-title)]">{trend.topic}</div>
                <div className="mt-1 text-sm text-[color:var(--ops-text-muted)]">{trend.summary}</div>
              </div>
              <StateBadge tone={trend.source_url ? 'ready' : 'muted'}>{trend.source_url ? 'X source' : 'local seed'}</StateBadge>
            </div>
            <div className="mt-3 text-xs text-[color:var(--ops-text-caption)]">{trend.author_handle ?? '@unknown'} · score {Math.round(trend.relevance_score * 100)} · {formatDateTime(trend.collected_at)}</div>
          </div>
        ))}
      </div>
    </SectionFrame>
  )
}
