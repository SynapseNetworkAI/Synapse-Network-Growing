import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ProjectPolicies from '../src/pages/ProjectPolicies'

const mockApi = {
  getProjectPolicies: vi.fn(),
  updateProjectPolicy: vi.fn(),
}

vi.mock('../src/api', async () => {
  const actual = await vi.importActual('../src/api')
  return {
    ...actual,
    api: {
      ...actual.api,
      getProjectPolicies: (...args: unknown[]) => mockApi.getProjectPolicies(...args),
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

describe('ProjectPolicies', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApi.getProjectPolicies.mockResolvedValue(POLICIES)
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
})
