import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

type SdkPackageRelease = {
  id: number
  package_version: string
  sdk_language: string
  package_name: string
  registry: string
}

type DbEvidence = {
  count: number
  ordered_versions: string[]
  event_count_for_anchor: number
}

const postgresUrl = process.env.OPS_E2E_DATABASE_URL || ''

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
    throw new Error('OPS_E2E_DATABASE_URL must point to a Postgres database for SDK release history E2E.')
  }
}

function runDbScript(script: string, args: string[] = []) {
  requirePostgresE2eUrl()
  return execFileSync(pythonBin(), ['-c', script, ...args], {
    cwd: repoRoot(),
    encoding: 'utf-8',
    env: { ...process.env, OPS_E2E_DATABASE_URL: postgresUrl },
  }).trim()
}

function clearSdkReleaseRows() {
  runDbScript(`
import os, psycopg

dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("delete from sdk_package_release_events")
        cur.execute("delete from sdk_package_releases")
    conn.commit()
`)
}

function shapeReleaseHistoryRows(rows: SdkPackageRelease[]) {
  runDbScript(
    `
import datetime as dt
import json
import os
import psycopg
import sys

rows = json.loads(sys.argv[1])
dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
base = dt.datetime(2026, 5, 23, 2, 0, 0)

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        for row in rows:
            patch = int(str(row["package_version"]).split(".")[-1])
            status = "published" if patch in {3, 5, 7, 9, 11} else "planned"
            failure = None
            channel = "preview"
            published_at = None
            if patch == 12:
                status = "failed"
                failure = "registry rejected scoped version"
                channel = "beta"
            elif patch == 10:
                channel = "next"
            elif status == "published":
                channel = "latest"
                published_at = base + dt.timedelta(minutes=patch, seconds=30)
            workflow = f"https://github.com/SynapseNetworkAI/Synapse-Network-Sdk/actions/runs/{9000 + patch}"
            package_url = f"https://pypi.org/project/synapse-client/{row['package_version']}/"
            cur.execute(
                """
                update sdk_package_releases
                   set status = %s,
                       channel = %s,
                       package_url = %s,
                       workflow_run_url = %s,
                       failure_summary = %s,
                       published_at = %s,
                       updated_at = %s
                 where id = %s
                """,
                (
                    status,
                    channel,
                    package_url,
                    workflow,
                    failure,
                    published_at,
                    base + dt.timedelta(minutes=patch),
                    row["id"],
                ),
            )
    conn.commit()
`,
    [JSON.stringify(rows)],
  )
}

function queryDbEvidence(anchorId: number): DbEvidence {
  const raw = runDbScript(
    `
import json
import os
import psycopg
import sys

anchor_id = int(sys.argv[1])
dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")

with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(*), array_agg(package_version order by updated_at desc, id desc)
              from sdk_package_releases
             where sdk_language = 'python'
               and registry = 'pypi'
               and package_name = 'synapse-client'
            """
        )
        count, ordered_versions = cur.fetchone()
        cur.execute(
            "select count(*) from sdk_package_release_events where sdk_package_release_id = %s",
            (anchor_id,),
        )
        event_count = cur.fetchone()[0]

print(json.dumps({
    "count": count,
    "ordered_versions": ordered_versions or [],
    "event_count_for_anchor": event_count,
}))
`,
    [String(anchorId)],
  )
  return JSON.parse(raw) as DbEvidence
}

function historyRow(history: Locator, version: string) {
  return history.getByRole('button', { name: new RegExp(`^${version.replaceAll('.', '\\.')}\\b`) })
}

async function initializePythonRelease(page: Page, packageVersion: string) {
  const response = await page.request.post('/api/releases/sdk-packages/initialize-train', {
    data: {
      release_train_version: packageVersion,
      channel: 'preview',
      packages: ['python'],
      release_notes: `SDK ${packageVersion} E2E release history seed.`,
    },
  })
  expect(response.ok()).toBeTruthy()
  const payload = (await response.json()) as SdkPackageRelease[]
  return payload[0]
}

async function seedReleaseHistory(page: Page) {
  clearSdkReleaseRows()
  const rows: SdkPackageRelease[] = []
  for (let patch = 1; patch <= 12; patch += 1) {
    rows.push(await initializePythonRelease(page, `1.0.${patch}`))
  }
  shapeReleaseHistoryRows(rows)
  return {
    rows,
    anchor: rows.find((row) => row.package_version === '1.0.7') ?? rows[0],
  }
}

async function recordBug(page: Page, error: unknown, testInfo: TestInfo, evidence: Record<string, unknown>) {
  let screenshotPath: string | null = null
  try {
    screenshotPath = testInfo.outputPath('sdk-package-release-history-failure.png')
    await page.screenshot({ path: screenshotPath, fullPage: true })
  } catch {
    screenshotPath = null
  }

  await page.request.post('/api/bugs/intake', {
    data: {
      source_key: 'manual_bug_report',
      project_key: 'synapse-network-growing',
      project_root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing-agent-b',
      title: `SDK package release history E2E: ${error instanceof Error ? error.message.slice(0, 120) : 'unknown failure'}`,
      summary: 'SDK package release result history E2E, screenshot validation, or DB evidence verification failed.',
      severity: 'high',
      source_ref: 'e2e:sdk-package-release-history',
      environment: 'local-postgres-e2e',
      log_excerpt: error instanceof Error ? error.stack || error.message : String(error),
      metadata: {
        component: 'sdk_package_release_history',
        test_name: testInfo.title,
        screenshot_path: screenshotPath,
        ...evidence,
      },
    },
  }).catch(() => undefined)
}

test('SDK package detail shows searchable paginated result history with DB evidence', async ({ page }, testInfo) => {
  const evidence: Record<string, unknown> = {}
  try {
    const { anchor } = await seedReleaseHistory(page)
    evidence.anchor_id = anchor.id

    const apiHistory = await page.request.get(`/api/releases/sdk-packages/${anchor.id}/history?limit=10&offset=0`)
    expect(apiHistory.ok()).toBeTruthy()
    const apiPayload = await apiHistory.json()
    const dbEvidence = queryDbEvidence(anchor.id)
    evidence.db = dbEvidence
    evidence.api_total = apiPayload.total

    expect(dbEvidence.count).toBe(12)
    expect(apiPayload.total).toBe(dbEvidence.count)
    expect(apiPayload.items.map((item: { package_version: string }) => item.package_version)).toEqual(
      dbEvidence.ordered_versions.slice(0, 10),
    )
    expect(dbEvidence.event_count_for_anchor).toBeGreaterThan(0)

    await page.goto(`/releases/sdk-packages/${anchor.id}`, { waitUntil: 'domcontentloaded' })
    const history = page.locator('section').filter({ has: page.getByRole('heading', { name: '发布结果历史' }) })
    const timeline = page.locator('section').filter({ has: page.getByRole('heading', { name: '操作时间线' }) })

    await expect(history).toBeVisible()
    await expect(timeline).toBeVisible()
    await expect(history.getByText('第 1 页 · 共 12 条结果')).toBeVisible()
    await expect(historyRow(history, '1.0.12')).toBeVisible()
    await expect(historyRow(history, '1.0.11')).toBeVisible()
    await expect(history.getByRole('button', { name: '打开 Registry' }).first()).toBeVisible()
    await expect(history.getByRole('button', { name: '打开 GitHub Tag' }).first()).toBeVisible()
    await expect(history.getByRole('button', { name: '打开 Workflow' }).first()).toBeVisible()
    await expect(timeline.getByText('initialize_train')).toBeVisible()

    await page.screenshot({
      path: testInfo.outputPath('sdk-package-release-history.png'),
      fullPage: true,
    })

    await history.getByPlaceholder('搜索版本 / train / 状态 / registry / failure summary').fill('registry rejected')
    await history.getByRole('button', { name: '搜索' }).click()
    await expect(history.getByText('第 1 页 · 共 1 条结果')).toBeVisible()
    await expect(historyRow(history, '1.0.12')).toBeVisible()
    await expect(history.getByText('registry rejected scoped version')).toBeVisible()

    await history.getByPlaceholder('搜索版本 / train / 状态 / registry / failure summary').fill('')
    await history.getByRole('combobox').nth(0).selectOption('published')
    await history.getByRole('button', { name: '搜索' }).click()
    await expect(history.getByText('第 1 页 · 共 5 条结果')).toBeVisible()
    await expect(historyRow(history, '1.0.11')).toBeVisible()

    await history.getByRole('combobox').nth(0).selectOption('')
    await history.getByRole('combobox').nth(1).selectOption('next')
    await history.getByRole('button', { name: '搜索' }).click()
    await expect(history.getByText('第 1 页 · 共 1 条结果')).toBeVisible()
    await expect(historyRow(history, '1.0.10')).toBeVisible()

    await history.getByRole('combobox').nth(1).selectOption('')
    await history.getByRole('button', { name: '搜索' }).click()
    await expect(history.getByText('第 1 页 · 共 12 条结果')).toBeVisible()
    await history.getByRole('button', { name: '下一页' }).click()
    await expect(history.getByText('第 2 页 · 共 12 条结果')).toBeVisible()
    await expect(historyRow(history, '1.0.2')).toBeVisible()
    await expect(historyRow(history, '1.0.1')).toBeVisible()

    await historyRow(history, '1.0.2').click()
    await expect(page).toHaveURL(/\/releases\/sdk-packages\/\d+$/)
    await expect(page.getByText('package version：')).toBeVisible()
    await expect(page.getByText('1.0.2').first()).toBeVisible()
  } catch (error) {
    await recordBug(page, error, testInfo, evidence)
    throw error
  }
})
