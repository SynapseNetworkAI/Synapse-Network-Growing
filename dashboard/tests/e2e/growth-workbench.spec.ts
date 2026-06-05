import { expect, test } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

type GrowthDbEvidence = {
  lead_count: number
  message_statuses: string[]
  event_types: string[]
  ai_check_count: number
  listing_count: number
  provider_profile_count: number
  provider_profile_websites: string[]
  provider_profile_descriptions: string[]
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
    throw new Error('OPS_E2E_DATABASE_URL must point to Postgres for Growth E2E.')
  }
}

function runDbScript<T>(script: string): T {
  requirePostgresE2eUrl()
  const output = execFileSync(pythonBin(), ['-c', script], {
    cwd: repoRoot(),
    encoding: 'utf-8',
    env: { ...process.env, OPS_E2E_DATABASE_URL: postgresUrl, OPS_DATABASE_URL: postgresUrl },
  }).trim()
  return JSON.parse(output) as T
}

function resetGrowthTables() {
  runDbScript(`
import json
import os
import psycopg

dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("""
            truncate table
                growth_provider_profiles,
                growth_outreach_events,
                growth_outreach_messages,
                growth_ai_visibility_checks,
                growth_discovery_listings,
                growth_campaigns,
                growth_leads
            restart identity cascade
        """)
    conn.commit()
print(json.dumps({"ok": True}))
`)
}

function queryGrowthEvidence(): GrowthDbEvidence {
  return runDbScript<GrowthDbEvidence>(`
import json
import os
import psycopg

dsn = os.environ["OPS_E2E_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn:
    with conn.cursor() as cur:
        cur.execute("select count(*) from growth_leads")
        lead_count = cur.fetchone()[0]
        cur.execute("select status from growth_outreach_messages order by id")
        message_statuses = [row[0] for row in cur.fetchall()]
        cur.execute("select event_type from growth_outreach_events order by id")
        event_types = [row[0] for row in cur.fetchall()]
        cur.execute("select count(*) from growth_ai_visibility_checks")
        ai_check_count = cur.fetchone()[0]
        cur.execute("select count(*) from growth_discovery_listings")
        listing_count = cur.fetchone()[0]
        cur.execute("select count(*) from growth_provider_profiles")
        provider_profile_count = cur.fetchone()[0]
        cur.execute("select website_url from growth_provider_profiles order by id")
        provider_profile_websites = [row[0] for row in cur.fetchall()]
        cur.execute("select company_description from growth_provider_profiles order by id")
        provider_profile_descriptions = [row[0] for row in cur.fetchall()]
print(json.dumps({
    "lead_count": lead_count,
    "message_statuses": message_statuses,
    "event_types": event_types,
    "ai_check_count": ai_check_count,
    "listing_count": listing_count,
    "provider_profile_count": provider_profile_count,
    "provider_profile_websites": provider_profile_websites,
    "provider_profile_descriptions": provider_profile_descriptions,
}))
`)
}

function seedGrowthFixtures() {
  runDbScript(`
import json
from datetime import datetime, timezone

from server.database import SessionLocal
from server.database_growth import GrowthLeadRow, GrowthOutreachMessageRow
from server.schemas_growth import (
    GrowthAIVisibilityCheckCreate,
    GrowthDiscoveryListingCreate,
    GrowthLeadCreate,
)
from server.services.growth import discovery, workbench
from server.services.growth.provider_profiles import sync_provider_profiles
from server.services.growth.serializer import json_dumps

db = SessionLocal()
try:
    investor = workbench.create_lead(
        db,
        GrowthLeadCreate(
            lead_type="investor",
            name="Ada Seed",
            organization="Agent Infra Capital",
            role_title="Partner",
            source_url="https://example.com/ada-seed",
            fit_score=88,
            confidence_score=78,
            evidence=[{"source": "portfolio", "reason": "agent infra thesis"}],
            next_action="Draft intro",
        ),
    )
    provider = workbench.create_lead(
        db,
        GrowthLeadCreate(
            lead_type="provider",
            name="Firecrawl",
            organization="Firecrawl",
            source_url="https://www.firecrawl.dev/",
            contact_channels=[
                {
                    "kind": "email",
                    "value": "partnerships@firecrawl.dev",
                    "source_url": "https://docs.firecrawl.dev/partner-integration",
                }
            ],
            fit_score=82,
            next_action="Invite onboarding",
        ),
    )
    lead = db.query(GrowthLeadRow).filter(GrowthLeadRow.id == provider.id).one()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    message = GrowthOutreachMessageRow(
        lead_id=lead.id,
        campaign_id=None,
        channel="email",
        subject="Synapse provider channel",
        body="Official site: https://www.synapse-network.ai/",
        personalization_evidence_json=json_dumps([{"source": "site", "reason": "provider fit"}]),
        status="sent",
        sent_at=now,
        metadata_json=json_dumps({"smtp_sent": True}),
    )
    db.add(message)
    lead.status = "sent"
    lead.last_contacted_at = now
    db.commit()
    profiles = sync_provider_profiles(db)
    discovery.create_ai_check(
        db,
        GrowthAIVisibilityCheckCreate(
            query="MCP monetization platform",
            platform="perplexity",
            answer_summary="Synapse not cited yet.",
            next_action="Create answer block.",
        ),
    )
    discovery.create_listing(
        db,
        GrowthDiscoveryListingCreate(
            surface="official_mcp_registry",
            target_repo="SynapseNetworkAI/Synapse-MCP",
            package_name="synapse-network-mcp",
            status="candidate",
        ),
    )
    print(json.dumps({"investor_id": investor.id, "provider_id": provider.id, "profiles": len(profiles)}))
finally:
    db.close()
`)
}

test('Growth workbench manages leads, draft review, AI visibility, and MCP listings', async ({ page }) => {
  resetGrowthTables()
  seedGrowthFixtures()

  await page.goto('/growth')
  await expect(page.getByTestId('growth-page')).toBeVisible()
  await expect(page.getByText('Ada Seed')).toBeVisible()

  await page.getByText('Ada Seed').click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('button', { name: '生成草稿' }).click()
  await expect(page.getByText('Synapse agent settlement layer')).toBeVisible()
  await page.getByRole('button', { name: '批准' }).click()
  await expect(page.getByRole('dialog')).toContainText('approved')
  await page.getByRole('button', { name: '加入待发送队列' }).click()
  await expect(page.getByRole('dialog')).toContainText('queued')
  await page.getByRole('button', { name: '标记已人工发送' }).click()
  await expect(page.getByRole('dialog')).toContainText('sent')
  await page.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await expect(page.getByRole('status')).toHaveCount(0, { timeout: 12_000 })

  await page.getByRole('button', { name: 'Providers' }).click()
  const profilePanel = page.getByTestId('provider-customer-profiles')
  await expect(profilePanel).toBeVisible()
  await expect(profilePanel.getByRole('heading', { name: 'Firecrawl' })).toBeVisible()
  await expect(profilePanel.getByRole('link', { name: 'https://www.firecrawl.dev/' })).toBeVisible()
  await expect(profilePanel.getByText(/search, scrape, crawl/)).toBeVisible()
  const profileScreenshotPath = path.join(repoRoot(), 'docs/archive/evidence/growth/provider-customer-profiles.png')
  fs.mkdirSync(path.dirname(profileScreenshotPath), { recursive: true })
  await page.screenshot({ path: profileScreenshotPath, fullPage: true })
  expect(fs.existsSync(profileScreenshotPath)).toBeTruthy()

  await page.getByRole('button', { name: 'AI Visibility' }).click()
  await expect(page.getByText('MCP monetization platform')).toBeVisible()
  await page.getByRole('button', { name: 'MCP Discovery' }).click()
  await expect(page.getByText('official_mcp_registry')).toBeVisible()

  const screenshotPath = path.join(repoRoot(), 'docs/archive/evidence/growth/growth-workbench.png')
  fs.mkdirSync(path.dirname(screenshotPath), { recursive: true })
  await page.screenshot({ path: screenshotPath, fullPage: true })
  expect(fs.existsSync(screenshotPath)).toBeTruthy()

  const evidence = queryGrowthEvidence()
  expect(evidence.lead_count).toBe(2)
  expect(evidence.message_statuses).toContain('sent')
  expect(evidence.event_types).toEqual(expect.arrayContaining(['message_drafted', 'message_approved', 'message_queued', 'message_sent']))
  expect(evidence.ai_check_count).toBe(1)
  expect(evidence.listing_count).toBe(1)
  expect(evidence.provider_profile_count).toBe(1)
  expect(evidence.provider_profile_websites).toContain('https://www.firecrawl.dev/')
  expect(evidence.provider_profile_descriptions.some((description) => description.includes('search, scrape, crawl'))).toBeTruthy()
})
