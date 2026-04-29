import { expect, test } from '@playwright/test'

test('Planning Mission Workbench shows hierarchy, stage rail, and centered details', async ({ page }, testInfo) => {
  await page.goto('/planning', { waitUntil: 'domcontentloaded' })

  const workbench = page.getByTestId('mission-workbench-tab')
  await expect(workbench).toBeVisible()
  await expect(workbench.getByRole('heading', { name: '目标 → 战线 → 任务 → 证据' })).toBeVisible()
  await expect(workbench.getByText('Opportunity').first()).toBeVisible()
  await expect(workbench.getByText('Candidate').first()).toBeVisible()
  await expect(workbench.getByText('Workflow').first()).toBeVisible()

  const firstDetailButton = workbench.getByRole('button', { name: '详情' }).first()
  await expect(firstDetailButton).toBeVisible()
  await firstDetailButton.click()
  const detailModal = page.getByRole('dialog', { name: /Mission item detail/ })
  await expect(detailModal).toBeVisible()
  await expect(detailModal.getByText('Next Action')).toBeVisible()
  await expect(detailModal.getByText('Status')).toBeVisible()

  await page.screenshot({
    path: testInfo.outputPath('planning-mission-workbench.png'),
    fullPage: true,
  })
})
