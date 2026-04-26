import { expect, test, type Page, type Route, type TestInfo } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { execFileSync } from 'node:child_process'

const routes = [
  { path: '/command-center', title: '司令部' },
  { path: '/planning', title: '经营规划' },
  { path: '/intake', title: '信号入口' },
  { path: '/gates', title: '门禁审批' },
  { path: '/requirements', title: '需求池' },
  { path: '/workflows', title: '运行轨迹' },
  { path: '/publishing', title: '官方账号内容发布' },
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

type MockSocialPost = {
  id: number
  platform: 'x'
  account_id: number
  account_handle: string
  account_display_name: string
  title: string | null
  body_text: string
  status: string
  generated_by: string
  reviewed_by: string | null
  review_note: string | null
  target_audience: string | null
  cta: string | null
  agent_rationale: string | null
  policy_check: {
    status: 'passed' | 'blocked'
    character_count: number
    warnings: string[]
    blocked_reasons: string[]
  }
  raw_agent_output: Record<string, unknown>
  published_at: string | null
  external_post_id: string | null
  external_url: string | null
  failure_summary: string | null
  media_assets: MockSocialMediaAsset[]
  events: unknown[]
  created_at: string
  updated_at: string
}

type MockSocialMediaAsset = {
  id: number
  post_id: number
  media_type: 'image'
  status: string
  prompt: string | null
  alt_text: string | null
  preview_url: string | null
  x_media_id: string | null
  failure_summary: string | null
  created_at: string
  updated_at: string
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

function socialPolicyCheck(bodyText: string): MockSocialPost['policy_check'] {
  const blockedReasons: string[] = []
  if (/guaranteed|risk-free|send funds|收益保证|稳赚/i.test(bodyText)) {
    blockedReasons.push('public post contains unsafe financial promise')
  }
  return {
    status: blockedReasons.length ? 'blocked' : 'passed',
    character_count: bodyText.length,
    warnings: [],
    blocked_reasons: blockedReasons,
  }
}

const realCodexSocialPrompt =
  '刚创建了x的账号，如何发布第一篇x聂荣介绍我们平台SynapseNetworl是做什么的让大家知道我们。刚上线了staging环境。网站是https://staging.synapse-network.ai。读取/Users/cliff/workspace/agent/Synapse-Network/docs 给出文档，生成第一篇官方推文。. Human-reviewed. Human-reviewed X update from Synapse Network.'

function socialDogfoodDir() {
  return path.resolve(process.cwd(), '..', 'dogfood-output', 'social-publishing-real-generation')
}

function writeSocialDogfoodReport({
  status,
  screenshotPath,
  consoleErrors,
  networkEvents,
  details,
  bugfixRequired,
}: {
  status: 'passed' | 'failed'
  screenshotPath?: string
  consoleErrors: string[]
  networkEvents: string[]
  details: string[]
  bugfixRequired?: string[]
}) {
  const outDir = socialDogfoodDir()
  fs.mkdirSync(path.join(outDir, 'screenshots'), { recursive: true })
  const report = [
    '# Social Publishing Real Codex Generation E2E',
    '',
    `Status: ${status}`,
    '',
    '## Prompt',
    '',
    '```text',
    realCodexSocialPrompt,
    '```',
    '',
    '## Details',
    '',
    ...details.map((line) => `- ${line}`),
    '',
    '## Screenshot',
    '',
    screenshotPath ? `![publishing-page](${screenshotPath})` : '- No screenshot captured.',
    '',
    '## Console Errors',
    '',
    consoleErrors.length ? consoleErrors.map((line) => `- ${line}`).join('\n') : '- none',
    '',
    '## Network Events',
    '',
    networkEvents.length ? networkEvents.map((line) => `- ${line}`).join('\n') : '- none',
    '',
    '## Bugfix Required',
    '',
    bugfixRequired?.length ? bugfixRequired.map((line) => `- ${line}`).join('\n') : '- none',
    '',
  ].join('\n')
  fs.writeFileSync(path.join(outDir, 'report.md'), report, 'utf-8')
}

function pythonBin() {
  const configured = process.env.PYTHON_BIN
  if (configured && fs.existsSync(configured)) return configured
  const local = '/Users/cliff/workspace/agent/.venv/bin/python'
  if (fs.existsSync(local)) return local
  return 'python3'
}

function querySocialDraftMaxId() {
  const dbPath = fs.existsSync(path.resolve(process.cwd(), '..', '.playwright', 'ops-e2e.sqlite'))
    ? '.playwright/ops-e2e.sqlite'
    : 'server/ops.db'
  const script = `
import sqlite3
conn = sqlite3.connect(${JSON.stringify(dbPath)})
row = conn.execute("select coalesce(max(id), 0) from social_post_drafts").fetchone()
print(row[0] or 0)
`
  return Number(execFileSync(pythonBin(), ['-c', script], { cwd: path.resolve(process.cwd(), '..'), encoding: 'utf-8' }).trim() || '0')
}

function queryLatestSocialDraftAfter(minId: number) {
  const dbPath = fs.existsSync(path.resolve(process.cwd(), '..', '.playwright', 'ops-e2e.sqlite'))
    ? '.playwright/ops-e2e.sqlite'
    : 'server/ops.db'
  const script = `
import json, sqlite3, sys
min_id = int(sys.argv[1])
conn = sqlite3.connect(${JSON.stringify(dbPath)})
conn.row_factory = sqlite3.Row
row = conn.execute(
    "select id, title, body_text, status, policy_check_json, raw_agent_output_json from social_post_drafts where id > ? order by id desc limit 1",
    (min_id,),
).fetchone()
if row is None:
    print("{}")
else:
    payload = dict(row)
    for key in ("policy_check_json", "raw_agent_output_json"):
        try:
            payload[key.removesuffix("_json")] = json.loads(payload.pop(key) or "{}")
        except Exception:
            payload[key.removesuffix("_json")] = {}
    print(json.dumps(payload, ensure_ascii=False))
`
  const raw = execFileSync(pythonBin(), ['-c', script, String(minId)], { cwd: path.resolve(process.cwd(), '..'), encoding: 'utf-8' })
  return JSON.parse(raw || '{}') as {
    id?: number
    title?: string
    body_text?: string
    status?: string
    policy_check?: { status?: string; character_count?: number }
    raw_agent_output?: Record<string, unknown>
  }
}

function latestSocialBackendLogExcerpt() {
  const logPath = path.resolve(process.cwd(), '..', 'server', 'logs', 'ops-dashboard.jsonl')
  if (!fs.existsSync(logPath)) return 'server log not found'
  const lines = fs.readFileSync(logPath, 'utf-8').split(/\r?\n/).filter(Boolean)
  return lines
    .slice(-300)
    .filter((line) => /social|generate-draft|codex_cli_exec|agent_generation/i.test(line))
    .slice(-20)
    .join('\n')
    .slice(0, 4000)
}

async function recordSocialDogfoodBug(page: Page, summary: string, logExcerpt: string) {
  await page.request
    .post('/api/bugs/intake', {
      data: {
        source_key: 'manual_bug_report',
        project_key: 'synapse-network-growing',
        project_root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing',
        title: 'Social Publishing real Codex generation E2E failed',
        summary,
        severity: 'high',
        source_ref: 'dogfood:social-publishing-real-generation',
        environment: 'local',
        log_excerpt: logExcerpt,
        metadata: { component: 'social_publishing', test_name: 'Social Publishing real Codex draft generation succeeds' },
      },
    })
    .catch(() => undefined)
}

async function installMockSocialApi(page: Page) {
  const posts: MockSocialPost[] = []
  let nextPostId = 7001
  let nextMediaId = 9001
  const now = () => new Date().toISOString()
  const account = {
    id: 1,
    platform: 'x',
    handle: 'SynapseNetworkA',
    display_name: 'Synapse Network',
    secret_ref: 'gcp://secret-manager/x-official-oauth2-user-token',
    status: 'active',
    created_at: now(),
    updated_at: now(),
  }

  await page.route('**/api/social/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()

    if (url.pathname === '/api/social/accounts' && method === 'GET') {
      await json(route, [account])
      return
    }

    if (url.pathname === '/api/social/posts' && method === 'GET') {
      const statusFilter = url.searchParams.get('status')
      const rows = statusFilter ? posts.filter((post) => post.status === statusFilter) : posts
      await json(route, rows)
      return
    }

    if (url.pathname === '/api/social/posts' && method === 'POST') {
      const payload = request.postDataJSON() as {
        account_id?: number | null
        title?: string | null
        body_text: string
        status?: string
        generated_by?: string
        target_audience?: string | null
        cta?: string | null
        agent_rationale?: string | null
        raw_agent_output?: Record<string, unknown>
      }
      const timestamp = now()
      const post: MockSocialPost = {
        id: nextPostId++,
        platform: 'x',
        account_id: payload.account_id ?? account.id,
        account_handle: account.handle,
        account_display_name: account.display_name,
        title: payload.title ?? null,
        body_text: payload.body_text,
        status: payload.status ?? 'needs_review',
        generated_by: payload.generated_by ?? 'operator',
        reviewed_by: null,
        review_note: null,
        target_audience: payload.target_audience ?? null,
        cta: payload.cta ?? null,
        agent_rationale: payload.agent_rationale ?? null,
        policy_check: socialPolicyCheck(payload.body_text),
        raw_agent_output: payload.raw_agent_output ?? { hidden_debug_marker: `raw-output-${payload.title ?? 'draft'}` },
        published_at: null,
        external_post_id: null,
        external_url: null,
        failure_summary: null,
        media_assets: [],
        events: [],
        created_at: timestamp,
        updated_at: timestamp,
      }
      posts.unshift(post)
      await json(route, post)
      return
    }

    if (url.pathname === '/api/social/posts/generate-draft' && method === 'POST') {
      const payload = request.postDataJSON() as {
        account_id?: number | null
        prompt: string
        actor?: string
        media_mode?: string
      }
      const timestamp = now()
      const unsafeMatch = payload.prompt.match(/Unsafe X draft \d+/)
      const title = unsafeMatch?.[0] ?? 'Synapse X publishing update'
      const bodyText = unsafeMatch
        ? 'Guaranteed risk-free returns. Send funds now.'
        : 'Synapse now has a simpler human-gated X publishing flow: prompt in, polished post out, operator click to publish.'
      const policyCheck = socialPolicyCheck(bodyText)
      const postId = nextPostId++
      const mediaId = nextMediaId++
      const mediaAssets: MockSocialMediaAsset[] = payload.media_mode === 'text_only' ? [] : [{
        id: mediaId,
        post_id: postId,
        media_type: 'image',
        status: 'ready',
        prompt: 'Dark SaaS visual of AI agents connected through a settlement layer.',
        alt_text: 'AI agents connected by the Synapse Network settlement layer.',
        preview_url: `/api/social/media/${mediaId}/preview`,
        x_media_id: null,
        failure_summary: null,
        created_at: timestamp,
        updated_at: timestamp,
      }]
      const post: MockSocialPost = {
        id: postId,
        platform: 'x',
        account_id: payload.account_id ?? account.id,
        account_handle: account.handle,
        account_display_name: account.display_name,
        title,
        body_text: bodyText,
        status: policyCheck.status === 'passed' ? 'approved' : 'needs_review',
        generated_by: 'social_content_agent_v1',
        reviewed_by: policyCheck.status === 'passed' ? payload.actor ?? 'operator' : null,
        review_note: null,
        target_audience: null,
        cta: null,
        agent_rationale: null,
        policy_check: policyCheck,
        raw_agent_output: { source: 'mock_social_content_agent_v1' },
        published_at: null,
        external_post_id: null,
        external_url: null,
        failure_summary: null,
        media_assets: mediaAssets,
        events: [],
        created_at: timestamp,
        updated_at: timestamp,
      }
      posts.unshift(post)
      await json(route, post)
      return
    }

    if (/^\/api\/social\/media\/\d+\/preview$/.test(url.pathname) && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'image/png',
        body: Buffer.from('fake-image'),
      })
      return
    }

    const postMatch = url.pathname.match(/^\/api\/social\/posts\/(\d+)(?:\/(request-rewrite|publish-x))?$/)
    if (!postMatch) {
      await json(route, { detail: 'not_found' }, 404)
      return
    }

    const post = posts.find((row) => row.id === Number(postMatch[1]))
    if (!post) {
      await json(route, { detail: 'post_not_found' }, 404)
      return
    }

    const action = postMatch[2]
    if (!action && method === 'PATCH') {
      const payload = request.postDataJSON() as Partial<MockSocialPost>
      if (typeof payload.title !== 'undefined') post.title = payload.title
      if (typeof payload.body_text === 'string') {
        post.body_text = payload.body_text
        post.policy_check = socialPolicyCheck(payload.body_text)
      }
      if (typeof payload.status === 'string') post.status = payload.status
      if (typeof payload.reviewed_by === 'string') post.reviewed_by = payload.reviewed_by
      if (typeof payload.review_note === 'string') post.review_note = payload.review_note
      if (typeof payload.target_audience !== 'undefined') post.target_audience = payload.target_audience
      if (typeof payload.cta !== 'undefined') post.cta = payload.cta
      if (typeof payload.agent_rationale !== 'undefined') post.agent_rationale = payload.agent_rationale
      post.updated_at = now()
      await json(route, post)
      return
    }

    if (action === 'request-rewrite' && method === 'POST') {
      post.status = 'needs_review'
      post.updated_at = now()
      await json(route, post)
      return
    }

    if (action === 'publish-x' && method === 'POST') {
      post.status = 'published'
      post.reviewed_by = post.reviewed_by ?? 'operator'
      post.media_assets = post.media_assets.map((asset) => ({ ...asset, status: 'uploaded', x_media_id: asset.x_media_id ?? `mock-media-${asset.id}` }))
      post.published_at = now()
      post.external_post_id = '1800000000000000002'
      post.external_url = 'https://x.com/SynapseNetworkA/status/1800000000000000002'
      post.updated_at = post.published_at
      await json(route, post)
      return
    }

    await json(route, { detail: 'method_not_allowed' }, 405)
  })
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

  const branchSelect = page.getByLabel('分支', { exact: true })
  await expect(branchSelect).toBeEnabled()
  await branchSelect.selectOption(branchName)
  await page.getByPlaceholder('记录发布窗口、手动执行位置或回滚注意事项。').fill('E2E staging release task creation only.')
  await expect(page.getByRole('button', { name: '创建发布任务' })).toBeEnabled()
  await page.getByRole('button', { name: '创建发布任务' }).press('Enter')

  await expect(page.getByRole('heading', { name: '新建发布任务' })).toBeHidden()
  await expect(page.getByRole('table').getByText(branchName)).toBeVisible()
  await expect(page.getByText('Service: gateway')).toBeVisible()
  await expect(page.getByRole('table').getByText('待执行')).toBeVisible()
  await expect(page.getByRole('button', { name: '提交 PR' })).toBeVisible()
  await expect(page.getByRole('button', { name: '发布到 staging' })).toHaveCount(0)
  await expect(page.getByText('Deploy:')).toHaveCount(0)

  await page.screenshot({
    path: testInfo.outputPath('release-task-created.png'),
    fullPage: true,
  })

  expect(failedApiResponses, 'Release task creation should not return 5xx API responses').toEqual([])
  expect(browserErrors, 'Release task creation should not emit uncaught browser errors').toEqual([])
})

test('Social Publishing is discoverable from the sidebar', async ({ page }) => {
  await page.goto('/planning', { waitUntil: 'domcontentloaded' })
  const publishingLink = page.getByRole('link', { name: /内容发布/i })
  await expect(publishingLink).toBeVisible()
  await publishingLink.click()
  await expect(page).toHaveURL(/\/publishing$/)
  await expect(page.getByRole('heading', { name: '官方账号内容发布' })).toBeVisible()
})

test('Social Publishing operator can generate and mock publish an X draft', async ({ page }, testInfo) => {
  await installMockSocialApi(page)

  const prompt = `E2E X launch note ${Date.now()}: audited content publishing queue with Agent drafts, human review, and explicit X publish.`
  const title = 'Synapse X publishing update'

  await page.goto('/publishing', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '官方账号内容发布' })).toBeVisible()
  await page.getByRole('button', { name: '让 Agent 写草稿' }).click()
  await expect(page.getByRole('heading', { name: '让 Agent 写草稿' })).toBeVisible()

  await page.getByLabel('目标 / Prompt').fill(prompt)
  await expect(page.getByLabel('媒体策略')).toHaveValue('auto')
  await page.getByRole('button', { name: '生成草稿' }).click()

  const draftRow = page.getByRole('row').filter({ hasText: title })
  await expect(draftRow).toBeVisible()
  await expect(draftRow.getByText('可发布')).toBeVisible()
  await expect(draftRow.getByText('prompt in, polished post out')).toBeVisible()
  await expect(draftRow.getByText('图片已生成')).toBeVisible()
  await expect(draftRow.getByAltText('AI agents connected by the Synapse Network settlement layer.')).toBeVisible()
  await expect(draftRow.getByText(prompt)).toHaveCount(0)
  await expect(draftRow.getByText('目标受众')).toHaveCount(0)
  await expect(draftRow.getByText('CTA')).toHaveCount(0)
  await expect(draftRow.getByText('Agent 生成理由')).toHaveCount(0)
  await expect(draftRow.getByRole('button', { name: '发布到 X' })).toBeVisible()
  await expect(draftRow.getByRole('button', { name: '批准' })).toHaveCount(0)

  await draftRow.getByRole('button', { name: '发布到 X' }).click()
  await expect(page.getByRole('heading', { name: '确认发布到 X' })).toBeVisible()
  await expect(page.getByText(/附带 1 张图片/)).toBeVisible()
  await page.getByRole('button', { name: '发布到 X' }).last().click()

  const publishedRow = page.getByRole('row').filter({ hasText: title })
  await expect(publishedRow.getByText('已发布')).toBeVisible()
  await expect(publishedRow.getByRole('link', { name: /Open on X · 1800000000000000002/ })).toBeVisible()

  await page.screenshot({
    path: testInfo.outputPath('social-publishing-mock-published.png'),
    fullPage: true,
  })
})

test('Social Publishing blocks unsafe draft approval before publish', async ({ page }) => {
  await installMockSocialApi(page)

  const title = `Unsafe X draft ${Date.now()}`
  const prompt = `${title}: Guaranteed risk-free returns. Send funds now to capture the launch opportunity.`

  await page.goto('/publishing', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '让 Agent 写草稿' }).click()
  await page.getByLabel('目标 / Prompt').fill(prompt)
  await page.getByRole('button', { name: '生成草稿' }).click()

  const blockedRow = page.getByRole('row').filter({ hasText: title })
  await expect(blockedRow).toBeVisible()
  await expect(blockedRow.getByText(/Blocked: public post contains unsafe financial promise/)).toBeVisible()
  await expect(blockedRow.getByRole('button', { name: '批准' })).toHaveCount(0)
  await expect(blockedRow.getByRole('button', { name: '发布到 X' })).toHaveCount(0)
})

test('Social Publishing real Codex draft generation succeeds', async ({ page }, testInfo: TestInfo) => {
  test.setTimeout(120_000)
  const consoleErrors: string[] = []
  const networkEvents: string[] = []
  const details: string[] = []
  const bugfixRequired: string[] = []
  const screenshotPath = path.join(socialDogfoodDir(), 'screenshots', 'generated-draft.png')
  const beforeMaxId = querySocialDraftMaxId()
  details.push(`Starting social_post_drafts max id: ${beforeMaxId}`)

  page.on('pageerror', (error) => consoleErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })
  page.on('response', async (response) => {
    const url = response.url()
    if (!url.includes('/api/social/posts/generate-draft')) return
    const excerpt = await response.text().catch(() => '')
    networkEvents.push(`${response.status()} ${url} ${excerpt.slice(0, 500)}`)
  })

  try {
    await page.goto('/publishing', { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: '官方账号内容发布' })).toBeVisible()
    await page.getByRole('button', { name: '让 Agent 写草稿' }).click()
    await page.getByLabel('目标 / Prompt').fill(realCodexSocialPrompt)
    await page.getByRole('button', { name: '生成草稿' }).click()

    const firstRow = page.locator('tbody tr').first()
    await expect(firstRow, 'real Codex generation should create a new visible draft row').toBeVisible({ timeout: 90_000 })
    await expect(firstRow.getByRole('button', { name: '发布到 X' }), 'real E2E validates publish readiness but must not click publish').toBeVisible({ timeout: 90_000 })

    const postsResponse = await page.request.get('/api/social/posts')
    expect(postsResponse.ok()).toBeTruthy()
    const posts = await postsResponse.json()
    expect(Array.isArray(posts)).toBeTruthy()
    const newest = posts[0]
    const dbNewest = queryLatestSocialDraftAfter(beforeMaxId)
    expect(dbNewest.id, 'a new social_post_drafts row should be inserted').toBeGreaterThan(beforeMaxId)
    expect(newest.title?.trim()).toBeTruthy()
    expect(newest.body_text?.trim()).toBeTruthy()
    expect(dbNewest.title?.trim()).toBeTruthy()
    expect(dbNewest.body_text?.trim()).toBeTruthy()
    expect(newest.body_text).not.toBe(realCodexSocialPrompt)
    expect(dbNewest.body_text).not.toBe(realCodexSocialPrompt)
    expect(newest.body_text.length).toBeLessThanOrEqual(280)
    expect(dbNewest.body_text!.length).toBeLessThanOrEqual(280)
    expect(newest.policy_check?.status).toBe('passed')
    expect(dbNewest.policy_check?.status).toBe('passed')
    expect(newest.status).toBe('approved')
    expect(dbNewest.status).toBe('approved')
    for (const forbidden of ['/Users/', '读取', '给出文档', '如何发布', '生成第一篇']) {
      expect(newest.body_text).not.toContain(forbidden)
      expect(newest.title).not.toContain(forbidden)
      expect(dbNewest.body_text).not.toContain(forbidden)
      expect(dbNewest.title).not.toContain(forbidden)
    }
    expect(JSON.stringify(newest).toLowerCase()).not.toContain('acceptance matrix')
    expect(JSON.stringify(newest).toLowerCase()).not.toContain('required_commands')

    await page.screenshot({ path: screenshotPath, fullPage: true })
    details.push(`Generated title: ${newest.title}`)
    details.push(`Generated body_text: ${newest.body_text}`)
    details.push(`Post id: ${newest.id}`)
    details.push(`DB inserted post id: ${dbNewest.id}`)
    writeSocialDogfoodReport({ status: 'passed', screenshotPath, consoleErrors, networkEvents, details, bugfixRequired })
    await testInfo.attach('social-publishing-real-generation-report', {
      path: path.join(socialDogfoodDir(), 'report.md'),
      contentType: 'text/markdown',
    })
  } catch (error) {
    fs.mkdirSync(path.dirname(screenshotPath), { recursive: true })
    await page.screenshot({ path: screenshotPath, fullPage: true }).catch(() => undefined)
    const message = error instanceof Error ? error.message : String(error)
    const backendLogExcerpt = latestSocialBackendLogExcerpt()
    details.push(message)
    details.push(`Backend log excerpt:\n${backendLogExcerpt}`)
    bugfixRequired.push('Real Social Publishing generation failed from the browser flow.')
    bugfixRequired.push(message)
    await recordSocialDogfoodBug(page, message, backendLogExcerpt)
    writeSocialDogfoodReport({ status: 'failed', screenshotPath, consoleErrors, networkEvents, details, bugfixRequired })
    throw error
  }
})
