// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import McpServerReleaseDetailPage from './McpServerReleaseDetailPage'

const navigateMock = vi.hoisted(() => vi.fn())
const apiMock = vi.hoisted(() => ({
  getServer: vi.fn(),
  events: vi.fn(),
  publishNpm: vi.fn(),
  submitRegistry: vi.fn(),
  runProdSmoke: vi.fn(),
  complete: vi.fn(),
  runReadiness: vi.fn(),
  createReleaseForServer: vi.fn(),
  getSubmissionReadiness: vi.fn(),
  verifySurfaceConfig: vi.fn(),
  patchSurfaceConfig: vi.fn(),
  liveCheckSurface: vi.fn(),
  submitSurface: vi.fn(),
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
    mcp_server_id: 3,
    server_key: 'synapse_mcp_server',
    server_name: 'SynapseNetwork MCP Server',
    package_name: '@synapse-network-ai/mcp-server',
    package_registry: 'npm',
    package_version: '0.1.0',
    registry_name: 'io.github.SynapseNetworkAI/synapse-network-mcp-server',
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
      surface({ id: 1, surface_key: 'npm_registry', surface_label: 'npm', category: 'artifact', status: 'package_ready' }),
      surface({ id: 2, surface_key: 'official_mcp_registry', surface_label: 'Official MCP Registry', category: 'official_registry', status: 'candidate' }),
      surface({ id: 3, surface_key: 'glama', surface_label: 'Glama', category: 'directory', status: 'listed', listing_url: 'https://glama.ai/mcp/servers/synapse' }),
      surface({ id: 4, surface_key: 'openai_remote_mcp', surface_label: 'OpenAI Remote MCP', category: 'llm_platform', status: 'blocked_requires_remote_mcp', failure_reason: 'Remote MCP endpoint required.' }),
      surface({ id: 5, surface_key: 'claude_remote_mcp', surface_label: 'Claude MCP Connector', category: 'llm_platform', status: 'blocked_requires_remote_mcp', failure_reason: 'Remote MCP endpoint required.' }),
    ],
    published_at: null,
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
    ...overrides,
  }
}

function surface(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    mcp_server_release_id: 7,
    surface_key: 'official_mcp_registry',
    surface_label: 'Official MCP Registry',
    category: 'official_registry',
    status: 'candidate',
    listing_url: null,
    submission_url: 'https://github.com/modelcontextprotocol/registry',
    failure_reason: null,
    operator_note: null,
    evidence: {},
    last_checked_at: null,
    updated_at: null,
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
    tools: ['discover_services', 'invoke_and_pay', 'get_receipt'],
    security_boundary: 'stdio MCP server; API credentials stay in local env.',
    status: 'active',
    metadata: {},
    latest_release: release(),
    surface_summary: {},
    created_at: '2026-05-31T00:00:00Z',
    updated_at: '2026-05-31T00:00:00Z',
    ...overrides,
  }
}

function readiness() {
  return {
    server_id: 3,
    release_id: 7,
    items: [
      {
        surface_key: 'npm_registry',
        surface_label: 'npm',
        category: 'artifact',
        surface_status: 'package_ready',
        config_status: 'not_configured',
        readiness_status: 'not_configured',
        reason: 'Missing env refs: NODE_AUTH_TOKEN|NPM_TOKEN.',
        required_env_vars: ['NODE_AUTH_TOKEN|NPM_TOKEN'],
        missing_env_vars: ['NODE_AUTH_TOKEN|NPM_TOKEN'],
        submission_mode: 'auto',
        credential_ref: 'env:NODE_AUTH_TOKEN|NPM_TOKEN',
      },
      {
        surface_key: 'official_mcp_registry',
        surface_label: 'Official MCP Registry',
        category: 'official_registry',
        surface_status: 'candidate',
        config_status: 'not_configured',
        readiness_status: 'not_configured',
        reason: 'Missing local tool: mcp-publisher.',
        required_env_vars: [],
        missing_env_vars: [],
        submission_mode: 'auto',
        credential_ref: 'local:mcp-publisher',
      },
      {
        surface_key: 'openai_remote_mcp',
        surface_label: 'OpenAI Remote MCP',
        category: 'llm_platform',
        surface_status: 'blocked_requires_remote_mcp',
        config_status: 'verified',
        readiness_status: 'blocked',
        reason: 'Remote MCP endpoint is required.',
        required_env_vars: [],
        missing_env_vars: [],
        submission_mode: 'readonly',
        credential_ref: null,
      },
    ],
  }
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/releases/mcp-servers/3']}>
      <Routes>
        <Route path="/releases/mcp-servers/:id" element={<McpServerReleaseDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('McpServerReleaseDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getServer.mockResolvedValue(server())
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
    apiMock.createReleaseForServer.mockResolvedValue(release({ package_version: '0.1.1' }))
    apiMock.getSubmissionReadiness.mockResolvedValue(readiness())
    apiMock.verifySurfaceConfig.mockResolvedValue({
      surface_key: 'npm_registry',
      verification_status: 'not_configured',
      verification_summary: 'Missing env refs: NODE_AUTH_TOKEN|NPM_TOKEN.',
      missing_env_vars: ['NODE_AUTH_TOKEN|NPM_TOKEN'],
      required_tools: [],
      checked_at: '2026-05-31T00:03:00Z',
    })
    apiMock.patchSurfaceConfig.mockResolvedValue({})
    apiMock.liveCheckSurface.mockResolvedValue({
      release_id: 7,
      surface_key: 'npm_registry',
      status: 'blocked',
      summary: 'npm package URL is missing.',
      evidence: {},
      checked_at: '2026-05-31T00:04:00Z',
    })
    apiMock.submitSurface.mockResolvedValue(surface({ status: 'submitted' }))
  })

  it('shows overview, registry, AI platform, smoke evidence, and events tabs', async () => {
    renderDetail()

    expect(await screen.findByText('SynapseNetwork MCP Server')).toBeInTheDocument()
    expect(screen.getByText('MCP Server Registry Matrix')).toBeInTheDocument()
    expect(screen.getByText('Registries')).toBeInTheDocument()
    expect(screen.getByText('Configs')).toBeInTheDocument()
    expect(screen.getByText('AI Platforms')).toBeInTheDocument()
    expect(screen.getAllByText('Smoke Evidence').length).toBeGreaterThan(0)
    expect(screen.getByText('Events')).toBeInTheDocument()
    expect(screen.getByText('npx -y @synapse-network-ai/mcp-server')).toBeInTheDocument()

    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'AI Platforms' }))
    expect(screen.getByText('OpenAI Remote MCP')).toBeInTheDocument()
    expect(screen.getByText('Claude MCP Connector')).toBeInTheDocument()
    expect(screen.getAllByText('需要 Remote MCP').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: 'Events' }))
    expect(screen.getByText('readiness_passed')).toBeInTheDocument()
  })

  it('shows surface config readiness and verifies without exposing secrets', async () => {
    const user = userEvent.setup()
    renderDetail()

    await user.click(await screen.findByRole('button', { name: 'Configs' }))
    expect(screen.getByText('渠道配置与提交就绪度')).toBeInTheDocument()
    expect(screen.getByText('env:NODE_AUTH_TOKEN|NPM_TOKEN')).toBeInTheDocument()
    expect(screen.getAllByText('not_configured').length).toBeGreaterThan(0)
    expect(screen.getByText(/Missing env refs/)).toBeInTheDocument()

    await user.click(screen.getAllByRole('button', { name: 'Verify config' })[0])
    await waitFor(() => {
      expect(apiMock.verifySurfaceConfig).toHaveBeenCalledWith('npm_registry')
    })
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
      expect(apiMock.getServer).toHaveBeenCalledTimes(2)
    })
  })

  it('shows the next valid runner action for each status', async () => {
    apiMock.getServer.mockResolvedValueOnce(server({
      latest_release: release({
        status: 'npm_published',
        package_url: 'https://www.npmjs.com/package/@synapse-network-ai/mcp-server/v/0.1.0',
      }),
    }))
    const user = userEvent.setup()
    renderDetail()

    await user.click(await screen.findByRole('button', { name: 'Submit Registry' }))
    await waitFor(() => {
      expect(apiMock.submitRegistry).toHaveBeenCalledWith(7, { actor: 'operator' })
    })
  })
})
