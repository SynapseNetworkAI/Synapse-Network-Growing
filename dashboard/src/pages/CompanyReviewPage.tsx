import {
  CompanyOpsErrorState,
  CompanyOpsLoadingState,
  CompanyReviewSection,
  StatsBar,
  useCompanyOpsData,
} from './companyOpsShared'

export default function CompanyReviewPage() {
  const {
    stats,
    review,
    loading,
    error,
    load,
    bundleResult,
    materializingBundle,
    handleMaterializeBundle,
  } = useCompanyOpsData()

  if (loading) return <CompanyOpsLoadingState />
  if (error) return <CompanyOpsErrorState onRetry={() => { load().catch(() => {}) }} />

  return (
    <div data-testid="company-review-page">
      {stats && <StatsBar stats={stats} />}
      {review && (
        <CompanyReviewSection
          review={review}
          bundleResult={bundleResult}
          materializingBundle={materializingBundle}
          onMaterializeBundle={() => { handleMaterializeBundle().catch(() => {}) }}
        />
      )}
    </div>
  )
}
