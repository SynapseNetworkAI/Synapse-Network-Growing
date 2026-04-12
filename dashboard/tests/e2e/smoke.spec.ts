import { expect, test, type Route } from '@playwright/test'

type Task = {
  id: number
  description: string
  agent_id: string
  status: string
  requires_approval: boolean
  priority: string
  project_id: string | null
  project_label: string | null
  agent_group: string | null
  skill_name: string | null
  context_files: string | null
  retry_of_task_id: number | null
  attempt_no: number
  last_error_message: string | null
  runtime_backend: string | null
  runtime_session_id: string | null
  runtime_selected_agent: string | null
  output_path: string | null
  output_content: string | null
  execution_time_ms: number | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

type Approval = {
  id: number
  task_id: number
  status: string
  reviewer: string | null
  comment: string | null
  created_at: string
  decided_at: string | null
  task: Task | null
}

type TaskLog = {
  id: number
  task_id: number
  event_type: string
  detail: string | null
  created_at: string
}

type TaskHistoryItem = {
  task_id: number
  retry_of_task_id: number | null
  attempt_no: number
  status: string
  project_id: string | null
  agent_group: string | null
  agent_id: string
  skill_name: string | null
  last_error_message: string | null
  runtime_backend: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

type Requirement = {
  id: number
  title: string
  description_markdown: string
  status: string
  priority: string
  source: string
  source_ref: string | null
  target_project_path?: string | null
  current_plan_version: number
  blocked_by_count: number
  active_workflow_run_id: number | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  routing_context?: {
    routing_mode: string
    target_project_path: string | null
    summary: string | null
    automation_ready: boolean
    readiness_status: string
    routed_project_keys: string[]
    routed_display_names: string[]
    skipped_project_keys: string[]
    project_scorecards: Array<Record<string, unknown>>
  }
  score_breakdown?: {
    total: number
  }
}

type RequirementDetail = {
  requirement: Requirement
  workflow_run: {
    id: number
    requirement_id: number
    plan_version: number
    status: string
    triggered_by: string
    planner_artifact_id: number | null
    started_at: string | null
    completed_at: string | null
    created_at: string | null
    updated_at: string | null
    steps: Array<{
      id: number
      workflow_run_id: number
      requirement_id: number
      step_key: string
      step_type: string
      title: string
      status: string
      sequence_no: number
      assigned_agent_id: string | null
      assigned_workflow_role: string | null
      branch_from_step_id: number | null
      compatibility_task_id: number | null
      retry_count: number
      handoff_summary_markdown: string | null
      done_when_markdown: string
      started_at: string | null
      completed_at: string | null
    }>
  } | null
  dependencies: Array<{
    id: number
    requirement_id: number
    depends_on_requirement_id: number
    depends_on_title: string
    depends_on_status: string
    dependency_type: string
  }>
  acceptance_checks: Array<{
    id: number
    requirement_id: number
    check_key: string
    description: string
    check_type: string
    owner_role: string
    status: string
    success_criteria_markdown: string | null
    verified_by_step_id: number | null
    evidence_artifact_id: number | null
    created_at: string | null
    updated_at: string | null
  }>
  artifacts: Array<{
    id: number
    requirement_id: number
    workflow_run_id: number | null
    step_id: number | null
    producer_step_id: number | null
    artifact_type: string
    path: string | null
    content_summary: string | null
    human_readable_body: string | null
    machine_readable_payload: string | null
    created_at: string | null
  }>
}

const TASK_LOGS_PATTERN = /^\/api\/tasks\/(\d+)\/logs$/
const TASK_HISTORY_PATTERN = /^\/api\/tasks\/(\d+)\/history$/
const TASK_RETRY_PATTERN = /^\/api\/tasks\/(\d+)\/retry$/
const REQUIREMENT_DETAIL_PATTERN = /^\/api\/requirements\/(\d+)$/

const agents = [
  {
    id: 'seo_strategist',
    display_name: 'SEO Strategist',
    goal: '负责站点审计与结构优化',
    group: 'optimization',
    persona_path: null,
    skills: '["seo-audit","analytics-tracking"]',
    task_count: 2,
    completed_count: 0,
  },
  {
    id: 'content_writer',
    display_name: 'Content Writer',
    goal: '负责极简主义文案写作',
    group: 'content',
    persona_path: null,
    skills: '["copywriting","cold-email"]',
    task_count: 2,
    completed_count: 2,
  },
]

const skills = ['seo-audit', 'analytics-tracking', 'copywriting', 'cold-email']

function makeTask(overrides: Partial<Task>): Task {
  return {
    id: 0,
    description: 'Task description',
    agent_id: 'content_writer',
    status: 'pending',
    requires_approval: false,
    priority: 'normal',
    project_id: 'Synapse-Network-Growing',
    project_label: 'Synapse-Network-Growing',
    agent_group: 'content',
    skill_name: 'copywriting',
    context_files: null,
    retry_of_task_id: null,
    attempt_no: 1,
    last_error_message: null,
    runtime_backend: null,
    runtime_session_id: null,
    runtime_selected_agent: null,
    output_path: null,
    output_content: null,
    execution_time_ms: null,
    created_at: '2026-04-09T09:00:00.000000',
    started_at: null,
    completed_at: null,
    ...overrides,
  }
}

const completedTask = makeTask({
  id: 18,
  description: 'Write a 3-bullet launch copy teaser for Synapse Network aimed at AI agent developers.',
  status: 'completed',
  runtime_backend: 'copilot_sdk',
  runtime_session_id: 'task-1775725256108',
  runtime_selected_agent: 'editor',
  output_content: '**Synapse Network: Launch Teaser for AI Agent Developers**\n\n- Give your agent a $5 USDC budget.',
  execution_time_ms: 42852,
  created_at: '2026-04-09T09:00:56.097007',
  started_at: '2026-04-09T09:00:56.102651',
  completed_at: '2026-04-09T09:01:38.985111',
})

const failedTask = makeTask({
  id: 4,
  description: 'Investigate why the onboarding landing page build fails after asset compression.',
  agent_id: 'seo_strategist',
  status: 'failed',
  priority: 'high',
  agent_group: 'optimization',
  skill_name: 'seo-audit',
  last_error_message: 'Asset pipeline checksum mismatch during static export.',
  output_content: '[ERROR] Asset pipeline checksum mismatch during static export.',
  created_at: '2026-04-09T09:02:00.000000',
  started_at: '2026-04-09T09:02:05.000000',
  completed_at: '2026-04-09T09:02:30.000000',
})

const runtimeLogs = [
  {
    id: 409,
    task_id: 18,
    event_type: 'runtime_started',
    detail: 'backend=copilot_sdk model=gpt-4.1',
    created_at: '2026-04-09T09:01:38.963350',
  },
  {
    id: 692,
    task_id: 18,
    event_type: 'assistant_output',
    detail: '**Synapse Network: Launch Teaser for AI Agent Developers**',
    created_at: '2026-04-09T09:01:38.984409',
  },
  {
    id: 693,
    task_id: 18,
    event_type: 'runtime_idle',
    detail: '',
    created_at: '2026-04-09T09:01:38.984483',
  },
]

const taskHistory = [
  {
    task_id: 18,
    retry_of_task_id: null,
    attempt_no: 1,
    status: 'completed',
    project_id: 'Synapse-Network-Growing',
    agent_group: 'content',
    agent_id: 'content_writer',
    skill_name: 'copywriting',
    last_error_message: null,
    runtime_backend: 'copilot_sdk',
    created_at: '2026-04-09T09:00:56.097007',
    started_at: '2026-04-09T09:00:56.102651',
    completed_at: '2026-04-09T09:01:38.985111',
  },
]

const companyReview = {
  id: 11,
  cycle_label: '2026-W15',
  title: 'Company Operating Review',
  summary_markdown: 'Cycle focus: release blockers.\n\nRecommended next move: SDK critical release blocker.',
  portfolio_summary: {
    active_requirements: 2,
    open_signals: 3,
    approval_required_decisions: 1,
    rebalance_opportunities: 1,
    projects_over_budget: 0,
    blocked_publish_projects: 1,
  },
  project_highlights: [
    {
      project_key: 'synapse-network-sdk',
      display_name: 'Synapse-Network-Sdk',
      readiness_status: 'ready',
      readiness_score: 100,
      active_count: 0,
      queued_count: 2,
      bug_report_count: 1,
      blocked_publish_count: 1,
      scheduler_weight: 1.1,
      autonomy_mode: 'execute_autonomously',
      budget_used: 24,
      budget_remaining: 71,
    },
  ],
  bottlenecks: [
    {
      item_key: 'blocked-publish:synapse-network-sdk',
      title: 'Synapse-Network-Sdk publish gate is blocked',
      severity: 'high',
      summary: 'One publish blocker remains open.',
      project_key: 'synapse-network-sdk',
      recommendation: 'Prioritize release blocker cleanup.',
    },
  ],
  incidents: [
    {
      item_key: 'signal:7',
      title: 'SDK critical release blocker',
      severity: 'high',
      summary: 'The SDK release is blocked by failing checks.',
      project_key: 'synapse-network-sdk',
      recommendation: 'Convert to a release bottleneck requirement.',
    },
  ],
  next_cycle_recommendations: [
    {
      candidate_type: 'signal',
      title: 'SDK critical release blocker',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      action: 'intake',
      score: 88,
      budget_cost: 26,
      source_ref: 'signal:7',
      rationale: 'Top-ranked release bottleneck across the portfolio.',
    },
  ],
  next_cycle_requirement_bundle: [
    {
      bundle_item_key: 'signal:7',
      title: 'Release Bottleneck: Synapse-Network-Sdk - SDK critical release blocker',
      candidate_type: 'signal',
      project_key: 'synapse-network-sdk',
      project_display_name: 'Synapse-Network-Sdk',
      action: 'intake',
      materialization_mode: 'create_requirement',
      priority: 'high',
      score: 88,
      budget_cost: 26,
      source_ref: 'signal:7',
      target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Sdk',
      requirement_id: null,
      template_key: 'release_bottleneck',
      rationale: 'Top-ranked release bottleneck across the portfolio.',
      description_markdown: '## Optimization Template',
      acceptance_checks: [
        { check_key: 'release_blocker_removed' },
        { check_key: 'rollback_path_documented' },
      ],
      approval_required: true,
    },
  ],
  operator_review_package: {
    title: 'Operator Review Package',
    summary_markdown: 'Cycle `2026-W15` operator package.\n\n- Bundle candidates: 1',
    checklist: [
      'Confirm the next-cycle bundle matches the current company goal and operator bandwidth.',
    ],
    decisions: [
      {
        decision_key: 'bundle-approval:signal:7',
        title: 'Approve next-cycle bundle item: Release Bottleneck: Synapse-Network-Sdk - SDK critical release blocker',
        decision_type: 'bundle_approval',
        severity: 'high',
        summary: 'Synapse-Network-Sdk / intake / score 88',
        owner_hint: 'operator',
        related_bundle_item_key: 'signal:7',
      },
    ],
    recommended_bundle_item_keys: ['signal:7'],
  },
  source_snapshot: {
    scheduler_generated_at: '2026-04-11T13:00:00Z',
  },
  created_at: '2026-04-11T13:00:00Z',
  updated_at: '2026-04-11T13:05:00Z',
}

test.beforeEach(async ({ page }) => {
  let nextTaskId = 30
  let tasks: Task[] = [completedTask, failedTask]
  let approvals: Approval[] = [
    {
      id: 7,
      task_id: 18,
      status: 'pending',
      reviewer: null,
      comment: null,
      created_at: '2026-04-09T09:01:39.000000',
      decided_at: null,
      task: completedTask,
    },
    {
      id: 8,
      task_id: 4,
      status: 'pending',
      reviewer: null,
      comment: null,
      created_at: '2026-04-09T09:01:50.000000',
      decided_at: null,
      task: makeTask({
        id: 28,
        description: 'Approve the revised launch FAQ before publishing to the public docs.',
        agent_id: 'content_writer',
        status: 'pending_approval',
        requires_approval: true,
        output_content: 'Draft FAQ ready for final approval.',
        created_at: '2026-04-09T09:01:45.000000',
      }),
    },
  ]
  let taskLogsById: Record<number, TaskLog[]> = {
    18: runtimeLogs,
    4: [
      {
        id: 700,
        task_id: 4,
        event_type: 'runtime_error',
        detail: 'Asset pipeline checksum mismatch during static export.',
        created_at: '2026-04-09T09:02:30.000000',
      },
    ],
  }
  let taskHistoryById: Record<number, TaskHistoryItem[]> = {
    18: taskHistory,
    4: [
      {
        task_id: 4,
        retry_of_task_id: null,
        attempt_no: 1,
        status: 'failed',
        project_id: 'Synapse-Network-Growing',
        agent_group: 'optimization',
        agent_id: 'seo_strategist',
        skill_name: 'seo-audit',
        last_error_message: 'Asset pipeline checksum mismatch during static export.',
        runtime_backend: null,
        created_at: '2026-04-09T09:02:00.000000',
        started_at: '2026-04-09T09:02:05.000000',
        completed_at: '2026-04-09T09:02:30.000000',
      },
    ],
  }

  let requirements: Requirement[] = [
    {
      id: 1,
      title: 'Launch FAQ quality gate',
      description_markdown: 'Validate the launch FAQ flow and continue via bugfix until checks pass.',
      status: 'in_progress',
      priority: 'high',
      source: 'manual',
      source_ref: null,
      current_plan_version: 1,
      blocked_by_count: 0,
      active_workflow_run_id: 77,
      started_at: '2026-04-09T09:10:00.000000',
      completed_at: null,
      created_at: '2026-04-09T09:09:00.000000',
      updated_at: '2026-04-09T09:11:00.000000',
    },
  ]

  let requirementDetails: Record<number, RequirementDetail> = {
    1: {
      requirement: requirements[0],
      dependencies: [],
      workflow_run: {
        id: 77,
        requirement_id: 1,
        plan_version: 1,
        status: 'running',
        triggered_by: 'user',
        planner_artifact_id: 401,
        started_at: '2026-04-09T09:10:00.000000',
        completed_at: null,
        created_at: '2026-04-09T09:09:30.000000',
        updated_at: '2026-04-09T09:11:00.000000',
        steps: [
          {
            id: 1001,
            workflow_run_id: 77,
            requirement_id: 1,
            step_key: 'implementation',
            step_type: 'implementation',
            title: 'Implement requirement: Launch FAQ quality gate',
            status: 'completed',
            sequence_no: 10,
            assigned_agent_id: 'content_writer',
            assigned_workflow_role: 'implementer',
            branch_from_step_id: null,
            compatibility_task_id: 41,
            retry_count: 0,
            handoff_summary_markdown: null,
            done_when_markdown: 'Implementation output is produced and ready for independent review.',
            started_at: '2026-04-09T09:10:00.000000',
            completed_at: '2026-04-09T09:10:20.000000',
          },
          {
            id: 1002,
            workflow_run_id: 77,
            requirement_id: 1,
            step_key: 'test',
            step_type: 'test',
            title: 'Validate requirement output: Launch FAQ quality gate',
            status: 'failed',
            sequence_no: 30,
            assigned_agent_id: 'seo_strategist',
            assigned_workflow_role: 'tester',
            branch_from_step_id: null,
            compatibility_task_id: 42,
            retry_count: 0,
            handoff_summary_markdown: null,
            done_when_markdown: 'Validation completes with a test report and all validation targets passed.',
            started_at: '2026-04-09T09:10:21.000000',
            completed_at: '2026-04-09T09:10:35.000000',
          },
          {
            id: 1003,
            workflow_run_id: 77,
            requirement_id: 1,
            step_key: 'bugfix-1002',
            step_type: 'bugfix',
            title: 'Bugfix after test failure',
            status: 'running',
            sequence_no: 50,
            assigned_agent_id: 'content_writer',
            assigned_workflow_role: 'bugfixer',
            branch_from_step_id: 1002,
            compatibility_task_id: 43,
            retry_count: 0,
            handoff_summary_markdown: null,
            done_when_markdown: 'Bugfix output resolves the recorded failure and is ready for re-review.',
            started_at: '2026-04-09T09:10:36.000000',
            completed_at: null,
          },
        ],
      },
      acceptance_checks: [
        {
          id: 1,
          requirement_id: 1,
          check_key: 'review_passed',
          description: 'Review step confirms implementation output quality.',
          check_type: 'manual_review',
          owner_role: 'reviewer',
          status: 'passed',
          success_criteria_markdown: null,
          verified_by_step_id: 1001,
          evidence_artifact_id: 501,
          created_at: '2026-04-09T09:09:30.000000',
          updated_at: '2026-04-09T09:10:20.000000',
        },
        {
          id: 2,
          requirement_id: 1,
          check_key: 'validation_passed',
          description: 'Validation passes after bugfix.',
          check_type: 'content_assertion',
          owner_role: 'tester',
          status: 'failed',
          success_criteria_markdown: null,
          verified_by_step_id: 1002,
          evidence_artifact_id: 502,
          created_at: '2026-04-09T09:09:30.000000',
          updated_at: '2026-04-09T09:10:35.000000',
        },
      ],
      artifacts: [
        {
          id: 502,
          requirement_id: 1,
          workflow_run_id: 77,
          step_id: 1002,
          producer_step_id: 1002,
          artifact_type: 'bug_report',
          path: null,
          content_summary: 'Validation failed in FAQ flow.',
          human_readable_body: 'Validation failed in FAQ flow.',
          machine_readable_payload: '{}',
          created_at: '2026-04-09T09:10:35.000000',
        },
      ],
    },
  }

  const buildStats = () => ({
    agent_count: 6,
    task_total: tasks.length,
    task_pending: tasks.filter((task) => task.status === 'pending').length,
    task_running: tasks.filter((task) => task.status === 'running').length,
    task_completed: tasks.filter((task) => task.status === 'completed').length,
    task_failed: tasks.filter((task) => task.status === 'failed').length,
    approval_pending: approvals.filter((approval) => approval.status === 'pending').length,
  })

  const json = async (route: Route, body: unknown, status = 200) => route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })

  const getFilteredTasks = (requestUrl: URL) => {
    const status = requestUrl.searchParams.get('status')
    const projectId = requestUrl.searchParams.get('project_id')
    const agentGroup = requestUrl.searchParams.get('agent_group')
    const agentId = requestUrl.searchParams.get('agent_id')
    const onlyAnomalies = requestUrl.searchParams.get('only_anomalies') === 'true'
    const page = Number(requestUrl.searchParams.get('page') || '1')
    const pageSize = Number(requestUrl.searchParams.get('page_size') || '10')
    const filtered = tasks.filter((task) => {
      if (status && task.status !== status) return false
      if (projectId && task.project_id !== projectId) return false
      if (agentGroup && task.agent_group !== agentGroup) return false
      if (agentId && task.agent_id !== agentId) return false
      if (onlyAnomalies && task.status !== 'failed' && task.status !== 'rejected' && !task.last_error_message) return false
      return true
    })
    const statusCounts = filtered.reduce<Record<string, number>>((acc, task) => {
      acc[task.status] = (acc[task.status] || 0) + 1
      return acc
    }, {})
    const start = (page - 1) * pageSize
    const items = filtered.slice(start, start + pageSize)
    return {
      items,
      total: filtered.length,
      page,
      page_size: pageSize,
      total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
      status_counts: statusCounts,
    }
  }

  const handleRequirementRoutes = async (
    route: Route,
    method: string,
    path: string,
    postData: string,
  ) => {
    if (method === 'GET' && path === '/api/requirements') {
      await json(route, requirements)
      return true
    }

    if (method === 'POST' && path === '/api/requirements') {
      const body = JSON.parse(postData || '{}') as { title?: string; description_markdown?: string; priority?: string }
      const createdRequirement: Requirement = {
        id: 99,
        title: body.title || 'Untitled requirement',
        description_markdown: body.description_markdown || '',
        status: 'ready',
        priority: body.priority || 'normal',
        source: 'manual',
        source_ref: null,
        target_project_path: null,
        current_plan_version: 0,
        blocked_by_count: 0,
        active_workflow_run_id: null,
        started_at: null,
        completed_at: null,
        created_at: '2026-04-09T09:12:00.000000',
        updated_at: '2026-04-09T09:12:00.000000',
        routing_context: {
          routing_mode: 'unrouted',
          target_project_path: null,
          summary: 'Requirement is not routed to a managed project yet.',
          automation_ready: false,
          readiness_status: 'unrouted',
          routed_project_keys: [],
          routed_display_names: [],
          skipped_project_keys: [],
          project_scorecards: [],
        },
        score_breakdown: {
          total: 40,
        },
      }
      const createdDetail: RequirementDetail = {
        requirement: createdRequirement,
        workflow_run: null,
        dependencies: [],
        acceptance_checks: [],
        artifacts: [],
      }
      requirements = [createdRequirement, ...requirements]
      requirementDetails[createdRequirement.id] = createdDetail
      await json(route, createdDetail, 201)
      return true
    }

    const requirementDetailMatch = REQUIREMENT_DETAIL_PATTERN.exec(path)
    if (method === 'GET' && requirementDetailMatch) {
      const detail = requirementDetails[Number(requirementDetailMatch[1])]
      await json(route, detail || { message: 'Not found' }, detail ? 200 : 404)
      return true
    }

    if (method === 'POST' && path === '/api/requirements/1/plan') {
      await json(route, requirementDetails[1])
      return true
    }

    if (method === 'POST' && path === '/api/requirements/1/start') {
      await json(route, requirementDetails[1])
      return true
    }

    return false
  }

  const handleTaskRoutes = async (
    route: Route,
    requestUrl: URL,
    method: string,
    path: string,
    postData: string,
  ) => {
    if (method === 'POST' && path === '/api/tasks/suggest-execution') {
      await json(route, {
        agent_id: 'content_writer',
        skill_name: 'copywriting',
        confidence: 0.92,
        reason: 'Matched copywriting keywords in the task description.',
        requires_confirmation: false,
        candidates: [],
      })
      return true
    }

    if (method === 'GET' && path === '/api/tasks') {
      await json(route, getFilteredTasks(requestUrl))
      return true
    }

    if (method === 'POST' && path === '/api/tasks') {
      const body = JSON.parse(postData || '{}') as {
        description?: string
        agent_id?: string
        requires_approval?: boolean
        priority?: string
        skill_name?: string | null
      }
      const selectedAgent = agents.find((agent) => agent.id === body.agent_id) || agents[0]
      const createdTask = makeTask({
        id: nextTaskId++,
        description: body.description || 'Untitled task',
        agent_id: selectedAgent.id,
        requires_approval: Boolean(body.requires_approval),
        priority: body.priority || 'normal',
        skill_name: body.skill_name || null,
        agent_group: selectedAgent.group,
        created_at: '2026-04-09T09:05:00.000000',
      })
      tasks = [createdTask, ...tasks]
      taskLogsById[createdTask.id] = []
      taskHistoryById[createdTask.id] = []
      await json(route, createdTask, 201)
      return true
    }

    const taskLogsMatch = TASK_LOGS_PATTERN.exec(path)
    if (method === 'GET' && taskLogsMatch) {
      await json(route, taskLogsById[Number(taskLogsMatch[1])] || [])
      return true
    }

    const taskHistoryMatch = TASK_HISTORY_PATTERN.exec(path)
    if (method === 'GET' && taskHistoryMatch) {
      await json(route, taskHistoryById[Number(taskHistoryMatch[1])] || [])
      return true
    }

    const retryMatch = TASK_RETRY_PATTERN.exec(path)
    if (method === 'POST' && retryMatch) {
      const sourceTaskId = Number(retryMatch[1])
      const sourceTask = tasks.find((task) => task.id === sourceTaskId)
      if (!sourceTask) {
        await json(route, { message: 'Task not found' }, 404)
        return true
      }

      const retriedTask = makeTask({
        ...sourceTask,
        id: nextTaskId++,
        status: 'running',
        retry_of_task_id: sourceTask.id,
        attempt_no: sourceTask.attempt_no + 1,
        last_error_message: null,
        output_content: null,
        created_at: '2026-04-09T09:06:00.000000',
        started_at: '2026-04-09T09:06:05.000000',
        completed_at: null,
      })
      tasks = [retriedTask, ...tasks]
      taskLogsById[retriedTask.id] = [
        {
          id: 900,
          task_id: retriedTask.id,
          event_type: 'runtime_started',
          detail: 'Retry task restarted in browser smoke fixture.',
          created_at: '2026-04-09T09:06:05.000000',
        },
      ]
      taskHistoryById[sourceTask.id] = [
        ...(taskHistoryById[sourceTask.id] || []),
        {
          task_id: retriedTask.id,
          retry_of_task_id: sourceTask.id,
          attempt_no: retriedTask.attempt_no,
          status: retriedTask.status,
          project_id: retriedTask.project_id,
          agent_group: retriedTask.agent_group,
          agent_id: retriedTask.agent_id,
          skill_name: retriedTask.skill_name,
          last_error_message: retriedTask.last_error_message,
          runtime_backend: retriedTask.runtime_backend,
          created_at: retriedTask.created_at,
          started_at: retriedTask.started_at,
          completed_at: retriedTask.completed_at,
        },
      ]
      taskHistoryById[retriedTask.id] = taskHistoryById[sourceTask.id]
      await json(route, retriedTask)
      return true
    }

    return false
  }

  const handleApprovalRoutes = async (
    route: Route,
    requestUrl: URL,
    method: string,
    path: string,
    postData: string,
  ) => {
    if (method === 'GET' && path === '/api/approvals') {
      const status = requestUrl.searchParams.get('status')
      await json(route, status ? approvals.filter((item) => item.status === status) : approvals)
      return true
    }

    if (method === 'POST' && path === '/api/approvals/7/decide') {
      const body = JSON.parse(postData || '{}') as { comment?: string; reviewer?: string }
      approvals = approvals.map((item) => item.id === 7
        ? {
            ...item,
            status: 'approved',
            reviewer: body.reviewer || 'cto',
            comment: body.comment || null,
            decided_at: '2026-04-09T09:02:00.000000',
          }
        : item)
      await json(route, approvals.find((item) => item.id === 7) || null)
      return true
    }

    if (method === 'POST' && path === '/api/approvals/bulk-decide') {
      const body = JSON.parse(postData || '{}') as {
        approval_ids?: number[]
        comment?: string
        reviewer?: string
        action?: 'approve' | 'reject'
      }
      approvals = approvals.map((item) => body.approval_ids?.includes(item.id)
        ? {
            ...item,
            status: body.action === 'reject' ? 'rejected' : 'approved',
            reviewer: body.reviewer || 'cto',
            comment: body.comment || null,
            decided_at: '2026-04-09T09:02:00.000000',
          }
        : item)
      await json(route, approvals)
      return true
    }

    return false
  }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const postData = request.postData() || ''

    if (method === 'GET' && path === '/api/dashboard/stats') return json(route, buildStats())
    if (method === 'GET' && path === '/api/company-review') return json(route, companyReview)
    if (method === 'GET' && path === '/api/agents') return json(route, agents)
    if (method === 'GET' && path === '/api/skills') return json(route, skills)
    if (await handleRequirementRoutes(route, method, path, postData)) return
    if (await handleTaskRoutes(route, url, method, path, postData)) return
    if (await handleApprovalRoutes(route, url, method, path, postData)) return

    return json(route, { message: `Unhandled route: ${method} ${path}` }, 500)
  })
})

test('loads org chart dashboard shell in browser', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByTestId('orgchart-page')).toBeVisible()
  await expect(page.getByTestId('stats-bar')).toContainText('Agent 总数')
  await expect(page.getByText('Company COO Dashboard')).toBeVisible()
  await expect(page.getByTestId('operator-rituals-panel')).toContainText('Daily / Weekly Ritual Board')
})

test('shows copilot runtime metadata in task drawer', async ({ page }) => {
  await page.goto('/tasks')

  await expect(page.getByTestId('taskboard-page')).toBeVisible()
  await expect(page.getByTestId('task-18')).toBeVisible()

  await page.getByTestId('task-18').click()

  await expect(page.getByTestId('task-detail-page')).toBeVisible()
  await expect(page.getByTestId('runtime-backend-18')).toContainText('copilot_sdk')
  await expect(page.getByTestId('runtime-agent-18')).toContainText('editor')
  await expect(page.getByTestId('runtime-session-18')).toContainText('task-1775725256108')
  await expect(page.getByTestId('execution-time-18')).toContainText('42.9s')
  await expect(page.getByTestId('runtime-events-18')).toContainText('Synapse Network: Launch Teaser for AI Agent Developers')
  await expect(page.getByTestId('runtime-events-18')).not.toContainText('runtime_started')
  await expect(page.getByTestId('runtime-events-18')).not.toContainText('assistant_output')
})

test('approves a pending item in approvals center', async ({ page }) => {
  await page.goto('/approvals')

  await expect(page.getByTestId('approvals-page')).toBeVisible()
  await expect(page.getByTestId('approval-7')).toBeVisible()

  await page.getByTestId('approval-comment-7').fill('looks good')
  await page.getByTestId('approve-7').click()
  await expect(page.locator('[data-testid="approval-7"]')).toHaveCount(0)
  await expect(page.getByTestId('approval-8')).toBeVisible()

  await page.getByTestId('approval-filter').selectOption('approved')

  const approvedCard = page.getByTestId('approval-7')
  await expect(approvedCard).toBeVisible()
  await expect(approvedCard).toContainText('approved')
  await expect(approvedCard).toContainText('looks good')
  await expect(approvedCard).toContainText('审批人: cto')
})

test('creates a task from the task board form', async ({ page }) => {
  await page.goto('/tasks')

  await page.getByTestId('create-btn').click()
  await expect(page.getByTestId('create-form')).toBeVisible()

  await page.getByTestId('agent-select').selectOption('content_writer')
  await page.getByTestId('skill-select').selectOption('copywriting')
  await page.getByTestId('priority-select').selectOption('high')
  await page.getByTestId('approval-checkbox').check()
  await page.getByTestId('task-description').fill('Draft a launch FAQ that explains how AI agent teams can start with Synapse in under 5 minutes.')
  await page.getByTestId('submit-btn').click()

  const createdTask = page.getByTestId('task-30')
  await expect(createdTask).toBeVisible()
  await expect(createdTask).toContainText('Draft a launch FAQ that explains how AI agent teams can start with Synapse in under 5 minutes.')
  await expect(createdTask).toContainText('@content_writer')
  await expect(createdTask).toContainText('⚡ 高')
  await expect(page.locator('[data-testid="create-form"]')).toHaveCount(0)
})

test('renders requirement pool with bugfix branch and captures screenshot', async ({ page }) => {
  await page.goto('/requirements')

  await expect(page.getByTestId('requirements-page')).toBeVisible()
  await expect(page.getByTestId('requirement-card-1')).toContainText('Launch FAQ quality gate')
  await page.getByTestId('requirement-card-1').locator('button').first().click()
  await expect(page.getByTestId('workflow-steps-panel')).toBeVisible()
  await expect(page.getByTestId('workflow-step-1003')).toContainText('Bugfix after test failure')

  await page.screenshot({ path: 'test-results/requirements-pool.png', fullPage: true })
})

test('retries a failed task and shows the new running attempt', async ({ page }) => {
  await page.goto('/tasks')

  await expect(page.getByTestId('task-4')).toBeVisible()
  await expect(page.getByTestId('retry-4')).toBeVisible()

  await page.getByTestId('retry-4').click()

  const retriedTask = page.getByTestId('task-30')
  await expect(retriedTask).toBeVisible()
  await expect(retriedTask).toContainText('执行中')
  await expect(retriedTask).toContainText('第 2 次')
  await expect(retriedTask).toContainText('@seo_strategist')
  await expect(page.getByTestId('task-summary-bar')).toContainText('执行中')
})

test('bulk approves multiple pending items', async ({ page }) => {
  await page.goto('/approvals')

  await expect(page.getByTestId('approval-7')).toBeVisible()
  await expect(page.getByTestId('approval-8')).toBeVisible()

  await page.getByTestId('select-approval-7').check()
  await page.getByTestId('select-approval-8').check()

  await expect(page.getByTestId('bulk-approval-bar')).toContainText('已选择 2 个待审批项')
  await page.getByTestId('bulk-approval-comment').fill('batch approved in smoke test')
  await page.getByTestId('bulk-approve').click()

  await expect(page.getByText('暂无审批项')).toBeVisible()
  await page.getByTestId('approval-filter').selectOption('approved')

  const firstApprovedCard = page.getByTestId('approval-7')
  const secondApprovedCard = page.getByTestId('approval-8')
  await expect(firstApprovedCard).toBeVisible()
  await expect(secondApprovedCard).toBeVisible()
  await expect(firstApprovedCard).toContainText('approved')
  await expect(secondApprovedCard).toContainText('approved')
  await expect(firstApprovedCard).toContainText('batch approved in smoke test')
  await expect(secondApprovedCard).toContainText('审批人: cto')
})
