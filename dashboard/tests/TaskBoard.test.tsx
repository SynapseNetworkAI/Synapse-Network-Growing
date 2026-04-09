import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import TaskBoard from '../src/pages/TaskBoard'

// Mock API
const mockApi = {
  getTasks: vi.fn(),
  getAgents: vi.fn(),
  getSkills: vi.fn(),
  createTask: vi.fn(),
  suggestTaskExecution: vi.fn(),
  runTask: vi.fn(),
  retryTask: vi.fn(),
  bulkRetryTasks: vi.fn(),
  getTaskLogs: vi.fn(),
  getTaskHistory: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getTasks: (...args: unknown[]) => mockApi.getTasks(...args),
    getAgents: (...args: unknown[]) => mockApi.getAgents(...args),
    getSkills: (...args: unknown[]) => mockApi.getSkills(...args),
    createTask: (...args: unknown[]) => mockApi.createTask(...args),
    suggestTaskExecution: (...args: unknown[]) => mockApi.suggestTaskExecution(...args),
    runTask: (...args: unknown[]) => mockApi.runTask(...args),
    retryTask: (...args: unknown[]) => mockApi.retryTask(...args),
    bulkRetryTasks: (...args: unknown[]) => mockApi.bulkRetryTasks(...args),
    getTaskLogs: (...args: unknown[]) => mockApi.getTaskLogs(...args),
    getTaskHistory: (...args: unknown[]) => mockApi.getTaskHistory(...args),
  },
}))

const AGENTS = [
  {
    id: 'seo_strategist',
    display_name: 'SEO Strategist',
    goal: 'Optimize',
    group: 'optimization',
    persona_path: null,
    skills: '["seo-audit","ai-seo","site-architecture"]',
    task_count: 0,
    completed_count: 0,
  },
  {
    id: 'content_writer',
    display_name: 'Content Writer',
    goal: 'Write copy',
    group: 'content',
    persona_path: null,
    skills: '["copywriting","cold-email"]',
    task_count: 0,
    completed_count: 0,
  },
]

const SKILLS = ['seo-audit', 'ai-seo', 'copywriting', 'cold-email', 'content-strategy', 'social-content']

const PENDING_TASK = {
  id: 1,
  description: 'Audit synapse.network SEO',
  agent_id: 'seo_strategist',
  status: 'pending',
  requires_approval: false,
  priority: 'normal',
  project_id: 'Synapse-Network-Growing',
  project_label: 'Synapse-Network-Growing',
  agent_group: 'optimization',
  skill_name: 'seo-audit',
  context_files: null,
  retry_of_task_id: null,
  attempt_no: 1,
  last_error_message: null,
  output_path: null,
  output_content: null,
  execution_time_ms: null,
  created_at: '2026-04-10T00:00:00Z',
  started_at: null,
  completed_at: null,
}

const RUNNING_TASK = {
  ...PENDING_TASK,
  id: 2,
  status: 'running',
  started_at: '2026-04-10T00:01:00Z',
}

const COMPLETED_TASK = {
  ...PENDING_TASK,
  id: 3,
  status: 'completed',
  skill_name: 'seo-audit',
  output_content: '# SEO Report\n\nSite looks good!',
  execution_time_ms: 12500,
  started_at: '2026-04-10T00:01:00Z',
  completed_at: '2026-04-10T00:01:12Z',
}

const FAILED_TASK = {
  ...PENDING_TASK,
  id: 4,
  status: 'failed',
  output_content: '[ERROR] OPENAI_API_KEY not set. Configure the environment variable to enable LLM execution.',
  last_error_message: 'OPENAI_API_KEY not set. Configure the environment variable to enable LLM execution.',
  completed_at: '2026-04-10T00:02:00Z',
}

const HISTORY_ITEMS = [
  {
    task_id: 1,
    retry_of_task_id: null,
    attempt_no: 1,
    status: 'failed',
    project_id: 'Synapse-Network-Growing',
    agent_group: 'optimization',
    agent_id: 'seo_strategist',
    skill_name: 'seo-audit',
    last_error_message: 'OPENAI_API_KEY not set',
    created_at: '2026-04-10T00:00:00Z',
    started_at: '2026-04-10T00:01:00Z',
    completed_at: '2026-04-10T00:02:00Z',
  },
  {
    task_id: 4,
    retry_of_task_id: 1,
    attempt_no: 2,
    status: 'failed',
    project_id: 'Synapse-Network-Growing',
    agent_group: 'optimization',
    agent_id: 'seo_strategist',
    skill_name: 'seo-audit',
    last_error_message: 'timeout',
    created_at: '2026-04-10T00:03:00Z',
    started_at: '2026-04-10T00:03:30Z',
    completed_at: '2026-04-10T00:04:00Z',
  },
]

const AUTO_SUGGESTION = {
  agent_id: 'cro_optimizer',
  skill_name: 'analytics-tracking',
  confidence: 0.88,
  reason: 'CRO Optimizer / analytics-tracking 命中任务语义: analytics, tracking, utm',
  requires_confirmation: false,
  candidates: [
    {
      agent_id: 'cro_optimizer',
      display_name: 'CRO Optimizer',
      agent_group: 'optimization',
      skill_name: 'analytics-tracking',
      confidence: 0.88,
      reason: 'CRO Optimizer / analytics-tracking 命中任务语义: analytics, tracking, utm',
    },
  ],
}

const LOW_CONFIDENCE_SUGGESTION = {
  agent_id: 'dev_rel',
  skill_name: 'content-strategy',
  confidence: 0.41,
  reason: '缺少明确语义命中，需要人工确认',
  requires_confirmation: true,
  candidates: [
    {
      agent_id: 'dev_rel',
      display_name: 'DevRel',
      agent_group: 'content',
      skill_name: 'content-strategy',
      confidence: 0.41,
      reason: '缺少明确语义命中，需要人工确认',
    },
    {
      agent_id: 'seo_strategist',
      display_name: 'SEO Strategist',
      agent_group: 'optimization',
      skill_name: 'seo-audit',
      confidence: 0.39,
      reason: '缺少明确语义命中，需要人工确认',
    },
  ],
}

describe('TaskBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getTasks.mockResolvedValue([])
    mockApi.getAgents.mockResolvedValue(AGENTS)
    mockApi.getSkills.mockResolvedValue(SKILLS)
    mockApi.suggestTaskExecution.mockResolvedValue(AUTO_SUGGESTION)
    mockApi.retryTask.mockResolvedValue({ ...RUNNING_TASK, id: 10 })
    mockApi.bulkRetryTasks.mockResolvedValue([{ ...RUNNING_TASK, id: 10 }])
    mockApi.getTaskHistory.mockResolvedValue([])
  })

  it('renders the task board page', async () => {
    render(<TaskBoard />)
    expect(screen.getByText('任务看板')).toBeDefined()
    await waitFor(() => {
      expect(mockApi.getTasks).toHaveBeenCalled()
    })
  })

  it('fetches and displays skills list', async () => {
    render(<TaskBoard />)
    await waitFor(() => {
      expect(mockApi.getSkills).toHaveBeenCalled()
    })
  })

  it('shows empty state when no tasks', async () => {
    render(<TaskBoard />)
    await waitFor(() => {
      expect(screen.getByTestId('empty-tasks')).toBeDefined()
    })
  })

  // ── Create form ──────────────────────────────────────────

  it('shows create form with skill selector', async () => {
    render(<TaskBoard />)
    fireEvent.click(screen.getByTestId('create-btn'))
    await waitFor(() => {
      expect(screen.getByTestId('skill-select')).toBeDefined()
      expect(screen.getByTestId('agent-select')).toBeDefined()
    })
  })

  it('populates skill dropdown from agent skills when agent selected', async () => {
    render(<TaskBoard />)
    fireEvent.click(screen.getByTestId('create-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('agent-select')).toBeDefined()
    })

    // Select SEO strategist
    fireEvent.change(screen.getByTestId('agent-select'), { target: { value: 'seo_strategist' } })

    // Skill dropdown should have agent-specific skills
    const skillSelect = screen.getByTestId('skill-select') as HTMLSelectElement
    const options = Array.from(skillSelect.options).map(o => o.value)
    expect(options).toContain('seo-audit')
    expect(options).toContain('ai-seo')
  })

  it('submits task with skill_name', async () => {
    mockApi.createTask.mockResolvedValue({ ...PENDING_TASK })
    render(<TaskBoard />)
    fireEvent.click(screen.getByTestId('create-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('agent-select')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('agent-select'), { target: { value: 'seo_strategist' } })
    fireEvent.change(screen.getByTestId('skill-select'), { target: { value: 'seo-audit' } })

    const textarea = screen.getByTestId('task-description') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: 'Audit synapse.network' } })

    fireEvent.click(screen.getByTestId('submit-btn'))

    await waitFor(() => {
      expect(mockApi.createTask).toHaveBeenCalledWith(
        expect.objectContaining({
          agent_id: 'seo_strategist',
          skill_name: 'seo-audit',
          description: 'Audit synapse.network',
        })
      )
    })
  })

  it('auto-selects agent and skill for a task description', async () => {
    mockApi.createTask.mockResolvedValue({ ...PENDING_TASK, agent_id: 'cro_optimizer', skill_name: 'analytics-tracking' })
    render(<TaskBoard />)
    fireEvent.click(screen.getByTestId('create-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('task-description')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('task-description'), {
      target: { value: 'Create a full analytics tracking plan with UTM coverage and event taxonomy' },
    })

    await waitFor(() => {
      expect(mockApi.suggestTaskExecution).toHaveBeenCalled()
      expect(screen.getByTestId('auto-suggestion-summary').textContent).toContain('analytics-tracking')
    })

    fireEvent.click(screen.getByTestId('submit-btn'))

    await waitFor(() => {
      expect(mockApi.createTask).toHaveBeenCalledWith(expect.objectContaining({
        agent_id: 'cro_optimizer',
        skill_name: 'analytics-tracking',
        confirm_auto_selection: true,
      }))
    })
  })

  it('requires confirmation for low-confidence auto-selection', async () => {
    mockApi.suggestTaskExecution.mockResolvedValue(LOW_CONFIDENCE_SUGGESTION)
    render(<TaskBoard />)
    fireEvent.click(screen.getByTestId('create-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('task-description')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('task-description'), {
      target: { value: 'Help me with this task soon' },
    })

    await waitFor(() => {
      expect(screen.getByTestId('suggestion-candidates')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('submit-btn'))
    expect(mockApi.createTask).not.toHaveBeenCalled()

    fireEvent.click(screen.getByTestId('suggestion-candidate-0'))
    fireEvent.click(screen.getByTestId('submit-btn'))

    await waitFor(() => {
      expect(mockApi.createTask).toHaveBeenCalledWith(expect.objectContaining({
        agent_id: 'dev_rel',
        skill_name: 'content-strategy',
      }))
    })
  })

  // ── Task card display ────────────────────────────────────

  it('displays pending task with run button', async () => {
    mockApi.getTasks.mockResolvedValue([PENDING_TASK])
    render(<TaskBoard />)
    await waitFor(() => {
      expect(screen.getByTestId('task-1')).toBeDefined()
      expect(screen.getByTestId('run-1')).toBeDefined()
    })
  })

  it('displays running task with spinner', async () => {
    mockApi.getTasks.mockResolvedValue([RUNNING_TASK])
    render(<TaskBoard />)
    await waitFor(() => {
      expect(screen.getByTestId('task-2')).toBeDefined()
      expect(screen.getByTestId('spinner-2')).toBeDefined()
    })
  })

  it('shows project section heading', async () => {
    mockApi.getTasks.mockResolvedValue([PENDING_TASK])
    render(<TaskBoard />)
    await waitFor(() => {
      expect(screen.getByTestId('project-section-Synapse-Network-Growing')).toBeDefined()
    })
  })

  it('calls runTask with skill parameter', async () => {
    mockApi.getTasks.mockResolvedValue([PENDING_TASK])
    mockApi.runTask.mockResolvedValue(RUNNING_TASK)
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('run-1')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('run-1'))

    await waitFor(() => {
      expect(mockApi.runTask).toHaveBeenCalledWith(1, 'seo-audit')
    })
  })

  it('shows failed task summary and retry actions', async () => {
    mockApi.getTasks.mockResolvedValue([FAILED_TASK])
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('error-summary-4').textContent).toContain('OPENAI_API_KEY not set')
      expect(screen.getByTestId('retry-4')).toBeDefined()
      expect(screen.getByTestId('edit-retry-4')).toBeDefined()
    })
  })

  it('calls retryTask for failed task', async () => {
    mockApi.getTasks.mockResolvedValue([FAILED_TASK])
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('retry-4')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('retry-4'))

    await waitFor(() => {
      expect(mockApi.retryTask).toHaveBeenCalledWith(4, 'run_now')
    })
  })

  it('prefills create form when editing failed retry', async () => {
    mockApi.getTasks.mockResolvedValue([FAILED_TASK])
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('edit-retry-4')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('edit-retry-4'))

    await waitFor(() => {
      expect(screen.getByTestId('create-form')).toBeDefined()
      expect((screen.getByTestId('task-description') as HTMLTextAreaElement).value).toContain('Audit synapse.network SEO')
    })
  })

  // ── Expanded task detail ─────────────────────────────────

  it('shows task detail in right drawer', async () => {
    mockApi.getTasks.mockResolvedValue([COMPLETED_TASK])
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('task-3')).toBeDefined()
    })

    fireEvent.click(screen.getByText('#3'))

    await waitFor(() => {
      expect(screen.getByTestId('task-drawer')).toBeDefined()
      const badge = screen.getByTestId('skill-badge-3')
      expect(badge).toBeDefined()
      expect(badge.textContent).toContain('seo-audit')
    })
  })

  it('shows output content in expanded view', async () => {
    mockApi.getTasks.mockResolvedValue([COMPLETED_TASK])
    mockApi.getTaskHistory.mockResolvedValue([])
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('task-3')).toBeDefined()
    })

    fireEvent.click(screen.getByText('#3'))

    await waitFor(() => {
      expect(screen.getByTestId('task-drawer').textContent).toContain('SEO Report')
      expect(screen.getByTestId('task-drawer').textContent).toContain('Site looks good')
    })
  })

  it('loads and renders retry history timeline in expanded view', async () => {
    mockApi.getTasks.mockResolvedValue([FAILED_TASK])
    mockApi.getTaskHistory.mockResolvedValue(HISTORY_ITEMS)
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('task-4')).toBeDefined()
    })

    fireEvent.click(screen.getByText('#4'))

    await waitFor(() => {
      expect(mockApi.getTaskHistory).toHaveBeenCalledWith(4)
      expect(screen.getByTestId('history-4').textContent).toContain('重试历史时间线')
      expect(screen.getByTestId('history-item-4-1').textContent).toContain('尝试 #1')
      expect(screen.getByTestId('history-item-4-4').textContent).toContain('尝试 #2')
    })
  })

  it('selects failed tasks and triggers bulk retry', async () => {
    mockApi.getTasks.mockResolvedValue([FAILED_TASK, { ...FAILED_TASK, id: 8, retry_of_task_id: 4, attempt_no: 3 }])
    render(<TaskBoard />)

    await waitFor(() => {
      expect(screen.getByTestId('select-task-4')).toBeDefined()
      expect(screen.getByTestId('select-task-8')).toBeDefined()
    })

    fireEvent.click(screen.getByTestId('select-task-4'))
    fireEvent.click(screen.getByTestId('select-task-8'))

    await waitFor(() => {
      expect(screen.getByTestId('bulk-retry-bar').textContent).toContain('2')
    })

    fireEvent.click(screen.getByTestId('bulk-retry'))

    await waitFor(() => {
      expect(mockApi.bulkRetryTasks).toHaveBeenCalledWith({ task_ids: [4, 8], mode: 'run_now' })
    })
  })

  // ── Polling ──────────────────────────────────────────────

  it('starts polling when running tasks exist', async () => {
    // Just verify that getTasks is called multiple times (poll mechanism)
    let callCount = 0
    mockApi.getTasks.mockImplementation(() => {
      callCount++
      // After 2 calls, switch to completed to stop polling
      if (callCount >= 3) return Promise.resolve([COMPLETED_TASK])
      return Promise.resolve([RUNNING_TASK])
    })

    render(<TaskBoard />)

    // Wait for initial load + at least one poll cycle
    await waitFor(() => {
      expect(callCount).toBeGreaterThanOrEqual(2)
    }, { timeout: 10000 })
  })

  it('passes group filter to getTasks', async () => {
    render(<TaskBoard />)

    fireEvent.click(screen.getByTestId('advanced-filters-toggle'))
    await waitFor(() => {
      expect(screen.getByTestId('group-filter')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('group-filter'), { target: { value: 'optimization' } })

    await waitFor(() => {
      expect(mockApi.getTasks).toHaveBeenLastCalledWith(expect.objectContaining({ agent_group: 'optimization' }))
    })
  })

  // ── Skill select on run for tasks without skill_name ────

  it('shows inline skill dropdown for tasks without skill_name', async () => {
    const taskNoSkill = { ...PENDING_TASK, skill_name: null }
    mockApi.getTasks.mockResolvedValue([taskNoSkill])
    render(<TaskBoard />)

    const el = await screen.findByTestId('run-skill-1', {}, { timeout: 3000 })
    expect(el).toBeDefined()
  })

  it('runs task without manual skill selection when auto-resolution is available', async () => {
    const taskNoSkill = { ...PENDING_TASK, skill_name: null }
    mockApi.getTasks.mockResolvedValue([taskNoSkill])
    render(<TaskBoard />)

    const runBtn = await screen.findByTestId('run-1', {}, { timeout: 3000 })
    fireEvent.click(runBtn)

    await waitFor(() => {
      expect(mockApi.runTask).toHaveBeenCalledWith(1, undefined)
    })
  })
})
