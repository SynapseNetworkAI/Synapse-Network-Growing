// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import McpServersPanel from './McpServersPanel'

const navigateMock = vi.hoisted(() => vi.fn())
const apiMock = vi.hoisted(() => ({
  listCatalog: vi.fn(),
  createServer: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../mcpServerReleasesApi', () => ({
  mcpServerReleasesApi: apiMock,
}))

function surface(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    mcp_server_release_id: 7,
    surface_key: 'official_mcp_registry',
    surface_label: 'Official MCP Registry',
    category: 'official_registry',
    status: 'blocked_missing_artifact',
    listing_url: null,
    submission_url: 'https://github.com/modelcontextprotocol/registry',
    failure_reason: 'npm artifact missing.',
    operator_note: null,
    evidence: {},
    last_checked_at: null,
    updated_at: null,
    ...overrides,
  }
}

function release(overrides: Record<string, unknown> = {}) {
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
      surface({ id: 2, surface_key: 'glama', surface_label: 'Glama', category: 'directory' }),
      surface({ id: 3, surface_key: 'openai_remote_mcp', surface_label: 'OpenAI Remote MCP', category: 'llm_platform', status: 'blocked_requires_remote_mcp' }),
    ],
    published_at: null,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
    ...overrides,
  }
}

function server(overrides: Record<string, unknown> = {}) {
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
    ...overrides,
  }
}

function page(items = [server()]) {
  return { items, total: items.length, page: 1, page_size: 10, total_pages: 1 }
}

describe('McpServersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.listCatalog.mockResolvedValue(page())
    apiMock.createServer.mockResolvedValue(server({ id: 9, server_key: 'new-mcp-server' }))
  })

  it('lists a multi-server MCP registry matrix without mixing it into SDK packages', async () => {
    render(<McpServersPanel search="" />, { wrapper: MemoryRouter })

    expect(await screen.findByText('MCP Server Registry Matrix')).toBeInTheDocument()
    expect(screen.getByText('SynapseNetwork MCP Server')).toBeInTheDocument()
    expect(screen.getByText('SynapseNetworkAI/Synapse-Network-MCP-Server')).toBeInTheDocument()
    expect(screen.getByText('@synapse-network-ai/mcp-server')).toBeInTheDocument()
    expect(screen.getByText(/OpenAI \/ Claude remote MCP readiness/)).toBeInTheDocument()
    expect(apiMock.listCatalog).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      search: undefined,
      transport_kind: undefined,
      surface_category: undefined,
    })
  })

  it('filters by transport and surface category', async () => {
    const user = userEvent.setup()
    render(<McpServersPanel search="remote" />, { wrapper: MemoryRouter })

    await screen.findByText('SynapseNetwork MCP Server')
    const filters = screen.getAllByRole('combobox')
    await user.selectOptions(filters[0], 'remote_http')
    await user.selectOptions(filters[1], 'llm_platform')

    await waitFor(() => {
      expect(apiMock.listCatalog).toHaveBeenLastCalledWith({
        page: 1,
        page_size: 10,
        search: 'remote',
        transport_kind: 'remote_http',
        surface_category: 'llm_platform',
      })
    })
  })

  it('adds a new MCP server catalog row and opens its detail page', async () => {
    const user = userEvent.setup()
    render(<McpServersPanel search="" />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '新增 MCP Server' }))
    const dialog = screen.getByRole('dialog', { name: '新增 MCP Server' })
    const fields = within(dialog).getAllByRole('textbox')
    await user.clear(fields[0])
    await user.type(fields[0], 'new-mcp-server')
    await user.clear(fields[1])
    await user.type(fields[1], 'New MCP Server')
    await user.click(within(dialog).getByRole('button', { name: '加入矩阵' }))

    await waitFor(() => {
      expect(apiMock.createServer).toHaveBeenCalledWith(expect.objectContaining({
        server_key: 'new-mcp-server',
        server_name: 'New MCP Server',
        tools: ['discover_services', 'invoke_and_pay', 'get_receipt'],
      }))
      expect(navigateMock).toHaveBeenCalledWith('/releases/mcp-servers/9')
    })
  })
})
