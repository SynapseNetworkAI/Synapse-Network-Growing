import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import TaskDetail from '../src/pages/TaskDetail'

const mockApi = {
  getTasks: vi.fn(),
  getTaskLogs: vi.fn(),
  getTaskHistory: vi.fn(),
  getTaskFileChanges: vi.fn(),
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
      runtime_backend: 'copilot_sdk',
      runtime_session_id: 'task-1775725256108',
      runtime_selected_agent: 'editor',
      output_path: null,
      output_content: '**Synapse Network: Launch Teaser for AI Agent Developers**',
      execution_time_ms: 42852,
      requirement_id: 12,
      requirement_title: 'Launch teaser polishing',
      output_files: [],
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
        runtime_backend: 'copilot_sdk',
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

    expect(screen.getByTestId('runtime-backend-18')).toHaveTextContent('copilot_sdk')
    expect(screen.getByTestId('runtime-agent-18')).toHaveTextContent('editor')
    expect(screen.getByTestId('runtime-session-18')).toHaveTextContent('task-1775725256108')
    expect(screen.getByText('📋 #12 Launch teaser polishing')).toBeInTheDocument()
    expect(screen.getByText(/dashboard\/src\/pages\/Home\.tsx/)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('memory-section')).toHaveTextContent('Launch Playbook')
    })
  })
})
