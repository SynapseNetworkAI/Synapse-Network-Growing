import type { PlanningGoal } from './api'

export interface MissionBoardItem {
  id: string
  type: string
  title: string
  status: string
  risk_level: string
  next_action: string
  deep_link: string | null
  evidence_label: string
  updated_at: string | null
}

export interface MissionBoard {
  active_goal: PlanningGoal | null
  lanes: {
    product_planner: MissionBoardItem[]
    growth_lead: MissionBoardItem[]
    software_engineer: MissionBoardItem[]
  }
  lane_summary: Record<string, { count: number }>
  unassigned: {
    count: number
    items: MissionBoardItem[]
  }
  traction_proof?: {
    status: string
    items: Array<{
      key: string
      label: string
      status: string
      evidence_label: string
      next_action: string
      deep_link: string
    }>
  }
  next_actions: Array<{
    lane: string
    title: string
    next_action: string
    deep_link: string | null
    status: string
  }>
  manifest?: {
    id: number
    version_name: string
    cycle_label: string
    updated_at: string | null
  }
}
