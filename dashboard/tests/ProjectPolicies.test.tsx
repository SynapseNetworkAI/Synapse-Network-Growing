import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ProjectPolicies from '../src/pages/ProjectPolicies'

const mockApi = {
  getProjectPolicies: vi.fn(),
  getProjectOnboardings: vi.fn(),
  createProjectOnboarding: vi.fn(),
  updateProjectPolicy: vi.fn(),
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
    notes: 'Primary product repo.',
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

    fireEvent.change(screen.getByDisplayValue('Primary product repo.'), { target: { value: 'Updated notes' } })
    fireEvent.click(screen.getByTestId('project-policy-save-1'))

    await waitFor(() => {
      expect(mockApi.updateProjectPolicy).toHaveBeenCalledWith(1, expect.objectContaining({
        notes: 'Updated notes',
        release_mode: 'manual',
        status: 'active',
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
})
