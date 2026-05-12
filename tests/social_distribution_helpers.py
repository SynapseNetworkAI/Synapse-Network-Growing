from server.services.social.agent_content_pack import (
    AgentDistributionDraft,
    CanonicalAssetPack,
)


def patch_agent_distribution(monkeypatch):
    def fake_platform_draft(**kwargs):
        platform = kwargs["platform"]
        channel = kwargs["channel_key"]
        canonical = kwargs.get("canonical_url")
        metadata = {
            "generated_by": "agent_content_pack_v1",
            "platform": platform,
            "channel_key": channel,
            "human_gate_required": True,
            "auto_publish": False,
            "format_kind": (
                "long_article"
                if platform in {"dev", "devto", "hashnode"}
                else "hn_submission"
                if platform == "hacker_news"
                else "discussion_post"
            ),
            "target_length": "test platform target",
        }
        if platform in {"dev", "devto", "hashnode"} and not canonical:
            metadata["warning"] = "canonical_url_missing"
        if platform == "x":
            metadata.update(
                {
                    "format_kind": "x_thread",
                    "target_length": "thread of tweets under 280 weighted chars",
                    "x_format": "thread",
                    "tweets": [
                        f"{kwargs['asset_title']} starts with one operating-system problem.",
                        "The bottleneck is not code speed. It is context switching, broken handoffs, and quality drift.",
                        "The fix is a control plane: plan once, generate platform drafts, then keep publishing human-gated.",
                    ],
                    "weighted_counts": [64, 98, 106],
                    "counting_mode": "conservative",
                }
            )
        return AgentDistributionDraft(
            title=f"{platform} draft: {kwargs['asset_title']}",
            body=_fake_platform_body(platform, channel, kwargs, metadata),
            checklist=_fake_platform_checklist(platform, channel, canonical),
            risk_level="normal",
            rationale=f"Adapted for {platform}",
            metadata=metadata,
        )

    def fake_asset_pack(**kwargs):
        asset_type = kwargs["asset_type"]
        signals = kwargs["signals"]
        lead = signals[0]
        return CanonicalAssetPack(
            title=f"Agent asset: {lead.title}",
            summary=f"Agent summary for {lead.summary}",
            body=f"Agent body for {asset_type}: {lead.title}",
            asset_type=asset_type,
            source_type="asset_planner",
            goal_key="synapse_public_preview_traction",
            key_facts=[lead.title],
            recommended_channels=["x", "hacker_news", "devto", "hashnode"],
            source_signal_refs=[signal.source_ref for signal in signals],
            generation_reason="fake agent generation for tests",
            generation_metadata={
                "provider": "test",
                "generated_by": "agent_content_pack_v1",
            },
        )

    monkeypatch.setattr(
        "server.services.social.distribution_generation.generate_platform_task_draft",
        fake_platform_draft,
    )
    monkeypatch.setattr(
        "server.services.social.distribution_asset_planner.generate_canonical_asset_pack",
        fake_asset_pack,
    )


def _fake_platform_body(platform, channel, kwargs, metadata):
    if platform == "x":
        return "\n\n".join(
            f"{index + 1}/3\n{tweet}" for index, tweet in enumerate(metadata["tweets"])
        )
    multiplier = 40 if platform in {"dev", "devto", "hashnode"} else 8
    return (
        f"{platform}/{channel} agent-generated body for {kwargs['asset_title']} "
        * multiplier
    )


def _fake_platform_checklist(platform, channel, canonical):
    checklist = f"Human Gate required for {platform}/{channel}."
    if platform in {"dev", "devto", "hashnode"}:
        checklist += (
            f" Canonical URL 字段填写 {canonical}."
            if canonical
            else " Canonical URL missing."
        )
    return checklist
