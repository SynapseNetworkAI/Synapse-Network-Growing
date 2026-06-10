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
    if (url.includes('/growth/ai-visibility/official-sources')) return json(officialSources())
    if (url.includes('/growth/ai-visibility/probe-matrix')) return json(probeMatrix())
    if (url.includes('/growth/ai-visibility/presence-plan')) return json(presencePlan())
    if (url.includes('/growth/ai-visibility/source-host-feed-package')) return json(sourceHostFeedPackage())
    if (url.includes('/growth/ai-visibility/source-host-execution-checklist')) return json(sourceHostExecutionChecklist())
    if (url.includes('/growth/ai-visibility/docs-blueprint')) return json(docsBlueprint())
    if (url.includes('/growth/ai-visibility/design-handoff')) return json(designHandoff())
    if (url.includes('/growth/ai-visibility/weekly-report')) return json(weeklyReport())
    if (url.includes('/growth/ai-visibility/next-cycle')) return json(nextCycle())
    if (url.includes('/growth/ai-visibility/goal-audit')) return json(goalAudit())
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
    expect(screen.getByTestId('ai-visibility-official-sources')).toBeInTheDocument()
    expect(screen.getByText('Citation authority surfaces')).toBeInTheDocument()
    expect(screen.getByText('remote_mcp')).toBeInTheDocument()
    expect(screen.getAllByText('https://mcp.synapse-network.ai/mcp').length).toBeGreaterThan(0)
    expect(screen.getByTestId('ai-visibility-probe-matrix')).toBeInTheDocument()
    expect(screen.getByText('Answer-engine probe matrix')).toBeInTheDocument()
    expect(screen.getByText('ready_to_probe')).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-presence-plan')).toBeInTheDocument()
    expect(screen.getByText('Source-host presence plan')).toBeInTheDocument()
    expect(screen.getByText('Submit: https://mcpservers.org/submit')).toBeInTheDocument()
    expect(screen.getByText(/Payload: server_name, remote_mcp_endpoint/)).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-source-host-feed-package')).toBeInTheDocument()
    expect(screen.getByText('Source-host feed package')).toBeInTheDocument()
    expect(screen.getByText('Synapse Network MCP Server')).toBeInTheDocument()
    expect(screen.getByText(/ready_to_submit/)).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-source-host-execution-checklist')).toBeInTheDocument()
    expect(screen.getByText('Source-host execution checklist')).toBeInTheDocument()
    expect(screen.getByText('pending_submission')).toBeInTheDocument()
    expect(screen.getByText('GitHub repository URL')).toBeInTheDocument()
    expect(screen.getByText(/Record submission confirmation with --surface mcpservers_org/)).toBeInTheDocument()
    expect(screen.getByText(/Live search: https:\/\/mcpservers\.org\/\?q=Synapse%20Network/)).toBeInTheDocument()
    expect(screen.getByText(/Live gate: Open the search URLs/)).toBeInTheDocument()
    expect(screen.getAllByText('mcpservers.org').length).toBeGreaterThan(0)
    expect(screen.getByText('directory_listing')).toBeInTheDocument()
    expect(screen.getAllByText('Source-host action targets').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/mcp_directory_listing/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/mcpservers/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/MCPServers appeared in answer-engine source hosts/).length).toBeGreaterThan(0)
    expect(screen.getByText('brand_collision_present')).toBeInTheDocument()
    expect(screen.getByText(/synapsenetwork\.xyz/)).toBeInTheDocument()
    expect(screen.getByText('OPENAI_API_KEY')).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-release-unblock-plan')).toBeInTheDocument()
    expect(screen.getAllByText('production_jsonld_verified').length).toBeGreaterThan(0)
    expect(screen.getByText('Pending source PRs')).toBeInTheDocument()
    expect(screen.getAllByText('No pending source PRs.').length).toBeGreaterThan(0)
    expect(screen.getByText('post_publish_indexnow_submission')).toBeInTheDocument()
    expect(screen.getByText(/submit_indexnow_ai_visibility\.mjs --execute/)).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-feed-cycle-matrix')).toBeInTheDocument()
    expect(screen.getByText('Probe matrix')).toBeInTheDocument()
    expect(screen.getByText('Validate matrix')).toBeInTheDocument()
    expect(screen.getByTestId('ai-visibility-goal-audit')).toBeInTheDocument()
    expect(screen.getByText('Objective still requires external evidence')).toBeInTheDocument()
    expect(screen.getByText('GPT/Claude/Grok/Gemini search evidence')).toBeInTheDocument()
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
    target_platforms: ['chatgpt', 'claude', 'grok', 'gemini'],
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
      missing_platforms: ['chatgpt', 'claude', 'grok', 'gemini'],
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
    items: [{
      ...feedCycles().items[0],
      rank: 1,
      impact_score: 0,
      comparison_status: 'needs_external_probe',
      citation_quality_status: 'needs_external_probe',
      target_platforms: ['chatgpt'],
      covered_platforms: [],
      external_checks_count: 0,
      local_validation_count: 0,
      known_collision_competitors: [],
      official_cited_urls: [],
      source_host_actions: [sourceHostAction()],
      mentioned_delta: 0,
      cited_delta: 0,
      recommended_action: 'Resolve feed blockers.',
    }],
  }
}

function liveReadiness() {
  return { module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', run_group: '2026-06-05-live-readiness', canonical_homepage: 'https://www.synapse-network.ai/', status: 'blocked', ready_count: 0, blocked_count: 1, validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py', apply_command: 'python scripts/growth/record_ai_visibility_probe.py', items: [], total: 0 }
}

function externalProbeGate() {
  return { module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-external', status: 'blocked_until_api_keys', ready_to_execute: false, partial_ready_to_execute: false, manual_ready_to_execute: true, feed_ready: true, api_keys_ready: false, target_platforms: ['chatgpt', 'claude', 'grok', 'gemini'], ready_platforms: [], missing_platforms: ['chatgpt', 'claude', 'grok', 'gemini'], provider_readiness: [{ platform: 'chatgpt', env_key: 'OPENAI_API_KEY', configured: false }, { platform: 'gemini', env_key: 'GEMINI_API_KEY', configured: false }], blockers: ['chatgpt missing OPENAI_API_KEY.', 'gemini missing GEMINI_API_KEY.'], feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py', record_readiness_command: 'python scripts/growth/record_ai_visibility_probe.py', manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery --platforms chatgpt,claude,grok,gemini', api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok,gemini', api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok,gemini --execute', partial_api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt', partial_api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt --execute', record_probe_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/external.jsonl --apply', compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"' }
}

function officialSources() {
  return {
    module_key: 'ai_visibility',
    generated_at: '2026-06-05T00:00:00Z',
    official_citation_prefixes: ['https://www.synapse-network.ai/', 'https://docs.synapse-network.ai/', 'https://mcp.synapse-network.ai/'],
    total: 2,
    items: [
      { surface_key: 'www_homepage', surface: 'www', canonical_url: 'https://www.synapse-network.ai/', citation_role: 'Primary canonical.', feed_keys: ['brand_disambiguation_www'], required_for_success: true, validation_command: 'curl -fsS https://www.synapse-network.ai/', acceptance_signal: 'Homepage has facts.' },
      { surface_key: 'remote_mcp', surface: 'mcp', canonical_url: 'https://mcp.synapse-network.ai/mcp', citation_role: 'Hosted Remote MCP endpoint.', feed_keys: ['mcp_paid_api_discovery'], required_for_success: true, validation_command: 'curl -fsS https://mcp.synapse-network.ai/readyz', acceptance_signal: 'readyz is 200 and /mcp is 401.' },
    ],
  }
}

function probeMatrix() {
  return {
    module_key: 'ai_visibility',
    generated_at: '2026-06-05T00:00:00Z',
    target_platforms: ['chatgpt', 'claude', 'grok', 'gemini'],
    recommended_feed_key: 'mcp_paid_api_discovery',
    total: 1,
    rows: [{
      feed_key: 'mcp_paid_api_discovery',
      platform: 'chatgpt',
      status: 'ready_to_probe',
      run_group: '2026-06-05-mcp-weekly',
      queries: ['MCP server for paid API calls'],
      official_source_urls: ['https://www.synapse-network.ai/', 'https://mcp.synapse-network.ai/mcp'],
      success_decision_rule: 'Success requires an official citation.',
      manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery',
      record_probe_command: 'python scripts/growth/record_ai_visibility_probe.py docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly.jsonl --apply',
      compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"',
      evidence_directory: 'docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-weekly',
      blockers: [],
      next_actions: ['Run the chatgpt probe with unchanged query wording.'],
    }],
  }
}

function presencePlan() {
  return {
    module_key: 'ai_visibility',
    generated_at: '2026-06-05T00:00:00Z',
    feed_key: 'mcp_paid_api_discovery',
    run_group: '2026-06-06-source-hosts',
    status: 'ready_for_presence_work',
    source_hosts: ['mcpservers.org', 'docs.mcpay.tech'],
    actions: [{
      host: 'mcpservers.org',
      priority: 1,
      action_type: 'directory_listing',
      ownership: 'submittable',
      rationale: 'ChatGPT cited this MCP directory for paid MCP queries.',
      target_surface: 'https://mcpservers.org/',
      asset: 'Synapse Remote MCP listing metadata.',
      copy_points: ['Remote MCP endpoint: https://mcp.synapse-network.ai/mcp'],
      validation_command: 'curl -fsS "https://mcpservers.org/" | grep -i synapse',
      probe_followup: 'Rerun unchanged probes.',
      submit_url: 'https://mcpservers.org/submit',
      source_reference_url: 'https://mcpservers.org/submit',
      submission_payload: {
        server_name: 'Synapse Network MCP Server',
        remote_mcp_endpoint: 'https://mcp.synapse-network.ai/mcp',
        contact_email: '<operator email>',
      },
      operator_notes: [],
    }],
    blockers: [],
    validation_commands: ['python scripts/growth/run_ai_visibility_feed_validation.py'],
    next_probe_command: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok,gemini --execute',
    compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"',
  }
}

function sourceHostExecutionChecklist() {
  return {
    module_key: 'ai_visibility',
    checklist_type: 'source_host_feed_execution',
    generated_at: '2026-06-05T00:00:00Z',
    feed_key: 'mcp_paid_api_discovery',
    run_group: '2026-06-06-source-hosts',
    status: 'ready_for_operator_execution',
    items: [{
      key: '01-mcpservers.org-directory_submission',
      host: 'mcpservers.org',
      priority: 1,
      draft_type: 'directory_submission',
      execution_status: 'pending_submission',
      target_url: 'https://mcpservers.org/submit',
      design_handoff_frame: 'Directory Source-Host Submission Pack',
      action_required: 'Submit the directory form using the non-secret payload.',
      submission_fields: [
        { label: 'GitHub repository URL', value: 'https://github.com/SynapseNetworkAI/Synapse-Network-MCP-Server', notes: 'Use the public repo.' },
        { label: 'Remote MCP endpoint', value: 'https://mcp.synapse-network.ai/mcp', notes: 'Put in description if needed.' },
      ],
      submission_steps: ['Open https://mcpservers.org/submit in an operator-owned browser session.'],
      evidence_recording_steps: ['Record submission confirmation with --surface mcpservers_org.'],
      live_listing_search_urls: ['https://mcpservers.org/?q=Synapse%20Network'],
      live_listing_validation_steps: ['Open the search URLs and confirm a public listing page.'],
      required_evidence: ['submission_url_or_receipt', 'submitted_payload_summary', 'screenshot'],
      submission_confirmation_command: 'python scripts/growth/record_ai_visibility_source_host_execution.py --evidence-mode submission-confirmation',
      validation_command: 'curl -fsS "https://mcpservers.org/" | grep -i synapse',
      re_probe_command: 'python scripts/growth/run_ai_visibility_api_probe.py --execute',
      completion_gate: 'Do not mark complete until operator evidence proves the listing is live.',
    }],
    blockers: [],
    commands: {},
  }
}

function sourceHostFeedPackage() {
  return {
    module_key: 'ai_visibility',
    package_type: 'source_host_feed',
    generated_at: '2026-06-05T00:00:00Z',
    feed_key: 'mcp_paid_api_discovery',
    run_group: '2026-06-06-source-hosts',
    status: 'ready_for_operator_feed',
    source_hosts: ['mcpservers.org'],
    drafts: [{
      host: 'mcpservers.org',
      priority: 1,
      draft_type: 'directory_submission',
      status: 'ready_to_submit',
      target_url: 'https://mcpservers.org/submit',
      submit_url: 'https://mcpservers.org/submit',
      title: 'Synapse Network MCP Server',
      summary: 'Synapse Network Remote MCP lets AI agents discover payable APIs.',
      body_markdown: '# Synapse Network MCP Server',
      source_reference_url: 'https://mcpservers.org/submit',
      submission_payload: { server_name: 'Synapse Network MCP Server' },
      validation_command: 'curl -fsS "https://mcpservers.org/" | grep -i synapse',
      probe_followup: 'Rerun unchanged probes.',
      operator_notes: [],
    }],
    blockers: [],
    commands: {
      after_feed_probe: 'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok,gemini --execute',
    },
  }
}

function docsBlueprint() {
  return { category: 'AI Agent Payments', canonical_domain: 'https://www.synapse-network.ai/', target_repo: 'Synapse-Network', implementation_root: 'services/docs-front/content/docs/ai-agent-payments', pages: [{ slug: 'index', title: 'AI Agent Payments', canonical_url: 'https://docs.synapse-network.ai/ai-agent-payments', meta_description: 'Agent payments.', target_queries: ['AI agent payment API'], definition_block: 'Synapse Network is an agent payment layer.', fact_table: [], page_sections: ['Definition'], faq: [], schema_types: ['TechArticle'], stitch_notes: [], figma_components: [], mdx_skeleton: '# AI Agent Payments', validation_commands: [] }], shared_components: ['DefinitionBlock'], publishing_checklist: ['Implement MDX pages.'] }
}

function designHandoff() {
  return { title: 'Synapse AI Agent Payments Stitch To Figma Handoff', canonical_domain: 'https://www.synapse-network.ai/', source_tool: 'Stitch', target_tool: 'Figma', figma_file_name: 'Synapse AI Agent Payments Docs - AI Visibility', stitch_prompt: 'Design docs.', frames: [], component_specs: [], design_tokens: {}, import_steps: [], implementation_notes: [], acceptance_checks: [] }
}

function weeklyReport() {
  return { module_key: 'ai_visibility', generated_at: '2026-06-05T00:00:00Z', goal_status: 'optimizing', goal_achieved: false, required_stable_runs: 3, stable_positive_runs: 0, target_platforms: ['chatgpt', 'claude', 'grok', 'gemini'], covered_platforms: [], missing_platforms: ['chatgpt', 'claude', 'grok', 'gemini'], total_external_checks: 0, total_mentioned_count: 0, total_cited_count: 0, latest_feed_key: 'mcp_paid_api_discovery', latest_run_group: '', latest_comparison_status: 'needs_external_probe', feed_reports: [], blockers: ['Fewer than three stable positive external runs have been recorded.'], next_actions: ['Run probes.'], recommended_feed_key: 'mcp_paid_api_discovery', recommended_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py' }
}

function nextCycle() {
  return {
    module_key: 'ai_visibility',
    feed_key: 'mcp_paid_api_discovery',
    run_group: '2026-06-05-mcp',
    output_path: 'docs/archive/evidence/growth/ai-visibility/run.jsonl',
    missing_platforms: ['chatgpt'],
    blockers: ['Docs page must be live.'],
    next_actions: ['Publish docs.'],
    validation_commands: [],
    feed_validation_command: 'python scripts/growth/run_ai_visibility_feed_validation.py',
    manual_probe_template_command: 'python scripts/growth/generate_ai_visibility_probe_template.py',
    external_probe_gate_command: 'python scripts/growth/generate_ai_visibility_external_probe_gate.py',
    api_readiness_command: 'python scripts/growth/run_ai_visibility_api_probe.py',
    api_execute_command: 'python scripts/growth/run_ai_visibility_api_probe.py --execute',
    public_web_search_import_command: 'python scripts/growth/import_ai_visibility_public_search_snapshot.py snapshot.json --output public-web-search.jsonl',
    apply_command: 'python scripts/growth/record_ai_visibility_probe.py --apply',
    probe_matrix_command: 'python scripts/growth/generate_ai_visibility_probe_matrix.py --output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-probe-matrix.json',
    validate_matrix_command: 'python scripts/growth/validate_ai_visibility_probe_matrix.py docs/archive/evidence/growth/ai-visibility/run.jsonl --matrix-file docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-probe-matrix.json',
    cycle_summary_command: 'python scripts/growth/summarize_ai_visibility_cycle.py docs/archive/evidence/growth/ai-visibility/run.jsonl --output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-cycle-summary.json',
    operator_brief_command: 'python scripts/growth/generate_ai_visibility_operator_brief.py --feed-key mcp_paid_api_discovery --cycle-summary docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-cycle-summary.json --output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-operator-brief.md',
    goal_audit_command: 'python scripts/growth/generate_ai_visibility_goal_audit.py --output docs/archive/evidence/growth/ai-visibility/2026-06-05-mcp-goal-audit.json',
    compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"',
    weekly_report_command: 'python scripts/growth/export_ai_visibility_weekly_report.py',
  }
}

function pendingSourcePrs() {
  return []
}

function pendingPublicationGaps() {
  return [
    { surface: 'www-jsonld', url: 'https://www.synapse-network.ai/mcp-server-for-paid-api-calls', current_status: 200, expected_after_merge: 200, source_pr: 216, next_action: 'Deploy merged source PR #216.' },
    { surface: 'www-jsonld', url: 'https://www.synapse-network.ai/chatgpt-mcp-app-api-payments', current_status: 200, expected_after_merge: 200, source_pr: 216, next_action: 'Deploy merged source PR #216.' },
  ]
}

function releasePlan() {
  return { module_key: 'ai_visibility', feed_key: 'mcp_paid_api_discovery', status: 'production_jsonld_verified', generated_at: '2026-06-05T00:00:00Z', official_homepage: 'https://www.synapse-network.ai/', project_key: 'synapse-network', services: ['user-front'], branch_name: 'main', target_commit_sha: '09a8e5f', actor: 'codex', source_pr: { number: 216, state: 'MERGED', url: 'https://github.com/SynapseNetworkAI/Synapse-Network/pull/216' }, source_prs: [{ number: 216, state: 'MERGED', merge_commit: '09a8e5fcb1511ca19b2ec417474ba5e780510469' }], pending_source_prs: pendingSourcePrs(), predeploy_evidence: { status: 'target_branch_ready_live_prod_blocked', validations: [] }, deploy_readiness_status: 'production_jsonld_verified', deployment_gaps: [{ service_key: 'user-front', status: 'staging_and_production_at_target' }], pending_publication_gaps: [], verified_publication_surfaces: pendingPublicationGaps(), confirmed_facts: ['Official homepage canonical is https://www.synapse-network.ai/.', 'Production user-front release task #253 deployed commit 09a8e5fcb151.'], hard_boundaries: ['Do not run gcloud run deploy directly.'], known_blockers: [], environment_defaults: {}, command_groups: [{ key: 'post_publish_indexnow_submission', purpose: 'Submit IndexNow.', commands: ['node /private/tmp/synapse-ai-visibility-publish/scripts/seo/submit_indexnow_ai_visibility.mjs', 'node /private/tmp/synapse-ai-visibility-publish/scripts/seo/submit_indexnow_ai_visibility.mjs --execute | tee docs/archive/evidence/growth/ai-visibility/2026-06-05-after-prod-indexnow.json'], service_key: '', environment: '', notes: [] }], success_criteria: ['llms.txt includes MCP feed.', 'IndexNow submission runs after production validation.'] }
}

function releaseSnapshot() {
  return { module_key: 'ai_visibility', snapshot_type: 'release_blocker', generated_at: '2026-06-05T00:00:00Z', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-snapshot', target_commit_sha: '09a8e5f', official_homepage: 'https://www.synapse-network.ai/', status: 'blocked', release_plan_status: 'production_jsonld_verified', deploy_readiness_status: 'production_jsonld_verified', confirmed_facts: [], deployment_gaps: [], pending_source_prs: pendingSourcePrs(), pending_publication_gaps: [], verified_publication_surfaces: pendingPublicationGaps(), live_readiness: {}, gcloud: {}, external_probe_keys: {}, blockers: ['chatgpt external probe key missing: OPENAI_API_KEY.'], next_actions: ['Run external answer-engine probes.'] }
}

function handoffBundle() {
  return { module_key: 'ai_visibility', bundle_type: 'operator_handoff', generated_at: '2026-06-05T00:00:00Z', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-current', target_commit_sha: 'd8b5371e', official_homepage: 'https://www.synapse-network.ai/', status: 'blocked', release_status: 'blocked', live_readiness_status: 'blocked', external_probe_gate_status: 'blocked_until_feed_ready', goal_audit_status: 'incomplete', goal_achieved: false, ready_platforms: [], missing_platforms: ['chatgpt'], blockers: ['Docs page must be live.'], next_actions: ['Publish docs.'], files: { operator_brief: 'operator-brief.md', goal_audit: 'goal-audit.json' }, commands: { feed_validation: 'python scripts/growth/run_ai_visibility_feed_validation.py', goal_audit: 'python scripts/growth/generate_ai_visibility_goal_audit.py' } }
}

function optimizationBrief() {
  return { module_key: 'ai_visibility', title: 'Synapse AI Visibility Optimization Brief', status: 'blocked', generated_at: '2026-06-05T00:00:00Z', official_homepage: 'https://www.synapse-network.ai/', recommended_feed_key: 'mcp_paid_api_discovery', target_platforms: ['chatgpt'], blockers: ['Docs page must be live.'], next_actions: ['Publish docs.'], artifact_path: 'docs/archive/evidence/growth/ai-visibility/brief.md', export_command: 'python scripts/growth/generate_ai_visibility_optimization_brief.py', markdown: '# Synapse AI Visibility Optimization Brief' }
}

function goalAudit() {
  return {
    module_key: 'ai_visibility',
    generated_at: '2026-06-05T00:00:00Z',
    status: 'incomplete',
    goal_achieved: false,
    official_homepage: 'https://www.synapse-network.ai/',
    target_platforms: ['chatgpt', 'claude', 'grok', 'gemini'],
    completed_count: 5,
    total_required: 8,
    requirements: [
      { key: 'strategy', title: 'Agent optimization strategy', status: 'completed', required: true, evidence: '3 feed experiments.', blocker: '', next_action: '' },
      { key: 'external_search_evidence', title: 'GPT/Claude/Grok/Gemini search evidence', status: 'blocked', required: true, evidence: '', blocker: 'Missing real external GPT/Claude/Grok/Gemini evidence.', next_action: 'Run full external probes and record evidence.' },
    ],
    blockers: ['Missing real external GPT/Claude/Grok/Gemini evidence.'],
    next_actions: ['Run full external probes and record evidence.'],
    export_command: 'python scripts/growth/generate_ai_visibility_goal_audit.py',
  }
}

function comparison() {
  return { feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-mcp', previous_run_group: '', platforms: ['chatgpt'], external_platforms: ['chatgpt'], total_checks: 1, external_checks_count: 1, local_validation_count: 0, mentioned_count: 1, cited_count: 1, previous_mentioned_count: 0, previous_cited_count: 0, mentioned_delta: 1, cited_delta: 1, comparison_status: 'baseline', citation_quality_status: 'brand_collision_present', feed_effective: false, missing_platforms: ['claude', 'grok'], top_competitors: ['synapsenetwork.xyz'], source_hosts: ['mcpservers.org'], source_host_actions: [sourceHostAction()], known_collision_competitors: ['synapsenetwork.xyz'], official_cited_urls: ['https://www.synapse-network.ai/'], next_actions: ['Run probes.'], evidence_urls: [], latest_run_at: null }
}

function check() {
  return { id: 1, query: 'MCP paid API', platform: 'www_live_validation', answer_summary: 'Feed blocked.', synapse_mentioned: false, synapse_cited: false, cited_urls: [], competitor_mentions: [], missing_facts: ['Docs page must be live.'], next_action: 'Publish docs.', feed_key: 'mcp_paid_api_discovery', run_group: '2026-06-05-mcp', result_rank: 0, evidence_url: '', metadata: {}, run_at: null, created_at: null, updated_at: null }
}

function sourceHostAction() {
  return {
    host: 'mcpservers.org',
    surface: 'mcpservers',
    observed_count: 2,
    priority: 'p0',
    draft_type: 'mcp_directory_listing',
    rationale: 'MCPServers appeared in answer-engine source hosts for paid-MCP discovery queries, so Synapse needs a matching MCP directory listing.',
  }
}
