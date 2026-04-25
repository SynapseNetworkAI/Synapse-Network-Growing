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

test('Release management can create a staging release task without auto-deploying', async ({ page }, testInfo) => {
  const browserErrors: string[] = []
  const failedApiResponses: string[] = []
  const branchName = 'codex/e2e-staging-release-task'

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

  await page.goto('/releases', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '发布管理' }).click()

  await expect(page.getByRole('button', { name: '新建发布任务' })).toBeEnabled()
  await page.getByRole('button', { name: '新建发布任务' }).click()
  await expect(page.getByRole('heading', { name: '新建发布任务' })).toBeVisible()
  await expect(page.getByText('创建任务不会自动上线')).toBeVisible()
  await expect(page.getByRole('button', { name: '创建发布任务' })).toBeDisabled()

  await expect(page.getByLabel('分支')).toBeEnabled()
  await page.getByLabel('分支').selectOption(branchName)
  await page.getByPlaceholder('记录发布窗口、手动执行位置或回滚注意事项。').fill('E2E staging release task creation only.')
  await expect(page.getByRole('button', { name: '创建发布任务' })).toBeEnabled()
  await page.getByRole('button', { name: '创建发布任务' }).press('Enter')

  await expect(page.getByRole('heading', { name: '新建发布任务' })).toBeHidden()
  await expect(page.getByRole('table').getByText(branchName)).toBeVisible()
  await expect(page.getByText('Service: gateway')).toBeVisible()
  await expect(page.getByRole('table').getByText('待执行')).toBeVisible()
  await expect(page.getByRole('button', { name: '发布到 staging' })).toBeVisible()
  await expect(page.getByText('Deploy:')).toHaveCount(0)

  await page.screenshot({
    path: testInfo.outputPath('release-task-created.png'),
    fullPage: true,
  })

  expect(failedApiResponses, 'Release task creation should not return 5xx API responses').toEqual([])
  expect(browserErrors, 'Release task creation should not emit uncaught browser errors').toEqual([])
})
