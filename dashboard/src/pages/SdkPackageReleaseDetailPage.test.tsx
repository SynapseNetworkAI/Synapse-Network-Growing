// @vitest-environment jsdom

import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SdkPackageReleaseDetailPage from './SdkPackageReleaseDetailPage'

const navigateMock = vi.hoisted(() => vi.fn())
const apiMock = vi.hoisted(() => ({
  getSdkPackageRelease: vi.fn(),
  getSdkPackageReleaseEvents: vi.fn(),
  getSdkPackageReleaseHistory: vi.fn(),
  dryRunSdkPackageRelease: vi.fn(),
  publishSdkPackageRelease: vi.fn(),
  retrySdkPackageRelease: vi.fn(),
  syncSdkPackageReleaseStatuses: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

vi.mock('../sdkPackagesApi', () => ({
  sdkPackagesApi: apiMock,
}))

function release(overrides: Record<string, unknown> = {}) {
  return {
    id: 2,
    release_train_version: '1.0.0',
    sdk_language: 'python',
    package_name: 'synapse-client',
    registry: 'pypi',
    channel: 'latest',
    package_version: '1.0.0',
    git_tag: 'sdk/v1.0.0',
    status: 'published',
    package_url: 'https://pypi.org/project/synapse-client/1.0.0/',
    workflow_run_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/2',
    failure_summary: null,
    release_notes: 'Stable SDK release.',
    metadata: {},
    published_at: '2026-05-21T10:00:00Z',
    created_at: '2026-05-21T09:00:00Z',
    updated_at: '2026-05-21T10:00:00Z',
    ...overrides,
  }
}

function historyPage(overrides: Record<string, unknown> = {}) {
  return {
    items: [
      {
        id: 3,
        release_train_version: '1.0.1',
        sdk_language: 'python',
        package_name: 'synapse-client',
        registry: 'pypi',
        channel: 'latest',
        package_version: '1.0.1',
        status: 'published',
        package_url: 'https://pypi.org/project/synapse-client/1.0.1/',
        repo_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk',
        git_tag: 'sdk/v1.0.1',
        git_tag_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/tree/sdk/v1.0.1',
        workflow_run_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/3',
        failure_summary: null,
        published_at: '2026-05-22T10:00:00Z',
        updated_at: '2026-05-22T10:00:00Z',
      },
      {
        id: 2,
        release_train_version: '1.0.0',
        sdk_language: 'python',
        package_name: 'synapse-client',
        registry: 'pypi',
        channel: 'latest',
        package_version: '1.0.0',
        status: 'published',
        package_url: 'https://pypi.org/project/synapse-client/1.0.0/',
        repo_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk',
        git_tag: 'sdk/v1.0.0',
        git_tag_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/tree/sdk/v1.0.0',
        workflow_run_url: null,
        failure_summary: null,
        published_at: '2026-05-21T10:00:00Z',
        updated_at: '2026-05-21T10:00:00Z',
      },
    ],
    total: 12,
    limit: 10,
    offset: 0,
    ...overrides,
  }
}

function renderDetail() {
  return render(
    <MemoryRouter initialEntries={['/releases/sdk-packages/2']}>
      <Routes>
        <Route path="/releases/sdk-packages/:id" element={<SdkPackageReleaseDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SdkPackageReleaseDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.getSdkPackageRelease.mockResolvedValue(release())
    apiMock.getSdkPackageReleaseEvents.mockResolvedValue([
      {
        id: 10,
        sdk_package_release_id: 2,
        action: 'sync_status',
        from_status: 'publishing',
        to_status: 'published',
        actor: null,
        note: null,
        workflow_run_url: 'https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/2',
        error_summary: null,
        metadata: {},
        created_at: '2026-05-21T10:00:00Z',
      },
    ])
    apiMock.getSdkPackageReleaseHistory.mockImplementation((_id, filters) => (
      Promise.resolve(historyPage({ offset: filters?.offset ?? 0 }))
    ))
  })

  it('shows result history separately from the operation timeline', async () => {
    renderDetail()

    expect(await screen.findByText('发布结果历史')).toBeInTheDocument()
    expect(screen.getByText('操作时间线')).toBeInTheDocument()
    expect(screen.getAllByText('1.0.1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('1.0.0').length).toBeGreaterThan(0)
    expect(screen.getByText('sync_status')).toBeInTheDocument()
    expect(screen.getAllByText('打开 Registry').length).toBeGreaterThan(0)
    expect(screen.getAllByText('打开 GitHub Tag').length).toBeGreaterThan(0)
  })

  it('searches result history from the first page', async () => {
    const user = userEvent.setup()
    renderDetail()

    await screen.findByText('发布结果历史')
    await user.type(screen.getByPlaceholderText('搜索版本 / train / 状态 / registry / failure summary'), '1.0.0')
    await user.click(screen.getByRole('button', { name: '搜索' }))

    await waitFor(() => {
      expect(apiMock.getSdkPackageReleaseHistory).toHaveBeenLastCalledWith(2, {
        q: '1.0.0',
        status: undefined,
        channel: undefined,
        limit: 10,
        offset: 0,
      })
    })
  })

  it('paginates result history and navigates to a selected release record', async () => {
    const user = userEvent.setup()
    renderDetail()

    const historySection = (await screen.findByText('发布结果历史')).closest('section')
    expect(historySection).not.toBeNull()
    await user.click(within(historySection as HTMLElement).getByRole('button', { name: '下一页' }))

    await waitFor(() => {
      expect(apiMock.getSdkPackageReleaseHistory).toHaveBeenLastCalledWith(2, {
        q: undefined,
        status: undefined,
        channel: undefined,
        limit: 10,
        offset: 10,
      })
    })

    await user.click(within(historySection as HTMLElement).getAllByRole('button', { name: '查看详情' })[0])
    expect(navigateMock).toHaveBeenCalledWith('/releases/sdk-packages/3')
  })
})
