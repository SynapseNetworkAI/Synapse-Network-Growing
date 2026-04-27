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
  source_type: string
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

async function postJsonFromPage(page: Page, url: string, data: Record<string, unknown>) {
  return page.evaluate(async ({ endpoint, payload }) => {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    return {
      ok: response.ok,
      status: response.status,
      body: await response.json(),
    }
  }, { endpoint: url, payload: data })
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
  const now = () => new Date().toISOString()
  const trends = [
    {
      id: 8101,
      source_platform: 'x',
      source_url: 'https://x.com/OpenAI/status/100',
      author_handle: 'OpenAI',
      topic: 'AI agents need payment rails',
      summary: 'Agent builders increasingly need budgeted tool/API access. Use as content inspiration, not as sourced claim.',
      relevance_score: 0.87,
      status: 'active',
      collected_at: now(),
      updated_at: now(),
    },
  ]
  const watchlist = [
    {
      id: 8201,
      platform: 'x',
      handle: 'OpenAI',
      display_name: 'OpenAI',
      category: 'ai_platform',
      rationale: 'AI platform updates shape agent-builder narratives.',
      status: 'active',
      last_checked_at: now(),
      latest_summary: 'Platform updates and agent ecosystem signals.',
      updated_at: now(),
    },
    {
      id: 8202,
      platform: 'x',
      handle: 'NVIDIAAI',
      display_name: 'NVIDIA AI',
      category: 'ai_infrastructure',
      rationale: 'Infrastructure signals are useful for AI agent builders.',
      status: 'active',
      last_checked_at: now(),
      latest_summary: 'AI infrastructure and deployment narratives.',
      updated_at: now(),
    },
    {
      id: 8203,
      platform: 'x',
      handle: 'karpathy',
      display_name: 'Andrej Karpathy',
      category: 'ai_builder',
      rationale: 'High-signal technical commentary for agent workflows.',
      status: 'active',
      last_checked_at: now(),
      latest_summary: 'Developer education and AI product thinking.',
      updated_at: now(),
    },
  ]
  const replies: unknown[] = []
  const reposts: Array<Record<string, unknown>> = []
  const metrics = [
    {
      id: 8301,
      post_id: 7100,
      external_post_id: '1800000000000000001',
      impressions: 1800,
      likes: 42,
      replies: 4,
      reposts: 7,
      follows: 3,
      link_clicks: 29,
      summary: 'Developer education posts with concrete shipping proof performed best.',
      observed_at: now(),
    },
  ]
  let nextPostId = 7001
  let nextMediaId = 9001
  const account = {
    id: 1,
    platform: 'x',
    handle: 'SynapseNetworkA',
    display_name: 'Synapse Network',
    secret_ref: 'gcp://secret-manager/x-official-oauth2-user-token',
    status: 'active',
    auth_status: 'authorized',
    auth_message: 'Mock X OAuth is connected for E2E.',
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

    if (url.pathname === '/api/social/ops/overview' && method === 'GET') {
      await json(route, {
        active_goal_count: 1,
        draft_queue_count: posts.filter((post) => post.status !== 'published' && post.status !== 'rejected').length,
        needs_review_count: posts.filter((post) => post.status === 'needs_review').length,
        trend_count: trends.length,
        reply_needs_review_count: replies.length,
        repost_candidate_count: reposts.length,
        published_count: posts.filter((post) => post.status === 'published').length,
        human_gate_required: true,
        safety_summary: 'All public X actions require operator confirmation.',
      })
      return
    }

    if (url.pathname === '/api/social/campaign-goals' && method === 'GET') {
      await json(route, [
        {
          id: 8401,
          platform: 'x',
          title: 'Build Synapse Network brand trust',
          objective: 'Explain why AI agents need payment rails and governed API access.',
          status: 'active',
          cadence: 'daily',
          content_pillars: ['agent economy', 'developer use cases', 'shipping proof'],
          success_metrics: ['profile visits', 'developer replies', 'staging clicks'],
          created_by: 'operator',
          created_at: now(),
          updated_at: now(),
        },
      ])
      return
    }

    if (url.pathname === '/api/social/trends' && method === 'GET') {
      await json(route, trends)
      return
    }

    if (url.pathname === '/api/social/watchlist' && method === 'GET') {
      await json(route, watchlist)
      return
    }

    if (url.pathname === '/api/social/replies' && method === 'GET') {
      await json(route, replies)
      return
    }

    if (url.pathname === '/api/social/repost-candidates' && method === 'GET') {
      await json(route, reposts)
      return
    }

    if (url.pathname === '/api/social/post-metrics' && method === 'GET') {
      await json(route, metrics)
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
        source_type: payload.raw_agent_output?.source_type as string || 'manual_prompt',
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
        source_type: 'manual_prompt',
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

    const repostPublishMatch = url.pathname.match(/^\/api\/social\/repost-candidates\/(\d+)\/publish-x$/)
    if (repostPublishMatch && method === 'POST') {
      const candidate = reposts.find((row) => row.id === Number(repostPublishMatch[1]))
      if (!candidate) {
        await json(route, { detail: 'repost_candidate_not_found' }, 404)
        return
      }
      candidate.status = 'published'
      candidate.updated_at = now()
      await json(route, candidate)
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

  return { account, posts, trends, watchlist, replies, reposts, metrics, now }
}

type MockSocialApiState = Awaited<ReturnType<typeof installMockSocialApi>>

async function installMockXSocialRecurringApi(page: Page, social: MockSocialApiState) {
  let nextRunId = 9101
  let dailyDraftId: number | null = null
  const runs: Array<Record<string, unknown>> = []

  const workflowDefinitions = [
    {
      id: 101,
      workflow_key: 'x_social_daily_content_planner',
      display_name: 'X Social Daily Content Planner',
      description: 'Hourly tick that creates at most one X daily draft per operator local day.',
      status: 'active',
      trigger_type: 'scheduled',
      owner_role: 'growth_lead',
      schedule: { cadence: 'hourly', interval_hours: 1, operator_timezone: 'Asia/Kuala_Lumpur' },
      input_query: { platform: 'x', idempotency: 'daily_local_date' },
      output_action: { kind: 'create_social_draft', human_gate_required: true },
      escalation_rule: { on_failure: 'diagnostic_only' },
      validation_signal: { success_metric: 'one_needs_review_draft_per_day' },
      is_builtin: true,
      last_run_at: null,
      next_run_at: social.now(),
      is_due: true,
      health_status: 'healthy',
      last_result: {},
      created_at: social.now(),
      updated_at: social.now(),
    },
    {
      id: 102,
      workflow_key: 'x_social_trend_radar_sweep',
      display_name: 'X Social Trend Radar Sweep',
      description: 'Read-only high-signal trend collection for AI agent and payment narratives.',
      status: 'active',
      trigger_type: 'scheduled',
      owner_role: 'growth_lead',
      schedule: { cadence: 'interval', interval_minutes: 240 },
      input_query: { platform: 'x', quality_filter: true },
      output_action: { kind: 'retain_trend_items' },
      escalation_rule: { on_failure: 'diagnostic_only' },
      validation_signal: { success_metric: 'high_quality_trends_retained' },
      is_builtin: true,
      last_run_at: null,
      next_run_at: social.now(),
      is_due: true,
      health_status: 'healthy',
      last_result: {},
      created_at: social.now(),
      updated_at: social.now(),
    },
    {
      id: 103,
      workflow_key: 'x_social_repost_candidate_sweep',
      display_name: 'X Social Repost Candidate Sweep',
      description: 'Human-gated quote repost candidate generation from trends and watchlist highlights.',
      status: 'active',
      trigger_type: 'scheduled',
      owner_role: 'growth_lead',
      schedule: { cadence: 'interval', interval_minutes: 720 },
      input_query: { platform: 'x', human_gate_required: true },
      output_action: { kind: 'create_repost_candidates' },
      escalation_rule: { on_failure: 'diagnostic_only' },
      validation_signal: { success_metric: 'no_external_repost_api_called' },
      is_builtin: true,
      last_run_at: null,
      next_run_at: social.now(),
      is_due: true,
      health_status: 'healthy',
      last_result: {},
      created_at: social.now(),
      updated_at: social.now(),
    },
  ]

  function recordRun(workflowKey: string, dryRun: boolean, result: Record<string, unknown>) {
    const timestamp = social.now()
    const run = {
      id: nextRunId++,
      workflow_key: workflowKey,
      status: 'succeeded',
      triggered_by: 'operator',
      dry_run: dryRun,
      params: { dry_run: dryRun, auto_start: false, auto_dispatch_acceptance: false },
      result,
      error_excerpt: null,
      started_at: timestamp,
      completed_at: timestamp,
      duration_ms: 24,
    }
    runs.unshift(run)
    const workflow = workflowDefinitions.find((item) => item.workflow_key === workflowKey)
    if (workflow) {
      workflow.last_run_at = timestamp
      workflow.last_result = result
      workflow.is_due = false
      workflow.next_run_at = social.now()
    }
    return run
  }

  await page.route('**/api/recurring-workflows**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const method = request.method()

    if (url.pathname === '/api/recurring-workflows' && method === 'GET') {
      await json(route, workflowDefinitions)
      return
    }

    if (url.pathname === '/api/recurring-workflows/health' && method === 'GET') {
      await json(route, {
        bug_log_scheduler: { enabled: true, running: true },
        goal_planner_scheduler: { enabled: true, running: true },
        notification_dispatcher: { enabled: true, running: true },
        recurring_registry: { enabled: true, workflow_count: workflowDefinitions.length },
        x_social_scheduler: {
          enabled: true,
          running: true,
          workflow_keys: workflowDefinitions.map((workflow) => workflow.workflow_key),
          poll_seconds: 300,
        },
      })
      return
    }

    const runsMatch = url.pathname.match(/^\/api\/recurring-workflows\/([^/]+)\/runs$/)
    if (runsMatch && method === 'GET') {
      await json(route, runs.filter((run) => run.workflow_key === runsMatch[1]))
      return
    }

    const runMatch = url.pathname.match(/^\/api\/recurring-workflows\/([^/]+)\/run$/)
    if (!runMatch || method !== 'POST') {
      await json(route, { detail: 'not_found' }, 404)
      return
    }

    const workflowKey = runMatch[1]
    const payload = request.postDataJSON() as { dry_run?: boolean } | null
    const dryRun = Boolean(payload?.dry_run)
    let result: Record<string, unknown>

    if (workflowKey === 'x_social_trend_radar_sweep') {
      result = {
        status: 'succeeded',
        workflow_key: workflowKey,
        platform: 'x',
        retained_count: social.trends.length,
        filtered_count: 1,
        quality_filter: { engagement_threshold: 25, watchlist_weighted: true },
        external_actions: [],
      }
    } else if (workflowKey === 'x_social_repost_candidate_sweep') {
      if (!dryRun && social.reposts.length === 0) {
        social.reposts.push({
          id: 8501,
          platform: 'x',
          source_url: 'https://x.com/OpenAI/status/100',
          author_handle: 'OpenAI',
          source_text: 'AI agents increasingly need reliable tool access and payment primitives.',
          suggested_quote: 'This is exactly why agent-native payment rails matter: builders need budgeted API access without manual billing glue.',
          relevance_score: 0.91,
          status: 'needs_review',
          updated_at: social.now(),
        })
      }
      result = {
        status: 'succeeded',
        workflow_key: workflowKey,
        platform: 'x',
        candidate_count: social.reposts.length,
        created_candidate_ids: social.reposts.map((candidate) => candidate.id),
        human_gate_required: true,
        external_actions: [],
      }
    } else if (workflowKey === 'x_social_daily_content_planner') {
      if (dailyDraftId !== null) {
        result = {
          status: 'succeeded',
          workflow_key: workflowKey,
          platform: 'x',
          already_created: true,
          existing_post_id: dailyDraftId,
          planner_local_date: '2026-04-27',
        }
      } else {
        dailyDraftId = 8601
        if (!dryRun) {
          const bodyText = 'AI agents are becoming real software operators. Synapse Network gives them a settlement layer: budgeted API access, per-call payments, and human-governed trust for the agent economy. #AIAgents #AgentEconomy #APIs #Payments'
          social.posts.unshift({
            id: dailyDraftId,
            platform: 'x',
            account_id: social.account.id,
            source_type: 'daily_planner',
            account_handle: social.account.handle,
            account_display_name: social.account.display_name,
            title: 'Daily Synapse Network X draft',
            body_text: bodyText,
            status: 'needs_review',
            generated_by: 'x_social_daily_content_planner',
            reviewed_by: null,
            review_note: null,
            target_audience: null,
            cta: null,
            agent_rationale: null,
            policy_check: socialPolicyCheck(bodyText),
            raw_agent_output: {
              planner_local_date: '2026-04-27',
              planner_run_key: 'x_daily:1:2026-04-27',
              trend_item_ids: social.trends.map((trend) => trend.id),
              watchlist_handles: social.watchlist.map((item) => item.handle),
              recent_metric_post_ids: social.metrics.map((metric) => metric.external_post_id),
              variable_factor: 'OpenAI trend about agent tool access',
              metrics_available: true,
            },
            published_at: null,
            external_post_id: null,
            external_url: null,
            failure_summary: null,
            media_assets: [],
            events: [],
            created_at: social.now(),
            updated_at: social.now(),
          })
        }
        result = {
          status: 'succeeded',
          workflow_key: workflowKey,
          platform: 'x',
          already_created: false,
          created_post_id: dailyDraftId,
          planner_local_date: '2026-04-27',
          human_gate_required: true,
          source_type: 'daily_planner',
        }
      }
    } else {
      await json(route, { detail: 'unknown_workflow' }, 404)
      return
    }

    const run = recordRun(workflowKey, dryRun, result)
    await json(route, {
      workflow_key: workflowKey,
      status: 'succeeded',
      run_started_at: run.started_at,
      run_id: run.id,
      result,
    })
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

test('X Social Ops recurring workflows create one daily review draft and human-gated candidates', async ({ page }, testInfo) => {
  const social = await installMockSocialApi(page)
  await installMockXSocialRecurringApi(page, social)

  await page.goto('/schedules', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '定时任务' }).first()).toBeVisible()
  await expect(page.getByText('X Social Daily Content Planner').first()).toBeVisible()
  await expect(page.getByText('x_social_daily_content_planner').first()).toBeVisible()
  await expect(page.getByText('X Social Trend Radar Sweep').first()).toBeVisible()
  await expect(page.getByText('X Social Repost Candidate Sweep').first()).toBeVisible()

  const trendResult = await postJsonFromPage(page, '/api/recurring-workflows/x_social_trend_radar_sweep/run', {
    dry_run: false,
    auto_start: false,
    auto_dispatch_acceptance: false,
  })
  expect(trendResult.ok).toBeTruthy()
  expect(trendResult.body.result.retained_count).toBe(1)
  expect(trendResult.body.result.external_actions).toEqual([])

  const repostResult = await postJsonFromPage(page, '/api/recurring-workflows/x_social_repost_candidate_sweep/run', {
    dry_run: false,
    auto_start: false,
    auto_dispatch_acceptance: false,
  })
  expect(repostResult.ok).toBeTruthy()
  expect(repostResult.body.result.candidate_count).toBe(1)
  expect(repostResult.body.result.human_gate_required).toBe(true)

  const dailyResult = await postJsonFromPage(page, '/api/recurring-workflows/x_social_daily_content_planner/run', {
    dry_run: false,
    auto_start: false,
    auto_dispatch_acceptance: false,
  })
  expect(dailyResult.ok).toBeTruthy()
  expect(dailyResult.body.result.already_created).toBe(false)
  expect(dailyResult.body.result.human_gate_required).toBe(true)
  expect(dailyResult.body.result.source_type).toBe('daily_planner')

  const secondDailyResult = await postJsonFromPage(page, '/api/recurring-workflows/x_social_daily_content_planner/run', {
    dry_run: false,
    auto_start: false,
    auto_dispatch_acceptance: false,
  })
  expect(secondDailyResult.ok).toBeTruthy()
  expect(secondDailyResult.body.result.already_created).toBe(true)
  expect(secondDailyResult.body.result.existing_post_id).toBe(dailyResult.body.result.created_post_id)

  await page.goto('/publishing', { waitUntil: 'domcontentloaded' })
  await page.getByRole('button', { name: '今日队列' }).click()
  const plannerRow = page.getByRole('row').filter({ hasText: 'Daily Synapse Network X draft' })
  await expect(plannerRow).toBeVisible()
  await expect(plannerRow.getByText('待审核')).toBeVisible()
  await expect(plannerRow.getByText('x_social_daily_content_planner')).toBeVisible()
  await expect(plannerRow.getByText('#AIAgents')).toBeVisible()
  await expect(plannerRow.getByRole('button', { name: '发布到 X' })).toHaveCount(0)
  await expect(page.getByRole('row').filter({ hasText: 'Daily Synapse Network X draft' })).toHaveCount(1)

  await page.getByRole('button', { name: '趋势雷达' }).click()
  await expect(page.getByText('AI agents need payment rails', { exact: true })).toBeVisible()
  await expect(page.getByText('@OpenAI').first()).toBeVisible()
  await expect(page.getByText('@NVIDIAAI').first()).toBeVisible()
  await expect(page.getByText('@karpathy').first()).toBeVisible()

  await page.getByRole('button', { name: '转发候选' }).click()
  await expect(page.getByText('@OpenAI').first()).toBeVisible()
  await expect(page.getByText('agent-native payment rails matter')).toBeVisible()
  await expect(page.getByText('第 1 / 1 页 · 共 1 条候选')).toBeVisible()
  await page.getByRole('button', { name: '详情' }).click()
  await expect(page.getByRole('dialog', { name: '转发 / 引用候选 #8501' })).toBeVisible()
  await page.getByRole('button', { name: '引用发布到 X' }).click()
  await expect(page.getByText(/公开发布 Agent 拟写的引用文案/)).toBeVisible()
  await expect(page.getByText('确认引用发布到 X')).toBeVisible()
  await page.getByRole('button', { name: '引用发布到 X' }).last().click()
  await expect(page.getByText('已发布')).toBeVisible()

  await page.screenshot({
    path: testInfo.outputPath('x-social-ops-daily-planner-e2e.png'),
    fullPage: true,
  })
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
    expect(newest.body_text.length).toBeGreaterThan(40)
    expect(dbNewest.body_text!.length).toBeGreaterThan(40)
    expect(newest.policy_check?.character_count).toBe(newest.body_text.length)
    expect(dbNewest.policy_check?.character_count).toBe(dbNewest.body_text!.length)
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
