export function presencePlan() {
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
    next_probe_command:
      'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok,gemini --execute',
    compare_command: 'curl -fsS "http://localhost:9700/api/growth/ai-visibility/comparisons"',
  }
}

export function sourceHostExecutionChecklist() {
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

export function sourceHostFeedPackage() {
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
      after_feed_probe:
        'python scripts/growth/run_ai_visibility_api_probe.py --platforms chatgpt,claude,grok,gemini --execute',
    },
  }
}
