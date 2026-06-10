{
  "module_key": "ai_visibility",
  "generated_at": "2026-06-09T14:51:01.150930Z",
  "goal_status": "optimizing",
  "goal_achieved": false,
  "required_stable_runs": 3,
  "stable_positive_runs": 0,
  "target_platforms": [
    "chatgpt",
    "claude",
    "grok",
    "gemini"
  ],
  "covered_platforms": [
    "chatgpt",
    "claude",
    "gemini",
    "grok"
  ],
  "missing_platforms": [],
  "total_external_checks": 542,
  "total_mentioned_count": 67,
  "total_cited_count": 16,
  "latest_feed_key": "agent_payment_category_pages",
  "latest_run_group": "2026-06-09-after-indexnow-live-disambiguation",
  "latest_comparison_status": "improved",
  "feed_reports": [
    {
      "feed_key": "agent_payment_category_pages",
      "latest_run_group": "2026-06-09-after-indexnow-live-disambiguation",
      "comparison_status": "improved",
      "citation_quality_status": "brand_collision_present",
      "feed_effective": false,
      "external_platforms": [
        "chatgpt"
      ],
      "missing_platforms": [
        "claude",
        "grok",
        "gemini"
      ],
      "known_collision_competitors": [
        "synapse.network"
      ],
      "source_hosts": [
        "agent402.dev",
        "augmentcode.com",
        "deepwiki.com",
        "developer.plugsurfing.com",
        "docs.spacelift.io",
        "docs.x.ai",
        "github.com",
        "glama.ai",
        "mcpservers.org"
      ],
      "official_cited_urls": [],
      "mentioned_count": 2,
      "cited_count": 0,
      "mentioned_delta": 2,
      "cited_delta": 0,
      "latest_run_at": "2026-06-09T14:50:48.328035",
      "next_actions": [
        "Compare against previous run group and keep feeding cited surfaces.",
        "Prioritize third-party presence on cited answer-engine hosts: agent402.dev, augmentcode.com, deepwiki.com."
      ]
    },
    {
      "feed_key": "mcp_paid_api_discovery",
      "latest_run_group": "2026-06-09-after-challenge-failclosed-refresh5",
      "comparison_status": "flat",
      "citation_quality_status": "missing_official_citation",
      "feed_effective": false,
      "external_platforms": [
        "chatgpt",
        "claude",
        "gemini",
        "grok"
      ],
      "missing_platforms": [],
      "known_collision_competitors": [],
      "source_hosts": [
        "mcp.directory",
        "docs.mcpay.tech",
        "alternativeto.net",
        "anythingmcp.com",
        "arxiv.org",
        "chatforest.com",
        "coincodecap.com",
        "mcp-marketplace.io",
        "mcpservers.org"
      ],
      "official_cited_urls": [],
      "mentioned_count": 0,
      "cited_count": 0,
      "mentioned_delta": 0,
      "cited_delta": 0,
      "latest_run_at": "2026-06-09T11:10:46.340466",
      "next_actions": [
        "Fix provider/API probe failure and rerun the same query.",
        "Deploy/refresh feed assets and rerun the same API probe.",
        "Prioritize third-party presence on cited answer-engine hosts: mcp.directory, docs.mcpay.tech, alternativeto.net."
      ]
    },
    {
      "feed_key": "brand_disambiguation_www",
      "latest_run_group": "2026-06-08-full-after-citation-facts-pr",
      "comparison_status": "improved",
      "citation_quality_status": "missing_official_citation",
      "feed_effective": false,
      "external_platforms": [
        "chatgpt",
        "claude",
        "gemini",
        "grok"
      ],
      "missing_platforms": [],
      "known_collision_competitors": [],
      "source_hosts": [
        "vertexaisearch.cloud.google.com",
        "w3.org",
        "mcp.so",
        "github.com",
        "agenticcontrolplane.com",
        "chat.mcp.so",
        "dock0.dev",
        "docs.mcpay.tech",
        "mcpservers.org"
      ],
      "official_cited_urls": [],
      "mentioned_count": 5,
      "cited_count": 0,
      "mentioned_delta": 2,
      "cited_delta": 0,
      "latest_run_at": "2026-06-08T05:03:19.823596",
      "next_actions": [
        "Compare against previous run group and keep feeding cited surfaces.",
        "Fix provider/API probe failure and rerun the same query.",
        "Prioritize third-party presence on cited answer-engine hosts: vertexaisearch.cloud.google.com, w3.org, mcp.so."
      ]
    }
  ],
  "blockers": [
    "Fewer than three stable positive external runs have been recorded.",
    "Known Synapse brand collision results still appear in external probe evidence: synapse.network."
  ],
  "next_actions": [
    "Fix provider/API probe failure and rerun the same query.",
    "Deploy/refresh feed assets and rerun the same API probe.",
    "Add or strengthen disambiguation copy for known collision domains: synapse.network."
  ],
  "recommended_feed_key": "mcp_paid_api_discovery",
  "recommended_probe_template_command": "python scripts/growth/generate_ai_visibility_probe_template.py --feed-key mcp_paid_api_discovery --run-group YYYY-MM-DD-weekly --mode after-feed --output docs/archive/evidence/growth/ai-visibility/YYYY-MM-DD-weekly.jsonl"
}
