// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { WorkbenchPagination } from './WorkbenchPagination'

describe('WorkbenchPagination', () => {
  it('renders total, range, page count, and current page semantics', () => {
    render(
      <WorkbenchPagination
        page={2}
        pageSize={20}
        totalItems={138}
        itemLabel="个 bug"
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    )

    expect(screen.getByText('共 138 个 bug · 显示 21-40 · 第 2 / 7 页')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '第 2 页' })).toHaveAttribute('aria-current', 'page')
  })

  it('handles empty totals as a disabled single page', () => {
    render(
      <WorkbenchPagination
        page={1}
        pageSize={20}
        totalItems={0}
        onPageChange={vi.fn()}
        onPageSizeChange={vi.fn()}
      />,
    )

    expect(screen.getByText('共 0 条 · 显示 0-0 · 第 1 / 1 页')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '首页' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled()
  })

  it('calls page, page size, and jump handlers with bounded values', async () => {
    const user = userEvent.setup()
    const onPageChange = vi.fn()
    const onPageSizeChange = vi.fn()

    render(
      <WorkbenchPagination
        page={2}
        pageSize={20}
        totalItems={138}
        onPageChange={onPageChange}
        onPageSizeChange={onPageSizeChange}
      />,
    )

    await user.click(screen.getByRole('button', { name: '下一页' }))
    expect(onPageChange).toHaveBeenCalledWith(3)

    await user.selectOptions(screen.getByLabelText('每页条数'), '50')
    expect(onPageSizeChange).toHaveBeenCalledWith(50)

    await user.clear(screen.getByLabelText('跳至页码'))
    await user.type(screen.getByLabelText('跳至页码'), '99')
    await user.click(screen.getByRole('button', { name: '跳转' }))
    expect(onPageChange).toHaveBeenLastCalledWith(7)
  })
})
