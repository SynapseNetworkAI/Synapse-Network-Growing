import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

type ReplySeedEvidence = {
  asset_id: number
  reply_ids: number[]
  source_post_ids: string[]
}

type ReplyDbEvidence = {
  asset_count: number
  reply_count: number
  published_manual_count: number
  statuses: string[]
}

const postgresUrl = process.env.OPS_E2E_DATABASE_URL || ''
const taskTitle = 'X Week 1 Reply Block Day 5'

function repoRoot() {
  return path.resolve(process.cwd(), '..')
}

function pythonBin() {
  const configured = process.env.PYTHON_BIN
  if (configured && fs.existsSync(configured)) return configured
  const local = '/Users/cliff/workspace/agent/.venv/bin/python'
  if (fs.existsSync(local)) return local
  return 'python3'
}

function requirePostgresE2eUrl() {
  if (!postgresUrl.startsWith('postgresql')) {
    throw new Error('OPS_E2E_DATABASE_URL must point to a Postgres database for X reply task E2E.')
  }
}

function runDbScript<T>(script: string, args: string[] = []): T {
  requirePostgresE2eUrl()
  const output = execFileSync(pythonBin(), ['-c', script, ...args], {
    cwd: repoRoot(),
    encoding: 'utf-8',
    env: { ...process.env, OPS_E2E_DATABASE_URL: postgresUrl },
  }).trim()
  return JSON.parse(output) as T
}

function seedXReplyTask(): ReplySeedEvidence {
  return runDbScript<ReplySeedEvidence>(
    `
import datetime as dt
import json
import os
import psycopg
import sys

title = sys.argv[1]
dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
now = dt.datetime(2026, 5, 23, 10, 0, 0)
source_posts = [
    ("9001", "OpenAI", "https://x.com/OpenAI/status/9001", "Agent workflows need safer ways to call external APIs."),
    ("9002", "LangChainAI", "https://x.com/LangChainAI/status/9002", "Teams are turning agent workflows into production operating systems."),
    ("9003", "vercel", "https://x.com/vercel/status/9003", "Shipping AI products means more observability and tighter release loops."),
    ("9004", "AnthropicAI", "https://x.com/AnthropicAI/status/9004", "Reliable agents need clear tool boundaries and audit trails."),
    ("9005", "GitHub", "https://x.com/github/status/9005", "Agentic coding works best when review evidence stays attached to the task."),
]

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("delete from social_distribution_events")
        cur.execute("delete from social_distribution_documents")
        cur.execute("delete from social_distribution_tasks")
        cur.execute("delete from social_content_assets")
        cur.execute("delete from social_reply_items")
        cur.execute("delete from social_repost_candidates")
        cur.execute(
            """
            insert into social_content_assets (
                asset_type, source_type, title, body, summary, policy_check_json,
                agent_metadata_json, status, created_by, created_at, updated_at
            ) values (%s, 'manual_task', %s, %s, %s, '{}', %s, 'ready', 'operator', %s, %s)
            returning id
            """,
            (
                "reply",
                title,
                "Paste 5 real X URLs or watchlist posts for today's reply block.",
                "Generate five value-add X reply candidates for production review.",
                json.dumps({
                    "post_intent": "engagement_reply",
                    "target_platforms": ["x"],
                    "planned_publish_at": "2026-05-23T10:00:00+00:00",
                }, sort_keys=True),
                now,
                now,
            ),
        )
        asset_id = cur.fetchone()[0]
        cur.execute(
            """
            insert into social_distribution_documents (
                asset_id, task_id, document_kind, platform, channel_key, title,
                body_markdown, status, version, metadata_json, created_at, updated_at
            ) values (%s, null, 'source_plan', null, null, 'X reply block plan', %s, 'generated', 1, '{}', %s, %s)
            """,
            (
                asset_id,
                "## Core Points\\n- Use 5 real X source posts.\\n- Generate value-add replies only.\\n- No browser automation publish; manual publish required without X approval ref.",
                now,
                now,
            ),
        )
        reply_ids = []
        source_ids = []
        for index, (post_id, author, url, source_text) in enumerate(source_posts, start=1):
            metadata = {
                "generated_by": "x_reply_block_e2e",
                "model": "seeded-e2e",
                "agent_quality_review": {
                    "status": "passed",
                    "checks": ["length", "specificity", "no_engagement_bait", "no_link_spam"],
                },
                "x_reply_compliance": {
                    "approval_ref_configured": False,
                    "publish_mode": "agent_approved_needs_manual_publish",
                },
            }
            cur.execute(
                """
                insert into social_reply_items (
                    platform, external_reply_id, source_candidate_id, source_post_id,
                    source_author_handle, source_text, author_handle, incoming_text,
                    intent, suggested_reply, generation_reason, risk_level, status,
                    source_url, reviewed_by, metadata_json, created_at, updated_at
                ) values (
                    'x', %s, %s, %s, %s, %s, 'SynapseNetworkAI', %s,
                    'engagement_reply', %s, 'Specific, useful, and non-promotional.',
                    'normal', 'agent_approved_needs_manual_publish', %s, 'agent', %s, %s, %s
                )
                returning id
                """,
                (
                    f"target:{post_id}",
                    7000 + index,
                    post_id,
                    author,
                    source_text,
                    source_text,
                    f"One concrete operating-system angle: bind agent actions to scopes, budgets, evidence, and rollback notes before they touch production workflows. ({index}/5)",
                    url,
                    json.dumps(metadata, sort_keys=True),
                    now + dt.timedelta(seconds=index),
                    now + dt.timedelta(seconds=index),
                ),
            )
            reply_ids.append(cur.fetchone()[0])
            source_ids.append(post_id)
        reply_block = {
            "target_count": 5,
            "reply_ids": reply_ids,
            "failed_reply_ids": [],
            "source_candidate_ids": [7001, 7002, 7003, 7004, 7005],
            "processed_source_count": 5,
            "auto_publish": False,
            "approval_ref_configured": False,
            "publish_mode": "agent_approved_needs_manual_publish",
        }
        cur.execute(
            "update social_content_assets set agent_metadata_json = %s, updated_at = %s where id = %s",
            (
                json.dumps({
                    "post_intent": "engagement_reply",
                    "target_platforms": ["x"],
                    "planned_publish_at": "2026-05-23T10:00:00+00:00",
                    "reply_block": reply_block,
                }, sort_keys=True),
                now + dt.timedelta(minutes=1),
                asset_id,
            ),
        )
        cur.execute(
            """
            insert into social_distribution_events (asset_id, task_id, event_type, actor, summary, payload_json, created_at)
            values (%s, null, 'x_reply_block_candidates_generated', 'agent', 'Seeded 5 E2E reply candidates.', %s, %s)
            """,
            (asset_id, json.dumps(reply_block, sort_keys=True), now + dt.timedelta(minutes=1)),
        )
    conn.commit()

print(json.dumps({"asset_id": asset_id, "reply_ids": reply_ids, "source_post_ids": source_ids}))
`,
    [taskTitle],
  )
}

function queryReplyEvidence(): ReplyDbEvidence {
  return runDbScript<ReplyDbEvidence>(
    `
import json
import os
import psycopg
import sys

title = sys.argv[1]
dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("select count(*) from social_content_assets where title = %s", (title,))
        asset_count = cur.fetchone()[0]
        cur.execute(
            """
            select r.status
              from social_reply_items r
              join social_content_assets a
                on a.agent_metadata_json::jsonb -> 'reply_block' -> 'reply_ids' @> to_jsonb(r.id)
             where a.title = %s
             order by r.id asc
            """,
            (title,),
        )
        statuses = [row[0] for row in cur.fetchall()]
print(json.dumps({
    "asset_count": asset_count,
    "reply_count": len(statuses),
    "published_manual_count": sum(1 for status in statuses if status == "published_manual"),
    "statuses": statuses,
}))
`,
    [taskTitle],
  )
}

test('X Week 1 Reply Block Day 5 detail shows reply workflow and manual publish transition', async ({ page }, testInfo: TestInfo) => {
  const seed = seedXReplyTask()
  testInfo.attach('seed-evidence', {
    body: JSON.stringify(seed, null, 2),
    contentType: 'application/json',
  })

  await page.goto('/publishing?tab=tasks', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: '多渠道分发中心' })).toBeVisible()
  await expect(page.getByRole('button', { name: '全部' })).toBeVisible()
  await expect(page.getByRole('button', { name: '内容发布' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'X 回复', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'X 回复', exact: true }).click()
  const readyColumn = page.getByTestId('distribution-board-column-ready_to_publish')
  await expect(readyColumn.getByText(taskTitle)).toBeVisible()
  await expect(readyColumn.getByText('source posts')).toBeVisible()
  await expect(readyColumn.getByText('candidates')).toBeVisible()

  await page.screenshot({
    path: testInfo.outputPath('x-reply-task-board-ready.png'),
    fullPage: true,
  })

  await readyColumn.getByText(taskTitle).click()
  await expect(page.getByRole('heading', { name: taskTitle })).toBeVisible()
  await expect(page.getByText('Compliance Gate')).toBeVisible()
  await expect(page.getByText('manual publish required', { exact: true })).toBeVisible()
  await expect(page.getByText('Source Posts', { exact: true })).toBeVisible()
  await expect(page.getByText('Reply Candidates', { exact: true })).toBeVisible()
  for (const sourcePostId of seed.source_post_ids) {
    await expect(page.getByText(sourcePostId).first()).toBeVisible()
  }
  await expect(page.getByText('Canonical Article')).toHaveCount(0)
  await expect(page.getByText('Platform Docs')).toHaveCount(0)
  await expect(page.getByText('Channel Selection')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '通过 X API 发布' })).toHaveCount(0)

  await page.screenshot({
    path: testInfo.outputPath('x-reply-task-detail-candidates.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: '标记已手动发布' }).first().click()
  await expect(page.getByText('published_manual').first()).toBeVisible()
  const evidenceAfterManualPublish = queryReplyEvidence()
  expect(evidenceAfterManualPublish.asset_count).toBe(1)
  expect(evidenceAfterManualPublish.reply_count).toBe(5)
  expect(evidenceAfterManualPublish.published_manual_count).toBe(1)
  testInfo.attach('db-evidence-after-manual-publish', {
    body: JSON.stringify(evidenceAfterManualPublish, null, 2),
    contentType: 'application/json',
  })

  await page.getByRole('button', { name: '关闭', exact: true }).click()
  const liveColumn = page.getByTestId('distribution-board-column-live')
  await expect(liveColumn.getByText(taskTitle)).toBeVisible()
  await expect(liveColumn.getByText('1').first()).toBeVisible()

  await page.screenshot({
    path: testInfo.outputPath('x-reply-task-board-live.png'),
    fullPage: true,
  })
})
