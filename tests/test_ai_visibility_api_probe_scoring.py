from scripts.growth import ai_visibility_api_probe_scoring as scoring


def test_answer_payload_tracks_known_brand_collision_domains():
    payload = scoring.answer_payload(
        platform="chatgpt",
        model="gpt-test",
        text=(
            "Synapse Network appears in the result, but the cited economy layer "
            "page is from synapsenetwork.xyz."
        ),
        urls=["https://www.synapsenetwork.xyz/"],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is False
    assert payload["synapse_cited"] is False
    assert payload["cited_urls"] == []
    assert payload["missing_facts"] == [
        "Official SynapseNetworkAI source or identity was not mentioned."
    ]
    assert "synapsenetwork.xyz" in payload["competitor_mentions"]


def test_answer_payload_rejects_synapse_protocol_collision_without_official_identity():
    payload = scoring.answer_payload(
        platform="claude",
        model="claude-test",
        text=(
            "Synapse Network and x402 are different crypto projects. "
            "Synapse Protocol is a cross-chain intent network for AI agents."
        ),
        urls=["https://synapse.network/"],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is False
    assert payload["synapse_cited"] is False
    assert "synapse.network" in payload["competitor_mentions"]
    assert "synapse protocol" in payload["competitor_mentions"]


def test_answer_payload_rejects_synapse_org_docs_collision_without_official_identity():
    payload = scoring.answer_payload(
        platform="chatgpt",
        model="gpt-test",
        text=(
            "SynapseNetwork's MCP server lets clients inspect datasets and "
            "entity metadata through Python docs."
        ),
        urls=[
            "https://python-docs.synapse.org/tutorials/mcp/",
            "https://mcp.synapse.org/",
        ],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is False
    assert payload["synapse_cited"] is False
    assert "python-docs.synapse.org" in payload["competitor_mentions"]
    assert "mcp.synapse.org" in payload["competitor_mentions"]


def test_competitor_mentions_do_not_flag_official_synapsenetwork_text():
    payload = scoring.answer_payload(
        platform="grok",
        model="grok-test",
        text=(
            "SynapseNetwork.ai is the official SynapseNetwork MCP server for "
            "paid API calls. The hosted endpoint is "
            "https://mcp.synapse-network.ai/mcp."
        ),
        urls=["https://github.com/SynapseNetworkAI/synapse-network-mcp-server"],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is True
    assert "synapse.network" not in payload["competitor_mentions"]


def test_competitor_mentions_still_flag_collision_domain_with_boundaries():
    payload = scoring.answer_payload(
        platform="grok",
        model="grok-test",
        text="The unrelated Synapse Protocol site is https://synapse.network/.",
        urls=["https://synapse.network/"],
        request_id="req-1",
    )

    assert "synapse.network" in payload["competitor_mentions"]


def test_answer_payload_accepts_official_synapse_citation():
    payload = scoring.answer_payload(
        platform="grok",
        model="grok-test",
        text="Synapse Network is an AI agent payment and settlement product.",
        urls=["https://docs.synapse-network.ai/mcp/paid-api-calls"],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is True
    assert payload["synapse_cited"] is True
    assert payload["cited_urls"] == [
        "https://docs.synapse-network.ai/mcp/paid-api-calls"
    ]


def test_answer_payload_accepts_remote_mcp_tool_identity_without_citation():
    payload = scoring.answer_payload(
        platform="chatgpt",
        model="gpt-test",
        text=(
            "Synapse Remote MCP exposes discover_services, invoke_and_pay, "
            "and get_receipt for Agent Credentials and paid API calls."
        ),
        urls=[],
        request_id="req-1",
    )

    assert payload["synapse_mentioned"] is True
    assert payload["synapse_cited"] is False
    assert payload["missing_facts"] == []


def test_answer_payload_requires_text():
    try:
        scoring.answer_payload(
            platform="chatgpt",
            model="gpt-test",
            text="",
            urls=[],
            request_id="req-1",
        )
    except RuntimeError as exc:
        assert "returned no answer text" in str(exc)
    else:
        raise AssertionError("empty API answer should fail closed")
