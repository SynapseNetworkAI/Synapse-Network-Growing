import { useEffect, useState } from 'react'
import { api, type SocialPostMetricDailyResult, type SocialPostMetricDetail, type SocialPostMetricQueryResult, type SocialPostMetricSummary } from '../api'
import { SectionFrame, useToast } from './workbench'
import { SocialMetricsPanel } from './SocialOpsSummary'

function dateInputValue(offsetDays = 0) {
  const date = new Date()
  date.setDate(date.getDate() + offsetDays)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function SocialMetricsSection({ formatDateTime }: { formatDateTime: (value: string | null | undefined) => string }) {
  const toast = useToast()
  const [daily, setDaily] = useState<SocialPostMetricDailyResult | null>(null)
  const [metricRows, setMetricRows] = useState<SocialPostMetricQueryResult | null>(null)
  const [selectedMetric, setSelectedMetric] = useState<SocialPostMetricDetail | null>(null)
  const [summary, setSummary] = useState<SocialPostMetricSummary | null>(null)
  const [dateFrom, setDateFrom] = useState(() => dateInputValue(-29))
  const [dateTo, setDateTo] = useState(() => dateInputValue(0))
  const [page, setPage] = useState(1)

  async function loadMetrics(nextPage = page) {
    try {
      const [dailyRows, metricQueryRows, summaryRow] = await Promise.all([
        api.getSocialPostMetricsDaily({ date_from: dateFrom, date_to: dateTo, limit: 30, offset: 0 }),
        api.querySocialPostMetrics({ date_from: dateFrom, date_to: dateTo, limit: 20, offset: (nextPage - 1) * 20 }),
        api.getSocialPostMetricSummary(),
      ])
      setDaily(dailyRows)
      setMetricRows(metricQueryRows)
      setSummary(summaryRow)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载已发布效果失败')
    }
  }

  useEffect(() => {
    void loadMetrics(page)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page])

  return (
    <SectionFrame
      eyebrow="Published & Metrics"
      title="已发布效果"
      description="发布后观察 impressions、互动、链接点击和高质量回复，用于反哺下一轮内容 planner。"
    >
      <SocialMetricsPanel
        daily={daily}
        metricRows={metricRows}
        selectedMetric={selectedMetric}
        summary={summary}
        dateFrom={dateFrom}
        dateTo={dateTo}
        page={page}
        formatDateTime={formatDateTime}
        onDateFromChange={(value) => {
          setDateFrom(value)
          setPage(1)
        }}
        onDateToChange={(value) => {
          setDateTo(value)
          setPage(1)
        }}
        onSearch={() => {
          setPage(1)
          void loadMetrics(1)
        }}
        onPageChange={setPage}
        onOpenMetric={(id) => {
          api
            .getSocialPostMetric(id)
            .then(setSelectedMetric)
            .catch((error: unknown) => toast.error(error instanceof Error ? error.message : '加载发布效果详情失败'))
        }}
        onCloseMetric={() => setSelectedMetric(null)}
      />
    </SectionFrame>
  )
}
