// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import McpServersPanel from './McpServersPanel'

const navigateMock = vi.hoisted(() => vi.fn())
const apiMock = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  runReadiness: vi.fn(),
  syncStatuses: vi.fn(),
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
    status: 'planned',
    package_url: null,
    registry_url: null,
    workflow_run_url: null,
    failure_summary: null,
    release_notes: null,
    smoke_evidence: {},
    metadata: {},
    surfaces: [
      { id: 1, mcp_server_release_id: 7, surface_key: 'official_mcp_registry', surface_label: 'Official MCP Registry', status: 'candidate', listing_url: null, failure_reason: null, evidence: {}, updated_at: null },
      { id: 2, mcp_server_release_id: 7, surface_key: 'glama', surface_label: 'Glama', status: 'candidate', listing_url: null, failure_reason: null, evidence: {}, updated_at: null },
    ],
    published_at: null,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
    ...overrides,
  }
}

function page(items = [release()]) {
  return { items, total: items.length, page: 1, page_size: 10, total_pages: 1 }
}

describe('McpServersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.list.mockResolvedValue(page())
    apiMock.create.mockResolvedValue(release({ id: 8, package_version: '0.2.0' }))
    apiMock.runReadiness.mockResolvedValue(release({ status: 'readiness_running' }))
    apiMock.syncStatuses.mockResolvedValue({ processed_count: 0, ready_ids: [], package_published_ids: [], registry_listed_ids: [], smoke_passed_ids: [], error_ids: [] })
  })

  it('lists MCP server releases without mixing them into SDK packages', async () => {
    render(<McpServersPanel search="" />, { wrapper: MemoryRouter })

    expect(await screen.findByText('MCP Server Release Ledger')).toBeInTheDocument()
    expect(screen.getByText('SynapseNetwork MCP Server')).toBeInTheDocument()
    expect(screen.getByText('@synapse-network-ai/mcp-server')).toBeInTheDocument()
    expect(screen.getByText(/独立管理 MCP npm artifact/)).toBeInTheDocument()
    expect(apiMock.list).toHaveBeenCalledWith({ page: 1, page_size: 10, search: undefined, status: undefined })
  })

  it('can trigger readiness for planned releases', async () => {
    const user = userEvent.setup()
    render(<McpServersPanel search="" />, { wrapper: MemoryRouter })

    await screen.findByText('SynapseNetwork MCP Server')
    await user.click(screen.getByRole('button', { name: 'Run readiness' }))

    await waitFor(() => {
      expect(apiMock.runReadiness).toHaveBeenCalledWith(7, { actor: 'operator' })
      expect(apiMock.list).toHaveBeenCalledTimes(2)
    })
  })

  it('creates a new MCP release record and opens its detail page', async () => {
    const user = userEvent.setup()
    render(<McpServersPanel search="" />, { wrapper: MemoryRouter })

    await user.click(await screen.findByRole('button', { name: '新增 MCP 发布' }))
    const dialog = screen.getByRole('dialog', { name: '新增 MCP Server 发布' })
    const fields = within(dialog).getAllByRole('textbox')
    await user.clear(fields[0])
    await user.type(fields[0], '0.2.0')
    await user.type(fields[1], 'Public MCP registry launch.')
    await user.click(within(dialog).getByRole('button', { name: '创建发布记录' }))

    await waitFor(() => {
      expect(apiMock.create).toHaveBeenCalledWith({
        package_version: '0.2.0',
        release_notes: 'Public MCP registry launch.',
      })
      expect(navigateMock).toHaveBeenCalledWith('/releases/mcp-servers/8')
    })
  })
})
