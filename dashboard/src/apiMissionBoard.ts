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
  active_goals?: PlanningGoal[]
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

export type MissionWorkbenchStage =
  | 'opportunity'
  | 'candidate'
  | 'requirement'
  | 'workflow'
  | 'pr'
  | 'release'
  | 'online_record'

export interface MissionWorkbenchNode {
  id: string
  parent_id: string | null
  level: number
  type: string
  title: string
  status: string
  lane: string | null
  goal_key: string | null
  stage_statuses: Record<MissionWorkbenchStage, string>
  process_key?: string | null
  process_stages?: Array<{ key: string; label: string; status: string }>
  next_action: string
  deep_link: string | null
  detail_api: string | null
  updated_at: string | null
  evidence_label: string
  external_post_id?: string | null
  external_url?: string | null
  published_at?: string | null
  children: MissionWorkbenchNode[]
}

export interface MissionWorkbench {
  root: MissionWorkbenchNode | null
  unassigned: {
    count: number
    items: MissionBoardItem[]
  }
  summary: {
    active_goal_count: number
    work_item_count: number
  }
  manifest?: {
    id: number
    version_name?: string
    cycle_label?: string
    updated_at: string | null
  }
}

export type PlanningTaskBoardColumnKey =
  | 'backlog'
  | 'todo'
  | 'in_progress'
  | 'human_review'
  | 'rework'
  | 'delivery'
  | 'done'
  | 'canceled'

export interface PlanningTaskBoardCard {
  id: string
  object_id: number
  card_kind: 'requirement' | 'intake'
  intake_type?: 'product_opportunity' | 'requirement_candidate' | string
  task_key: string
  title: string
  status: string
  column_key: PlanningTaskBoardColumnKey
  goal_key: string
  project_key: string
  lane: string
  priority: string
  risk_level: string
  updated_at: string | null
  next_action: string
  deep_link: string | null
  detail_api: string | null
  latest_workflow_run_id: number | null
  delivery_label: string
  description: string
}

export interface PlanningTaskBoardColumn {
  key: PlanningTaskBoardColumnKey
  title: string
  description: string
  hidden: boolean
  count: number
  cards: PlanningTaskBoardCard[]
}

export interface PlanningTaskBoard {
  columns: PlanningTaskBoardColumn[]
  summary: {
    total: number
    visible_total: number
    include_done_days: number
  }
  generated_at: string | null
}
