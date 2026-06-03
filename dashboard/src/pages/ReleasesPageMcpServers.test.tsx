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
  listCatalog: vi.fn(),
  createServer: vi.fn(),
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

function surface(overrides: Record<string, unknown> = {}) {
  return {
    id: 21,
    mcp_server_release_id: 7,
    surface_key: 'official_mcp_registry',
    surface_label: 'Official MCP Registry',
    category: 'official_registry',
    status: 'blocked_missing_artifact',
    listing_url: null,
    submission_url: 'https://github.com/modelcontextprotocol/registry',
    failure_reason: 'npm artifact is not published yet.',
    operator_note: null,
    evidence: {},
    last_checked_at: null,
    updated_at: null,
    ...overrides,
  }
}

function release() {
  return {
    id: 7,
    mcp_server_id: 3,
    server_key: 'synapse_mcp_server',
    server_name: 'SynapseNetwork MCP Server',
    package_name: '@synapse-network-ai/mcp-server',
    package_registry: 'npm',
    package_version: '0.1.0',
    registry_name: 'io.github.SynapseNetworkAI/synapse-network-mcp-server',
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
    surfaces: [
      surface(),
      surface({
        id: 22,
        surface_key: 'openai_remote_mcp',
        surface_label: 'OpenAI Remote MCP',
        category: 'llm_platform',
        status: 'blocked_requires_remote_mcp',
      }),
      surface({
        id: 23,
        surface_key: 'glama',
        surface_label: 'Glama',
        category: 'directory',
        status: 'blocked_missing_artifact',
      }),
    ],
    published_at: null,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
  }
}

function server() {
  return {
    id: 3,
    server_key: 'synapse_mcp_server',
    server_name: 'SynapseNetwork MCP Server',
    repo_full_name: 'SynapseNetworkAI/Synapse-Network-MCP-Server',
    repo_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server',
    local_repo_path: null,
    package_name: '@synapse-network-ai/mcp-server',
    package_registry: 'npm',
    registry_name: 'io.github.SynapseNetworkAI/synapse-network-mcp-server',
    transport_kind: 'stdio',
    remote_endpoint_url: null,
    install_command: 'npx -y @synapse-network-ai/mcp-server',
    tools: ['discover_services', 'invoke_and_pay'],
    security_boundary: 'stdio MCP server; no browser automation.',
    status: 'active',
    metadata: {},
    latest_release: release(),
    surface_summary: {},
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
    mcpApiMock.listCatalog.mockResolvedValue({
      items: [server()],
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

    expect(await screen.findByText('MCP Server Registry Matrix')).toBeTruthy()
    expect(screen.getByText('SynapseNetwork MCP Server')).toBeTruthy()
    expect(screen.getByText(/多 MCP 仓库统一跟踪/)).toBeTruthy()
    expect(screen.getByText('SynapseNetworkAI/Synapse-Network-MCP-Server')).toBeTruthy()
    expect(screen.getByText('@synapse-network-ai/mcp-server')).toBeTruthy()
    expect(mcpApiMock.listCatalog).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      search: undefined,
      transport_kind: undefined,
      surface_category: undefined,
    })
  })
})
