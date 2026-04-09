import { expect, test } from '@playwright/test'

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

const agents = [
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

const skills = ['copywriting', 'cold-email']

const tasks: Task[] = [
  {
    id: 18,
    description: 'Write a 3-bullet launch copy teaser for Synapse Network aimed at AI agent developers.',
    agent_id: 'content_writer',
    status: 'completed',
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
    runtime_backend: 'copilot_sdk',
    runtime_session_id: 'task-1775725256108',
    runtime_selected_agent: 'editor',
    output_path: null,
    output_content: '**Synapse Network: Launch Teaser for AI Agent Developers**\n\n- Give your agent a $5 USDC budget.',
    execution_time_ms: 42852,
    created_at: '2026-04-09T09:00:56.097007',
    started_at: '2026-04-09T09:00:56.102651',
    completed_at: '2026-04-09T09:01:38.985111',
  },
]

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

const stats = {
  agent_count: 6,
  task_total: 18,
  task_pending: 0,
  task_running: 0,
  task_completed: 17,
  task_failed: 1,
  approval_pending: 1,
}

const orgTree = {
  root: {
    id: 'cto',
    display_name: 'CTO',
    type: 'cto',
    goal: 'Drive agentic growth execution',
    icon: '🧠',
    children: [
      {
        id: 'content-domain',
        display_name: 'Content',
        type: 'domain',
        goal: 'Content operations',
        icon: '✍️',
        color: 'blue',
        children: [
          {
            id: 'content-writer',
            display_name: 'Content Writer',
            type: 'service',
            goal: 'Writes launch copy',
            skills: ['copywriting', 'cold-email'],
          },
        ],
      },
    ],
  },
}

test.beforeEach(async ({ page }) => {
  let approvals = [
    {
      id: 7,
      task_id: 18,
      status: 'pending',
      reviewer: null,
      comment: null,
      created_at: '2026-04-09T09:01:39.000000',
      decided_at: null,
      task: tasks[0],
    },
  ]

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()

    const json = async (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })

    if (method === 'GET' && path === '/api/org') return json(orgTree)
    if (method === 'GET' && path === '/api/dashboard/stats') return json(stats)
    if (method === 'GET' && path === '/api/agents') return json(agents)
    if (method === 'POST' && path === '/api/agents/sync') return json(agents)
    if (method === 'GET' && path === '/api/skills') return json(skills)
    if (method === 'GET' && path === '/api/tasks') return json(tasks)
    if (method === 'GET' && path === '/api/tasks/18/logs') return json(runtimeLogs)
    if (method === 'GET' && path === '/api/tasks/18/history') return json(taskHistory)
    if (method === 'GET' && path === '/api/approvals') {
      const status = url.searchParams.get('status')
      return json(status ? approvals.filter((item) => item.status === status) : approvals)
    }
    if (method === 'POST' && path === '/api/approvals/7/decide') {
      const body = JSON.parse(request.postData() || '{}') as { comment?: string; reviewer?: string }
      approvals = approvals.map((item) => item.id === 7
        ? {
            ...item,
            status: 'approved',
            reviewer: body.reviewer || 'cto',
            comment: body.comment || null,
            decided_at: '2026-04-09T09:02:00.000000',
          }
        : item)
      return json(approvals[0])
    }
    if (method === 'POST' && path === '/api/approvals/bulk-decide') {
      const body = JSON.parse(request.postData() || '{}') as {
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
      return json(approvals)
    }

    return json({ message: `Unhandled route: ${method} ${path}` }, 500)
  })
})

test('loads org chart dashboard shell in browser', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByTestId('orgchart-page')).toBeVisible()
  await expect(page.getByTestId('stats-bar')).toContainText('Agent 总数')
  await expect(page.getByTestId('cto-node')).toContainText('CTO')
  await expect(page.getByTestId('domain-content-domain')).toContainText('Content')
})

test('shows copilot runtime metadata in task drawer', async ({ page }) => {
  await page.goto('/tasks')

  await expect(page.getByTestId('taskboard-page')).toBeVisible()
  await expect(page.getByTestId('task-18')).toBeVisible()

  await page.getByTestId('task-18').locator('p').first().click()

  await expect(page.getByTestId('task-drawer')).toBeVisible()
  await expect(page.getByTestId('runtime-backend-18')).toContainText('copilot_sdk')
  await expect(page.getByTestId('runtime-agent-18')).toContainText('editor')
  await expect(page.getByTestId('runtime-session-18')).toContainText('task-1775725256108')
  await expect(page.getByTestId('runtime-events-18')).toContainText('runtime_started')
  await expect(page.getByTestId('runtime-events-18')).toContainText('assistant_output')
})

test('approves a pending item in approvals center', async ({ page }) => {
  await page.goto('/approvals')

  await expect(page.getByTestId('approvals-page')).toBeVisible()
  await expect(page.getByTestId('approval-7')).toBeVisible()

  await page.getByTestId('approval-comment-7').fill('looks good')
  await page.getByTestId('approve-7').click()
  await expect(page.getByText('暂无审批项')).toBeVisible()

  await page.getByTestId('approval-filter').selectOption('approved')

  const approvedCard = page.getByTestId('approval-7')
  await expect(approvedCard).toBeVisible()
  await expect(approvedCard).toContainText('approved')
  await expect(approvedCard).toContainText('looks good')
  await expect(approvedCard).toContainText('审批人: cto')
})