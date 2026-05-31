import { expect, test, type Page, type TestInfo } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

type DbEvidence = {
  release_statuses: string[]
  surface_statuses: string[]
  growth_listing_count: number
  event_actions: string[]
  server_count: number
  surface_config_count: number
  leaked_secret_count: number
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
            "mcp_surface_configs",
            "mcp_discovery_surfaces",
            "mcp_servers",
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
        release_statuses = [cur.fetchone()[0]]
        cur.execute("select status from mcp_server_surfaces where mcp_server_release_id = %s order by surface_key", (release_id,))
        surface_statuses = [row[0] for row in cur.fetchall()]
        cur.execute("select count(*) from growth_discovery_listings where package_name = '@synapse-network-ai/mcp-server'")
        growth_listing_count = cur.fetchone()[0]
        cur.execute("select action from mcp_server_release_events where mcp_server_release_id = %s order by id", (release_id,))
        event_actions = [row[0] for row in cur.fetchall()]
        cur.execute("select count(*) from mcp_servers")
        server_count = cur.fetchone()[0]
        cur.execute("select count(*) from mcp_surface_configs")
        surface_config_count = cur.fetchone()[0]
        cur.execute(
            """
            select count(*) from mcp_surface_configs
             where credential_ref like 'npm_%'
                or credential_ref like 'pypi-%'
                or credential_ref like 'sk-%'
                or credential_ref like 'xox%'
            """
        )
        leaked_secret_count = cur.fetchone()[0]
print(json.dumps({
    "release_statuses": release_statuses,
    "surface_statuses": surface_statuses,
    "growth_listing_count": growth_listing_count,
    "event_actions": event_actions,
    "server_count": server_count,
    "surface_config_count": surface_config_count,
    "leaked_secret_count": leaked_secret_count,
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
    const catalog = await request.get('/api/releases/mcp-servers/catalog')
    expect(catalog.ok()).toBeTruthy()
    const catalogBody = await catalog.json() as { items: Array<{ id: number; server_name: string }> }
    const synapseServer = catalogBody.items.find((item) => item.server_name === 'SynapseNetwork MCP Server')
    expect(synapseServer).toBeTruthy()
    evidence.synapse_server_id = synapseServer?.id

    const remoteCreated = await request.post('/api/releases/mcp-servers/catalog', {
      data: {
        server_key: 'remote-demo-mcp',
        server_name: 'Remote Demo MCP Server',
        repo_full_name: 'SynapseNetworkAI/Remote-Demo-MCP',
        repo_url: 'https://github.com/SynapseNetworkAI/Remote-Demo-MCP',
        package_name: '@synapse-network-ai/remote-demo-mcp',
        package_registry: 'npm',
        registry_name: 'io.github.synapsenetworkai/remote-demo-mcp',
        transport_kind: 'remote_http',
        remote_endpoint_url: 'https://mcp.synapse-network.ai/mcp',
        install_command: 'npx -y @synapse-network-ai/remote-demo-mcp',
        tools: ['tools/list', 'services.invoke'],
      },
    })
    expect(remoteCreated.ok()).toBeTruthy()
    const remoteServer = await remoteCreated.json() as { id: number }
    evidence.remote_server_id = remoteServer.id

    const created = await request.post(`/api/releases/mcp-servers/catalog/${synapseServer?.id}/releases`, {
      data: {
        package_version: '0.1.0',
        release_notes: 'Synapse MCP public registry launch.',
      },
    })
    expect(created.ok()).toBeTruthy()
    const release = await created.json() as { id: number }
    evidence.release_id = release.id

    const remoteReleaseCreated = await request.post(`/api/releases/mcp-servers/catalog/${remoteServer.id}/releases`, {
      data: {
        package_version: '0.2.0',
        release_notes: 'Remote MCP endpoint readiness demo.',
      },
    })
    expect(remoteReleaseCreated.ok()).toBeTruthy()

    const openAiConfig = await request.patch('/api/releases/mcp-surfaces/openai_remote_mcp/config', {
      data: {
        submission_mode: 'readonly',
        auth_mode: 'none',
        credential_ref: '',
        required_env_vars: [],
      },
    })
    expect(openAiConfig.ok()).toBeTruthy()
    const openAiVerify = await request.post('/api/releases/mcp-surfaces/openai_remote_mcp/config/verify')
    expect(openAiVerify.ok()).toBeTruthy()

    await page.goto('/releases?tab=mcp-servers', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('mcp-servers-panel')).toBeVisible()
    await expect(page.getByText('SynapseNetwork MCP Server')).toBeVisible()
    await expect(page.getByText('Remote Demo MCP Server')).toBeVisible()
    await expect(page.getByText('@synapse-network-ai/mcp-server')).toBeVisible()
    await expect(page.getByText('@synapse-network-ai/remote-demo-mcp')).toBeVisible()
    await expect(page.getByText('缺少 npm artifact').first()).toBeVisible()

    mockRunnerCompleted(release.id)
    const surfacePatch = await request.patch(`/api/releases/mcp-servers/${release.id}/surfaces/official_mcp_registry`, {
      data: {
        status: 'listed',
        listing_url: 'https://registry.modelcontextprotocol.io/servers/io.github.synapsenetworkai/synapse-network-mcp-server',
        evidence: { source: 'e2e_mock_runner', registry_name: 'io.github.synapsenetworkai/synapse-network-mcp-server' },
      },
    })
    expect(surfacePatch.ok()).toBeTruthy()

    await page.goto(`/releases/mcp-servers/${synapseServer?.id}`, { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('mcp-release-detail')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Registries' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'AI Platforms' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Smoke Evidence' })).toBeVisible()
    await expect(page.getByText('npx -y @synapse-network-ai/mcp-server')).toBeVisible()
    await expect(page.getByText('https://www.npmjs.com/package/@synapse-network-ai/mcp-server/v/0.1.0')).toBeVisible()

    await page.getByRole('button', { name: 'Configs', exact: true }).click()
    await expect(page.getByText('渠道配置与提交就绪度')).toBeVisible()
    await expect(page.getByText('env:NODE_AUTH_TOKEN|NPM_TOKEN')).toBeVisible()
    await expect(page.getByText('not_configured').first()).toBeVisible()
    await expect(page.getByText('Missing env refs').first()).toBeVisible()
    const configScreenshotPath = path.join(repoRoot(), 'docs/archive/evidence/mcp-release/mcp-server-surface-configs.png')
    fs.mkdirSync(path.dirname(configScreenshotPath), { recursive: true })
    await page.screenshot({ path: configScreenshotPath, fullPage: true })
    expect(fs.existsSync(configScreenshotPath)).toBeTruthy()

    await page.getByRole('button', { name: 'Registries' }).click()
    await expect(page.getByText('Official MCP Registry', { exact: true })).toBeVisible()
    await expect(page.getByText('Glama MCP Directory', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'AI Platforms' }).click()
    await expect(page.getByText('OpenAI Remote MCP')).toBeVisible()
    await expect(page.getByText('需要 Remote MCP').first()).toBeVisible()
    await page.getByRole('button', { name: 'Events' }).click()
    await expect(page.getByText('readiness_passed')).toBeVisible()
    await expect(page.getByText('registry_listed', { exact: true })).toBeVisible()

    await page.goto(`/releases/mcp-servers/${remoteServer.id}`, { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Configs', exact: true }).click()
    await expect(page.getByText('OpenAI Remote MCP')).toBeVisible()
    await expect(page.getByText('submit_eligible').first()).toBeVisible()
    await page.getByRole('button', { name: 'AI Platforms' }).click()
    await expect(page.getByText('readiness: submit_eligible').first()).toBeVisible()

    const screenshotPath = path.join(repoRoot(), 'docs/archive/evidence/mcp-release/mcp-server-release.png')
    fs.mkdirSync(path.dirname(screenshotPath), { recursive: true })
    await page.screenshot({ path: screenshotPath, fullPage: true })
    expect(fs.existsSync(screenshotPath)).toBeTruthy()

    const dbEvidence = queryDbEvidence(release.id)
    evidence.db = dbEvidence
    expect(dbEvidence.release_statuses).toContain('registry_listed')
    expect(dbEvidence.surface_statuses).toContain('listed')
    expect(dbEvidence.growth_listing_count).toBe(1)
    expect(dbEvidence.server_count).toBe(2)
    expect(dbEvidence.surface_config_count).toBeGreaterThan(0)
    expect(dbEvidence.leaked_secret_count).toBe(0)
    expect(dbEvidence.event_actions).toEqual(expect.arrayContaining(['readiness_passed', 'surface_updated']))

    await page.goto('/growth', { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'MCP Discovery' }).click()
    await expect(page.getByText('@synapse-network-ai/mcp-server')).toBeVisible()
    await expect(page.getByText('official_mcp_registry')).toBeVisible()
  } catch (error) {
    await recordBug(page, error, testInfo, evidence)
    throw error
  }
})
