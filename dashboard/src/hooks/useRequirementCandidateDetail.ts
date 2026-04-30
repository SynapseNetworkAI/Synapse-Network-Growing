import { useEffect, useState } from 'react'
import { Location, NavigateFunction } from 'react-router-dom'
import { api, RequirementCandidate } from '../api'

const selectedCandidateId = (search: string) => Number(new URLSearchParams(search).get('candidate') || 0) || null

export function useRequirementCandidateDetail(location: Location, navigate: NavigateFunction) {
  const [candidateDetail, setCandidateDetail] = useState<RequirementCandidate | null>(null)
  const [candidateDetailLoading, setCandidateDetailLoading] = useState(false)
  const [candidateDetailError, setCandidateDetailError] = useState<string | null>(null)

  useEffect(() => {
    const candidateId = selectedCandidateId(location.search)
    if (!candidateId) {
      setCandidateDetail(null)
      setCandidateDetailError(null)
      setCandidateDetailLoading(false)
      return undefined
    }
    let cancelled = false
    setCandidateDetailLoading(true)
    setCandidateDetailError(null)
    api.getRequirementCandidate(candidateId)
      .then((candidate) => { if (!cancelled) setCandidateDetail(candidate) })
      .catch((err) => {
        if (!cancelled) {
          setCandidateDetail(null)
          setCandidateDetailError(err instanceof Error ? err.message : '加载 Candidate 详情失败')
        }
      })
      .finally(() => { if (!cancelled) setCandidateDetailLoading(false) })
    return () => { cancelled = true }
  }, [location.search])

  function closeCandidateDetail() {
    const params = new URLSearchParams(location.search)
    params.delete('candidate')
    const nextSearch = params.toString()
    navigate(`${location.pathname}${nextSearch ? `?${nextSearch}` : ''}`, { replace: true })
    setCandidateDetail(null)
    setCandidateDetailError(null)
    setCandidateDetailLoading(false)
  }

  function showCandidateDetail(candidate: RequirementCandidate) {
    setCandidateDetail(candidate)
    const params = new URLSearchParams(location.search)
    params.set('tab', 'engineering')
    params.set('candidate', String(candidate.id))
    navigate(`/planning?${params.toString()}`, { replace: true })
  }

  async function refreshCandidateDetail(candidateId: number) {
    setCandidateDetail(await api.getRequirementCandidate(candidateId))
  }

  return {
    candidateDetail,
    candidateDetailLoading,
    candidateDetailError,
    closeCandidateDetail,
    refreshCandidateDetail,
    showCandidateDetail,
  }
}
