import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TaskDetail from '../src/pages/TaskDetail'

const mockApi = {
  getTasks: vi.fn(),
  getTaskLogs: vi.fn(),
  getTaskHistory: vi.fn(),
  getTaskFileChanges: vi.fn(),
  getTaskOutputFile: vi.fn(),
  updateTask: vi.fn(),
}

const mockAgentsMemory = {
  search: vi.fn(),
}

vi.mock('../src/api', () => ({
  api: {
    getTasks: (...args: unknown[]) => mockApi.getTasks(...args),
    getTaskLogs: (...args: unknown[]) => mockApi.getTaskLogs(...args),
    getTaskHistory: (...args: unknown[]) => mockApi.getTaskHistory(...args),
    getTaskFileChanges: (...args: unknown[]) => mockApi.getTaskFileChanges(...args),
    getTaskOutputFile: (...args: unknown[]) => mockApi.getTaskOutputFile(...args),
    updateTask: (...args: unknown[]) => mockApi.updateTask(...args),
  },
  agentsMemoryApi: {
    search: (...args: unknown[]) => mockAgentsMemory.search(...args),
    linkFor: () => '#',
  },
}))

const taskPage = {
  items: [
    {
      id: 18,
      description: 'Write a 3-bullet launch copy teaser for Synapse Network aimed at AI agent developers.',
      agent_id: 'content_writer',
      status: 'completed',
      requires_approval: false,
      priority: 'high',
      project_id: 'Synapse-Network-Growing',
      project_label: 'Synapse-Network-Growing',
      agent_group: 'content',
      skill_name: 'copywriting',
      context_files: null,
      retry_of_task_id: null,
      attempt_no: 1,
      last_error_message: null,
      runtime_backend: 'codex_cli',
      runtime_provider: 'codex',
      runtime_model: 'gpt-5-codex',
      runtime_session_id: 'task-1775725256108',
      runtime_selected_agent: 'editor',
      output_path: null,
      output_content: '**Synapse Network: Launch Teaser for AI Agent Developers**',
      execution_time_ms: 42852,
      tokens_used: 3210,
      budget_cost_points: 17,
      requirement_id: 12,
      requirement_title: 'Launch teaser polishing',
      workflow_step_type: 'review',
      workflow_step_title: 'Review output',
      output_files: ['output.md', 'metadata.json'],
      created_at: '2026-04-09T09:00:56.097007',
      started_at: '2026-04-09T09:00:56.102651',
      completed_at: '2026-04-09T09:01:38.985111',
    },
  ],
  total: 1,
  page: 1,
  page_size: 100,
  total_pages: 1,
  status_counts: { completed: 1 },
}

function renderTaskDetail() {
  return render(
    <MemoryRouter initialEntries={['/tasks/18']}>
      <Routes>
        <Route path="/tasks/:id" element={<TaskDetail />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('TaskDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getTasks.mockResolvedValue(taskPage)
    mockApi.getTaskLogs.mockResolvedValue([
      {
        id: 102,
        task_id: 18,
        event_type: 'assistant_output',
        detail: 'Launch teaser generated.',
        created_at: '2026-04-09T09:01:02Z',
      },
    ])
    mockApi.getTaskHistory.mockResolvedValue([
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
        runtime_backend: 'codex_cli',
        runtime_provider: 'codex',
        runtime_model: 'gpt-5-codex',
        tokens_used: 3210,
        budget_cost_points: 17,
        created_at: '2026-04-09T09:00:56.097007',
        started_at: '2026-04-09T09:00:56.102651',
        completed_at: '2026-04-09T09:01:38.985111',
      },
    ])
    mockApi.getTaskFileChanges.mockResolvedValue({
      changed_files: [
        {
          filename: 'dashboard/src/pages/Home.tsx',
          additions: 12,
          deletions: 2,
          patch: '@@ -1,1 +1,1 @@',
        },
      ],
      target_project_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
      source: 'snapshot',
      captured_at: '2026-04-09T09:01:39Z',
    })
    mockApi.getTaskOutputFile.mockResolvedValue({
      file_name: 'output.md',
      content: '# Launch teaser\\n\\nThree bullets.',
      size_bytes: 42,
      truncated: false,
      content_type: 'text/markdown',
    })
    mockApi.updateTask.mockResolvedValue(taskPage.items[0])
    mockAgentsMemory.search.mockResolvedValue({
      query: 'launch teaser',
      total: 1,
      results: [
        {
          type: 'wiki',
          id: 'launch-playbook',
          title: 'Launch Playbook',
          snippet: 'Use launch copy with short bullets.',
          score: 0.88,
        },
      ],
    })
  })

  it('loads task detail from backend endpoints and renders runtime evidence', async () => {
    renderTaskDetail()

    await waitFor(() => {
      expect(screen.getByTestId('task-detail-page')).toBeInTheDocument()
    })

    expect(mockApi.getTasks).toHaveBeenCalledWith({ page: 1, page_size: 100 })
    expect(mockApi.getTaskLogs).toHaveBeenCalledWith(18)
    expect(mockApi.getTaskHistory).toHaveBeenCalledWith(18)
    expect(mockApi.getTaskFileChanges).toHaveBeenCalledWith(18)
    expect(mockAgentsMemory.search).toHaveBeenCalled()

    expect(screen.getByText('关联需求')).toBeInTheDocument()
    expect(screen.getByTestId('runtime-backend-18')).toHaveTextContent('codex_cli')
    expect(screen.getByTestId('runtime-agent-18')).toHaveTextContent('editor')
    expect(screen.getByTestId('runtime-session-18')).toHaveTextContent('task-1775725256108')
    expect(screen.getByTestId('tokens-used-18')).toHaveTextContent('3,210')
    expect(screen.getByTestId('tokens-total-18')).toHaveTextContent('3,210')
    expect(screen.getByText('Review')).toBeInTheDocument()
    expect(screen.getByText(/工作流步骤：Review output/)).toBeInTheDocument()
    expect(screen.getByText(/这是验证阶段任务/)).toBeInTheDocument()
    expect(screen.getByText('📋 #12 Launch teaser polishing')).toBeInTheDocument()
    expect(screen.getByText(/dashboard\/src\/pages\/Home\.tsx/)).toBeInTheDocument()
    expect(screen.getByText('Agent 输出')).toBeInTheDocument()
    expect(screen.getByText('📄 output.md')).toBeInTheDocument()
    fireEvent.click(screen.getByText('📄 output.md'))
    await waitFor(() => {
      expect(mockApi.getTaskOutputFile).toHaveBeenCalledWith(18, 'output.md')
    })
    expect(screen.getByText((content) => content.includes('Three bullets.'))).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('memory-section')).toHaveTextContent('Launch Playbook')
    })
  })

  it('allows editing and saving task detail', async () => {
    renderTaskDetail()

    await waitFor(() => {
      expect(screen.getByTestId('task-detail-page')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('toggle-edit-task-btn'))
    fireEvent.change(screen.getByTestId('edit-task-priority'), { target: { value: 'normal' } })
    fireEvent.change(screen.getByTestId('edit-task-description'), { target: { value: 'Edited task detail body' } })
    fireEvent.click(screen.getByTestId('save-task-btn'))

    await waitFor(() => {
      expect(mockApi.updateTask).toHaveBeenCalledWith(18, {
        description: 'Edited task detail body',
        priority: 'normal',
      })
    })
  })
})
