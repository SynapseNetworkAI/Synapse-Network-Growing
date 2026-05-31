// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../components/workbench'
import PublishingTrendResultsPage from './PublishingTrendResultsPage'

const apiMock = vi.hoisted(() => ({
  querySocialTrends: vi.fn(),
  getSocialTrend: vi.fn(),
}))

vi.mock('../api', () => ({
  api: apiMock,
}))

const xTrend = {
  id: 101,
  source_platform: 'x',
  source_url: 'https://x.com/OpenAI/status/4242',
  author_handle: 'OpenAI',
  topic: 'AI agents need payment rails',
  summary: 'Agent builders increasingly need budgeted tool/API access and payment primitives.',
  relevance_score: 0.91,
  status: 'new',
  source_kind: 'x_post',
  collected_at: '2026-04-26T12:00:00Z',
  updated_at: '2026-04-26T12:05:00Z',
}

const localSeed = {
  id: 102,
  source_platform: 'x',
  source_url: null,
  author_handle: null,
  topic: 'Local agent economy seed',
  summary: 'Seed trend: autonomous agents need governed access to paid APIs.',
  relevance_score: 0.75,
  status: 'saved',
  source_kind: 'local_seed',
  collected_at: '2026-04-26T13:00:00Z',
  updated_at: '2026-04-26T13:05:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <PublishingTrendResultsPage />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('PublishingTrendResultsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMock.querySocialTrends.mockResolvedValue({ items: [xTrend, localSeed], total: 2, limit: 20, offset: 0 })
    apiMock.getSocialTrend.mockResolvedValue(xTrend)
  })

  it('renders searchable trend results and opens centered detail modal', async () => {
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByRole('heading', { name: 'X 趋势雷达结果' })).toBeInTheDocument()
    expect(await screen.findByText('AI agents need payment rails')).toBeInTheDocument()
    expect(screen.getAllByText('本地趋势种子').length).toBeGreaterThan(0)
    expect(screen.getByText('第 1 / 1 页 · 共 2 条趋势')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('关键字搜索'))
    await user.type(screen.getByLabelText('关键字搜索'), 'payment rails')
    await user.selectOptions(screen.getByLabelText('来源类型'), 'x_post')
    await user.clear(screen.getByLabelText('作者筛选'))
    await user.type(screen.getByLabelText('作者筛选'), '@OpenAI')
    await user.click(screen.getByRole('button', { name: '搜索' }))

    await waitFor(() => {
      expect(apiMock.querySocialTrends).toHaveBeenLastCalledWith(expect.objectContaining({
        q: 'payment rails',
        source_kind: 'x_post',
        author_handle: '@OpenAI',
        limit: 20,
        offset: 0,
      }))
    })

    await user.click(screen.getAllByRole('button', { name: '详情' })[0])

    await waitFor(() => expect(apiMock.getSocialTrend).toHaveBeenCalledWith(101))
    expect(screen.getByRole('dialog', { name: '趋势详情 #101' })).toBeInTheDocument()
    expect(screen.getAllByText('Agent builders increasingly need budgeted tool/API access and payment primitives.').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: '打开 X 原帖' })).toHaveAttribute('href', 'https://x.com/OpenAI/status/4242')
  })

  it('shows local seed guidance in the detail modal when source url is missing', async () => {
    const user = userEvent.setup()
    apiMock.getSocialTrend.mockResolvedValue(localSeed)
    renderPage()

    await screen.findByText('Local agent economy seed')
    await user.click(screen.getAllByRole('button', { name: '详情' })[1])

    expect(await screen.findByRole('dialog', { name: '趋势详情 #102' })).toBeInTheDocument()
    expect(screen.getByText(/仅作内容灵感，不能引用转发/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '打开 X 原帖' })).not.toBeInTheDocument()
  })
})
