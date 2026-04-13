import {
  CompanyOpsErrorState,
  CompanyOpsLoadingState,
  RoleKpisSection,
  StatsBar,
  useCompanyOpsData,
} from './companyOpsShared'

export default function RoleKpisPage() {
  const { stats, roleKpis, loading, error, load } = useCompanyOpsData()

  if (loading) return <CompanyOpsLoadingState />
  if (error) return <CompanyOpsErrorState onRetry={() => { load().catch(() => {}) }} />

  return (
    <div data-testid="role-kpis-page">
      {stats && <StatsBar stats={stats} />}
      {roleKpis && <RoleKpisSection roleKpis={roleKpis} />}
    </div>
  )
}
