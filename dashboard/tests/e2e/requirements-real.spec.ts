import { expect, test } from '@playwright/test'

test('runs requirement workflow against the real backend and captures evidence', async ({ page, request }) => {
  const syncResp = await request.post('/api/agents/sync')
  expect(syncResp.ok()).toBeTruthy()

  await page.goto('/requirements')

  await expect(page.getByTestId('requirements-page')).toBeVisible()

  await page.getByTestId('create-requirement-btn').click()
  await page.getByTestId('requirement-title').fill('Playwright real E2E requirement')
  await page.getByTestId('requirement-description').fill('Validate the launch FAQ flow and keep iterating until validation passes.')
  await page.getByTestId('requirement-priority').selectOption('high')
  await page.getByTestId('submit-requirement-btn').click()
  await expect(page.getByRole('heading', { name: 'Playwright real E2E requirement' })).toBeVisible()

  let createdRequirementId: number | null = null
  await expect.poll(async () => {
    const resp = await request.get('/api/requirements')
    const requirements = await resp.json() as Array<{ id: number; title: string }>
    createdRequirementId = requirements.find((item) => item.title === 'Playwright real E2E requirement')?.id ?? null
    return createdRequirementId
  }).not.toBeNull()
  expect(createdRequirementId).not.toBeNull()

  await page.goto(`/requirements/${createdRequirementId}`)
  await expect(page.getByTestId('requirement-detail-page')).toBeVisible()

  await expect.poll(async () => {
    const detailResp = await request.get(`/api/requirements/${createdRequirementId}`)
    const detail = await detailResp.json() as { requirement: { status: string } }
    return detail.requirement.status
  }, { timeout: 15_000 }).toBe('done')

  await page.reload()
  await expect(page.getByTestId('workflow-steps-panel')).toBeVisible()

  const detailResp = await request.get(`/api/requirements/${createdRequirementId}`)
  expect(detailResp.ok()).toBeTruthy()
  const detail = await detailResp.json() as {
    workflow_run: { status: string; steps: Array<{ step_type: string; status: string }> } | null
    artifacts: Array<{ artifact_type: string }>
    acceptance_checks: Array<{ status: string }>
  }
  expect(detail.workflow_run?.status).toBe('completed')
  expect(detail.workflow_run?.steps.some((step) => step.step_type === 'implementation' && step.status === 'completed')).toBeTruthy()
  expect(detail.workflow_run?.steps.some((step) => step.step_type === 'bugfix')).toBeTruthy()
  expect(detail.artifacts.some((artifact) => artifact.artifact_type === 'bug_report')).toBeTruthy()
  expect(detail.artifacts.some((artifact) => artifact.artifact_type === 'validation_manifest')).toBeTruthy()
  expect(detail.acceptance_checks.every((check) => check.status === 'passed')).toBeTruthy()

  await page.reload()
  await expect(page.getByTestId('requirement-detail-page')).toContainText('已完成')
  await expect(page.getByTestId('workflow-steps-panel')).toContainText('Bugfix after test failure')
  await expect(page.getByTestId('artifacts-panel')).toContainText('bug_report')
  await expect(page.getByTestId('artifacts-panel')).toContainText('validation_manifest')
  await expect(page.getByTestId('acceptance-checks-panel')).toContainText('passed')

  await page.screenshot({ path: 'test-results/requirements-pool-real-e2e.png', fullPage: true })
})
