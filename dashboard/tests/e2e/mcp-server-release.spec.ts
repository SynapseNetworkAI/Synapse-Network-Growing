import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

type DbEvidence = {
  release_status: string
  surface_statuses: string[]
  growth_listing_count: number
  event_actions: string[]
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
    throw new Error('OPS_E2E_DATABASE_URL must point to Postgres for MCP release E2E.')
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

function resetMcpReleaseTables() {
  runDbScript(`
import json
import os
import psycopg

dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        for table in [
            "mcp_server_release_events",
            "mcp_server_surfaces",
            "mcp_server_releases",
            "growth_discovery_listings",
        ]:
            cur.execute(f"delete from {table}")
    conn.commit()
print(json.dumps({"ok": True}))
`)
}

function mockRunnerCompleted(releaseId: number) {
  runDbScript(`
import json
import os
import psycopg
import sys

release_id = int(sys.argv[1])
dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            update mcp_server_releases
               set status = 'registry_listed',
                   package_url = 'https://www.npmjs.com/package/@synapse-network-ai/mcp-server/v/0.1.0',
                   registry_url = 'https://registry.modelcontextprotocol.io/servers/io.github.synapsenetworkai/synapse-network-mcp-server',
                   smoke_evidence_json = '{"status":"passed","command":"SYNAPSE_ENV=prod npm run test:e2e:prod","charged_usdc":"0"}',
                   updated_at = now()
             where id = %s
            """,
            (release_id,),
        )
        cur.execute(
            """
            insert into mcp_server_release_events
                (mcp_server_release_id, action, from_status, to_status, actor, metadata_json, created_at)
            values
                (%s, 'readiness_passed', 'readiness_running', 'ready_to_publish', 'mock_runner', '{}', now()),
                (%s, 'npm_published', 'npm_publishing', 'npm_published', 'mock_runner', '{}', now()),
                (%s, 'registry_listed', 'registry_submitting', 'registry_listed', 'mock_runner', '{}', now())
            """,
            (release_id, release_id, release_id),
        )
    conn.commit()
print(json.dumps({"ok": True}))
`, [String(releaseId)])
}

function queryDbEvidence(releaseId: number): DbEvidence {
  return runDbScript<DbEvidence>(`
import json
import os
import psycopg
import sys

release_id = int(sys.argv[1])
dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("select status from mcp_server_releases where id = %s", (release_id,))
        release_status = cur.fetchone()[0]
        cur.execute("select status from mcp_server_surfaces where mcp_server_release_id = %s order by surface_key", (release_id,))
        surface_statuses = [row[0] for row in cur.fetchall()]
        cur.execute("select count(*) from growth_discovery_listings where package_name = '@synapse-network-ai/mcp-server'")
        growth_listing_count = cur.fetchone()[0]
        cur.execute("select action from mcp_server_release_events where mcp_server_release_id = %s order by id", (release_id,))
        event_actions = [row[0] for row in cur.fetchall()]
print(json.dumps({
    "release_status": release_status,
    "surface_statuses": surface_statuses,
    "growth_listing_count": growth_listing_count,
    "event_actions": event_actions,
}))
`, [String(releaseId)])
}

async function recordBug(page: Page, error: unknown, testInfo: TestInfo, evidence: Record<string, unknown>) {
  let screenshotPath: string | null = null
  try {
    screenshotPath = testInfo.outputPath('mcp-server-release-failure.png')
    await page.screenshot({ path: screenshotPath, fullPage: true })
  } catch {
    screenshotPath = null
  }

  await page.request.post('/api/bugs/intake', {
    data: {
      source_key: 'manual_bug_report',
      project_key: 'synapse-network-growing',
      project_root_path: '/Users/cliff/workspace/agent/Synapse-Network-Growing-agent-b',
      title: `MCP server release E2E: ${error instanceof Error ? error.message.slice(0, 120) : 'unknown failure'}`,
      summary: 'MCP server release tab E2E, screenshot validation, or DB evidence verification failed.',
      severity: 'high',
      source_ref: 'e2e:mcp-server-release',
      environment: 'local-postgres-e2e',
      log_excerpt: error instanceof Error ? error.stack || error.message : String(error),
      metadata: {
        component: 'mcp_server_release',
        test_name: testInfo.title,
        screenshot_path: screenshotPath,
        ...evidence,
      },
    },
  }).catch(() => undefined)
}

test('MCP Servers release tab tracks npm, registry, smoke evidence, and Growth discovery handoff', async ({ page, request }, testInfo) => {
  const evidence: Record<string, unknown> = {}
  try {
    resetMcpReleaseTables()
    const created = await request.post('/api/releases/mcp-servers', {
      data: {
        package_version: '0.1.0',
        release_notes: 'Synapse MCP public registry launch.',
      },
    })
    expect(created.ok()).toBeTruthy()
    const release = await created.json() as { id: number }
    evidence.release_id = release.id

    await page.goto('/releases?tab=mcp-servers', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('mcp-servers-panel')).toBeVisible()
    await expect(page.getByText('SynapseNetwork MCP Server')).toBeVisible()
    await expect(page.getByText('@synapse-network-ai/mcp-server')).toBeVisible()

    mockRunnerCompleted(release.id)
    const surfacePatch = await request.patch(`/api/releases/mcp-servers/${release.id}/surfaces/official_mcp_registry`, {
      data: {
        status: 'listed',
        listing_url: 'https://registry.modelcontextprotocol.io/servers/io.github.synapsenetworkai/synapse-network-mcp-server',
        evidence: { source: 'e2e_mock_runner', registry_name: 'io.github.synapsenetworkai/synapse-network-mcp-server' },
      },
    })
    expect(surfacePatch.ok()).toBeTruthy()

    await page.goto(`/releases/mcp-servers/${release.id}`, { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('mcp-release-detail')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Package' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Registry' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Smoke Evidence' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Directory Distribution' })).toBeVisible()
    await expect(page.getByText('npx -y @synapse-network-ai/mcp-server')).toBeVisible()
    await expect(page.getByText('https://www.npmjs.com/package/@synapse-network-ai/mcp-server/v/0.1.0')).toBeVisible()
    await expect(page.getByText('Official MCP Registry', { exact: true })).toBeVisible()
    await expect(page.getByText('readiness_passed')).toBeVisible()
    await expect(page.getByText('registry_listed', { exact: true })).toBeVisible()

    const screenshotPath = path.join(repoRoot(), 'docs/archive/evidence/mcp-release/mcp-server-release.png')
    fs.mkdirSync(path.dirname(screenshotPath), { recursive: true })
    await page.screenshot({ path: screenshotPath, fullPage: true })
    expect(fs.existsSync(screenshotPath)).toBeTruthy()

    const dbEvidence = queryDbEvidence(release.id)
    evidence.db = dbEvidence
    expect(dbEvidence.release_status).toBe('registry_listed')
    expect(dbEvidence.surface_statuses).toContain('listed')
    expect(dbEvidence.growth_listing_count).toBe(1)
    expect(dbEvidence.event_actions).toEqual(expect.arrayContaining(['initialize_mcp_release', 'surface_updated']))

    await page.goto('/growth', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'MCP Discovery' }).click()
    await expect(page.getByText('@synapse-network-ai/mcp-server')).toBeVisible()
    await expect(page.getByText('official_mcp_registry')).toBeVisible()
  } catch (error) {
    await recordBug(page, error, testInfo, evidence)
    throw error
  }
})
