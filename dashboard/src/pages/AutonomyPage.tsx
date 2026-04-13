import {
  AutonomousCooSection,
  CompanyOpsErrorState,
  CompanyOpsLoadingState,
  StatsBar,
  useCompanyOpsData,
} from './companyOpsShared'

export default function AutonomyPage() {
  const { stats, review, loading, error, load } = useCompanyOpsData()

  if (loading) return <CompanyOpsLoadingState />
  if (error) return <CompanyOpsErrorState onRetry={() => { load().catch(() => {}) }} />

  return (
    <div data-testid="autonomy-page">
      {stats && <StatsBar stats={stats} />}
      {review && <AutonomousCooSection review={review} />}
    </div>
  )
}
