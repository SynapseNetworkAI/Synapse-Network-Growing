import {
  CompanyOpsErrorState,
  CompanyOpsLoadingState,
  RecurringWorkflowsSection,
  StatsBar,
  useCompanyOpsData,
} from './companyOpsShared'

export default function RecurringWorkflowsPage() {
  const { stats, review, rituals, loading, error, load, ritualRunning, handleRunRitual } = useCompanyOpsData()

  if (loading) return <CompanyOpsLoadingState />
  if (error) return <CompanyOpsErrorState onRetry={() => { load().catch(() => {}) }} />

  return (
    <div data-testid="recurring-workflows-page">
      {stats && <StatsBar stats={stats} />}
      <RecurringWorkflowsSection
        review={review}
        rituals={rituals}
        ritualRunning={ritualRunning}
        onRunRitual={(workflowKey) => { handleRunRitual(workflowKey).catch(() => {}) }}
      />
    </div>
  )
}
