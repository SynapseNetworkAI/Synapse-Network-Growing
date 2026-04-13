import {
  AutonomousCooSection,
  CompanyOpsErrorState,
  CompanyOpsLoadingState,
  StatsBar,
  TodayPrioritiesPanel,
  WeeklyCooSummaryPanel,
  useCompanyOpsData,
} from './companyOpsShared'

export default function OrgChart() {
  const { stats, review, loading, error, load } = useCompanyOpsData()

  if (loading) return <CompanyOpsLoadingState />
  if (error) return <CompanyOpsErrorState onRetry={() => { load().catch(() => {}) }} />

  return (
    <div data-testid="orgchart-page">
      {stats && <StatsBar stats={stats} />}

      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Company COO Dashboard</h2>
          <p className="mt-1 text-sm text-slate-500">首页现在只保留运营总览与入口，不再承载完整 COO 大盘。</p>
        </div>
        <div className="text-sm text-slate-500">从这里进入公司复盘、角色 KPI、自治模式和定时任务。</div>
      </div>

      <div className="mb-6 grid gap-4 xl:grid-cols-[1.15fr,0.85fr]">
        <TodayPrioritiesPanel review={review} />
        <WeeklyCooSummaryPanel review={review} />
      </div>

      {review && <AutonomousCooSection review={review} compact />}
    </div>
  )
}
