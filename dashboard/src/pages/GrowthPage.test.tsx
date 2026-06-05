// @vitest-environment jsdom

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GrowthPage from './GrowthPage'

const investor = {
  id: 1,
  lead_type: 'investor',
  project_key: 'growing',
  name: 'Ada Seed',
  organization: 'Agent Infra Capital',
  role_title: 'Partner',
  public_profile_urls: ['https://example.com/ada'],
  contact_channels: [],
  source_kind: 'manual',
  source_url: 'https://example.com/ada',
  status: 'drafted',
  fit_score: 88,
  confidence_score: 75,
  risk_flags: [],
  evidence: [],
  metadata: {},
  next_action: 'Review draft',
  last_contacted_at: null,
  created_at: '2026-05-30T10:00:00',
  updated_at: '2026-05-30T10:00:00',
}

const provider = {
  ...investor,
  id: 2,
  lead_type: 'provider',
  name: 'Firecrawl',
  organization: 'Firecrawl',
  status: 'approved',
  contact_channels: [{ kind: 'email', value: 'partnerships@firecrawl.dev', confidence: 'high' }],
  metadata: {
    why_this_provider: 'Official MCP server for web search and scrape APIs.',
    contact_provenance: [{ source_url: 'https://docs.firecrawl.dev/partner-integration' }],
  },
}

const providerProfile = {
  id: 1,
  lead_id: 2,
  organization: 'Firecrawl',
  website_url: 'https://www.firecrawl.dev/',
  company_description: 'Firecrawl provides an API for AI systems to search, scrape, crawl, and interact with the web.',
  contact_email: 'partnerships@firecrawl.dev',
  contact_source_url: 'https://docs.firecrawl.dev/partner-integration',
  source_url: 'https://www.firecrawl.dev/',
  latest_message_id: 22,
  latest_message_subject: 'Synapse provider channel',
  latest_message_status: 'sent',
  last_contacted_at: '2026-05-31T10:00:00',
  profile_status: 'historical_lead',
  evidence: [{ source: 'https://www.firecrawl.dev/', reason: 'Company website and description source for customer profile.' }],
  metadata: {},
  created_at: '2026-05-31T10:00:00',
  updated_at: '2026-05-31T10:00:00',
}

const providerReply = {
  id: 1,
  lead_id: 2,
  message_id: 22,
  provider_profile_id: 1,
  mailbox_message_id: '<reply-firecrawl-1@example.com>',
  thread_id: 'thread-firecrawl',
  from_email: 'partnerships@firecrawl.dev',
  from_name: 'Firecrawl Partnerships',
  subject: 'Re: Synapse provider channel',
  snippet: 'Yes, please send details.',
  body_excerpt: 'Yes, please send details about the provider registration and pricing.',
  received_at: '2026-06-02T13:00:00',
  classification: 'interested',
  confidence_score: 85,
  suggested_reply_message_id: 23,
  suggested_reply_subject: 'Re: Synapse provider channel',
  suggested_reply_body: 'Thanks for getting back to me. I can send the provider registration details.\n\nOfficial site: https://www.synapse-network.ai/',
  suggested_reply_status: 'needs_review',
  status: 'drafted',
  evidence: [],
  metadata: { auto_send: false },
  created_at: '2026-06-02T13:01:00',
  updated_at: '2026-06-02T13:01:00',
}

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) } as Response)
}

function listPayload(items: unknown[]) {
  return { items, total: items.length, limit: 100, offset: 0, status_counts: {}, lead_type_counts: {} }
}

function installFetch() {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push(`${init?.method || 'GET'} ${url}`)
    if (url.includes('/growth/overview')) {
      return json({ lead_counts: { investor: 1, provider: 1 }, message_counts: { needs_review: 1 }, ai_visibility: { cited: 1 }, discovery_counts: { listed: 1 } })
    }
    if (url.includes('/growth/source-configs/default-provider')) {
      return json({ id: 1, config_key: 'agent_api_mcp_provider_discovery', name: 'Provider Discovery: MCP + API Services', config_type: 'github_mcp_repos', status: 'enabled', description: 'Find providers', query: {}, cadence: {}, thresholds: {}, last_run_at: null, last_result: {}, created_at: null, updated_at: null })
    }
    if (url.includes('/growth/source-configs/1/run')) {
      return json({ id: 5, source_config_id: 1, status: 'succeeded', dry_run: init?.body && String(init.body).includes('"dry_run":true'), params: {}, candidate_count: 1, created_count: 1, reused_count: 0, drafted_count: 1, error_summary: '', result: { candidates: [{ name: 'Firecrawl' }] }, started_at: null, completed_at: null, created_at: null, updated_at: null })
    }
    if (url.includes('/growth/source-configs/1/runs')) {
      return json({ items: [{ id: 5, source_config_id: 1, status: 'succeeded', dry_run: false, params: {}, candidate_count: 1, created_count: 1, reused_count: 0, drafted_count: 1, error_summary: '', result: {}, started_at: null, completed_at: null, created_at: null, updated_at: null }], total: 1, limit: 50, offset: 0 })
    }
    if (url.includes('/growth/source-configs') && init?.method === 'POST') {
      return json({ id: 2, config_key: 'agent_api_mcp_provider_discovery', name: 'Provider Discovery: MCP + API Services', config_type: 'github_mcp_repos', status: 'enabled', description: 'Find providers', query: {}, cadence: {}, thresholds: {}, last_run_at: null, last_result: {}, created_at: null, updated_at: null }, 201)
    }
    if (url.includes('/growth/source-configs')) {
      return json({ items: [{ id: 1, config_key: 'agent_api_mcp_provider_discovery', name: 'Provider Discovery: MCP + API Services', config_type: 'github_mcp_repos', status: 'enabled', description: 'Find providers', query: {}, cadence: {}, thresholds: {}, last_run_at: null, last_result: { candidate_count: 1, created_count: 1, drafted_count: 1 }, created_at: null, updated_at: null }], total: 1 })
    }
    if (url.includes('/growth/leads/1') && !url.includes('draft-message')) {
      return json({
        lead: investor,
        messages: [{ id: 10, lead_id: 1, campaign_id: null, channel: 'email', subject: 'Hello', body: 'Draft body', personalization_evidence: [], status: 'needs_review', approved_by: null, sent_at: null, failure_reason: null, metadata: {}, created_at: null, updated_at: null }],
        events: [{ id: 1, lead_id: 1, message_id: 10, event_type: 'message_drafted', actor: 'agent', from_status: null, to_status: 'needs_review', summary: '', metadata: {}, created_at: null }],
      })
    }
    if (url.includes('/growth/leads/2') && !url.includes('draft-message')) {
      return json({
        lead: provider,
        messages: [{
          id: 20,
          lead_id: 2,
          campaign_id: null,
          channel: 'email',
          subject: 'Synapse provider fit for Firecrawl',
          body: 'Firecrawl could expose metered agent web-data calls through Synapse.',
          personalization_evidence: [],
          status: 'approved',
          approved_by: 'operator',
          sent_at: null,
          failure_reason: null,
          metadata: {
            contact_email: 'partnerships@firecrawl.dev',
            contact_provenance: [{ source_url: 'https://docs.firecrawl.dev/partner-integration' }],
            gmail_status: 'not_created',
          },
          created_at: null,
          updated_at: null,
        }],
        events: [],
      })
    }
    if (url.includes('/growth/leads') && init?.method === 'POST') return json({ ...investor, id: 3 }, 201)
    if (url.includes('/growth/provider-profiles')) return json({ items: [providerProfile], total: 1, limit: 50, offset: 0 })
    if (url.includes('/growth/provider-replies')) return json({ items: [providerReply], total: 1, limit: 20, offset: 0 })
    if (url.includes('/growth/leads?') && url.includes('provider')) return json(listPayload([provider]))
    if (url.includes('/growth/leads')) return json(listPayload([investor]))
    if (url.includes('/growth/messages/10/approve')) return json({ id: 10, lead_id: 1, status: 'approved', subject: 'Hello', body: 'Draft body', personalization_evidence: [], channel: 'email', campaign_id: null, approved_by: 'operator', sent_at: null, failure_reason: null, metadata: {}, created_at: null, updated_at: null })
    if (url.includes('/growth/messages/20/create-gmail-draft')) return json({ id: 20, lead_id: 2, status: 'queued', subject: 'Synapse provider fit for Firecrawl', body: 'Draft body', personalization_evidence: [], channel: 'email', campaign_id: null, approved_by: 'operator', sent_at: null, failure_reason: null, metadata: { gmail_status: 'draft_created', gmail_draft_id: 'draft-123', draft_url: 'https://mail.google.com/mail/u/0/#drafts?compose=draft-123', contact_email: 'partnerships@firecrawl.dev' }, created_at: null, updated_at: null })
    if (url.includes('/growth/ai-visibility/optimization-plan')) {
      return json({
        module_key: 'ai_visibility',
        objective: 'Make Synapse Network discoverable and citable in ChatGPT, Claude, and Grok.',
        canonical_domain: 'https://www.synapse-network.ai/',
        critical_fixes: ['Use www canonical domain.'],
        baseline_queries: [
          { query: 'What is Synapse Network for AI agents?', intent: 'brand_disambiguation', target_platforms: ['chatgpt', 'claude', 'grok'], success_signal: 'Official citation appears.' },
        ],
        feed_experiments: [
          { feed_key: 'brand_disambiguation_www', surfaces: ['www', 'docs'], content_assets: ['canonical homepage metadata'], target_queries: ['What is Synapse Network for AI agents?'], measurement_window_days: 14 },
        ],
        product_docs: { canonical_domain: 'https://www.synapse-network.ai/', docs_category: 'AI Agent Payments', pages: ['/ai-agent-payments'], required_blocks: ['definition'], schema_types: ['FAQPage'] },
        design_plan: { stitch_prompt: 'Design an AI agent payments docs landing page.', figma_handoff: ['Import Stitch output.'], implementation_targets: ['docs-front'] },
        growing_workflows: ['ai_visibility_baseline_sweep', 'ai_visibility_search_probe'],
        success_criteria: ['Stable citations for three weekly runs.'],
      })
    }
    if (url.includes('/growth/ai-visibility/feed-package')) {
      return json({
        items: [{
          feed_key: 'agent_payment_category_pages',
          objective: 'Make AI agent payment category queries cite Synapse docs or marketing pages.',
          canonical_domain: 'https://www.synapse-network.ai/',
          surfaces: ['www', 'docs', 'github'],
          content_assets: ['/ai-agent-payments', 'SDK README answer block'],
          target_queries: ['AI agent payment API'],
          publish_assets: [
            {
              surface: 'www',
              target: 'https://www.synapse-network.ai/ai-agent-payments',
              purpose: 'Category landing page with extractable definition.',
              validation: 'curl -fsS https://www.synapse-network.ai/ai-agent-payments',
            },
          ],
          platform_strategies: [
            {
              platform: 'chatgpt',
              feed_focus: 'Official www/docs citation for category and how-to answers.',
              preferred_surfaces: ['www', 'docs', 'github'],
              probe_queries: ['AI agent payment API'],
              success_signal: 'ChatGPT cites the official docs surface.',
              fallback_action: 'Tighten definition blocks before rerunning.',
            },
            {
              platform: 'claude',
              feed_focus: 'Docs-first explanation with comparison and FAQ blocks.',
              preferred_surfaces: ['docs', 'github', 'www'],
              probe_queries: ['Synapse Network vs x402'],
              success_signal: 'Claude cites Synapse docs.',
              fallback_action: 'Add comparison evidence before rerunning.',
            },
            {
              platform: 'grok',
              feed_focus: 'Fresh public web and social distribution signals.',
              preferred_surfaces: ['www', 'docs', 'x_profile'],
              probe_queries: ['AI agent payment API'],
              success_signal: 'Grok mentions Synapse from public web.',
              fallback_action: 'Publish distribution copy with canonical links.',
            },
          ],
          stitch_prompt: 'Design a technical documentation landing page for Synapse Network.',
          figma_handoff: ['Import Stitch output.'],
          validation_commands: ['curl -fsS https://www.synapse-network.ai/llms.txt'],
          probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key agent_payment_category_pages --run-group YYYY-MM-DD-after-feed --mode after-feed',
          success_metrics: ['Stable citations for three weekly runs.'],
          next_actions: ['Publish AI Agent Payments docs category and www landing pages.'],
        }],
        total: 1,
      })
    }
    if (url.includes('/growth/ai-visibility/feed-cycles')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        target_platforms: ['chatgpt', 'claude', 'grok'],
        recommended_feed_key: 'mcp_paid_api_discovery',
        items: [
          {
            feed_key: 'mcp_paid_api_discovery',
            status: 'feed_blocked',
            objective: 'Make MCP paid API queries cite Synapse docs.',
            latest_run_group: '',
            latest_comparison_status: 'needs_external_probe',
            feed_ready: false,
            external_probe_ready: false,
            feed_effective: false,
            external_platforms: [],
            missing_platforms: ['chatgpt', 'claude', 'grok'],
            mentioned_count: 0,
            cited_count: 0,
            blockers: ['Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.'],
            next_actions: ['Resolve feed blockers before external probes.'],
            publish_surfaces: ['www', 'docs', 'mcp_registry'],
            feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-mcp_paid_api_discovery-weekly',
            manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery',
            api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok',
            api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok --execute',
            compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery"',
            latest_run_at: null,
          },
        ],
        total: 1,
      })
    }
    if (url.includes('/growth/ai-visibility/feed-scorecard')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        recommended_feed_key: 'mcp_paid_api_discovery',
        ranking_basis: 'Impact score rewards feed readiness, GPT/Claude/Grok coverage, Synapse mentions, citations, positive deltas, and durable feed effectiveness.',
        items: [
          {
            feed_key: 'mcp_paid_api_discovery',
            rank: 1,
            impact_score: 0,
            status: 'feed_blocked',
            objective: 'Make MCP paid API queries cite Synapse docs.',
            latest_run_group: '',
            comparison_status: 'needs_external_probe',
            feed_ready: false,
            external_probe_ready: false,
            feed_effective: false,
            target_platforms: ['chatgpt', 'claude', 'grok'],
            covered_platforms: [],
            missing_platforms: ['chatgpt', 'claude', 'grok'],
            external_checks_count: 0,
            local_validation_count: 0,
            mentioned_count: 0,
            cited_count: 0,
            mentioned_delta: 0,
            cited_delta: 0,
            blockers: ['Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.'],
            next_actions: ['Resolve feed blockers before external probes.'],
            recommended_action: 'Resolve feed blockers, then rerun live readiness before external probes.',
            feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery',
            api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok',
            api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok --execute',
            compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery"',
          },
        ],
        total: 1,
      })
    }
    if (url.includes('/growth/ai-visibility/docs-blueprint')) {
      return json({
        category: 'AI Agent Payments',
        canonical_domain: 'https://www.synapse-network.ai/',
        target_repo: 'Synapse-Network',
        implementation_root: 'services/docs-front/content/docs/ai-agent-payments',
        pages: [{
          slug: 'index',
          title: 'AI Agent Payments',
          canonical_url: 'https://docs.synapse-network.ai/ai-agent-payments',
          meta_description: 'Learn how Synapse Network lets AI agents pay for APIs.',
          target_queries: ['AI agent payment API'],
          definition_block: 'Synapse Network is a payment and settlement layer for AI agents.',
          fact_table: [{ label: 'Product', value: 'Synapse Network' }],
          page_sections: ['Definition', 'Agent payment flow'],
          faq: [{ question: 'What is Synapse?', answer: 'Agent payments.' }],
          schema_types: ['TechArticle', 'FAQPage'],
          stitch_notes: ['Use a technical docs layout.'],
          figma_components: ['DocsHeader', 'DefinitionBlock', 'FactsTable'],
          mdx_skeleton: '# AI Agent Payments',
          validation_commands: ['curl -fsS https://docs.synapse-network.ai/ai-agent-payments'],
        }],
        shared_components: ['DefinitionBlock', 'MachineReadableFacts'],
        publishing_checklist: ['Implement MDX pages.'],
      })
    }
    if (url.includes('/growth/ai-visibility/design-handoff')) {
      return json({
        title: 'Synapse AI Agent Payments Stitch To Figma Handoff',
        canonical_domain: 'https://www.synapse-network.ai/',
        source_tool: 'Stitch',
        target_tool: 'Figma',
        figma_file_name: 'Synapse AI Agent Payments Docs - AI Visibility',
        stitch_prompt: 'Design a technical docs page for Synapse Network.',
        frames: [{
          name: 'AI Agent Payments Docs Landing',
          purpose: 'Primary documentation landing page for AI answer engines and developer readers.',
          source_page_slug: 'index',
          layout_notes: ['Canonical URL: https://docs.synapse-network.ai/ai-agent-payments'],
          figma_components: ['DocsHeader', 'DefinitionBlock', 'FactsTable'],
          stitch_prompt: 'Create the main docs landing page.',
        }],
        component_specs: [{ name: 'DefinitionBlock', purpose: 'Answer block', implementation: 'MDX callout' }],
        design_tokens: { radius: '8px' },
        import_steps: ['Generate the three frames in Stitch using the frame-specific prompts.'],
        implementation_notes: ['Target repo: Synapse-Network'],
        acceptance_checks: ['Figma frame includes the canonical www homepage.'],
      })
    }
    if (url.includes('/growth/ai-visibility/weekly-report')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        goal_status: 'optimizing',
        goal_achieved: false,
        required_stable_runs: 3,
        stable_positive_runs: 1,
        target_platforms: ['chatgpt', 'claude', 'grok'],
        covered_platforms: ['chatgpt', 'claude'],
        missing_platforms: ['grok'],
        total_external_checks: 3,
        total_mentioned_count: 2,
        total_cited_count: 1,
        latest_feed_key: 'agent_payment_category_pages',
        latest_run_group: '2026-06-18-after-docs-launch',
        latest_comparison_status: 'improved',
        feed_reports: [],
        blockers: ['Fewer than three stable positive external runs have been recorded.', 'Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.'],
        next_actions: ['Run and record missing platform probes: grok.', 'Publish MCP paid API docs and www llms feed.'],
        recommended_feed_key: 'agent_payment_category_pages',
        recommended_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key agent_payment_category_pages --run-group YYYY-MM-DD-weekly --mode after-feed',
      })
    }
    if (url.includes('/growth/ai-visibility/next-cycle')) {
      return json({
        module_key: 'ai_visibility',
        feed_key: 'agent_payment_category_pages',
        run_group: '2026-06-05-agent_payment_category_pages-weekly',
        output_path: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly.jsonl',
        missing_platforms: ['grok'],
        blockers: [
          'Fewer than three stable positive external runs have been recorded.',
          'Production docs page https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.',
        ],
        next_actions: [
          'Run and record missing platform probes: grok.',
          'Publish MCP paid API docs and www llms feed.',
        ],
        validation_commands: ['curl -fsS https://www.synapse-network.ai/llms.txt'],
        feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-feed-validation.jsonl',
        manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --mode after-feed',
        external_probe_gate_command: 'python scripts/growth/generate_ai_visibility_external_probe_gate.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-external-probe-gate.json',
        api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --platforms chatgpt,claude,grok --query "AI agent payment API"',
        api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly --platforms chatgpt,claude,grok --query "AI agent payment API" --execute',
        public_web_search_import_command: 'python scripts/growth/import_ai_visibility_public_search_snapshot.py docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-public-web-search-snapshot.json --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-public-web-search.jsonl',
        apply_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly.jsonl --apply',
        probe_matrix_command: 'python scripts/growth/generate_ai_visibility_probe_matrix.py --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-probe-matrix.json',
        validate_matrix_command: 'python scripts/growth/validate_ai_visibility_probe_matrix.py docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly.jsonl --matrix-file docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-probe-matrix.json --feed-key agent_payment_category_pages --run-group 2026-06-05-agent_payment_category_pages-weekly',
        cycle_summary_command: 'python scripts/growth/summarize_ai_visibility_cycle.py docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly.jsonl --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-cycle-summary.json',
        operator_brief_command: 'python scripts/growth/generate_ai_visibility_operator_brief.py --feed-key agent_payment_category_pages --cycle-summary docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-cycle-summary.json --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-operator-brief.md',
        goal_audit_command: 'python scripts/growth/generate_ai_visibility_goal_audit.py --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-goal-audit.json',
        compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=agent_payment_category_pages&run_group=2026-06-05-agent_payment_category_pages-weekly" | python -m json.tool',
        weekly_report_command: 'python scripts/growth/export_ai_visibility_weekly_report.py --output docs/archive/evidence/growth/ai-visibility/2026-06-05-agent_payment_category_pages-weekly-weekly-report.json',
      })
    }
    if (url.includes('/growth/ai-visibility/goal-audit')) {
      return json({ module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', status: 'incomplete', goal_achieved: false, official_homepage: 'https://www.synapse-network.ai/', target_platforms: ['chatgpt', 'claude', 'grok'], completed_count: 5, total_required: 8, requirements: [{ key: 'external_search_evidence', title: 'GPT/Claude/Grok search evidence', status: 'blocked', required: true, evidence: '', blocker: 'Missing external evidence.', next_action: 'Run full external probes.' }], blockers: ['Missing external evidence.'], next_actions: ['Run full external probes.'], export_command: 'python scripts/growth/generate_ai_visibility_goal_audit.py' })
    }
    if (url.includes('/growth/ai-visibility/release-unblock-plan')) {
      return json({
        module_key: 'ai_visibility',
        feed_key: 'mcp_paid_api_discovery',
        status: 'blocked_until_gcloud_auth',
        generated_at: '2026-06-05T00:00:00Z',
        official_homepage: 'https://www.synapse-network.ai/',
        project_key: 'synapse-network',
        services: ['docs-front', 'user-front'],
        branch_name: 'main',
        target_commit_sha: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9',
        actor: 'codex/ai-visibility-release-unblock',
        source_pr: {
          number: 204,
          state: 'MERGED',
          head_ref: 'codex/ai-visibility-docs-llms-endpoint',
          base_ref: 'main',
          merged_at: '2026-06-05T00:54:23Z',
          url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/204',
        },
        source_prs: [
          { number: 203, state: 'MERGED', merge_commit: '04c6cfd4477f86569c83322a1119580dcf01091e', purpose: 'Add MCP paid API calls visibility docs and www llms feed.' },
          { number: 204, state: 'MERGED', merge_commit: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9', purpose: 'Expose the MCP paid API docs URL and Remote MCP endpoint in docs-front llms.txt.' },
        ],
        predeploy_evidence: {
          status: 'target_branch_ready_live_prod_blocked',
          path: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-synapse-target-branch-predeploy-readiness.json',
          branch: 'main',
          commit: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9',
          validation_count: 5,
          validations: [
            { command: 'node scripts/ci/ai_visibility_assets_check.mjs', result: 'passed' },
            { command: 'node scripts/ci/seo_public_assets_check.mjs', result: 'passed' },
          ],
          screenshots: [
            '/Users/cliff/workspace/agent/Synapse-Network-Growing/docs/archive/evidence/growth/ai-visibility-synapse-docs-mcp-paid-api-calls-local-20260605.png',
          ],
        },
        deploy_readiness_status: 'ready_for_release_runner_after_gcloud_auth',
        deployment_gaps: [
          {
            service_key: 'docs-front',
            status: 'production_behind_target',
            staging_commit: '04c6cfd4477f86569c83322a1119580dcf01091e',
            production_commit: '6af377ba8199193ad12a1fbc27d20ea64f0e3e18',
            target_commit: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9',
            next_action: 'Re-run staging for d8b5371e, then promote docs-front production.',
          },
        ],
        confirmed_facts: [
          'Official homepage canonical is https://www.synapse-network.ai/.',
          'Synapse-Network main is pinned to merged PR #204 commit d8b5371e11fea2d962dcc656b9b8d08d0c1379d9.',
          'Remote MCP endpoint is https://mcp.synapse-network.ai/mcp; live readiness expects /readyz=200 and unauthenticated /mcp=401.',
          'Growing release runner remains the deployment path; direct gcloud run deploy is out of bounds.',
        ],
        hard_boundaries: [
          'Do not run gcloud run deploy directly.',
          'Production must promote the successful staging digest for the same commit.',
        ],
        known_blockers: [
          'GCloud auth fails non-interactively until a human runs gcloud auth login.',
          'Production https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.',
          'Production homepage https://www.synapse-network.ai/ is reachable, but https://www.synapse-network.ai/llms.txt does not expose the MCP paid API guide and Remote MCP endpoint yet.',
        ],
        environment_defaults: {
          ops_base_url: 'http://localhost:9700',
          target_repo_worktree: '/private/tmp/synapse-ai-visibility-publish',
        },
        command_groups: [
          {
            key: 'gcloud_auth_and_target_commit_preflight',
            purpose: 'Restore non-interactive GCloud access.',
            commands: ['gcloud auth login'],
            service_key: '',
            environment: '',
            notes: [],
          },
          {
            key: 'create_and_run_docs-front_production',
            purpose: 'Promote docs-front.',
            commands: ['PYTHONPATH=. .venv/bin/python scripts/local/run_deploy_worker.py --once --deployment-record-id $DOCS_FRONT_PROD_DEPLOYMENT_RECORD_ID'],
            service_key: 'docs-front',
            environment: 'production',
            notes: [],
          },
          {
            key: 'production_validation',
            purpose: 'Verify public feed.',
            commands: ['curl -fsS https://www.synapse-network.ai/llms.txt'],
            service_key: '',
            environment: '',
            notes: [],
          },
        ],
        success_criteria: ['https://www.synapse-network.ai/llms.txt includes MCP Server for Paid API Calls.'],
      })
    }
    if (url.includes('/growth/ai-visibility/release-snapshot')) {
      return json({
        module_key: 'ai_visibility',
        snapshot_type: 'release_blocker',
        generated_at: '2026-06-05T00:00:00Z',
        feed_key: 'mcp_paid_api_discovery',
        run_group: '2026-06-05-mcp_paid_api_discovery-release-snapshot',
        target_commit_sha: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9',
        official_homepage: 'https://www.synapse-network.ai/',
        status: 'blocked',
        release_plan_status: 'blocked_until_gcloud_auth',
        deploy_readiness_status: 'ready_for_release_runner_after_gcloud_auth',
        confirmed_facts: [
          'Official homepage canonical is https://www.synapse-network.ai/.',
          'Remote MCP endpoint is https://mcp.synapse-network.ai/mcp; live readiness expects /readyz=200 and unauthenticated /mcp=401.',
        ],
        deployment_gaps: [
          {
            service_key: 'docs-front',
            status: 'production_behind_target',
            target_commit: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9',
          },
        ],
        live_readiness: {
          status: 'blocked',
          ready_count: 0,
          blocked_count: 1,
          items: [],
        },
        gcloud: {
          staging: {
            project_id: 'fabled-archive-494108-k5',
            ok: false,
            status: 'failed',
            summary: 'Reauthentication failed. Please run gcloud auth login.',
          },
          production: {
            project_id: 'synapse-network-prod',
            ok: false,
            status: 'failed',
            summary: 'Reauthentication failed. Please run gcloud auth login.',
          },
        },
        external_probe_keys: {
          chatgpt: { env_key: 'OPENAI_API_KEY', configured: false },
          claude: { env_key: 'ANTHROPIC_API_KEY', configured: false },
          grok: { env_key: 'XAI_API_KEY', configured: false },
        },
        blockers: [
          'GCloud auth fails non-interactively until a human runs gcloud auth login.',
          'Docs /mcp/paid-api-calls page must be live.',
          'chatgpt external probe key missing: OPENAI_API_KEY.',
        ],
        next_actions: [
          'Run gcloud auth login, then rerun this snapshot before creating release tasks.',
          'Deploy docs-front and user-front target commit through Growing release tasks.',
        ],
      })
    }
    if (url.includes('/growth/ai-visibility/handoff-bundle')) {
      return json({
        module_key: 'ai_visibility',
        bundle_type: 'operator_handoff',
        generated_at: '2026-06-05T00:00:00Z',
        feed_key: 'mcp_paid_api_discovery',
        run_group: '2026-06-05-current',
        target_commit_sha: 'd8b5371e11fea2d962dcc656b9b8d08d0c1379d9',
        official_homepage: 'https://www.synapse-network.ai/',
        status: 'blocked',
        release_status: 'blocked',
        live_readiness_status: 'blocked',
        external_probe_gate_status: 'blocked_until_feed_ready',
        goal_audit_status: 'incomplete', goal_achieved: false,
        ready_platforms: ['chatgpt', 'claude'],
        missing_platforms: ['grok'],
        blockers: ['Docs /mcp/paid-api-calls page must be live.', 'GCloud auth fails non-interactively.'],
        next_actions: ['Run gcloud auth login.'],
        files: { manifest: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-current-handoff/manifest.json', operator_brief: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-current-handoff/operator-brief.md', goal_audit: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-current-handoff/goal-audit.json' },
        commands: {
          rerun_handoff: 'python scripts/growth/generate_ai_visibility_handoff_bundle.py --feed-key mcp_paid_api_discovery',
          feed_validation: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery',
          api_readiness: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok',
          partial_api_readiness: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude',
          goal_audit: 'python scripts/growth/generate_ai_visibility_goal_audit.py',
          compare: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery"',
        },
      })
    }
    if (url.includes('/growth/ai-visibility/external-probe-gate')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        feed_key: 'mcp_paid_api_discovery',
        run_group: '2026-06-05-mcp_paid_api_discovery-external-probe',
        status: 'blocked_until_feed_ready',
        ready_to_execute: false,
        partial_ready_to_execute: false,
        manual_ready_to_execute: false,
        feed_ready: false,
        api_keys_ready: false,
        target_platforms: ['chatgpt', 'claude', 'grok'],
        ready_platforms: [],
        missing_platforms: ['chatgpt', 'claude', 'grok'],
        provider_readiness: [
          { platform: 'chatgpt', env_key: 'OPENAI_API_KEY', configured: false },
          { platform: 'claude', env_key: 'ANTHROPIC_API_KEY', configured: false },
          { platform: 'grok', env_key: 'XAI_API_KEY', configured: false },
        ],
        blockers: [
          'Docs /mcp/paid-api-calls page must be live.',
          'chatgpt missing OPENAI_API_KEY.',
        ],
        feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery',
        record_readiness_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-feed-validation.jsonl --allow-local-validation --apply',
        manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery',
        api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok',
        api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok --execute',
        record_probe_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-external-probes.jsonl --apply',
        compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery" | python -m json.tool',
      })
    }
    if (url.includes('/growth/ai-visibility/official-sources')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        official_citation_prefixes: [
          'https://www.synapse-network.ai/',
          'https://docs.synapse-network.ai/',
          'https://mcp.synapse-network.ai/',
        ],
        total: 2,
        items: [
          {
            surface_key: 'www_homepage',
            surface: 'www',
            canonical_url: 'https://www.synapse-network.ai/',
            citation_role: 'Primary canonical.',
            feed_keys: ['brand_disambiguation_www'],
            required_for_success: true,
            validation_command: 'curl -fsS https://www.synapse-network.ai/',
            acceptance_signal: 'Homepage has facts.',
          },
          {
            surface_key: 'remote_mcp',
            surface: 'mcp',
            canonical_url: 'https://mcp.synapse-network.ai/mcp',
            citation_role: 'Hosted Remote MCP endpoint.',
            feed_keys: ['mcp_paid_api_discovery'],
            required_for_success: true,
            validation_command: 'curl -fsS https://mcp.synapse-network.ai/readyz',
            acceptance_signal: 'readyz is 200 and /mcp is 401.',
          },
        ],
      })
    }
    if (url.includes('/growth/ai-visibility/probe-matrix')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        target_platforms: ['chatgpt', 'claude', 'grok'],
        recommended_feed_key: 'mcp_paid_api_discovery',
        total: 1,
        rows: [
          {
            feed_key: 'mcp_paid_api_discovery',
            platform: 'chatgpt',
            status: 'ready_to_probe',
            run_group: '2026-06-05-mcp-weekly',
            queries: ['MCP server for paid API calls'],
            official_source_urls: [
              'https://www.synapse-network.ai/',
              'https://mcp.synapse-network.ai/mcp',
            ],
            success_decision_rule: 'Success requires an official citation.',
            manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery',
            record_probe_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly.jsonl --apply',
            compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"',
            evidence_directory: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly',
            blockers: [],
            next_actions: ['Run the chatgpt probe with unchanged query wording.'],
          },
        ],
      })
    }
    if (url.includes('/growth/ai-visibility/optimization-brief')) {
      return json({
        module_key: 'ai_visibility',
        title: 'Synapse AI Visibility Optimization Brief',
        status: 'blocked',
        generated_at: '2026-06-05T00:00:00Z',
        official_homepage: 'https://www.synapse-network.ai/',
        recommended_feed_key: 'mcp_paid_api_discovery',
        target_platforms: ['chatgpt', 'claude', 'grok'],
        blockers: ['Production https://docs.synapse-network.ai/mcp/paid-api-calls is not live yet.'],
        next_actions: ['Resolve feed blockers before external probes.'],
        artifact_path: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-operator-brief-optimization-brief.md',
        export_command: 'python scripts/growth/generate_ai_visibility_optimization_brief.py --run-group 2026-06-05-operator-brief --output docs/archive/evidence/growth/ai-visibility/2026-06-05-operator-brief-optimization-brief.md',
        markdown: '# Synapse AI Visibility Optimization Brief',
      })
    }
    if (url.includes('/growth/ai-visibility/live-readiness')) {
      return json({
        module_key: 'ai_visibility',
        generated_at: '2026-06-05T00:00:00Z',
        run_group: '2026-06-05-live-readiness',
        canonical_homepage: 'https://www.synapse-network.ai/',
        status: 'blocked',
        ready_count: 1,
        blocked_count: 1,
        validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery --run-group 2026-06-05-live-readiness --output docs/archive/evidence/growth/ai-visibility/2026-06-05-live-readiness-feed-validation.jsonl',
        apply_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-live-readiness-feed-validation.jsonl --allow-local-validation --apply',
        total: 2,
        items: [
          {
            feed_key: 'brand_disambiguation_www',
            status: 'ready',
            feed_ready: true,
            external_probe_ready: true,
            run_group: '2026-06-05-live-readiness',
            platform: 'www_live_validation',
            query: 'Brand disambiguation live feed readiness',
            answer_summary: 'Live feed validation passed.',
            checked_urls: ['https://www.synapse-network.ai/llms.txt'],
            missing_facts: [],
            next_action: 'Run GPT/Claude/Grok brand probes with generated template.',
            checks: [
              {
                label: 'llms',
                url: 'https://www.synapse-network.ai/llms.txt',
                status: 200,
                ok: true,
                final_url: 'https://www.synapse-network.ai/llms.txt',
                error: '',
                contains_synapse: true,
              },
            ],
          },
          {
            feed_key: 'mcp_paid_api_discovery',
            status: 'blocked',
            feed_ready: false,
            external_probe_ready: false,
            run_group: '2026-06-05-live-readiness',
            platform: 'mcp_live_validation',
            query: 'Remote MCP live readiness',
            answer_summary: 'Live feed validation blocked: docs_mcp_paid_api_calls=404',
            checked_urls: ['https://docs.synapse-network.ai/mcp/paid-api-calls'],
            missing_facts: [
              'Docs /mcp/paid-api-calls page must be live.',
              'www llms.txt must include the MCP paid API calls guide and Remote MCP endpoint.',
            ],
            next_action: 'Publish /mcp/paid-api-calls and www llms.txt MCP feed updates before external answer-engine probes.',
            checks: [
              {
                label: 'docs_mcp_paid_api_calls',
                url: 'https://docs.synapse-network.ai/mcp/paid-api-calls',
                status: 404,
                ok: false,
                final_url: 'https://docs.synapse-network.ai/mcp/paid-api-calls',
                error: '',
                contains_synapse: false,
              },
            ],
          },
        ],
      })
    }
    if (url.includes('/growth/ai-visibility/comparisons')) {
      return json({
        items: [{
          feed_key: 'brand_disambiguation_www',
          run_group: '2026-06-04-baseline',
          previous_run_group: '',
          platforms: ['chatgpt', 'claude'],
          external_platforms: ['chatgpt', 'claude'],
          total_checks: 2,
          external_checks_count: 2,
          local_validation_count: 0,
          mentioned_count: 1,
          cited_count: 1,
          previous_mentioned_count: 0,
          previous_cited_count: 0,
          mentioned_delta: 0,
          cited_delta: 0,
          comparison_status: 'baseline',
          feed_effective: false,
          missing_platforms: ['grok'],
          top_competitors: ['synapse.network'],
          next_actions: ['Fix www canonical and sitemap.'],
          evidence_urls: ['https://example.com/evidence'],
          latest_run_at: null,
        }],
        total: 1,
      })
    }
    if (url.includes('/growth/ai-visibility/checks') && init?.method === 'POST') return json({ id: 2, query: 'agent API marketplace', platform: 'chatgpt', answer_summary: '', synapse_mentioned: false, synapse_cited: false, cited_urls: [], competitor_mentions: [], missing_facts: [], next_action: '', run_at: null, created_at: null, updated_at: null }, 201)
    if (url.includes('/growth/ai-visibility/checks')) return json({ items: [{ id: 1, query: 'MCP monetization platform', platform: 'perplexity', answer_summary: 'No citation', synapse_mentioned: false, synapse_cited: false, cited_urls: [], competitor_mentions: ['RapidAPI'], missing_facts: [], next_action: 'Create answer block', run_at: null, created_at: null, updated_at: null }], total: 1, limit: 100, offset: 0 })
    if (url.includes('/growth/discovery-listings') && init?.method === 'POST') return json({ id: 2, surface: 'glama', target_repo: '', package_name: '', listing_url: '', status: 'candidate', submission_evidence: {}, verification_evidence: {}, failure_reason: '', last_checked_at: null, created_at: null, updated_at: null }, 201)
    if (url.includes('/growth/discovery-listings')) return json({ items: [{ id: 1, surface: 'official_mcp_registry', target_repo: 'SynapseNetworkAI/Synapse-MCP', package_name: 'synapse-network-mcp', listing_url: 'https://registry.example/synapse', status: 'listed', submission_evidence: {}, verification_evidence: {}, failure_reason: '', last_checked_at: null, created_at: null, updated_at: null }], total: 1, limit: 100, offset: 0 })
    return json({})
  }))
  return calls
}

describe('GrowthPage', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/growth')
    installFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders lead tabs, metrics, creates a lead, and opens lead detail actions', async () => {
    const calls = installFetch()
    render(<GrowthPage />)

    await screen.findByText('Provider Source Configs')
    expect(screen.getByText('Growth')).toBeInTheDocument()
    expect(screen.getByText('AI cited')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Investors' }))
    await screen.findByText('Ada Seed')
    fireEvent.click(screen.getByRole('button', { name: '新增 Lead' }))
    const createDialog = await screen.findByRole('dialog', { name: /新增 investor lead/i })
    fireEvent.change(within(createDialog).getByPlaceholderText('investor name'), { target: { value: 'New Investor' } })
    fireEvent.click(within(createDialog).getByRole('button', { name: '创建 Lead' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/leads')).toBe(true))

    fireEvent.click(screen.getByText('Ada Seed'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Draft body')).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: '批准' }))
    await waitFor(() => expect(calls.some((call) => call.includes('/api/growth/messages/10/approve'))).toBe(true))
  })

  it('renders provider and MCP discovery workflows', async () => {
    const calls = installFetch()
    render(<GrowthPage />)

    fireEvent.click(screen.getByRole('button', { name: 'Providers' }))
    expect((await screen.findAllByText('Firecrawl')).length).toBeGreaterThan(0)
    expect(await screen.findByTestId('provider-customer-profiles')).toBeInTheDocument()
    expect(await screen.findByTestId('provider-reply-inbox')).toBeInTheDocument()
    expect(screen.getByText('Provider Reply Inbox')).toBeInTheDocument()
    expect(screen.getByText('Firecrawl Partnerships')).toBeInTheDocument()
    expect(screen.getByText(/provider registration details/)).toBeInTheDocument()
    expect(screen.getByText(/https:\/\/www\.synapse-network\.ai\//)).toBeInTheDocument()
    expect(screen.getByText('Provider Customer Profiles')).toBeInTheDocument()
    expect(screen.getByText('https://www.firecrawl.dev/')).toBeInTheDocument()
    expect(screen.getByText(/search, scrape, crawl/)).toBeInTheDocument()
    fireEvent.click(screen.getAllByText('Firecrawl')[0])
    const providerDialog = await screen.findByRole('dialog')
    expect(within(providerDialog).getByText('partnerships@firecrawl.dev')).toBeInTheDocument()
    expect(within(providerDialog).getByText(/partner-integration/)).toBeInTheDocument()
    fireEvent.click(within(providerDialog).getByRole('button', { name: '创建 Gmail Draft' }))
    await waitFor(() => expect(calls.some((call) => call.includes('/api/growth/messages/20/create-gmail-draft'))).toBe(true))
    fireEvent.click(within(providerDialog).getByRole('button', { name: /关闭/i }))

    fireEvent.click(screen.getByRole('button', { name: 'MCP Discovery' }))
    await screen.findByText('official_mcp_registry')
    fireEvent.click(screen.getByRole('button', { name: '新增 Listing' }))
    const mcpDialog = await screen.findByRole('dialog', { name: '新增 MCP Discovery Listing' })
    fireEvent.change(within(mcpDialog).getByPlaceholderText('surface'), { target: { value: 'glama' } })
    fireEvent.click(within(mcpDialog).getByRole('button', { name: '记录 Listing' }))
    await waitFor(() => expect(calls.some((call) => call === 'POST /api/growth/discovery-listings')).toBe(true))
  })
  it('opens AI visibility from the tab query string', async () => {
    window.history.pushState({}, '', '/growth?tab=ai-visibility')
    render(<GrowthPage />)
    await screen.findByTestId('ai-visibility-optimization-panel')
    expect(screen.getByText('AI Visibility Optimization')).toBeInTheDocument()
    expect(screen.queryByText('Provider Source Configs')).not.toBeInTheDocument()
  })

  it('renders source configs and can run provider acquisition', async () => {
    const calls = installFetch()
    render(<GrowthPage />)
    await screen.findByText('Provider Source Configs')
    expect(screen.getByText('Provider Discovery: MCP + API Services')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Dry Run' }))
    await waitFor(() => expect(calls.some((call) => call.includes('/api/growth/source-configs/1/run'))).toBe(true))
    await screen.findByRole('dialog', { name: 'Provider Discovery: MCP + API Services' })
  })
})
