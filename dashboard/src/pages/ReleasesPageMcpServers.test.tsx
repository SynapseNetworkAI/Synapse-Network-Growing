// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReleasesPage from './ReleasesPage'

const apiMock = vi.hoisted(() => ({
  getReleaseCandidates: vi.fn(),
  getReleaseTasks: vi.fn(),
  getReleaseTasksPage: vi.fn(),
  getReleaseTaskGateStatus: vi.fn(),
  getOnlineReleaseRecords: vi.fn(),
  getProjectPolicies: vi.fn(),
  syncReleasePrStatuses: vi.fn(),
  syncReleaseTaskDeploymentStatuses: vi.fn(),
  getScheduledCloudRunJobsStatus: vi.fn(),
  getDeploymentEvents: vi.fn(),
}))
const mcpApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  syncStatuses: vi.fn(),
  create: vi.fn(),
  runReadiness: vi.fn(),
}))

vi.mock('../api', () => ({ api: apiMock }))
vi.mock('../apiReleaseTasks', () => ({
  getReleaseTasksPage: apiMock.getReleaseTasksPage,
  getReleaseTaskGateStatus: apiMock.getReleaseTaskGateStatus,
  deployReleaseTask: vi.fn(),
  attachReleaseTaskPrebuiltImage: vi.fn(),
}))
vi.mock('../apiDeployments', () => ({ getDeploymentEvents: apiMock.getDeploymentEvents }))
vi.mock('../mcpServerReleasesApi', () => ({ mcpServerReleasesApi: mcpApiMock }))

function release() {
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
    status: 'planned',
    package_url: null,
    registry_url: null,
    workflow_run_url: null,
    failure_summary: null,
    release_notes: null,
    smoke_evidence: {},
    metadata: {},
    surfaces: [],
    published_at: null,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
  }
}

describe('ReleasesPage MCP Servers tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getReleaseCandidates.mockResolvedValue([])
    apiMock.getReleaseTasks.mockResolvedValue([])
    apiMock.getReleaseTasksPage.mockResolvedValue({ items: [], total: 0, limit: 10, offset: 0 })
    apiMock.getOnlineReleaseRecords.mockResolvedValue([])
    apiMock.getProjectPolicies.mockResolvedValue([])
    apiMock.getDeploymentEvents.mockResolvedValue([])
    apiMock.getScheduledCloudRunJobsStatus.mockResolvedValue({ diagnostics: [], updated_at: null, items: [] })
    mcpApiMock.list.mockResolvedValue({
      items: [release()],
      total: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    })
  })

  it('opens the independent MCP Servers release tab from URL state', async () => {
    render(
      <MemoryRouter initialEntries={['/releases?tab=mcp-servers']}>
        <ReleasesPage />
      </MemoryRouter>,
    )

    expect(await screen.findByText('MCP Server Release Ledger')).toBeTruthy()
    expect(screen.getByText('SynapseNetwork MCP Server')).toBeTruthy()
    expect(screen.getByText(/不混入 SDK Packages/)).toBeTruthy()
    expect(mcpApiMock.list).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      search: undefined,
      status: undefined,
    })
  })
})
