import { useEffect, useState } from 'react'

const DEFAULT_PAGE_SIZE_OPTIONS = [20, 50, 100]

function clampPage(value: number, totalPages: number) {
  if (!Number.isFinite(value)) return 1
  return Math.max(1, Math.min(totalPages, Math.trunc(value)))
}

function pageItems(page: number, totalPages: number) {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1)
  const numbers = new Set<number>([1, totalPages, page - 1, page, page + 1].filter((value) => value >= 1 && value <= totalPages))
  const ordered = Array.from(numbers).sort((a, b) => a - b)
  const result: Array<number | string> = []
  ordered.forEach((value, index) => {
    const previous = ordered[index - 1]
    if (previous != null && value - previous > 1) result.push(`ellipsis-${previous}-${value}`)
    result.push(value)
  })
  return result
}

export type WorkbenchPaginationProps = {
  page: number
  pageSize: number
  totalItems: number
  pageSizeOptions?: number[]
  itemLabel?: string
  loading?: boolean
  showJump?: boolean
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

export function WorkbenchPagination({
  page,
  pageSize,
  totalItems,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  itemLabel = '条',
  loading = false,
  showJump = true,
  onPageChange,
  onPageSizeChange,
}: WorkbenchPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / Math.max(1, pageSize)))
  const safePage = clampPage(page, totalPages)
  const rangeStart = totalItems === 0 ? 0 : (safePage - 1) * pageSize + 1
  const rangeEnd = totalItems === 0 ? 0 : Math.min(totalItems, safePage * pageSize)
  const [jumpValue, setJumpValue] = useState(String(safePage))

  useEffect(() => {
    setJumpValue(String(safePage))
  }, [safePage])

  const requestPage = (nextPage: number) => {
    onPageChange(clampPage(nextPage, totalPages))
  }

  const submitJump = () => {
    const parsed = Number(jumpValue)
    requestPage(parsed)
  }

  return (
    <nav
      aria-label="分页"
      className="flex flex-wrap items-center justify-between gap-3 border-t border-[color:var(--ops-stroke-soft)] px-5 py-4 text-sm text-[color:var(--ops-text-muted)]"
    >
      <div>
        共 {totalItems} {itemLabel} · 显示 {rangeStart}-{rangeEnd} · 第 {safePage} / {totalPages} 页
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2">
          <span>每页</span>
          <select
            aria-label="每页条数"
            className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
            value={pageSize}
            disabled={loading}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {pageSizeOptions.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <span>条</span>
        </label>

        <div className="flex flex-wrap items-center gap-2" aria-label="分页导航">
          <button type="button" disabled={safePage <= 1 || loading} className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" onClick={() => requestPage(1)}>首页</button>
          <button type="button" disabled={safePage <= 1 || loading} className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" onClick={() => requestPage(safePage - 1)}>上一页</button>
          {pageItems(safePage, totalPages).map((item) => typeof item === 'number' ? (
            <button
              key={item}
              type="button"
              aria-current={item === safePage ? 'page' : undefined}
              aria-label={`第 ${item} 页`}
              disabled={loading}
              className={`rounded-lg px-3 py-2 text-sm ${item === safePage ? 'bg-blue-600 text-white' : 'border border-[color:var(--ops-stroke-strong)]'}`}
              onClick={() => requestPage(item)}
            >
              {item}
            </button>
          ) : (
            <span key={item} className="px-2 text-sm text-[color:var(--ops-text-caption)]" aria-hidden="true">…</span>
          ))}
          <button type="button" disabled={safePage >= totalPages || loading} className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" onClick={() => requestPage(safePage + 1)}>下一页</button>
          <button type="button" disabled={safePage >= totalPages || loading} className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" onClick={() => requestPage(totalPages)}>末页</button>
        </div>

        {showJump ? (
          <label className="flex items-center gap-2">
            <span>跳至</span>
            <input
              aria-label="跳至页码"
              className="w-16 rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm"
              inputMode="numeric"
              value={jumpValue}
              disabled={loading}
              onChange={(event) => setJumpValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') submitJump()
              }}
            />
            <span>页</span>
            <button type="button" disabled={loading} className="rounded-lg border border-[color:var(--ops-stroke-strong)] px-3 py-2 text-sm disabled:opacity-40" onClick={submitJump}>跳转</button>
          </label>
        ) : null}
      </div>
    </nav>
  )
}
