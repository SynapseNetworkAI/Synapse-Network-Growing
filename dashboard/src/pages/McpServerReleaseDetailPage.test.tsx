// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import McpServerReleaseDetailPage from './McpServerReleaseDetailPage'

const navigateMock = vi.hoisted(() => vi.fn())
const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  events: vi.fn(),
  publishNpm: vi.fn(),
  submitRegistry: vi.fn(),
  runProdSmoke: vi.fn(),
  complete: vi.fn(),
  runReadiness: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../mcpServerReleasesApi', () => ({
  mcpServerReleasesApi: apiMock,
}))

function release(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    server_key: 'synapse_mcp_server',
    server_name: 'SynapseNetwork MCP Server',
    package_name: '@synapse-network-ai/mcp-server',
    package_registry: 'npm',
    package_version: '0.1.0',
    registry_name: 'io.github.synapsenetworkai/synapse-network-mcp-server',
    git_tag: 'mcp-server/v0.1.0',
    install_command: 'npx -y @synapse-network-ai/mcp-server',
    status: 'ready_to_publish',
    package_url: null,
    registry_url: null,
    workflow_run_url: null,
    failure_summary: null,
    release_notes: 'First public stdio package.',
    smoke_evidence: {},
    metadata: {},
    surfaces: [
      { id: 1, mcp_server_release_id: 7, surface_key: 'official_mcp_registry', surface_label: 'Official MCP Registry', status: 'candidate', listing_url: null, failure_reason: null, evidence: {}, updated_at: null },
      { id: 2, mcp_server_release_id: 7, surface_key: 'glama', surface_label: 'Glama', status: 'listed', listing_url: 'https://glama.ai/mcp/servers/synapse', failure_reason: null, evidence: {}, updated_at: null },
    ],
    published_at: null,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
    ...overrides,
  }
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/releases/mcp-servers/7']}>
      <Routes>
        <Route path="/releases/mcp-servers/:id" element={<McpServerReleaseDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('McpServerReleaseDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.get.mockResolvedValue(release())
    apiMock.events.mockResolvedValue([
      {
        id: 11,
        mcp_server_release_id: 7,
        action: 'readiness_passed',
        from_status: 'readiness_running',
        to_status: 'ready_to_publish',
        actor: 'runner',
        note: null,
        workflow_run_url: null,
        error_summary: null,
        metadata: {},
        created_at: '2026-05-31T00:02:00Z',
      },
    ])
    apiMock.publishNpm.mockResolvedValue(release({ status: 'npm_publishing' }))
    apiMock.submitRegistry.mockResolvedValue(release({ status: 'registry_submitting' }))
    apiMock.runProdSmoke.mockResolvedValue(release({ status: 'prod_smoke_running' }))
    apiMock.complete.mockResolvedValue(release({ status: 'completed' }))
    apiMock.runReadiness.mockResolvedValue(release({ status: 'readiness_running' }))
  })

  it('shows package, registry, smoke evidence, directory distribution, and events', async () => {
    renderDetail()

    expect(await screen.findByText('SynapseNetwork MCP Server')).toBeInTheDocument()
    expect(screen.getAllByText('Package').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Registry').length).toBeGreaterThan(0)
    expect(screen.getByText('Smoke Evidence')).toBeInTheDocument()
    expect(screen.getByText('Directory Distribution')).toBeInTheDocument()
    expect(screen.getByText('Events')).toBeInTheDocument()
    expect(screen.getByText('npx -y @synapse-network-ai/mcp-server')).toBeInTheDocument()
    expect(screen.getByText('io.github.synapsenetworkai/synapse-network-mcp-server')).toBeInTheDocument()
    expect(screen.getByText('readiness_passed')).toBeInTheDocument()
  })

  it('requires the exact Human Gate phrase before npm publish can be triggered', async () => {
    const user = userEvent.setup()
    renderDetail()

    await user.click(await screen.findByRole('button', { name: 'Publish npm' }))
    const dialog = screen.getByRole('dialog', { name: 'Publish MCP npm package' })
    const publishButton = within(dialog).getByRole('button', { name: '触发 npm publish' })
    expect(publishButton).toBeDisabled()

    await user.type(within(dialog).getByRole('textbox'), 'PUBLISH_MCP_0.1.0')
    expect(publishButton).not.toBeDisabled()
    await user.click(publishButton)

    await waitFor(() => {
      expect(apiMock.publishNpm).toHaveBeenCalledWith(7, {
        actor: 'operator',
        confirm_phrase: 'PUBLISH_MCP_0.1.0',
      })
      expect(apiMock.get).toHaveBeenCalledTimes(2)
    })
  })

  it('shows the next valid runner action for each status', async () => {
    apiMock.get.mockResolvedValueOnce(release({ status: 'npm_published', package_url: 'https://www.npmjs.com/package/@synapse-network-ai/mcp-server/v/0.1.0' }))
    const user = userEvent.setup()
    renderDetail()

    await user.click(await screen.findByRole('button', { name: 'Submit Registry' }))
    await waitFor(() => {
      expect(apiMock.submitRegistry).toHaveBeenCalledWith(7, { actor: 'operator' })
    })
  })
})
