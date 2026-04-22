import { expect, test } from '@playwright/test'

const routes = [
  { path: '/command-center', title: '司令部' },
  { path: '/planning', title: '经营规划' },
  { path: '/intake', title: '信号入口' },
  { path: '/gates', title: '门禁审批' },
  { path: '/requirements', title: '需求池' },
  { path: '/workflows', title: '运行轨迹' },
  { path: '/schedules', title: '定时任务' },
  { path: '/releases', title: '发布' },
  { path: '/projects', title: '项目' },
  { path: '/errors', title: '错误' },
  { path: '/factory/workflows', title: '状态机定义' },
  { path: '/factory/atoms', title: '原子能力库' },
  { path: '/knowledge', title: '知识资产' },
  { path: '/system/notifications', title: '通知队列' },
]

function screenshotName(path: string) {
  return path.replace(/^\//, '').replaceAll('/', '-') || 'command-center'
}

test('Ops Console primary pages render with local data and screenshot evidence', async ({ page }, testInfo) => {
  const browserErrors: string[] = []
  const failedApiResponses: string[] = []

  page.on('pageerror', (error) => browserErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      browserErrors.push(message.text())
    }
  })
  page.on('response', (response) => {
    const url = response.url()
    if (url.includes('/api/') && response.status() >= 500) {
      failedApiResponses.push(`${response.status()} ${url}`)
    }
  })

  for (const route of routes) {
    await page.goto(route.path, { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: route.title }).first()).toBeVisible()
    await expect(page.getByText('Agent Ops')).toBeVisible()
    await expect(page.locator('body')).not.toContainText(/Application error|Unhandled Runtime Error|No routes matched/i)
    await page.waitForLoadState('networkidle', { timeout: 2_000 }).catch(() => undefined)
    await page.screenshot({
      path: testInfo.outputPath(`${screenshotName(route.path)}.png`),
      fullPage: true,
    })
  }

  expect(failedApiResponses, 'No validated page should return 5xx API responses').toEqual([])
  expect(browserErrors, 'No validated page should emit uncaught browser errors').toEqual([])
})
