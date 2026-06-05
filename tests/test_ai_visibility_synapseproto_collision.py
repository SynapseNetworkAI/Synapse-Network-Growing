from scripts.growth import run_ai_visibility_api_probe as api_probe
from scripts.growth.generate_ai_visibility_probe_template import (
    KNOWN_COLLISION_DOMAINS,
    generate_records,
)
from scripts.growth.import_ai_visibility_public_search_snapshot import (
    records_from_snapshot,
)
from server.services.growth.ai_visibility_comparison_helpers import (
    KNOWN_BRAND_COLLISION_COMPETITORS,
)
from server.services.growth.ai_visibility_plan import (
    ai_visibility_feed_packages,
    ai_visibility_optimization_plan,
)


SNAPSHOT = {
    "snapshot_type": "public_web_search_visibility",
    "observed_at": "2026-06-05T22:29:25Z",
    "feed_key": "mcp_paid_api_discovery",
    "run_group": "2026-06-06-synapseproto-drift",
    "official_homepage": "https://www.synapse-network.ai/",
    "queries": [
        {
            "query": "Synapse Network AI agent payments",
            "synapse_found_in_returned_results": False,
            "observed_competitors_or_adjacent_results": [
                {
                    "name": "Synapse Protocol",
                    "url": "https://www.synapseproto.com/",
                }
            ],
        }
    ],
    "next_actions": ["Add Synapse Protocol disambiguation copy."],
}


def test_synapseproto_is_known_brand_collision_in_probe_metadata():
    records = generate_records(
        feed_key="mcp_paid_api_discovery",
        run_group="2026-06-06-synapseproto-drift",
        platforms=["chatgpt"],
        queries=["Synapse Network AI agent payments"],
        mode="after-feed",
    )

    assert "synapseproto.com" in KNOWN_COLLISION_DOMAINS
    assert "synapseproto.com" in records[0].metadata["known_collision_domains"]


def test_synapseproto_collision_does_not_count_as_synapse_citation():
    payload = api_probe.answer_payload(
        platform="chatgpt",
        model="gpt-test",
        text="Synapse Protocol is a settlement layer for AI agent transactions.",
        urls=["https://www.synapseproto.com/"],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is False
    assert payload["synapse_cited"] is False
    assert "synapseproto.com" in payload["competitor_mentions"]


def test_public_search_snapshot_records_synapseproto_competitor():
    records = records_from_snapshot(
        SNAPSHOT,
        source_path=(
            "docs/archive/evidence/growth/ai-visibility/"
            "2026-06-06-public-web-search-snapshot-synapseproto-drift.json"
        ),
    )

    assert records[0].platform == "public_web_search"
    assert records[0].synapse_mentioned is False
    assert records[0].competitor_mentions == ["Synapse Protocol"]
    assert records[0].metadata["result_urls"] == ["https://www.synapseproto.com/"]


def test_ai_visibility_plan_names_synapse_protocol_collision():
    plan = ai_visibility_optimization_plan()
    package = ai_visibility_feed_packages("brand_disambiguation_www").items[0]

    assert "synapseproto.com" in KNOWN_BRAND_COLLISION_COMPETITORS
    assert any("Synapse Protocol" in fix for fix in plan.critical_fixes)
    assert any("synapseproto.com" in action for action in package.next_actions)
