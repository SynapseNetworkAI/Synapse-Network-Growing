import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ProjectPolicies from '../src/pages/ProjectPolicies'

const mockApi = {
  getProjectPolicies: vi.fn(),
  getProjectOnboardings: vi.fn(),
  createProjectOnboarding: vi.fn(),
  updateProjectPolicy: vi.fn(),
  deleteProjectPolicy: vi.fn(),
}

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectPolicies: (...args: unknown[]) => mockApi.getProjectPolicies(...args),
      getProjectOnboardings: (...args: unknown[]) => mockApi.getProjectOnboardings(...args),
      createProjectOnboarding: (...args: unknown[]) => mockApi.createProjectOnboarding(...args),
      updateProjectPolicy: (...args: unknown[]) => mockApi.updateProjectPolicy(...args),
      deleteProjectPolicy: (...args: unknown[]) => mockApi.deleteProjectPolicy(...args),
    },
  }
})

const POLICIES = [
  {
    id: 1,
    project_key: 'synapse-network',
    display_name: 'Synapse-Network',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network',
    status: 'active',
    allowed_write_globs: ['**'],
    forbidden_globs: ['.git/**', 'node_modules/**'],
    required_checks: ['pytest -q', 'npm test'],
    release_mode: 'manual',
    requires_manual_approval: true,
    autonomy_mode: 'execute_with_approval',
    allow_rebalance: true,
    allow_preemption: false,
    capability_matrix: {
      shell_access: true,
      git_read: true,
      git_write: true,
      git_push: false,
      network_access: false,
      publish: false,
    },
    interrupt_policy: {
      operator_confirmation_actions: ['git_push', 'publish'],
      auto_pause_on_events: ['capability_denied', 'policy_violation'],
      auto_abort_on_events: ['forbidden_write'],
    },
    scheduler_weight: 1.4,
    max_parallel_requirements: 2,
    portfolio_budget_points: 130,
    notes: 'Primary product repo.',
    created_at: '2026-04-11T10:00:00Z',
    updated_at: '2026-04-11T10:05:00Z',
  },
  {
    id: 2,
    project_key: 'sandbox-app',
    display_name: 'Sandbox App',
    root_path: '/tmp/sandbox-app',
    status: 'active',
    allowed_write_globs: ['src/**'],
    forbidden_globs: ['secrets/**'],
    required_checks: ['pytest -q'],
    release_mode: 'manual',
    requires_manual_approval: true,
    autonomy_mode: 'recommend',
    allow_rebalance: true,
    allow_preemption: false,
    capability_matrix: {
      shell_access: true,
      git_read: true,
      git_write: true,
      git_push: false,
      network_access: false,
      publish: false,
    },
    interrupt_policy: {
      operator_confirmation_actions: ['git_push', 'publish'],
      auto_pause_on_events: ['capability_denied'],
      auto_abort_on_events: ['forbidden_write'],
    },
    scheduler_weight: 1.1,
    max_parallel_requirements: 1,
    portfolio_budget_points: 120,
    notes: 'Temporary sandbox policy.',
    created_at: '2026-04-11T10:00:00Z',
    updated_at: '2026-04-11T10:05:00Z',
  },
]

const ONBOARDINGS = [
  {
    id: 7,
    project_key: 'synapse-network',
    display_name: 'Synapse-Network',
    root_path: '/Users/cliff/workspace/agent/Synapse-Network',
    docs_entrypoints: ['/Users/cliff/workspace/agent/Synapse-Network/docs/README.md'],
    validation_commands: ['pytest -q', 'npm test'],
    agents_memory_namespace: 'synapse-network',
    policy_id: 1,
    readiness_status: 'ready',
    readiness_score: 100,
    readiness_items: [
      {
        key: 'repo_exists',
        label: 'Repository Path',
        status: 'ready',
        message: 'Repository path is reachable.',
        details: ['/Users/cliff/workspace/agent/Synapse-Network'],
      },
    ],
    missing_items: [],
    notes: 'Primary product onboarding.',
    created_at: '2026-04-11T10:10:00Z',
    updated_at: '2026-04-11T10:10:00Z',
  },
]

describe('ProjectPolicies', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getProjectPolicies.mockResolvedValue(POLICIES)
    mockApi.getProjectOnboardings.mockResolvedValue(ONBOARDINGS)
    mockApi.createProjectOnboarding.mockResolvedValue(ONBOARDINGS[0])
    mockApi.updateProjectPolicy.mockResolvedValue(POLICIES[0])
    mockApi.deleteProjectPolicy.mockResolvedValue(undefined)
    })

  it('renders project policies', async () => {
    render(<MemoryRouter><ProjectPolicies /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('project-policies-page')).toBeInTheDocument()
      expect(screen.getByTestId('project-policy-card-1')).toBeInTheDocument()
    })

    expect(screen.getByDisplayValue('Synapse-Network')).toBeInTheDocument()
    expect(screen.getByDisplayValue('/Users/cliff/workspace/agent/Synapse-Network')).toBeInTheDocument()
    expect(screen.getByTestId('project-onboarding-card-7')).toBeInTheDocument()
    expect(screen.getByText('score: 100')).toBeInTheDocument()
  })

  it('updates a project policy', async () => {
    render(<MemoryRouter><ProjectPolicies /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('project-policy-save-1')).toBeInTheDocument()
    })

    const policyCard = screen.getByTestId('project-policy-card-1')

    fireEvent.change(within(policyCard).getByDisplayValue('Primary product repo.'), { target: { value: 'Updated notes' } })
    fireEvent.change(within(policyCard).getByLabelText('自治模式'), { target: { value: 'execute_autonomously' } })
    fireEvent.change(within(policyCard).getByLabelText('调度权重'), { target: { value: '1.8' } })
    fireEvent.change(within(policyCard).getByLabelText('项目并行槽位'), { target: { value: '3' } })
    fireEvent.change(within(policyCard).getByLabelText('项目预算'), { target: { value: '160' } })
    fireEvent.click(within(policyCard).getByLabelText('允许 git push'))
    fireEvent.click(within(policyCard).getByLabelText('允许 publish'))
    fireEvent.click(screen.getByTestId('project-policy-save-1'))

    await waitFor(() => {
      expect(mockApi.updateProjectPolicy).toHaveBeenCalledWith(1, expect.objectContaining({
        notes: 'Updated notes',
        release_mode: 'manual',
        status: 'active',
        autonomy_mode: 'execute_autonomously',
        capability_matrix: expect.objectContaining({
          git_push: true,
          publish: true,
        }),
        interrupt_policy: expect.objectContaining({
          operator_confirmation_actions: ['git_push', 'publish'],
        }),
        scheduler_weight: 1.8,
        max_parallel_requirements: 3,
        portfolio_budget_points: 160,
      }))
    })
  })

  it('submits a project onboarding pack and refreshes readiness results', async () => {
    render(<MemoryRouter><ProjectPolicies /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('project-onboarding-submit')).toBeInTheDocument()
    })

    const onboardingPanel = screen.getByTestId('project-onboarding-panel')

    fireEvent.change(within(onboardingPanel).getByLabelText('项目 Key'), { target: { value: 'sdk-app' } })
    fireEvent.change(within(onboardingPanel).getByLabelText('显示名称'), { target: { value: 'SDK App' } })
    fireEvent.change(within(onboardingPanel).getByLabelText('项目根路径'), { target: { value: '/Users/cliff/workspace/agent/Synapse-Network-Sdk' } })
    fireEvent.change(within(onboardingPanel).getByLabelText('Docs Entrypoints'), {
      target: { value: '/Users/cliff/workspace/agent/Synapse-Network-Sdk/README.md' },
    })
    fireEvent.change(within(onboardingPanel).getByLabelText('Validation Commands'), {
      target: { value: 'pytest -q\nnpm run build' },
    })
    fireEvent.change(within(onboardingPanel).getByLabelText('Agents-Memory Namespace'), {
      target: { value: 'synapse-network-sdk' },
    })
    fireEvent.click(screen.getByTestId('project-onboarding-submit'))

    await waitFor(() => {
      expect(mockApi.createProjectOnboarding).toHaveBeenCalledWith(expect.objectContaining({
        project_key: 'sdk-app',
        display_name: 'SDK App',
        root_path: '/Users/cliff/workspace/agent/Synapse-Network-Sdk',
        docs_entrypoints: ['/Users/cliff/workspace/agent/Synapse-Network-Sdk/README.md'],
        validation_commands: ['pytest -q', 'npm run build'],
        agents_memory_namespace: 'synapse-network-sdk',
        auto_create_policy: true,
        release_mode: 'manual',
        requires_manual_approval: true,
      }))
    })

    expect(mockApi.getProjectPolicies).toHaveBeenCalledTimes(2)
    expect(mockApi.getProjectOnboardings).toHaveBeenCalledTimes(2)
  })

  it('deletes a non-default project policy', async () => {
    render(<MemoryRouter><ProjectPolicies /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('project-policy-delete-2')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('project-policy-delete-2'))
    expect(screen.getByTestId('project-policy-delete-dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('project-policy-delete-confirm'))

    await waitFor(() => {
      expect(mockApi.deleteProjectPolicy).toHaveBeenCalledWith(2)
    })
    expect(mockApi.getProjectPolicies).toHaveBeenCalledTimes(2)
    expect(mockApi.getProjectOnboardings).toHaveBeenCalledTimes(2)
    expect(screen.getByTestId('project-policies-feedback')).toHaveTextContent('策略已删除')
  })

  it('shows inline feedback when a default managed policy cannot be deleted', async () => {
    mockApi.deleteProjectPolicy.mockRejectedValueOnce(new Error('Default managed project policies cannot be deleted. Disable them instead.'))
    render(<MemoryRouter><ProjectPolicies /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByTestId('project-policy-delete-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('project-policy-delete-1'))
    fireEvent.click(screen.getByTestId('project-policy-delete-confirm'))

    await waitFor(() => {
      expect(mockApi.deleteProjectPolicy).toHaveBeenCalledWith(1)
    })

    const feedback = screen.getByTestId('project-policies-feedback')
    expect(feedback).toHaveTextContent('暂时无法删除')
    expect(feedback).toHaveTextContent('Default managed project policies cannot be deleted. Disable them instead.')
  })
})
