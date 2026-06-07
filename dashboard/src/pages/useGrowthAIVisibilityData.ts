import { useState } from 'react'
import {
  api,
  type GrowthAIVisibilityCheck,
  type GrowthAIVisibilityComparison,
  type GrowthAIVisibilityDesignHandoff,
  type GrowthAIVisibilityDocsBlueprint,
  type GrowthAIVisibilityExternalProbeGate,
  type GrowthAIVisibilityFeedCycle,
  type GrowthAIVisibilityFeedPackage,
  type GrowthAIVisibilityFeedScorecard,
  type GrowthAIVisibilityGoalAudit,
  type GrowthAIVisibilityHandoffBundle,
  type GrowthAIVisibilityLiveReadiness,
  type GrowthAIVisibilityNextCycle,
  type GrowthAIVisibilityOptimizationBrief,
  type GrowthAIVisibilityOfficialSourceList,
  type GrowthAIVisibilityOptimizationPlan,
  type GrowthAIVisibilityPresencePlan,
  type GrowthAIVisibilityProbeMatrix,
  type GrowthAIVisibilityReleaseSnapshot,
  type GrowthAIVisibilityReleaseUnblockPlan,
  type GrowthAIVisibilityWeeklyReport,
} from '../api'
import type { GrowthAIVisibilitySourceHostExecutionChecklist, GrowthAIVisibilitySourceHostFeedPackage } from '../apiGrowthAiVisibilityPlanTypes'

export function useGrowthAIVisibilityData() {
  const [items, setItems] = useState<GrowthAIVisibilityCheck[]>([])
  const [comparisons, setComparisons] = useState<GrowthAIVisibilityComparison[]>([])
  const [feedPackages, setFeedPackages] = useState<GrowthAIVisibilityFeedPackage[]>([])
  const [feedCycles, setFeedCycles] = useState<GrowthAIVisibilityFeedCycle[]>([])
  const [feedScorecard, setFeedScorecard] = useState<GrowthAIVisibilityFeedScorecard | null>(null)
  const [docsBlueprint, setDocsBlueprint] = useState<GrowthAIVisibilityDocsBlueprint | null>(null)
  const [designHandoff, setDesignHandoff] = useState<GrowthAIVisibilityDesignHandoff | null>(null)
  const [weeklyReport, setWeeklyReport] = useState<GrowthAIVisibilityWeeklyReport | null>(null)
  const [nextCycle, setNextCycle] = useState<GrowthAIVisibilityNextCycle | null>(null)
  const [goalAudit, setGoalAudit] = useState<GrowthAIVisibilityGoalAudit | null>(null)
  const [releasePlan, setReleasePlan] = useState<GrowthAIVisibilityReleaseUnblockPlan | null>(null)
  const [releaseSnapshot, setReleaseSnapshot] = useState<GrowthAIVisibilityReleaseSnapshot | null>(null)
  const [handoffBundle, setHandoffBundle] = useState<GrowthAIVisibilityHandoffBundle | null>(null)
  const [optimizationBrief, setOptimizationBrief] = useState<GrowthAIVisibilityOptimizationBrief | null>(null)
  const [liveReadiness, setLiveReadiness] = useState<GrowthAIVisibilityLiveReadiness | null>(null)
  const [externalProbeGate, setExternalProbeGate] = useState<GrowthAIVisibilityExternalProbeGate | null>(null)
  const [officialSources, setOfficialSources] = useState<GrowthAIVisibilityOfficialSourceList | null>(null)
  const [probeMatrix, setProbeMatrix] = useState<GrowthAIVisibilityProbeMatrix | null>(null)
  const [presencePlan, setPresencePlan] = useState<GrowthAIVisibilityPresencePlan | null>(null)
  const [sourceHostFeedPackage, setSourceHostFeedPackage] = useState<GrowthAIVisibilitySourceHostFeedPackage | null>(null)
  const [sourceHostExecutionChecklist, setSourceHostExecutionChecklist] = useState<GrowthAIVisibilitySourceHostExecutionChecklist | null>(null)
  const [plan, setPlan] = useState<GrowthAIVisibilityOptimizationPlan | null>(null)

  const load = async (options: { includeRuntimeEvidence: boolean; search: string }) => {
    const includeRuntimeEvidence = options.includeRuntimeEvidence
    const [
      planPayload,
      feedPackagePayload,
      feedCyclePayload,
      feedScorecardPayload,
      liveReadinessPayload,
      externalProbeGatePayload,
      docsBlueprintPayload,
      designHandoffPayload,
      weeklyReportPayload,
      nextCyclePayload,
      goalAuditPayload,
      releasePlanPayload,
      releaseSnapshotPayload,
      handoffBundlePayload,
      briefPayload,
      officialSourcesPayload,
      probeMatrixPayload,
      presencePlanPayload,
      sourceHostFeedPackagePayload,
      sourceHostExecutionChecklistPayload,
      comparisonPayload,
      checksPayload,
    ] = await Promise.all([
      api.getGrowthAIVisibilityOptimizationPlan(),
      api.getGrowthAIVisibilityFeedPackage(),
      api.getGrowthAIVisibilityFeedCycles(),
      api.getGrowthAIVisibilityFeedScorecard(),
      includeRuntimeEvidence ? api.getGrowthAIVisibilityLiveReadiness() : Promise.resolve(null),
      includeRuntimeEvidence ? api.getGrowthAIVisibilityExternalProbeGate() : Promise.resolve(null),
      api.getGrowthAIVisibilityDocsBlueprint(),
      api.getGrowthAIVisibilityDesignHandoff(),
      api.getGrowthAIVisibilityWeeklyReport(),
      api.getGrowthAIVisibilityNextCycle(),
      api.getGrowthAIVisibilityGoalAudit(),
      api.getGrowthAIVisibilityReleaseUnblockPlan(),
      includeRuntimeEvidence ? api.getGrowthAIVisibilityReleaseSnapshot() : Promise.resolve(null),
      includeRuntimeEvidence ? api.getGrowthAIVisibilityHandoffBundle() : Promise.resolve(null),
      api.getGrowthAIVisibilityOptimizationBrief(),
      api.getGrowthAIVisibilityOfficialSources(),
      api.getGrowthAIVisibilityProbeMatrix(),
      api.getGrowthAIVisibilityPresencePlan(),
      api.getGrowthAIVisibilitySourceHostFeedPackage(),
      api.getGrowthAIVisibilitySourceHostExecutionChecklist(),
      api.getGrowthAIVisibilityComparisons({ limit: 10 }),
      api.getGrowthAIVisibilityChecks({ q: options.search || undefined, limit: 100 }),
    ])
    setPlan(planPayload)
    setFeedPackages(feedPackagePayload.items)
    setFeedCycles(feedCyclePayload.items)
    setFeedScorecard(feedScorecardPayload)
    setLiveReadiness(liveReadinessPayload)
    setExternalProbeGate(externalProbeGatePayload)
    setDocsBlueprint(docsBlueprintPayload)
    setDesignHandoff(designHandoffPayload)
    setWeeklyReport(weeklyReportPayload)
    setNextCycle(nextCyclePayload)
    setGoalAudit(goalAuditPayload)
    setReleasePlan(releasePlanPayload)
    setReleaseSnapshot(releaseSnapshotPayload)
    setHandoffBundle(handoffBundlePayload)
    setOptimizationBrief(briefPayload)
    setOfficialSources(officialSourcesPayload)
    setProbeMatrix(probeMatrixPayload)
    setPresencePlan(presencePlanPayload)
    setSourceHostFeedPackage(sourceHostFeedPackagePayload)
    setSourceHostExecutionChecklist(sourceHostExecutionChecklistPayload)
    setComparisons(comparisonPayload.items)
    setItems(checksPayload.items)
  }

  return {
    plan,
    externalProbeGate,
    officialSources,
    probeMatrix,
    presencePlan,
    sourceHostFeedPackage,
    sourceHostExecutionChecklist,
    liveReadiness,
    optimizationBrief,
    handoffBundle,
    releaseSnapshot,
    releasePlan,
    nextCycle,
    goalAudit,
    weeklyReport,
    designHandoff,
    docsBlueprint,
    feedScorecard,
    feedCycles,
    feedPackages,
    comparisons,
    items,
    load,
  }
}
