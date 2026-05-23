import type { request } from './api'

export interface RecurringWorkflow {
  id: number
  workflow_key: string
  display_name: string
  description: string
  status: string
  trigger_type: string
  owner_role: string
  schedule: Record<string, unknown>
  input_query: Record<string, unknown>
  output_action: Record<string, unknown>
  escalation_rule: Record<string, unknown>
  validation_signal: Record<string, unknown>
  is_builtin: boolean
  last_run_at: string | null
  next_run_at: string | null
  is_due: boolean
  health_status: string
  last_result: Record<string, unknown>
  handler_key?: string | null
  category?: string | null
  risk_level?: string | null
  editable?: boolean
  deletable?: boolean
  created_at: string | null
  updated_at: string | null
}

export interface RecurringWorkflowRun {
  id: number
  workflow_key: string
  status: string
  triggered_by: string
  dry_run: boolean
  params: Record<string, unknown>
  result: Record<string, unknown>
  error_excerpt: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number
}

export interface RecurringWorkflowRunResult {
  workflow_key: string
  status: string
  run_started_at: string | null
  run_id: number | null
  result: Record<string, unknown>
}

export interface RecurringWorkflowHealth {
  bug_log_scheduler: Record<string, unknown>
  goal_planner_scheduler?: Record<string, unknown>
  notification_dispatcher: Record<string, unknown>
  recurring_registry: Record<string, unknown>
}

export interface ScheduleTemplate {
  template_key: string
  display_name: string
  description: string
  category: string
  risk_level: string
  handler_key: string
  schedule: Record<string, unknown>
  input_query: Record<string, unknown>
  output_action: Record<string, unknown>
  validation_signal: Record<string, unknown>
}

type RequestFn = typeof request

export function createSchedulesApi(requestFn: RequestFn) {
  return {
    getRecurringWorkflows: () => requestFn<RecurringWorkflow[]>('/recurring-workflows'),
    getRecurringWorkflowHealth: () => requestFn<RecurringWorkflowHealth>('/recurring-workflows/health'),
    getRecurringWorkflowRuns: (workflowKey: string, limit = 50) =>
      requestFn<RecurringWorkflowRun[]>(`/recurring-workflows/${workflowKey}/runs?limit=${encodeURIComponent(String(limit))}`),
    runRecurringWorkflow: (
      workflowKey: string,
      data?: {
        dry_run?: boolean
        auto_start?: boolean
        intake_min_score?: number
        intake_max_created?: number
        acceptance_limit?: number
        auto_dispatch_acceptance?: boolean
      },
    ) =>
      requestFn<RecurringWorkflowRunResult>(`/recurring-workflows/${workflowKey}/run`, {
        method: 'POST',
        body: JSON.stringify(data || {}),
      }),
    getSchedules: () => requestFn<RecurringWorkflow[]>('/schedules'),
    getScheduleTemplates: () => requestFn<ScheduleTemplate[]>('/schedules/templates'),
    getScheduleRuns: (scheduleKey: string, limit = 50) =>
      requestFn<RecurringWorkflowRun[]>(`/schedules/${scheduleKey}/runs?limit=${encodeURIComponent(String(limit))}`),
    createSchedule: (data: Record<string, unknown>) =>
      requestFn<RecurringWorkflow>('/schedules', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    updateSchedule: (scheduleKey: string, data: Record<string, unknown>) =>
      requestFn<RecurringWorkflow>(`/schedules/${scheduleKey}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    deleteSchedule: (scheduleKey: string) =>
      requestFn<{ deleted: boolean; schedule: Record<string, unknown> }>(`/schedules/${scheduleKey}`, {
        method: 'DELETE',
      }),
    runSchedule: (
      scheduleKey: string,
      data?: {
        dry_run?: boolean
        auto_start?: boolean
        intake_min_score?: number
        intake_max_created?: number
        acceptance_limit?: number
        auto_dispatch_acceptance?: boolean
      },
    ) =>
      requestFn<RecurringWorkflowRunResult>(`/schedules/${scheduleKey}/run`, {
        method: 'POST',
        body: JSON.stringify(data || {}),
      }),
  }
}
