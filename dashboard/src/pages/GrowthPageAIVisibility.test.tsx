// @vitest-environment jsdom

import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import GrowthPage from './GrowthPage'

function json(data: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(data) } as Response)
}

function installFetch() {
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/growth/overview')) {
      return json({ lead_counts: {}, message_counts: {}, ai_visibility: { cited: 1 }, discovery_counts: {} })
    }
    if (url.includes('/growth/leads')) {
      return json({ items: [], total: 0, limit: 10, offset: 0, status_counts: {}, lead_type_counts: {} })
    }
    if (url.includes('/growth/provider-profiles')) return json({ items: [], total: 0, limit: 50, offset: 0 })
    if (url.includes('/growth/provider-replies')) return json({ items: [], total: 0, limit: 20, offset: 0 })
    if (url.includes('/growth/source-configs')) return json({ items: [], total: 0 })
    if (url.includes('/growth/discovery-listings')) return json({ items: [], total: 0, limit: 100, offset: 0 })
    if (url.includes('/growth/ai-visibility/optimization-plan')) return json(optimizationPlan())
    if (url.includes('/growth/ai-visibility/feed-package')) return json({ items: [feedPackage()], total: 1 })
    if (url.includes('/growth/ai-visibility/feed-cycles')) return json(feedCycles())
    if (url.includes('/growth/ai-visibility/feed-scorecard')) return json(feedScorecard())
    if (url.includes('/growth/ai-visibility/live-readiness')) return json(liveReadiness())
    if (url.includes('/growth/ai-visibility/external-probe-gate')) return json(externalProbeGate())
    if (url.includes('/growth/ai-visibility/docs-blueprint')) return json(docsBlueprint())
    if (url.includes('/growth/ai-visibility/design-handoff')) return json(designHandoff())
    if (url.includes('/growth/ai-visibility/weekly-report')) return json(weeklyReport())
    if (url.includes('/growth/ai-visibility/next-cycle')) return json(nextCycle())
    if (url.includes('/growth/ai-visibility/release-unblock-plan')) return json(releasePlan())
    if (url.includes('/growth/ai-visibility/release-snapshot')) return json(releaseSnapshot())
    if (url.includes('/growth/ai-visibility/handoff-bundle')) return json(handoffBundle())
    if (url.includes('/growth/ai-visibility/optimization-brief')) return json(optimizationBrief())
    if (url.includes('/growth/ai-visibility/comparisons')) return json({ items: [comparison()], total: 1 })
    if (url.includes('/growth/ai-visibility/checks')) return json({ items: [check()], total: 1, limit: 100, offset: 0 })
    return json({})
  }))
}

describe('GrowthPage AI visibility', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/growth?tab=ai-visibility')
    installFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens from the query string and renders the release gate evidence', async () => {
    render(<GrowthPage />)

    await screen.findByTestId('ai-visibility-optimization-panel')
    expect(screen.getAllByText('https://www.synapse-network.ai/').length).toBeGreaterThan(0)
    expect(screen.getByTestId('ai-visibility-external-probe-gate')).toBeInTheDocument()
    expect(screen.getByText('manual ready')).toBeInTheDocument()
    expect(screen.getByText('Manual UI ready')).toBeInTheDocument()
    expect(screen.getAllByText('Manual template').length).toBeGreaterThan(0)
    expect(screen.getByText('Record evidence')).toBeInTheDocument()
    expect(screen.getByText('brand_collision_present')).toBeInTheDocument()
    expect(screen.getByText(/synapsenetwork\.xyz/)).toBeInTheDocument()
    expect(screen.getByText('OPENAI_API_KEY')).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-release-unblock-plan')).toBeInTheDocument()
    expect(screen.getAllByText('blocked_until_gcloud_auth').length).toBeGreaterThan(0)
    expect(screen.getByTestId('ai-visibility-feed-cycle-matrix')).toBeInTheDocument()
    expect(screen.getAllByText('mcp_paid_api_discovery').length).toBeGreaterThan(0)
    expect(screen.queryByText('Provider Source Configs')).not.toBeInTheDocument()
  })
})

function optimizationPlan() {
  return {
    module_key: 'ai_visibility',
    objective: 'Make Synapse Network discoverable and citable in answer engines.',
    canonical_domain: 'https://www.synapse-network.ai/',
    critical_fixes: ['Use www canonical domain.'],
    baseline_queries: [{ query: 'What is Synapse Network?', intent: 'brand', target_platforms: ['chatgpt'], success_signal: 'Official citation appears.' }],
    feed_experiments: [{ feed_key: 'mcp_paid_api_discovery', surfaces: ['www'], content_assets: ['llms.txt'], target_queries: ['MCP paid API'], measurement_window_days: 14 }],
    product_docs: { canonical_domain: 'https://www.synapse-network.ai/', docs_category: 'MCP', pages: ['/mcp/paid-api-calls'], required_blocks: ['definition'], schema_types: ['FAQPage'] },
    design_plan: { stitch_prompt: 'Design MCP docs.', figma_handoff: ['Import Stitch output.'], implementation_targets: ['docs-front'] },
    growing_workflows: ['ai_visibility_search_probe'],
    success_criteria: ['Stable citations for three weekly runs.'],
  }
}

function feedPackage() {
  return {
    feed_key: 'mcp_paid_api_discovery',
    objective: 'Make MCP paid API queries cite Synapse docs.',
    canonical_domain: 'https://www.synapse-network.ai/',
    surfaces: ['www', 'docs'],
    content_assets: ['/mcp/paid-api-calls'],
    target_queries: ['MCP paid API'],
    publish_assets: [{ surface: 'docs', target: 'https://docs.synapse-network.ai/mcp/paid-api-calls', purpose: 'Docs source', validation: 'curl -fsS https://docs.synapse-network.ai/mcp/paid-api-calls' }],
    platform_strategies: [{ platform: 'chatgpt', feed_focus: 'Official docs citation.', preferred_surfaces: ['docs'], probe_queries: ['MCP paid API'], success_signal: 'ChatGPT cites docs.', fallback_action: 'Tighten definition.' }],
    stitch_prompt: 'Design technical docs.',
    figma_handoff: ['Import Stitch output.'],
    validation_commands: ['curl -fsS https://www.synapse-network.ai/llms.txt'],
    probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery',
    success_metrics: ['Citation observed.'],
    next_actions: ['Publish docs.'],
  }
}

function feedCycles() {
  return {
    module_key: 'ai_visibility',
    generated_at: '2026-06-05T00:00:00Z',
    target_platforms: ['chatgpt', 'claude', 'grok'],
    recommended_feed_key: 'mcp_paid_api_discovery',
    total: 1,
    items: [{
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
      blockers: ['Docs /mcp/paid-api-calls page must be live.'],
      next_actions: ['Resolve feed blockers before external probes.'],
      publish_surfaces: ['www', 'docs'],
      feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py --feed-key mcp_paid_api_discovery',
      manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery',
      api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery',
      api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --feed-key mcp_paid_api_discovery --execute',
      compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons?feed_key=mcp_paid_api_discovery"',
      latest_run_at: null,
    }],
  }
}

function feedScorecard() {
  return {
    module_key: 'ai_visibility',
    generated_at: '2026-06-05T00:00:00Z',
    recommended_feed_key: 'mcp_paid_api_discovery',
    ranking_basis: 'Impact score rewards feed readiness.',
    total: 1,
    items: [{ ...feedCycles().items[0], rank: 1, impact_score: 0, comparison_status: 'needs_external_probe', citation_quality_status: 'needs_external_probe', target_platforms: ['chatgpt'], covered_platforms: [], external_checks_count: 0, local_validation_count: 0, known_collision_competitors: [], official_cited_urls: [], mentioned_delta: 0, cited_delta: 0, recommended_action: 'Resolve feed blockers.' }],
  }
}

function liveReadiness() {
  return { module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', run_group: '2026-06-05-live-readiness', canonical_homepage: 'https://www.synapse-network.ai/', status: 'blocked', ready_count: 0, blocked_count: 1, validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py', apply_command: 'python scripts/growth/record_ai_visibility_probe.py', items: [], total: 0 }
}

function externalProbeGate() {
  return { module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-external', status: 'blocked_until_api_keys', ready_to_execute: false, partial_ready_to_execute: false, manual_ready_to_execute: true, feed_ready: true, api_keys_ready: false, target_platforms: ['chatgpt', 'claude', 'grok'], ready_platforms: [], missing_platforms: ['chatgpt', 'claude', 'grok'], provider_readiness: [{ platform: 'chatgpt', env_key: 'OPENAI_API_KEY', configured: false }], blockers: ['chatgpt missing OPENAI_API_KEY.'], feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py', record_readiness_command: 'python scripts/growth/record_ai_visibility_probe.py', manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery', api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py', api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --execute', partial_api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt', partial_api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt --execute', record_probe_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/external.jsonl --apply', compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"' }
}

function docsBlueprint() {
  return { category: 'AI Agent Payments', canonical_domain: 'https://www.synapse-network.ai/', target_repo: 'Synapse-Network', implementation_root: 'services/docs-front/content/docs/ai-agent-payments', pages: [{ slug: 'index', title: 'AI Agent Payments', canonical_url: 'https://docs.synapse-network.ai/ai-agent-payments', meta_description: 'Agent payments.', target_queries: ['AI agent payment API'], definition_block: 'Synapse Network is an agent payment layer.', fact_table: [], page_sections: ['Definition'], faq: [], schema_types: ['TechArticle'], stitch_notes: [], figma_components: [], mdx_skeleton: '# AI Agent Payments', validation_commands: [] }], shared_components: ['DefinitionBlock'], publishing_checklist: ['Implement MDX pages.'] }
}

function designHandoff() {
  return { title: 'Synapse AI Agent Payments Stitch To Figma Handoff', canonical_domain: 'https://www.synapse-network.ai/', source_tool: 'Stitch', target_tool: 'Figma', figma_file_name: 'Synapse AI Agent Payments Docs - AI Visibility', stitch_prompt: 'Design docs.', frames: [], component_specs: [], design_tokens: {}, import_steps: [], implementation_notes: [], acceptance_checks: [] }
}

function weeklyReport() {
  return { module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', goal_status: 'optimizing', goal_achieved: false, required_stable_runs: 3, stable_positive_runs: 0, target_platforms: ['chatgpt', 'claude', 'grok'], covered_platforms: [], missing_platforms: ['chatgpt', 'claude', 'grok'], total_external_checks: 0, total_mentioned_count: 0, total_cited_count: 0, latest_feed_key: 'mcp_paid_api_discovery', latest_run_group: '', latest_comparison_status: 'needs_external_probe', feed_reports: [], blockers: ['Fewer than three stable positive external runs have been recorded.'], next_actions: ['Run probes.'], recommended_feed_key: 'mcp_paid_api_discovery', recommended_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py' }
}

function nextCycle() {
  return { module_key: 'ai_visibility', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-mcp', output_path: 'docs/archive/evidence/growth/ai-visibility/run.jsonl', missing_platforms: ['chatgpt'], blockers: ['Docs page must be live.'], next_actions: ['Publish docs.'], validation_commands: [], feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py', manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py', api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py', api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --execute', apply_command: 'python scripts/growth/record_ai_visibility_probe.py --apply', compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"', weekly_report_command: 'python scripts/growth/export_ai_visibility_weekly_report.py' }
}

function releasePlan() {
  return { module_key: 'ai_visibility', feed_key: 'mcp_paid_api_discovery', status: 'blocked_until_gcloud_auth', generated_at: '2026-06-05T00:00:00Z', official_homepage: 'https://www.synapse-network.ai/', project_key: 'synapse-network', services: ['docs-front'], branch_name: 'main', target_commit_sha: 'd8b5371e', actor: 'codex', source_pr: { state: 'MERGED', url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/204' }, source_prs: [], predeploy_evidence: { status: 'target_branch_ready_live_prod_blocked', validations: [] }, deploy_readiness_status: 'ready_for_release_runner_after_gcloud_auth', deployment_gaps: [{ service_key: 'docs-front', status: 'production_behind_target' }], confirmed_facts: ['Official homepage canonical is https://www.synapse-network.ai/.'], hard_boundaries: ['Do not run gcloud run deploy directly.'], known_blockers: ['GCloud auth fails non-interactively.'], environment_defaults: {}, command_groups: [{ key: 'gcloud_auth', purpose: 'Restore auth.', commands: ['gcloud auth login'], service_key: '', environment: '', notes: [] }], success_criteria: ['llms.txt includes MCP feed.'] }
}

function releaseSnapshot() {
  return { module_key: 'ai_visibility', snapshot_type: 'release_blocker', generated_at: '2026-06-05T00:00:00Z', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-snapshot', target_commit_sha: 'd8b5371e', official_homepage: 'https://www.synapse-network.ai/', status: 'blocked', release_plan_status: 'blocked_until_gcloud_auth', deploy_readiness_status: 'ready_for_release_runner_after_gcloud_auth', confirmed_facts: [], deployment_gaps: [], live_readiness: {}, gcloud: {}, external_probe_keys: {}, blockers: ['GCloud auth fails non-interactively.'], next_actions: ['Run gcloud auth login.'] }
}

function handoffBundle() {
  return { module_key: 'ai_visibility', bundle_type: 'operator_handoff', generated_at: '2026-06-05T00:00:00Z', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-current', target_commit_sha: 'd8b5371e', official_homepage: 'https://www.synapse-network.ai/', status: 'blocked', release_status: 'blocked', live_readiness_status: 'blocked', external_probe_gate_status: 'blocked_until_feed_ready', ready_platforms: [], missing_platforms: ['chatgpt'], blockers: ['Docs page must be live.'], next_actions: ['Publish docs.'], files: { operator_brief: 'operator-brief.md' }, commands: { feed_validation: 'python scripts/growth/run_ai_visibility_feed_validation.py' } }
}

function optimizationBrief() {
  return { module_key: 'ai_visibility', title: 'Synapse AI Visibility Optimization Brief', status: 'blocked', generated_at: '2026-06-05T00:00:00Z', official_homepage: 'https://www.synapse-network.ai/', recommended_feed_key: 'mcp_paid_api_discovery', target_platforms: ['chatgpt'], blockers: ['Docs page must be live.'], next_actions: ['Publish docs.'], artifact_path: 'docs/archive/evidence/growth/ai-visibility/brief.md', export_command: 'python scripts/growth/generate_ai_visibility_optimization_brief.py', markdown: '# Synapse AI Visibility Optimization Brief' }
}

function comparison() {
  return { feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-mcp', previous_run_group: '', platforms: ['chatgpt'], external_platforms: ['chatgpt'], total_checks: 1, external_checks_count: 1, local_validation_count: 0, mentioned_count: 1, cited_count: 1, previous_mentioned_count: 0, previous_cited_count: 0, mentioned_delta: 1, cited_delta: 1, comparison_status: 'baseline', citation_quality_status: 'brand_collision_present', feed_effective: false, missing_platforms: ['claude', 'grok'], top_competitors: ['synapsenetwork.xyz'], known_collision_competitors: ['synapsenetwork.xyz'], official_cited_urls: ['https://www.synapse-network.ai/'], next_actions: ['Run probes.'], evidence_urls: [], latest_run_at: null }
}

function check() {
  return { id: 1, query: 'MCP paid API', platform: 'www_live_validation', answer_summary: 'Feed blocked.', synapse_mentioned: false, synapse_cited: false, cited_urls: [], competitor_mentions: [], missing_facts: ['Docs page must be live.'], next_action: 'Publish docs.', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-mcp', result_rank: 0, evidence_url: '', metadata: {}, run_at: null, created_at: null, updated_at: null }
}
